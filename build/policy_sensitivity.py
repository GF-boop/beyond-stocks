"""Sensibilite des deux familles diversifiees aux parametres de politique.

Le corps du papier reproche a ACO de ne rapporter la robustesse de leur
resultat qu'au niveau de la *composition* optimale, jamais au niveau des
*magnitudes* de bien-etre. Le sweep sur gamma (Annexe F) applique ce test au
coefficient d'aversion. Ce script fait de meme pour deux parametres de
politique du menage qu'ACO faisait varier lui aussi (Table VII) mais sans
publier l'effet sur les magnitudes :

* le taux de contribution pendant la vie active, r_c dans {5, 10, 15} % ;
* le taux de retrait reel a la retraite, r_w dans {3, 4, 5} %.

Points de methode :

* Les poids et le levier restent les definitions figees du manifeste. Aucun
  poids, levier ou actif n'est re-optimise dans une ligne.
* Axe r_c : le taux de reference d'ACO 33/67 est *aussi* fixe a r_c dans
  chaque ligne, et l'utilite cible est recalculee a ce r_c. La question est
  donc : dans un monde ou tout le monde epargne r_c %, la diversification
  reduit-elle encore le taux requis et la ruine d'un montant comparable ? Un
  ancrage a 10 % fixe rendrait l'ecart mecaniquement proportionnel a r_c et
  n'apprendrait rien.
* Axe r_w : le taux d'epargne de reference reste 10 % (comme partout ailleurs
  dans le papier) et seul le retrait varie. La ruine etant l'epuisement du
  compte financier, elle est mecaniquement tres sensible a r_w.
* La ligne r_c = 10 % de l'axe contribution et la ligne r_w = 4 % de l'axe
  retrait sont le cas de reference et doivent coincider.

Sorties autonomes pour main.tex :

* ``figures/policy_sensitivity.json`` : audit complet ;
* ``figures/policy_sensitivity.tex`` : tabular a deux panneaux inclus par
  l'annexe.
"""

from __future__ import annotations

import argparse
import json
import os
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


CONTRIBUTION_RATES = (0.05, 0.10, 0.15)
WITHDRAWAL_RATES = (0.03, 0.04, 0.05)


def _row(rows, base_rate, withdrawal_rate, runs, seed, spread, fx_hedge_cost,
         trend_fee, trend_cost, scenarios=None):
  """Un point du sweep : ACO 33/67 epargne ``base_rate`` et retire
  ``withdrawal_rate``, les deux familles sont evaluees aux memes tirages."""
  if scenarios is None:
    functions_all = return_functions(
        rows, spread, trend_fee, trend_cost, 0.0, fx_hedge_cost)
    names = (BENCHMARK_NAME, *PORTFOLIOS)
    scenarios = scenarios_for(rows, functions, runs, 10.0, seed)

  target_utility = expected_utility(
      scenarios, BENCHMARK_NAME, base_rate, GAMMA, withdrawal_rate)
  benchmark = evaluate_batch(
      scenarios, BENCHMARK_NAME, base_rate, withdrawal_rate, GAMMA)
  benchmark_ruin = float(np.mean(benchmark.ruined))

  entry = {
      "contribution_rate": base_rate,
      "withdrawal_rate": withdrawal_rate,
      "benchmark_ruin": benchmark_ruin,
      "portfolios": {},
  }
  # Taux d'epargne de reference d'ACO sur cette ligne : c'est ``base_rate`` (5,
  # 10 ou 15 % sur l'axe contribution), pas 10 % en dur.
  entry["benchmark_savings_rate"] = base_rate
  for name in PORTFOLIOS:
    outcomes = evaluate_batch(
        scenarios, name, base_rate, withdrawal_rate, GAMMA)
    equivalent = equivalent_savings_rate(
        scenarios, name, target_utility, GAMMA, withdrawal_rate)
    ruin = float(np.mean(outcomes.ruined))
    entry["portfolios"][name] = {
        "ruin": ruin,
        "equivalent_savings_rate": equivalent,
        "ruin_reduction_vs_aco": benchmark_ruin - ruin,
        # L'ecart d'epargne est mesure contre le taux de reference de cette
        # ligne, pas contre 10 % en dur.
        "saving_reduction_vs_aco": base_rate - equivalent,
    }
  clear_utility_batches()
  return entry


def evaluate_contribution_axis(rows, runs, seed, spread, fx_hedge_cost,
                               trend_fee, trend_cost, scenarios=None):
  out = []
  for base_rate in CONTRIBUTION_RATES:
    entry = _row(rows, base_rate, WITHDRAWAL_RATE, runs, seed, spread,
                 fx_hedge_cost, trend_fee, trend_cost, scenarios)
    out.append(entry)
  return out


def evaluate_withdrawal_axis(rows, runs, seed, spread, fx_hedge_cost,
                             trend_fee, trend_cost, scenarios=None):
  out = []
  for withdrawal_rate in WITHDRAWAL_RATES:
    entry = _row(rows, BASE_SAVINGS_RATE, withdrawal_rate, runs, seed, spread,
                 fx_hedge_cost, trend_fee, trend_cost, scenarios)
    out.append(entry)
  return out


def point(value: float) -> str:
  return f"{100.0 * value:+.2f}"


def pct(value: float) -> str:
  return f"{100.0 * value:.2f}\\%"


def write_tex(path: str, contribution, withdrawal, runs: int) -> None:
  # Rendu en NIVEAUX : chaque famille se lit directement contre les deux
  # colonnes de reference ACO (ruine et epargne), sans interpreter le signe
  # d'un ecart. Sur l'axe contribution l'epargne de reference d'ACO est r_c,
  # pas 10 %, ce que la colonne ``ACO sav'' rend explicite ligne par ligne.
  def body(entry, axis_value_pct):
    proportional = entry["portfolios"][PROPORTIONAL]
    equal_weight = entry["portfolios"][EQUAL_WEIGHT]
    return (f"{axis_value_pct} & \\emph{{{pct(entry['benchmark_ruin'])}}} & "
            f"\\emph{{{pct(entry['benchmark_savings_rate'])}}} & "
            f"{pct(proportional['ruin'])} & "
            f"{pct(proportional['equivalent_savings_rate'])} & "
            f"{pct(equal_weight['ruin'])} & "
            f"{pct(equal_weight['equivalent_savings_rate'])} \\\\\n")

  with open(path, "w", encoding="utf-8") as handle:
    handle.write("% Genere par build/policy_sensitivity.py -- ne pas editer.\n")
    handle.write("\\begin{table}[H]\n\\centering\n")
    handle.write("\\caption{Contribution- and withdrawal-rate sensitivity of "
                 "the fixed diversified families}\n")
    handle.write("\\label{tab:policy-sensitivity}\n")
    handle.write("\\small\\setlength{\\tabcolsep}{4pt}\n")
    handle.write("\\begin{tabular}{rrrrrrr}\n\\toprule\n")
    handle.write("Rate & \\multicolumn{2}{c}{ACO 33/67} & "
                 "\\multicolumn{2}{c}{Proportional 200\\%} & "
                 "\\multicolumn{2}{c}{Equal-weight 200\\%} \\\\\n")
    handle.write("\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(lr){6-7}\n")
    handle.write(" & Ruin & Saving & Ruin & Equiv.\\ saving & Ruin & "
                 "Equiv.\\ saving \\\\\n")
    handle.write("\\multicolumn{7}{l}{\\footnotesize\\emph{lower is better, "
                 "the ACO columns are the reference}} \\\\\n\\midrule\n")

    handle.write("\\multicolumn{7}{l}{\\emph{Contribution rate $r_c$ "
                 "(withdrawal held at 4\\%)}} \\\\\n")
    for entry in contribution:
      rate = entry["contribution_rate"]
      marker = "\\,$^{\\dagger}$" if abs(rate - BASE_SAVINGS_RATE) < 1e-9 else ""
      handle.write(body(entry, f"$r_c={100 * rate:g}\\%${marker}"))

    handle.write("\\addlinespace\n")
    handle.write("\\multicolumn{7}{l}{\\emph{Withdrawal rate $r_w$ "
                 "(contribution held at 10\\%)}} \\\\\n")
    for entry in withdrawal:
      rate = entry["withdrawal_rate"]
      marker = "\\,$^{\\dagger}$" if abs(rate - WITHDRAWAL_RATE) < 1e-9 else ""
      handle.write(body(entry, f"$r_w={100 * rate:g}\\%${marker}"))

    handle.write("\\bottomrule\n\\end{tabular}\n")
    handle.write("\\begin{minipage}{0.96\\textwidth}\\footnotesize\n")
    handle.write(
        "\\textit{Note:} %s paired lifecycle paths per row, full "
        "1{,}557-country-year panel, ten-year mean stationary blocks, "
        "$\\phi=30$ bp and $\\kappa=10$ bp. Entries are levels, in percent: "
        "retirement ruin and the utility-equivalent saving rate, both lower "
        "is better. The two ACO 33/67 columns are the reference. The two "
        "200\\%% families keep their fixed weights and gross exposure in every "
        "row. On the contribution-rate axis the ACO 33/67 benchmark also "
        "contributes $r_c$, so its reference saving rate is $r_c$ itself and "
        "the family saving is the rate that matches ACO's lifecycle utility at "
        "that $r_c$. On the withdrawal-rate axis the benchmark saving rate "
        "stays at 10\\%%. $^{\\dagger}$Baseline.\n"
        % f"{runs:,}".replace(",", "{,}"))
    handle.write("\\end{minipage}\n\\end{table}\n")


def _report(entry: dict) -> str:
  proportional = entry["portfolios"][PROPORTIONAL]
  equal_weight = entry["portfolios"][EQUAL_WEIGHT]
  return (f"ACO ruin {entry['benchmark_ruin']:.2%}  "
          f"P dr {proportional['ruin_reduction_vs_aco'] * 100:+.2f} "
          f"ds {proportional['saving_reduction_vs_aco'] * 100:+.2f}  "
          f"EW dr {equal_weight['ruin_reduction_vs_aco'] * 100:+.2f} "
          f"ds {equal_weight['saving_reduction_vs_aco'] * 100:+.2f}")


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
  parser.add_argument("--fx-hedge-cost", type=float,
                      default=DEFAULT_FX_HEDGE_COST)
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--output-json", default=os.path.join(
      HERE, "..", "paper", "figures", "policy_sensitivity.json"))
  parser.add_argument("--output-tex", default=os.path.join(
      HERE, "..", "paper", "figures", "policy_sensitivity.tex"))
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre positif")

  rows = read_panel(args.panel)
  if len(rows) < 2:
    raise ValueError("Panel trop court")

  n = len(CONTRIBUTION_RATES) + len(WITHDRAWAL_RATES)
  print(f"Policy sensitivity: {n} lignes x {args.runs:,} chemins"
        .replace(",", " "))
  functions_all = return_functions(
      rows, args.spread, args.trend_fee, args.trend_cost, 0.0,
      args.fx_hedge_cost)
  names = (BENCHMARK_NAME, *PORTFOLIOS)
  scenarios = scenarios_for(
      rows, {name: functions_all[name] for name in names}, args.runs, 10.0,
      args.seed)

  contribution = evaluate_contribution_axis(
      rows, args.runs, args.seed, args.spread, args.fx_hedge_cost,
      args.trend_fee, args.trend_cost, scenarios)
  for entry in contribution:
    print(f"  r_c {entry['contribution_rate']:>5.0%}: {_report(entry)}")

  withdrawal = evaluate_withdrawal_axis(
      rows, args.runs, args.seed, args.spread, args.fx_hedge_cost,
      args.trend_fee, args.trend_cost, scenarios)
  for entry in withdrawal:
    print(f"  r_w {entry['withdrawal_rate']:>5.0%}: {_report(entry)}")

  payload = {
      "runs_per_row": args.runs,
      "seed": args.seed,
      "spread": args.spread,
      "fx_hedge_cost": args.fx_hedge_cost,
      "trend_fee": args.trend_fee,
      "trend_cost": args.trend_cost,
      "base_contribution_rate": BASE_SAVINGS_RATE,
      "base_withdrawal_rate": WITHDRAWAL_RATE,
      "proportional_portfolio": PROPORTIONAL,
      "equal_weight_portfolio": EQUAL_WEIGHT,
      "contribution_axis": contribution,
      "withdrawal_axis": withdrawal,
  }
  os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
  write_tex(args.output_tex, contribution, withdrawal, args.runs)
  print(f"{args.output_json}\n{args.output_tex}")


if __name__ == "__main__":
  main()
