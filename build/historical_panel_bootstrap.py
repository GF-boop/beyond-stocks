#!/usr/bin/env python3
"""Nested bootstrap of the calendar history for the central 175% comparison.

An outer stationary bootstrap resamples complete calendar-year cross-sections.
Thus each selected synthetic year retains every country return, global sleeve
and conversion convention observed in its source calendar year.  Original
calendar blocks are kept consecutive; the copied years are then relabelled in
chronological synthetic order so the inner ACO-style country-block bootstrap
can operate normally.  The output measures variation across possible
historical panels, separate from Monte Carlo error conditional on one panel.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_fixed_stacked_utility import (  # noqa: E402
    BENCHMARK_NAME, DEFAULT_FX_HEDGE_COST, DEFAULT_SPREAD, return_functions,
)
from compare_gold_trend_equal_vol import DEFAULT_TREND_COST, DEFAULT_TREND_FEE  # noqa: E402
from compare_lifecycle_utility import (  # noqa: E402
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, clear_utility_batches,
    equivalent_savings_rate, evaluate_batch, expected_utility,
)
from historical_uncertainty import scenarios_for  # noqa: E402
from replicate_extended import read_panel  # noqa: E402


CENTRAL = ("70/46.67/29.17/29.17 ACO", "43.75/43.75/43.75/43.75 ACO")


def outer_years(years: list[int], mean_block: float, rng: random.Random) -> list[int]:
  """Stationary blocks on the full annual calendar, wrapping at its endpoints."""
  result: list[int] = []
  count = len(years)
  probability = 1.0 / mean_block
  while len(result) < count:
    start = rng.randrange(count)
    length = max(1, math.ceil(math.log(1.0 - rng.random()) /
                              math.log(1.0 - probability)))
    result.extend(years[(start + offset) % count] for offset in range(length))
  return result[:count]


def resampled_panel(rows: list[dict[str, float]], years: list[int], sampled: list[int]) -> list[dict[str, float]]:
  by_year: dict[int, list[dict[str, float]]] = {}
  for row in rows:
    by_year.setdefault(int(row["year"]), []).append(row)
  synthetic: list[dict[str, float]] = []
  for synthetic_year, source_year in zip(years, sampled):
    for source in by_year[source_year]:
      copied = dict(source)
      copied["year"] = synthetic_year
      synthetic.append(copied)
  return synthetic


def evaluate(rows: list[dict[str, float]], runs: int, seed: int) -> dict:
  all_functions = return_functions(rows, DEFAULT_SPREAD, DEFAULT_TREND_FEE,
                                   DEFAULT_TREND_COST, 0.0,
                                   DEFAULT_FX_HEDGE_COST)
  names = (BENCHMARK_NAME, *CENTRAL)
  functions = {name: all_functions[name] for name in names}
  scenarios = scenarios_for(rows, functions, runs, 10.0, seed)
  target = expected_utility(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE,
                            GAMMA, WITHDRAWAL_RATE)
  benchmark = evaluate_batch(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE,
                             WITHDRAWAL_RATE, GAMMA)
  output = {"benchmark_ruin": float(np.mean(benchmark.ruined)), "strategies": {}}
  for name in CENTRAL:
    outcome = evaluate_batch(scenarios, name, BASE_SAVINGS_RATE,
                             WITHDRAWAL_RATE, GAMMA)
    output["strategies"][name] = {
        "ruin_probability": float(np.mean(outcome.ruined)),
        "ruin_difference_vs_aco": float(np.mean(outcome.ruined.astype(float)
                                                  - benchmark.ruined.astype(float))),
        "equivalent_savings_rate": equivalent_savings_rate(
            scenarios, name, target, GAMMA, WITHDRAWAL_RATE),
    }
  clear_utility_batches()
  return output


def percentile(values: list[float], probability: float) -> float:
  return float(np.quantile(np.asarray(values), probability))


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--outer-replicates", type=int, default=200)
  parser.add_argument("--inner-runs", type=int, default=1_000)
  parser.add_argument("--outer-mean-block", type=float, default=10.0)
  parser.add_argument("--seed", type=int, default=20260905)
  parser.add_argument("--output-json", required=True)
  args = parser.parse_args()
  if args.outer_replicates < 2 or args.inner_runs < 1 or args.outer_mean_block <= 1:
    raise ValueError("outer replicates >= 2, inner runs >= 1, block length > 1 required")
  rows = read_panel(args.panel)
  years = sorted({int(row["year"]) for row in rows})
  rng = random.Random(args.seed)
  replicates = []
  for index in range(args.outer_replicates):
    sampled = outer_years(years, args.outer_mean_block, rng)
    result = evaluate(resampled_panel(rows, years, sampled), args.inner_runs,
                      args.seed + index + 1)
    result["replicate"] = index + 1
    result["unique_source_years"] = len(set(sampled))
    replicates.append(result)
    print(f"{index + 1}/{args.outer_replicates}: ACO ruin {result['benchmark_ruin']:.2%}")
  summary = {}
  for name in CENTRAL:
    summary[name] = {}
    for metric in ("ruin_difference_vs_aco", "equivalent_savings_rate", "ruin_probability"):
      values = [item["strategies"][name][metric] for item in replicates]
      summary[name][metric] = {
          "median": float(statistics.median(values)),
          "p05": percentile(values, 0.05), "p95": percentile(values, 0.95),
          "share_better_than_aco": (float(np.mean(np.asarray(values) < 0.0))
                                      if metric == "ruin_difference_vs_aco" else None),
      }
  payload = {
      "purpose": "Nested stationary bootstrap of complete calendar-year panels",
      "outer_replicates": args.outer_replicates, "inner_runs": args.inner_runs,
      "outer_mean_block_years": args.outer_mean_block, "inner_mean_block_years": 10.0,
      "seed": args.seed, "calendar_years": [min(years), max(years)],
      "source_observations": len(rows), "summary": summary, "replicates": replicates,
  }
  os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")


if __name__ == "__main__":
  main()
