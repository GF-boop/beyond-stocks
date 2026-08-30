"""Sensibilite historique des deux familles diversifiees a ACO.

Les intervalles de Monte Carlo habituels conditionnent sur le panel historique
observe : ils repondent a ``combien de trajectoires faut-il ?'', non a ``que se
passerait-il si l'histoire disponible etait differente ?''. Ce script produit
trois perturbations transparentes de cette histoire :

* blocs stationnaires de longueur moyenne 5, 10 et 20 ans ;
* fenetres commencant en 1927, 1950 et 1970 ;
* filtre ex ante d'investissabilite ;
* leave-one-country-out sur les seize pays du panel.

Les portefeuilles restent strictement les definitions figees du manifeste. En
particulier, aucun poids, levier ou actif n'est re-estime dans une variante.
Les resultats sont des diagnostics de sensibilite historique, et non des
intervalles de confiance frequentistes : les variantes se recouvrent fortement
et les dates de coupure sont des choix economiques explicites.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from dataclasses import asdict, dataclass

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
    build_scenario,
    clear_utility_batches,
    draw_death_age,
    equivalent_savings_rate,
    evaluate_batch,
    expected_utility,
)
from income_process import draw_household_income  # noqa: E402
from investability import exclusion_reason  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import MAX_AGE, START_AGE, block_bootstrap, read_panel  # noqa: E402


PROPORTIONAL = "80/53.33/33.33/33.33 ACO"
EQUAL_WEIGHT = "50/50/50/50 ACO"
PORTFOLIOS = (PROPORTIONAL, EQUAL_WEIGHT)


@dataclass(frozen=True)
class Specification:
  label: str
  mean_block: float = 10.0
  year_from: int | None = None
  omit_country: str | None = None
  investable_only: bool = False


def select_rows(rows: list[dict[str, float]], spec: Specification
                ) -> list[dict[str, float]]:
  selected = rows
  if spec.year_from is not None:
    selected = [row for row in selected if row["year"] >= spec.year_from]
  if spec.omit_country is not None:
    selected = [row for row in selected
                if row["country"] != spec.omit_country]
  if spec.investable_only:
    selected = [
        row for row in selected
        if exclusion_reason(row["country"], int(row["year"]),
                            float(row["inflation"])) is None
    ]
  if len(selected) < 2:
    raise ValueError(f"Echantillon vide ou trop court : {spec.label}")
  return selected


def scenarios_for(rows: list[dict[str, float]], functions, runs: int,
                  mean_block: float, seed: int):
  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(seed)
  scenarios = []
  for _ in range(runs):
    path = block_bootstrap(rows, horizon, rng, mean_block)
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, _ = draw_household_income(rng)
    scenarios.append(build_scenario(
        path, functions, female_death, male_death,
        female_income, male_income))
  return scenarios


def evaluate_specification(rows: list[dict[str, float]], spec: Specification,
                           runs: int, seed: int, spread: float,
                           fx_hedge_cost: float, trend_fee: float,
                           trend_cost: float) -> dict:
  selected = select_rows(rows, spec)
  functions_all = return_functions(
      selected, spread, trend_fee, trend_cost, 0.0, fx_hedge_cost)
  names = (BENCHMARK_NAME, *PORTFOLIOS)
  functions = {name: functions_all[name] for name in names}
  scenarios = scenarios_for(selected, functions, runs, spec.mean_block, seed)
  target_utility = expected_utility(
      scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
  benchmark = evaluate_batch(
      scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
  benchmark_ruin = float(np.mean(benchmark.ruined))
  benchmark_vol = statistics.stdev(
      functions[BENCHMARK_NAME](row) for row in selected)

  result = {
      "specification": asdict(spec),
      "observations": len(selected),
      "year_first": min(row["year"] for row in selected),
      "year_last": max(row["year"] for row in selected),
      "countries": len({row["country"] for row in selected}),
      "benchmark_ruin": benchmark_ruin,
      "benchmark_volatility": benchmark_vol,
      "portfolios": {},
  }
  for name in PORTFOLIOS:
    outcomes = evaluate_batch(
        scenarios, name, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
    equivalent = equivalent_savings_rate(
        scenarios, name, target_utility, GAMMA, WITHDRAWAL_RATE)
    ruin = float(np.mean(outcomes.ruined))
    volatility = statistics.stdev(functions[name](row) for row in selected)
    result["portfolios"][name] = {
        "ruin": ruin,
        "equivalent_savings_rate": equivalent,
        # Des signes positifs ont volontairement la meme lecture economique :
        # baisse de ruine et baisse de l'epargne requise relativement a ACO.
        "ruin_reduction_vs_aco": benchmark_ruin - ruin,
        "saving_reduction_vs_aco": BASE_SAVINGS_RATE - equivalent,
        "volatility": volatility,
        "volatility_gap_vs_aco": volatility - benchmark_vol,
    }
  clear_utility_batches()
  return result


def quantile(values: list[float], probability: float) -> float:
  return float(np.quantile(np.asarray(values, dtype=float), probability))


def result_cells(result: dict) -> tuple[float, float, float, float]:
  """Ecarts a ACO, gardes pour l'audit console et le test de non-inversion."""
  proportional = result["portfolios"][PROPORTIONAL]
  equal_weight = result["portfolios"][EQUAL_WEIGHT]
  return (
      proportional["ruin_reduction_vs_aco"],
      proportional["saving_reduction_vs_aco"],
      equal_weight["ruin_reduction_vs_aco"],
      equal_weight["saving_reduction_vs_aco"],
  )


def level_cells(result: dict) -> tuple[float, float, float, float]:
  """Niveaux affiches : ruine et epargne equivalente des deux familles."""
  proportional = result["portfolios"][PROPORTIONAL]
  equal_weight = result["portfolios"][EQUAL_WEIGHT]
  return (
      proportional["ruin"],
      proportional["equivalent_savings_rate"],
      equal_weight["ruin"],
      equal_weight["equivalent_savings_rate"],
  )


def pct(value: float) -> str:
  return f"{100.0 * value:.2f}\\%"


def write_summary_tex(path: str, base: list[dict], leave_one_out: list[dict],
                      runs: int) -> None:
  # Rendu en NIVEAUX : chaque famille se lit directement contre la colonne
  # ``ACO ruin'', sans interpreter le signe d'un ecart. L'epargne de reference
  # d'ACO est 10 % partout. Pour les lignes LOO, on prend le quantile cellule
  # par cellule des niveaux, coherent avec les lignes de base.
  rows: list[tuple[str, str, float, tuple[float, float, float, float]]] = []
  for result in base:
    label = result["specification"]["label"]
    rows.append((label, f"{result['observations']:,}", result["benchmark_ruin"],
                 level_cells(result)))
  loo_obs = [result["observations"] for result in leave_one_out]
  loo_n_label = f"{min(loo_obs):,}--{max(loo_obs):,}"
  for label, probability in (("LOO minimum (16 countries)", 0.0),
                             ("LOO median (16 countries)", 0.5),
                             ("LOO maximum (16 countries)", 1.0)):
    cells = tuple(
        quantile([level_cells(result)[index] for result in leave_one_out],
                 probability)
        for index in range(4))
    rows.append((label, loo_n_label,
                 quantile([result["benchmark_ruin"] for result in leave_one_out],
                          probability), cells))

  with open(path, "w", encoding="utf-8") as handle:
    handle.write("\\begin{table}[H]\n\\centering\n")
    handle.write("\\caption{Historical-sample sensitivity of the fixed diversified families}\n")
    handle.write("\\label{tab:historical-uncertainty}\n")
    handle.write("\\scriptsize\\setlength{\\tabcolsep}{3pt}\n")
    handle.write("\\begin{tabular}{lrrrrrr}\n\\toprule\n")
    handle.write("Sample & $N$ & ACO ruin & \\multicolumn{2}{c}{Proportional 200\\%} & \\multicolumn{2}{c}{Equal-weight 200\\%} \\\\\n")
    handle.write("\\cmidrule(lr){4-5}\\cmidrule(lr){6-7}\n")
    handle.write(" & & & Ruin & Equiv.\\ saving & Ruin & Equiv.\\ saving \\\\\n")
    handle.write("\\multicolumn{7}{l}{\\emph{lower is better, ACO equivalent saving is $10\\%$ throughout}} \\\\\n\\midrule\n")
    for label, observations, aco_ruin, cells in rows:
      # Seul le comptage d'observations recoit le groupement {,} ; les virgules
      # des libelles restent des virgules ordinaires.
      grouped = observations.replace(",", "{,}")
      handle.write(
          f"{label} & {grouped} & \\emph{{{100 * aco_ruin:.2f}\\%}} & "
          f"{pct(cells[0])} & {pct(cells[1])} & {pct(cells[2])} & {pct(cells[3])} \\\\\n")
    handle.write("\\bottomrule\n\\end{tabular}\n")
    handle.write("\\begin{minipage}{0.97\\textwidth}\\footnotesize\n")
    handle.write(
        "\\textit{Note:} Each row uses %s paired lifecycle paths. Entries are "
        "levels, in percent: retirement ruin and the utility-equivalent saving "
        "rate, both lower is better. The ACO 33/67 ruin column is the "
        "reference and its equivalent saving is $10\\%%$ throughout. The two "
        "200\\%% families retain their fixed 200\\%% gross exposures, and no "
        "weight or leverage is re-estimated. ``LOO'' reports the cellwise "
        "minimum, median, and maximum across the sixteen leave-one-country-out "
        "samples, so a row need not correspond to one common omitted country. "
        "These are historical sensitivity results, not confidence intervals.\n"
        % f"{runs:,}".replace(",", "{,}"))
    handle.write("\\end{minipage}\n\\end{table}\n")


def write_loo_tex(path: str, leave_one_out: list[dict], runs: int) -> None:
  with open(path, "w", encoding="utf-8") as handle:
    handle.write("\\begin{table}[H]\n\\centering\n")
    handle.write("\\caption{Leave-one-country-out historical sensitivity}\n")
    handle.write("\\label{tab:historical-uncertainty-loo}\n")
    handle.write("\\small\n\\begin{tabular}{lrrrrr}\n\\toprule\n")
    handle.write("Omitted country & ACO ruin & \\multicolumn{2}{c}{Proportional 200\\%} & \\multicolumn{2}{c}{Equal-weight 200\\%} \\\\\n")
    handle.write("\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\n")
    handle.write(" & & Ruin & Equiv.\\ saving & Ruin & Equiv.\\ saving \\\\\n")
    handle.write("\\multicolumn{6}{l}{\\emph{lower is better, ACO equivalent saving is $10\\%$}} \\\\\n\\midrule\n")
    for result in leave_one_out:
      country = result["specification"]["omit_country"]
      cells = level_cells(result)
      handle.write(
          f"{country} & \\emph{{{100 * result['benchmark_ruin']:.2f}\\%}} & "
          f"{pct(cells[0])} & {pct(cells[1])} & "
          f"{pct(cells[2])} & {pct(cells[3])} \\\\\n")
    handle.write("\\bottomrule\n\\end{tabular}\n")
    handle.write("\\begin{minipage}{0.94\\textwidth}\\footnotesize\n")
    handle.write(
        "\\textit{Note:} %s paired paths per omission, ten-year mean stationary "
        "blocks. Levels in percent, lower is better, with the same columns as "
        "Table~\\ref{tab:historical-uncertainty}.\n" % f"{runs:,}".replace(",", "{,}"))
    handle.write("\\end{minipage}\n\\end{table}\n")


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=5_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
  parser.add_argument("--fx-hedge-cost", type=float,
                      default=DEFAULT_FX_HEDGE_COST)
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--output-json", default=os.path.join(
      HERE, "..", "paper", "figures", "historical_uncertainty.json"))
  parser.add_argument("--summary-tex", default=os.path.join(
      HERE, "..", "paper", "figures", "historical_uncertainty.tex"))
  parser.add_argument("--loo-tex", default=os.path.join(
      HERE, "..", "paper", "figures", "historical_uncertainty_loo.tex"))
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre strictement positif")

  rows = read_panel(args.panel)
  countries = sorted({row["country"] for row in rows})
  base_specs = [
      Specification("Full panel, 5-year blocks", mean_block=5.0),
      Specification("Full panel, 10-year blocks", mean_block=10.0),
      Specification("Full panel, 20-year blocks", mean_block=20.0),
      Specification("1950--2025, 10-year blocks", mean_block=10.0,
                    year_from=1950),
      Specification("1970--2025, 10-year blocks", mean_block=10.0,
                    year_from=1970),
      Specification("Investability screen, 10-year blocks", mean_block=10.0,
                    investable_only=True),
  ]
  loo_specs = [Specification(f"Omit {country}", omit_country=country)
               for country in countries]
  all_specs = [*base_specs, *loo_specs]
  outputs: list[dict] = []
  print(f"Historical sensitivity: {len(all_specs)} specifications x "
        f"{args.runs:,} paired paths".replace(",", " "))
  # Meme graine pour toutes les lignes : chaque ligne perturbe le panel, pas
  # le tirage, donc un flux commun isole l'effet du changement d'echantillon et
  # fait coincider la ligne panel-complet 10 ans avec les tables principales.
  for index, spec in enumerate(all_specs, start=1):
    output = evaluate_specification(
        rows, spec, args.runs, args.seed, args.spread,
        args.fx_hedge_cost, args.trend_fee, args.trend_cost)
    outputs.append(output)
    proportional, equal_weight = (output["portfolios"][name]
                                   for name in PORTFOLIOS)
    print(f"  {index:>2}/{len(all_specs)} {spec.label:<32} "
          f"P: ruin {proportional['ruin_reduction_vs_aco']:+.2%}, "
          f"saving {proportional['saving_reduction_vs_aco']:+.2%}; "
          f"EW: ruin {equal_weight['ruin_reduction_vs_aco']:+.2%}, "
          f"saving {equal_weight['saving_reduction_vs_aco']:+.2%}")

  base = outputs[:len(base_specs)]
  leave_one_out = outputs[len(base_specs):]
  os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
  payload = {
      "runs_per_specification": args.runs,
      "seed": args.seed,
      "spread": args.spread,
      "fx_hedge_cost": args.fx_hedge_cost,
      "trend_fee": args.trend_fee,
      "trend_cost": args.trend_cost,
      "proportional_portfolio": PROPORTIONAL,
      "equal_weight_portfolio": EQUAL_WEIGHT,
      "base_specifications": base,
      "leave_one_out": leave_one_out,
  }
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
  write_summary_tex(args.summary_tex, base, leave_one_out, args.runs)
  write_loo_tex(args.loo_tex, leave_one_out, args.runs)

  for name in PORTFOLIOS:
    all_positive = sum(
        all(value > 0.0 for value in result_cells(result)[
            0 if name == PROPORTIONAL else 2:
            2 if name == PROPORTIONAL else 4])
        for result in leave_one_out)
    print(f"  {name}: both criteria improve in {all_positive}/{len(leave_one_out)} "
          "leave-one-out samples")


if __name__ == "__main__":
  main()
