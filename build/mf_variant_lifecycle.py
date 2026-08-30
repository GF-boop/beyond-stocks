"""Effet des variantes de construction du managed futures sur ruine et epargne.

``build/mf_variants.py`` montre que quatre recettes alternatives du proxy
managed futures gardent une correlation annuelle de 0,77 a 0,96 avec la version
retenue. Une correlation elevee ne garantit toutefois pas que le classement
lifecycle survive : la ruine et l'epargne equivalente dependent de l'ordre des
rendements dans les mauvaises sequences, pas seulement de la correlation.

Ce script rejoue donc le modele lifecycle complet, une fois par variante, sur
les deux familles diversifiees a 200 %. Chemin par chemin : on reconstruit la
serie annuelle reelle brute USD du managed futures pour la variante (meme
recette mensuelle que ``pipeline/panel_managed_futures.py``), on la couvre dans
la monnaie de chaque resident (meme recette que
``pipeline/panel_replication_tendance.py``), et on evalue les deux familles et
le benchmark ACO 33/67 a la graine commune 20260827 sur 10 000 trajectoires
appariees, exactement comme la Table 5.

Le modele applique un cout de rotation forfaitaire (``TREND_DRAG``) identique
pour toutes les variantes, par construction : les frais de rotation mesures,
propres a chaque signal, entrent dans la table des moments de
``mf_variants.py``, pas ici. La variante a frais doubles est traitee en passant
``trend_fee = 1,70 %`` au lieu de la valeur canonique.

Sorties autonomes pour main.tex :

* ``figures/mf_variant_lifecycle.json`` : audit complet ;
* ``figures/mf_variant_lifecycle.tex``  : tabular inclus par l'annexe C.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_fixed_stacked_utility import (  # noqa: E402
    BENCHMARK_NAME,
    DEFAULT_FX_HEDGE_COST,
    DEFAULT_SPREAD,
    return_functions,
)
from compare_gold_trend_equal_vol import (  # noqa: E402
    DEFAULT_TREND_COST,
    DEFAULT_TREND_FEE,
)
from compare_lifecycle_utility import (  # noqa: E402
    BASE_SAVINGS_RATE,
    GAMMA,
    WITHDRAWAL_RATE,
    clear_utility_batches,
    equivalent_savings_rate,
    evaluate_batch,
    expected_utility,
)
from historical_uncertainty import (  # noqa: E402
    EQUAL_WEIGHT,
    PORTFOLIOS,
    PROPORTIONAL,
    scenarios_for,
)
from replicate_extended import read_panel  # noqa: E402

import panel_replication_tendance as prt  # noqa: E402

DATA = os.path.join(HERE, "..", "data")
MONTHLY = os.path.join(DATA, "managed-futures-monthly.csv")
CPI = os.path.join(DATA, "cpi-monthly.csv")

REPLICATION_PANEL = os.path.join(DATA, "replication-panel.csv")
WORLD_PANEL = os.path.join(DATA, "jst-ntsg-panel-2025.csv")
GOLD_PANEL = os.path.join(DATA, "gold-annual.csv")

OUT_DIR = os.path.join(HERE, "..", "paper", "figures")
OUT_JSON = os.path.join(OUT_DIR, "mf_variant_lifecycle.json")
OUT_TEX = os.path.join(OUT_DIR, "mf_variant_lifecycle.tex")

REFERENCE_KEY = "1_6_12"

# (cle, libelle, colonne de rendement brut, colonne de collateral,
#  frais de gestion appliques dans le modele)
VARIANTS = [
    ("1_6_12", "1/6/12 blend (baseline)",
     "mf_1_6_12_gross_return", "mf_1_6_12_cash_collateral_return",
     DEFAULT_TREND_FEE),
    ("1_3_12", "1/3/12 blend",
     "mf_1_3_12_gross_return", "mf_1_3_12_cash_collateral_return",
     DEFAULT_TREND_FEE),
    ("12m", "12-month signal only",
     "signal_12m_gross_return", "signal_12m_cash_collateral_return",
     DEFAULT_TREND_FEE),
    ("1m", "1-month signal only",
     "signal_1m_gross_return", "signal_1m_cash_collateral_return",
     DEFAULT_TREND_FEE),
    ("1_6_12_2fee", "1/6/12 blend, fee doubled to 1.70\\%",
     "mf_1_6_12_gross_return", "mf_1_6_12_cash_collateral_return",
     2.0 * DEFAULT_TREND_FEE),
]


def month_number(month: str) -> int:
  year, part = month.split("-")
  return int(year) * 12 + int(part) - 1


def previous_month(month: str) -> str:
  number = month_number(month) - 1
  return f"{number // 12:04d}-{number % 12 + 1:02d}"


def read_cpi() -> dict[str, float]:
  """CPI mensuel americain, avec comblement du seul octobre 2025 manquant.

  Reproduit ``fill_isolated_gaps`` de ``pipeline/panel_managed_futures.py`` :
  un trou d'exactement un mois est comble par moyenne geometrique des voisins,
  jamais une borne.
  """
  with open(CPI, encoding="utf-8") as handle:
    cpi = {row["month"]: float(row["cpi"])
           for row in csv.DictReader(handle) if row.get("cpi")}
  months = sorted(cpi)
  for index in range(1, len(months)):
    earlier, later = months[index - 1], months[index]
    if month_number(later) - month_number(earlier) != 2:
      continue
    cpi[previous_month(later)] = (cpi[earlier] * cpi[later]) ** 0.5
  return cpi


def annual_us_real_gross(gross_col: str, cash_col: str,
                         cpi: dict[str, float]
                         ) -> tuple[dict[int, float], dict[int, float]]:
  """Serie annuelle reelle brute USD d'une variante, et son collateral.

  Deflation mois par mois par le CPI americain avant composition, annees
  civiles completes seulement, aucun frais ni cout de rotation applique ici :
  le modele applique ``TREND_FEE`` et ``TREND_DRAG`` en aval, comme pour la
  serie canonique de ``pipeline/panel_managed_futures.py``.
  """
  by_year: dict[int, list[float]] = {}
  by_year_cash: dict[int, list[float]] = {}
  with open(MONTHLY, encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      gross = row.get(gross_col)
      cash = row.get(cash_col)
      if not gross or not cash:
        continue
      month = row["month"]
      earlier = previous_month(month)
      if month not in cpi or earlier not in cpi:
        continue
      deflator = cpi[month] / cpi[earlier]
      by_year.setdefault(int(month[:4]), []).append(
          (1.0 + float(gross)) / deflator - 1.0)
      by_year_cash.setdefault(int(month[:4]), []).append(
          (1.0 + float(cash)) / deflator - 1.0)

  annual: dict[int, float] = {}
  annual_cash: dict[int, float] = {}
  for year, values in by_year.items():
    cash_values = by_year_cash.get(year, [])
    if len(values) != 12 or len(cash_values) != 12:
      continue
    compounded = 1.0
    for value in values:
      compounded *= 1.0 + value
    annual[year] = compounded - 1.0
    cash_compounded = 1.0
    for value in cash_values:
      cash_compounded *= 1.0 + value
    annual_cash[year] = cash_compounded - 1.0
  return annual, annual_cash


def variant_panel_rows(trend_us: dict[int, float],
                       cash_us: dict[int, float]) -> list[dict[str, float]]:
  """Panel de replication complet avec la poche de tendance de la variante.

  Reutilise ``panel_replication_tendance.build`` a l'identique : seule la serie
  USD de tendance injectee change, la couverture dans chaque monnaie de
  resident et toutes les autres poches sont recalculees par le meme code que le
  panel du papier.
  """
  panel = prt.read_rows(REPLICATION_PANEL)
  world = {int(row["year"]): row for row in prt.read_rows(WORLD_PANEL)}
  gold = {int(row["year"]): float(row["gold_real"])
          for row in prt.read_rows(GOLD_PANEL)}
  built = prt.build(panel, world, trend_us, cash_us, gold)

  fieldnames = [
      "country", "year", "domestic_equity_real", "international_equity_real",
      "international_equity_real_constant_real_fx",
      "world_equity_real_resident_reconstructed", "xrusd",
      "world_equity_real", "world_equity_source", "bond_real", "bill_real",
      "world_bond_real", "world_bill_real", "world_bond_real_unhedged",
      "world_bill_real_unhedged", "world_bond_issuers", "inflation",
      "trend_real", "trend_cash_us_real", "trend_real_unhedged", "gold_real",
  ]
  tmp = os.path.join(OUT_DIR, "_mf_variant_panel.tmp.csv")
  with open(tmp, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(built)
  rows = read_panel(tmp)
  os.remove(tmp)
  return rows


def evaluate_variant(rows: list[dict[str, float]], runs: int, seed: int,
                     spread: float, fx_hedge_cost: float, trend_fee: float,
                     trend_cost: float) -> dict:
  functions_all = return_functions(
      rows, spread, trend_fee, trend_cost, 0.0, fx_hedge_cost)
  names = (BENCHMARK_NAME, *PORTFOLIOS)
  functions = {name: functions_all[name] for name in names}
  scenarios = scenarios_for(rows, functions, runs, 10.0, seed)

  target_utility = expected_utility(
      scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
  benchmark = evaluate_batch(
      scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
  benchmark_ruin = float(np.mean(benchmark.ruined))

  result = {
      "benchmark_ruin": benchmark_ruin,
      "portfolios": {},
  }
  for name in PORTFOLIOS:
    outcomes = evaluate_batch(
        scenarios, name, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
    equivalent = equivalent_savings_rate(
        scenarios, name, target_utility, GAMMA, WITHDRAWAL_RATE)
    ruin = float(np.mean(outcomes.ruined))
    trend_series = [functions[name](row) for row in rows]
    result["portfolios"][name] = {
        "ruin": ruin,
        "equivalent_savings_rate": equivalent,
        "ruin_reduction_vs_aco": benchmark_ruin - ruin,
        "saving_reduction_vs_aco": BASE_SAVINGS_RATE - equivalent,
        "volatility": statistics.stdev(trend_series),
    }
  clear_utility_batches()
  return result


def moments(series: list[float]) -> tuple[float, float]:
  mean = statistics.fmean(series)
  sd = statistics.stdev(series)
  m3 = sum((x - mean) ** 3 for x in series) / len(series)
  return mean, m3 / sd ** 3


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
  parser.add_argument("--fx-hedge-cost", type=float,
                      default=DEFAULT_FX_HEDGE_COST)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre strictement positif")

  cpi = read_cpi()
  os.makedirs(OUT_DIR, exist_ok=True)

  built_us = {}
  for key, _label, gross_col, cash_col, _fee in VARIANTS:
    built_us[key] = annual_us_real_gross(gross_col, cash_col, cpi)

  # correlation annuelle de chaque serie USD brute avec la reference, sur les
  # annees communes, pour rappeler le lien avec la table des moments
  ref_years = sorted(built_us[REFERENCE_KEY][0])
  ref_series = [built_us[REFERENCE_KEY][0][y] for y in ref_years]

  results = []
  print(f"Variantes MF -> lifecycle : {len(VARIANTS)} x {args.runs:,} "
        "trajectoires appariees".replace(",", " "))
  for key, label, _g, _c, fee in VARIANTS:
    trend_us, cash_us = built_us[key]
    rows = variant_panel_rows(trend_us, cash_us)
    outcome = evaluate_variant(
        rows, args.runs, args.seed, args.spread, args.fx_hedge_cost, fee,
        args.trend_cost)

    common = [y for y in ref_years if y in trend_us]
    series = [trend_us[y] for y in common]
    ref = [built_us[REFERENCE_KEY][0][y] for y in common]
    ma, mr = statistics.fmean(series), statistics.fmean(ref)
    num = sum((a - ma) * (b - mr) for a, b in zip(series, ref))
    den = (sum((a - ma) ** 2 for a in series)
           * sum((b - mr) ** 2 for b in ref)) ** 0.5
    corr = num / den
    mean_us, skew_us = moments([trend_us[y] for y in sorted(trend_us)])

    proportional = outcome["portfolios"][PROPORTIONAL]
    equal_weight = outcome["portfolios"][EQUAL_WEIGHT]
    results.append({
        "key": key,
        "label": label,
        "management_fee": fee,
        "us_real_gross_mean": mean_us,
        "us_real_gross_skew": skew_us,
        "corr_with_baseline": corr,
        "benchmark_ruin": outcome["benchmark_ruin"],
        "proportional": proportional,
        "equal_weight": equal_weight,
    })
    print(f"  {label:<40} ACO ruin {100 * outcome['benchmark_ruin']:5.2f}%  "
          f"P druin {100 * proportional['ruin_reduction_vs_aco']:+5.2f} "
          f"dsav {100 * proportional['saving_reduction_vs_aco']:+5.2f}  "
          f"EW druin {100 * equal_weight['ruin_reduction_vs_aco']:+5.2f} "
          f"dsav {100 * equal_weight['saving_reduction_vs_aco']:+5.2f}  "
          f"corr {corr:.3f}")

  payload = {
      "runs": args.runs,
      "seed": args.seed,
      "spread": args.spread,
      "fx_hedge_cost": args.fx_hedge_cost,
      "trend_cost": args.trend_cost,
      "trend_fee_baseline": DEFAULT_TREND_FEE,
      "reference": REFERENCE_KEY,
      "proportional_portfolio": PROPORTIONAL,
      "equal_weight_portfolio": EQUAL_WEIGHT,
      "results": results,
  }
  with open(OUT_JSON, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")

  # Rendu en NIVEAUX, pas en ecart : le lecteur compare directement chaque
  # portefeuille a ACO, sans avoir a interpreter le signe d'un delta. ACO 33/67
  # est la premiere ligne du corps du tableau, et toutes les valeurs de ruine
  # et d'epargne en dessous sont plus basses, ce qui se voit d'un coup d'oeil.
  aco_ruin = statistics.fmean([r["benchmark_ruin"] for r in results])
  with open(OUT_TEX, "w", encoding="utf-8") as f:
    f.write("% Genere par build/mf_variant_lifecycle.py -- ne pas editer.\n")
    f.write("\\begin{tabular}{lrrrrr}\n\\toprule\n")
    f.write("MF sleeve & Corr.\\ & \\multicolumn{2}{c}{Proportional 200\\%} & "
            "\\multicolumn{2}{c}{Equal-weight 200\\%} \\\\\n")
    f.write("\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\n")
    f.write(" & baseline & Ruin & Equiv.\\ saving & "
            "Ruin & Equiv.\\ saving \\\\\n\\midrule\n")
    f.write(f"\\emph{{ACO 33/67 (all-equity)}} & --- & "
            f"\\emph{{{100 * aco_ruin:.2f}\\%}} & \\emph{{10.00\\%}} & "
            f"\\emph{{{100 * aco_ruin:.2f}\\%}} & \\emph{{10.00\\%}} \\\\\n")
    f.write("\\addlinespace\n")
    for r in results:
      marker = "$^{\\dagger}$" if r["key"] == REFERENCE_KEY else ""
      f.write(
          f"\\quad {r['label']}{marker} & {r['corr_with_baseline']:.2f} & "
          f"{100 * r['proportional']['ruin']:.2f}\\% & "
          f"{100 * r['proportional']['equivalent_savings_rate']:.2f}\\% & "
          f"{100 * r['equal_weight']['ruin']:.2f}\\% & "
          f"{100 * r['equal_weight']['equivalent_savings_rate']:.2f}\\% \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

  print(f"\n{OUT_JSON}\n{OUT_TEX}")


if __name__ == "__main__":
  main()
