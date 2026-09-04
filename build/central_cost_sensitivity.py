"""Stress de couts prospectifs sur les deux familles centrales a 200 %.

Les familles proportionnelle et equiponderee conservent leurs poids fixes de
200 % bruts. Le script ne recale donc ni le levier ni les actifs : il varie
seulement le spread de financement phi et la friction annuelle de couverture
kappa, puis rapporte l'epargne equivalente et la ruine dans le meme modele de
cycle de vie que le tableau central.

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


FINANCING_SPREADS = (0.003, 0.010, 0.020, 0.030)
PORTFOLIOS = (*PORTFOLIOS, 'ACO 33/67 200%')
HEDGE_COSTS = (0.001, 0.005, 0.010)


def evaluate(rows: list[dict[str, float]], runs: int, seed: int, spread: float,
             hedge_cost: float, trend_fee: float, trend_cost: float) -> dict:
  functions_all = return_functions(
      rows, spread, trend_fee, trend_cost, 0.0, hedge_cost)
  names = (BENCHMARK_NAME, *PORTFOLIOS)
  functions = {name: functions_all[name] for name in names}
  scenarios = scenarios_for(rows, functions, runs, 10.0, seed)
  target = expected_utility(
      scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
  benchmark = evaluate_batch(
      scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
  output = {
      "spread": spread,
      "hedge_cost": hedge_cost,
      "benchmark_ruin": float(np.mean(benchmark.ruined)),
      "portfolios": {},
  }
  for name in PORTFOLIOS:
    outcomes = evaluate_batch(
        scenarios, name, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
    output["portfolios"][name] = {
        "equivalent_savings_rate": equivalent_savings_rate(
            scenarios, name, target, GAMMA, WITHDRAWAL_RATE),
        "ruin_probability": float(np.mean(outcomes.ruined)),
    }
  clear_utility_batches()
  return output


def pct(value: float) -> str:
  return f"{100.0 * value:.2f}\\%"


def write_cost_tex(path: str, financing: list[dict], hedging: list[dict],
                   runs: int) -> None:
  def row(label: str, result: dict) -> str:
    proportional = result["portfolios"][PROPORTIONAL]
    equal_weight = result["portfolios"][EQUAL_WEIGHT]
    return (f"{label} & {pct(result['spread'])} & {pct(result['hedge_cost'])} & "
            f"{pct(proportional['equivalent_savings_rate'])} & "
            f"{pct(proportional['ruin_probability'])} & "
            f"{pct(equal_weight['equivalent_savings_rate'])} & "
            f"{pct(equal_weight['ruin_probability'])} \\\\\n")
  with open(path, "w", encoding="utf-8") as handle:
    handle.write("\\begin{table}[H]\n\\centering\n")
    handle.write("\\caption{Prospective financing and hedging-cost stress at 200\\% gross exposure}\n")
    handle.write("\\label{tab:central-cost-sensitivity}\n")
    handle.write("\\small\\setlength{\\tabcolsep}{3.5pt}\n")
    handle.write("\\begin{tabular}{lrrrrrr}\n\\toprule\n")
    handle.write("Stress & $\\phi$ & $\\kappa$ & \\multicolumn{2}{c}{Proportional 200\\%} & \\multicolumn{2}{c}{Equal-weight 200\\%} \\\\\n")
    handle.write(" & & & Saving & Ruin & Saving & Ruin \\\\\n\\midrule\n")
    for result in financing:
      basis_points = round(result["spread"] * 10_000)
      label = f"Financing {basis_points} bp"
      handle.write(row(label, result))
    handle.write("\\addlinespace\n")
    for result in hedging:
      basis_points = round(result["hedge_cost"] * 10_000)
      label = f"Hedging {basis_points} bp"
      handle.write(row(label, result))
    handle.write("\\bottomrule\n\\end{tabular}\n")
    handle.write("\\begin{minipage}{0.97\\textwidth}\\footnotesize\n")
    handle.write(
        "\\textit{Note:} %s paired lifecycle paths per row, ten-year mean "
        "stationary blocks, full 1{,}557-country-year panel. The financing "
        "rows hold $\\kappa=10$ bp, and the hedging rows hold $\\phi=30$ bp. "
        "Both costs are fixed prospective haircuts applied to every historical "
        "year, not forecasts of the financing or hedging terms that prevailed "
        "in those years. Saving is utility-equivalent relative to ACO 33/67 at "
        "10\\%%.\n" % f"{runs:,}".replace(",", "{,}"))
    handle.write("\\end{minipage}\n\\end{table}\n")


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--output-json", default=os.path.join(
      HERE, "..", "paper", "figures", "central_cost_sensitivity.json"))
  parser.add_argument("--cost-tex", default=os.path.join(
      HERE, "..", "paper", "figures", "central_cost_sensitivity.tex"))
  parser.add_argument("--financing-spread", action="append", type=float,
                      help="run only the specified financing spread(s)")
  parser.add_argument("--hedge-cost", action="append", type=float,
                      help="run only the specified hedge friction(s)")
  parser.add_argument("--skip-financing", action="store_true")
  parser.add_argument("--skip-hedging", action="store_true")
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs must be positive")
  rows = read_panel(args.panel)
  if len(rows) < 2:
    raise ValueError("Panel too short")
  print(f"Central cost sensitivity: 7 specifications x {args.runs:,} paths"
        .replace(",", " "))
  financing = []
  financing_spreads = (() if args.skip_financing
                       else tuple(args.financing_spread or FINANCING_SPREADS))
  for spread in financing_spreads:
    # Memes trajectoires pour chaque cout : les differences entre lignes ne
    # reflètent donc pas un nouveau tirage de mortalite, revenu ou rendement.
    result = evaluate(rows, args.runs, args.seed, spread,
                      DEFAULT_FX_HEDGE_COST, args.trend_fee, args.trend_cost)
    financing.append(result)
    print(f"  phi {spread:.2%}, kappa {DEFAULT_FX_HEDGE_COST:.2%}: "
          + report(result))
  hedging = []
  hedge_costs = (() if args.skip_hedging
                 else tuple(args.hedge_cost or HEDGE_COSTS))
  for cost in hedge_costs:
    result = evaluate(rows, args.runs, args.seed,
                      DEFAULT_SPREAD, cost, args.trend_fee, args.trend_cost)
    hedging.append(result)
    print(f"  phi {DEFAULT_SPREAD:.2%}, kappa {cost:.2%}: " + report(result))
  payload = {
      "runs_per_specification": args.runs,
      "seed": args.seed,
      "financing_stress": financing,
      "hedging_stress": hedging,
  }
  os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
  if financing_spreads == FINANCING_SPREADS and hedge_costs == HEDGE_COSTS:
    write_cost_tex(args.cost_tex, financing, hedging, args.runs)


def report(result: dict) -> str:
  values = []
  for name, short in ((PROPORTIONAL, "P"), (EQUAL_WEIGHT, "EW")):
    item = result["portfolios"][name]
    values.append(f"{short} saving {item['equivalent_savings_rate']:.2%}, "
                  f"ruin {item['ruin_probability']:.2%}")
  return "; ".join(values)


if __name__ == "__main__":
  main()
