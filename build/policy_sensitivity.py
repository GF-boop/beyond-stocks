"""Sensitivity of the two diversified families to policy parameters.

ACO report the robustness of their result only for the optimal *composition*,
never for the *magnitudes* of welfare. The gamma sweep applies this test to
risk aversion. This script does the same for two household policy parameters
that ACO also varied (Table VII) without publishing the effect on magnitudes:

* the contribution rate during working life, r_c in {5, 10, 15}%;
* the real withdrawal rate in retirement, r_w in {3, 4, 5}%.

Method:

* Weights and leverage stay the frozen definitions of the manifest. No weight,
  leverage or asset is re-optimised in any row.
* r_c axis: the reference rate of ACO 33/67 is *also* set to r_c in each row,
  and the target utility is recomputed at that r_c. The question is therefore:
  in a world where everyone saves r_c%, does diversification still lower the
  required rate and ruin by a comparable amount? Anchoring at a fixed 10% would
  make the difference mechanically proportional to r_c and teach nothing.
* r_w axis: the reference savings rate stays 10% (as everywhere else in the
  paper) and only the withdrawal varies. Since ruin is the exhaustion of the
  financial account, it is mechanically very sensitive to r_w.
* The r_c = 10% row of the contribution axis and the r_w = 4% row of the
  withdrawal axis are the reference case and must coincide.

Outputs:

* ``figures/policy_sensitivity.json``: full audit, read by
  ``render_restored_appendices.py``;
* ``--output-tex``: optional two-panel LaTeX table.
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
PORTFOLIOS = (*PORTFOLIOS, 'ACO 33/67 200%')
WITHDRAWAL_RATES = (0.03, 0.04, 0.05)


def _row(rows, base_rate, withdrawal_rate, runs, seed, spread, fx_hedge_cost,
         trend_fee, trend_cost, scenarios=None):
  """One point of the sweep: ACO 33/67 saves ``base_rate`` and withdraws
  ``withdrawal_rate``; the two families are evaluated on the same draws."""
  if scenarios is None:
    functions_all = return_functions(
        rows, spread, trend_fee, trend_cost, 0.0, fx_hedge_cost)
    names = (BENCHMARK_NAME, *PORTFOLIOS)
    functions = {name: functions_all[name] for name in names}
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
  # ACO's reference savings rate in this row: it is ``base_rate`` (5, 10 or
  # 15% on the contribution axis), not a hard-coded 10%.
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
        # The saving difference is measured against this row's reference rate,
        # not against a hard-coded 10%.
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
  # Rendered in LEVELS: each family reads directly against the two ACO
  # reference columns (ruin and saving), without interpreting the sign of a
  # difference. On the contribution axis ACO's reference saving is r_c, not 10%,
  # which the ``ACO sav'' column makes explicit row by row.
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
    handle.write("% Generated by build/policy_sensitivity.py -- do not edit.\n")
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
        "1{,}561-country-year panel, ten-year mean stationary blocks, "
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
  parser.add_argument("--output-tex", default=None,
                      help="table LaTeX optionnelle ; l'annexe lit le JSON via render_restored_appendices.py")
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
  if args.output_tex:
    write_tex(args.output_tex, contribution, withdrawal, args.runs)
  print(args.output_json)


if __name__ == "__main__":
  main()
