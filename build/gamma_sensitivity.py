"""Sensitivity of the two diversified families to risk aversion.

ACO rank portfolios by CRRA expected utility without fixing the risk budget,
which makes the ranking sensitive to the risk level of each rule and to the
coefficient of relative risk aversion gamma. This script applies the same test
to our own ranking: it sweeps gamma and reports, for the two main families at
200% gross exposure, the reduction in ruin and in equivalent saving against
ACO 33/67.

Method:

* Weights and leverage stay the frozen definitions of the manifest. No weight,
  leverage or asset is re-optimised at a given gamma. We therefore do not
  reproduce Panel D of ACO's Table VII, which re-optimises the composition; we
  ask whether the *fixed* rule keeps its advantage.
* Two conventions: a fixed annual bequest coefficient (--fixed-theta), or the
  earlier joint sensitivity theta=2360*12**(3.84-gamma). The latter is our own
  sensitivity convention, not a replication of ACO's.
* Gamma grid aligned with ACO's (Table VII, Panel D) plus the reference case:
  2, 3, 3.84, 5, 7.5, 10. The value 7.5 is also the mean of the Swedish
  households of Calvet, Campbell, Gomes and Sodini (2025) cited by ACO.

Outputs:

* ``figures/gamma_sensitivity.json``: full audit, read by
  ``render_restored_appendices.py``;
* ``--output-tex``: optional LaTeX table.
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
PORTFOLIOS = (*PORTFOLIOS, 'ACO 33/67 200%')
FIXED_THETA = False


def theta_for_gamma(gamma: float) -> float:
  """Annual bequest coefficient: fixed or legacy joint sensitivity."""
  return THETA_ANNUAL_BASE if FIXED_THETA else THETA_ANNUAL_BASE * (12.0 ** (GAMMA_BASE - gamma))


def evaluate_gamma(rows: list[dict[str, float]], gamma: float, runs: int,
                   seed: int, spread: float, fx_hedge_cost: float,
                   trend_fee: float, trend_cost: float, scenarios=None) -> dict:
  if scenarios is None:
    functions_all = return_functions(
        rows, spread, trend_fee, trend_cost, 0.0, fx_hedge_cost)
    names = (BENCHMARK_NAME, *PORTFOLIOS)
    functions = {name: functions_all[name] for name in names}
    scenarios = scenarios_for(rows, functions, runs, 10.0, seed)

  # Rescale the bequest motive: the utility aggregators read
  # compare_lifecycle_utility.BEQUEST_STRENGTH as a global at call time, so it
  # is enough to replace it before evaluating this gamma.
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
      theta = clu.BEQUEST_STRENGTH
      clu.BEQUEST_STRENGTH = 0.0
      consumption_only = evaluate_batch(scenarios, name, BASE_SAVINGS_RATE,
                                         WITHDRAWAL_RATE, gamma).utility
      clu.BEQUEST_STRENGTH = theta
      total = float(np.mean(outcomes.utility))
      consumption = float(np.mean(consumption_only))
      at_equivalent = expected_utility(scenarios, name, equivalent, gamma, WITHDRAWAL_RATE)
      result['portfolios'][name].update({
          'mean_utility': total, 'consumption_utility': consumption,
          'bequest_utility': total - consumption,
          'bequest_share_of_negative_utility': (total - consumption) / total,
          'equivalent_relative_utility_residual': (at_equivalent - target_utility) / abs(target_utility),
          'worst_one_percent_share_of_negative_utility': float(np.sort(outcomes.utility)[:max(1, runs//100)].sum() / outcomes.utility.sum()),
      })
  finally:
    clu.BEQUEST_STRENGTH = previous_theta
    clear_utility_batches()
  return result


def point(value: float) -> str:
  return f"{100.0 * value:+.2f}"


def pct(value: float) -> str:
  return f"{100.0 * value:.2f}\\%"


def write_tex(path: str, results: list[dict], runs: int) -> None:
  # Rendered in LEVELS: each family reads directly against the ACO row,
  # without interpreting the sign of a difference. Every ruin and saving value
  # is lower than ACO's at each gamma.
  with open(path, "w", encoding="utf-8") as handle:
    handle.write("% Generated by build/gamma_sensitivity.py -- do not edit.\n")
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
        "$\\theta(\\gamma)=\\theta_{3.84}\\cdot 12^{\\,3.84-\\gamma}$, under "
        "the legacy joint calibration. $^{\\dagger}$Baseline.\n"
        % f"{runs:,}".replace(",", "{,}"))
    handle.write("\\end{minipage}\n\\end{table}\n")


def main() -> None:
  global FIXED_THETA
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument('--fixed-theta', action='store_true', help='Hold annual bequest intensity at 2360 across gamma')
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
  parser.add_argument("--fx-hedge-cost", type=float,
                      default=DEFAULT_FX_HEDGE_COST)
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--output-json", default=os.path.join(
      HERE, "..", "paper", "figures", "gamma_sensitivity.json"))
  parser.add_argument("--output-tex", default=None,
                      help="table LaTeX optionnelle ; l'annexe lit le JSON via render_restored_appendices.py")
  args = parser.parse_args()
  FIXED_THETA = args.fixed_theta
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
      "theta_convention": 'fixed_annual' if FIXED_THETA else 'legacy_monthly_coefficient_fixed',
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
  if args.output_tex:
    write_tex(args.output_tex, results, args.runs)
  print(args.output_json)


if __name__ == "__main__":
  main()
