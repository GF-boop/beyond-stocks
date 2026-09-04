"""Sensibilite des deux familles diversifiees au coefficient d'aversion.

Le corps du papier reproche a ACO de classer les portefeuilles par utilite
esperee CRRA sans fixer le budget de risque, ce qui rend le classement
sensible au niveau de risque de chaque regle et au coefficient d'aversion
relative gamma. Ce script applique le meme test a notre propre classement : il
balaie gamma et rapporte, pour les deux familles centrales a 200 % brut, la
reduction de ruine et la reduction d'epargne equivalente face a ACO 33/67.

Points de methode :

* Les poids et le levier restent les definitions figees du manifeste. Aucun
  poids, levier ou actif n'est re-optimise a un gamma donne. Nous ne
  reproduisons donc pas le Panel D de la Table VII d'ACO, qui re-optimise la
  composition ; nous demandons si la regle *fixe* garde son avantage.
* ACO calibrent le motif de legs a frequence mensuelle avec l'estimation de
  De Nardi, French et Jones (2010), puis divisent l'utilite mensuelle par
  12**gamma pour passer a l'annuel. L'intensite de legs annuelle depend donc
  de gamma : theta(gamma) = theta_annuel_base * 12**(GAMMA_BASE - gamma), ou
  theta_annuel_base = 2360 au gamma de reference 3,84. Sans ce reechelonnage,
  un balayage a theta fixe comparerait des preferences differentes a chaque
  ligne. Nous appliquons donc theta(gamma) exactement comme ACO le feraient.
* Grille gamma alignee sur celle d'ACO (Table VII, Panel D) plus le cas de
  reference : 2, 3, 3,84, 5, 7,5, 10. La valeur 7,5 correspond aussi a la
  moyenne des menages suedois de Calvet, Campbell, Gomes et Sodini (2025)
  citee par ACO.

Sorties autonomes pour main.tex :

* ``figures/gamma_sensitivity.json`` : audit complet ;
* ``figures/gamma_sensitivity.tex`` : tabular inclus par l'annexe.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import compare_lifecycle_utility as clu  # noqa: E402
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


GAMMA_BASE = clu.GAMMA                    # 3.84
THETA_ANNUAL_BASE = clu.BEQUEST_STRENGTH  # 2360, calibre a GAMMA_BASE
GAMMA_GRID = (2.0, 3.0, 3.84, 5.0, 7.5, 10.0)


def theta_for_gamma(gamma: float) -> float:
  """Intensite de legs annuelle coherente avec la calibration mensuelle d'ACO.

  ACO : U_annuel = U_mensuel / 12**gamma, avec un theta mensuel fixe. Donc
  theta_annuel(gamma) = theta_mensuel / 12**gamma. Au gamma de reference,
  theta_annuel = THETA_ANNUAL_BASE, d'ou theta_mensuel = THETA_ANNUAL_BASE *
  12**GAMMA_BASE et theta_annuel(gamma) = THETA_ANNUAL_BASE *
  12**(GAMMA_BASE - gamma).
  """
  return THETA_ANNUAL_BASE * (12.0 ** (GAMMA_BASE - gamma))


def evaluate_gamma(rows: list[dict[str, float]], gamma: float, runs: int,
                   seed: int, spread: float, fx_hedge_cost: float,
                   trend_fee: float, trend_cost: float, scenarios=None) -> dict:
  if scenarios is None:
    functions_all = return_functions(
        rows, spread, trend_fee, trend_cost, 0.0, fx_hedge_cost)
    names = (BENCHMARK_NAME, *PORTFOLIOS)
    functions = {name: functions_all[name] for name in names}
    scenarios = scenarios_for(rows, functions, runs, 10.0, seed)

  # Reechelonnage du motif de legs : les agregateurs d'utilite lisent
  # compare_lifecycle_utility.BEQUEST_STRENGTH comme un global au moment de
  # l'appel, donc il suffit de le remplacer avant d'evaluer ce gamma.
  previous_theta = clu.BEQUEST_STRENGTH
  clu.BEQUEST_STRENGTH = theta_for_gamma(gamma)
  try:
    target_utility = expected_utility(
        scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, gamma, WITHDRAWAL_RATE)
    benchmark = evaluate_batch(
        scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, gamma)
    benchmark_ruin = float(np.mean(benchmark.ruined))

    result = {
        "gamma": gamma,
        "bequest_theta_annual": clu.BEQUEST_STRENGTH,
        "benchmark_ruin": benchmark_ruin,
        "benchmark_equivalent_savings_rate": BASE_SAVINGS_RATE,
        "portfolios": {},
    }
    for name in PORTFOLIOS:
      outcomes = evaluate_batch(
          scenarios, name, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, gamma)
      equivalent = equivalent_savings_rate(
          scenarios, name, target_utility, gamma, WITHDRAWAL_RATE)
      ruin = float(np.mean(outcomes.ruined))
      result["portfolios"][name] = {
          "ruin": ruin,
          "equivalent_savings_rate": equivalent,
          "ruin_reduction_vs_aco": benchmark_ruin - ruin,
          "saving_reduction_vs_aco": BASE_SAVINGS_RATE - equivalent,
      }
  finally:
    clu.BEQUEST_STRENGTH = previous_theta
    clear_utility_batches()
  return result


def point(value: float) -> str:
  return f"{100.0 * value:+.2f}"


def pct(value: float) -> str:
  return f"{100.0 * value:.2f}\\%"


def write_tex(path: str, results: list[dict], runs: int) -> None:
  # Rendu en NIVEAUX : chaque famille se lit directement contre la ligne ACO,
  # sans avoir a interpreter le signe d'un ecart. Toutes les valeurs de ruine
  # et d'epargne sont plus basses que celles d'ACO a chaque gamma.
  with open(path, "w", encoding="utf-8") as handle:
    handle.write("% Genere par build/gamma_sensitivity.py -- ne pas editer.\n")
    handle.write("\\begin{table}[H]\n\\centering\n")
    handle.write("\\caption{Risk-aversion sensitivity of the fixed diversified "
                 "families}\n")
    handle.write("\\label{tab:gamma-sensitivity}\n")
    handle.write("\\small\\setlength{\\tabcolsep}{4pt}\n")
    handle.write("\\begin{tabular}{rrrrrr}\n\\toprule\n")
    handle.write("$\\gamma$ & ACO ruin & \\multicolumn{2}{c}{Proportional "
                 "200\\%} & \\multicolumn{2}{c}{Equal-weight 200\\%} \\\\\n")
    handle.write("\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\n")
    handle.write(" & & Ruin & Equiv.\\ saving & Ruin & Equiv.\\ saving "
                 "\\\\\n")
    handle.write("\\multicolumn{6}{l}{\\footnotesize\\emph{lower is better, "
                 "ACO equivalent saving is $10\\%$ at every $\\gamma$}} "
                 "\\\\\n\\midrule\n")
    for result in results:
      proportional = result["portfolios"][PROPORTIONAL]
      equal_weight = result["portfolios"][EQUAL_WEIGHT]
      marker = "$^{\\dagger}$" if abs(result["gamma"] - GAMMA_BASE) < 1e-9 else ""
      handle.write(
          f"{result['gamma']:g}{marker} & \\emph{{{pct(result['benchmark_ruin'])}}} & "
          f"{pct(proportional['ruin'])} & "
          f"{pct(proportional['equivalent_savings_rate'])} & "
          f"{pct(equal_weight['ruin'])} & "
          f"{pct(equal_weight['equivalent_savings_rate'])} \\\\\n")
    handle.write("\\bottomrule\n\\end{tabular}\n")
    handle.write("\\begin{minipage}{0.95\\textwidth}\\footnotesize\n")
    handle.write(
        "\\textit{Note:} %s paired lifecycle paths per row, full "
        "1{,}557-country-year panel, ten-year mean stationary blocks, "
        "$\\phi=30$ bp and $\\kappa=10$ bp. Entries are levels, in percent: "
        "retirement ruin and the utility-equivalent saving rate, both lower "
        "is better. The ACO 33/67 ruin column is shown for reference and its "
        "equivalent saving is $10\\%%$ throughout. The two 200\\%% families keep "
        "their fixed weights and gross exposure at every $\\gamma$, so this is "
        "a sensitivity of the fixed rule, not a reoptimized allocation. "
        "Retirement ruin is a wealth-depletion event and does not depend on "
        "$\\gamma$, so the ruin columns are constant by construction and only "
        "the equivalent-saving columns respond. The bequest intensity is "
        "rescaled to each $\\gamma$ as "
        "$\\theta(\\gamma)=\\theta_{3.84}\\cdot 12^{\\,3.84-\\gamma}$, matching "
        "ACO's monthly-to-annual convention. $^{\\dagger}$Baseline.\n"
        % f"{runs:,}".replace(",", "{,}"))
    handle.write("\\end{minipage}\n\\end{table}\n")


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
      HERE, "..", "paper", "figures", "gamma_sensitivity.json"))
  parser.add_argument("--output-tex", default=os.path.join(
      HERE, "..", "paper", "figures", "gamma_sensitivity.tex"))
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre positif")

  rows = read_panel(args.panel)
  if len(rows) < 2:
    raise ValueError("Panel trop court")

  print(f"Gamma sensitivity: {len(GAMMA_GRID)} valeurs x {args.runs:,} chemins"
        .replace(",", " "))
  functions_all = return_functions(
      rows, args.spread, args.trend_fee, args.trend_cost, 0.0,
      args.fx_hedge_cost)
  names = (BENCHMARK_NAME, *PORTFOLIOS)
  scenarios = scenarios_for(
      rows, {name: functions_all[name] for name in names}, args.runs, 10.0,
      args.seed)
  results = []
  for gamma in GAMMA_GRID:
    result = evaluate_gamma(
        rows, gamma, args.runs, args.seed, args.spread, args.fx_hedge_cost,
        args.trend_fee, args.trend_cost, scenarios)
    results.append(result)
    proportional = result["portfolios"][PROPORTIONAL]
    equal_weight = result["portfolios"][EQUAL_WEIGHT]
    print(f"  gamma {gamma:>4g}: ACO ruin {result['benchmark_ruin']:.2%}  "
          f"P dr {proportional['ruin_reduction_vs_aco']*100:+.2f} "
          f"ds {proportional['saving_reduction_vs_aco']*100:+.2f}  "
          f"EW dr {equal_weight['ruin_reduction_vs_aco']*100:+.2f} "
          f"ds {equal_weight['saving_reduction_vs_aco']*100:+.2f}")

  payload = {
      "runs_per_gamma": args.runs,
      "seed": args.seed,
      "spread": args.spread,
      "fx_hedge_cost": args.fx_hedge_cost,
      "trend_fee": args.trend_fee,
      "trend_cost": args.trend_cost,
      "gamma_base": GAMMA_BASE,
      "theta_annual_base": THETA_ANNUAL_BASE,
      "proportional_portfolio": PROPORTIONAL,
      "equal_weight_portfolio": EQUAL_WEIGHT,
      "results": results,
  }
  os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
  write_tex(args.output_tex, results, args.runs)
  print(f"{args.output_json}\n{args.output_tex}")


if __name__ == "__main__":
  main()
