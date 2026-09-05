#!/usr/bin/env python3
"""Finance a common retirement-income target across fixed portfolios.

For each paired lifecycle path, the target is the financial withdrawal that
the unlevered ACO 33/67 portfolio would plan at age 65 after saving 10% of
income: 4% of that path's ACO retirement wealth.  Every candidate strategy
saves the same 10%, faces the same income, mortality and return path, and is
asked to finance that fixed real annual draw.  Public pensions are identical
within a path and are therefore reported separately from the financial target.

This is deliberately not an equivalent-saving calculation.  It asks whether a
strategy can deliver ACO's planned financial retirement income, rather than
allowing its own retirement wealth to lower the withdrawal goal.
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
    BENCHMARK_NAME, DEFAULT_FX_HEDGE_COST, DEFAULT_SPREAD, return_functions,
)
from compare_gold_trend_equal_vol import DEFAULT_TREND_COST, DEFAULT_TREND_FEE  # noqa: E402
from compare_lifecycle_utility import BASE_SAVINGS_RATE, _utility_batch, evaluate_batch  # noqa: E402
from historical_uncertainty import scenarios_for  # noqa: E402
from replicate_extended import read_panel  # noqa: E402


CENTRAL = (
    BENCHMARK_NAME,
    "ACO 33/67 175%",
    "70/46.67/29.17/29.17 ACO",
    "43.75/43.75/43.75/43.75 ACO",
)


def evaluate(scenarios, strategy: str, target: np.ndarray, return_events=False) -> dict:
  """Evaluate a constant path-specific financial draw, in real dollars."""
  batch = _utility_batch(scenarios, strategy)
  wealth = BASE_SAVINGS_RATE * batch.retirement_wealth_unit.copy()
  initial_wealth = wealth.copy()
  active = batch.active
  years_active = active.sum(axis=0)
  paid = np.zeros(len(scenarios), dtype=float)
  shortfall = np.zeros(len(scenarios), dtype=float)
  ever_short = np.zeros(len(scenarios), dtype=bool)
  short_years = np.zeros(len(scenarios), dtype=int)
  for offset in range(batch.returns.shape[0]):
    present = active[offset]
    served = np.minimum(wealth, target)
    gap = np.maximum(0.0, target - served)
    paid[present] += served[present]
    shortfall[present] += gap[present]
    ever_short[present] |= gap[present] > 0.005
    short_years[present] += (gap[present] > 0.005).astype(int)
    wealth[present] = np.maximum(0.0, wealth[present] - served[present])
    wealth[present] = np.maximum(
        0.0, wealth[present] * (1.0 + batch.returns[offset, present]))
  required = target * years_active
  retired = required > 0.005
  positive_capital = retired & (initial_wealth > 0.0)
  implicit_rates = target[positive_capital] / initial_wealth[positive_capital]
  funding_ratio = np.ones(len(scenarios), dtype=float)
  shortfall_share = np.zeros(len(scenarios), dtype=float)
  funding_ratio[retired] = paid[retired] / required[retired]
  shortfall_share[retired] = shortfall[retired] / required[retired]
  result = {
      "shortfall_probability_all_paths": float(np.mean(ever_short)),
      "shortfall_count": int(ever_short.sum()),
      "eligible_path_count": int(retired.sum()),
      "retired_path_share": float(np.mean(retired)),
      "implicit_withdrawal_rate_positive_capital": {
          "median": float(np.median(implicit_rates)),
          "p90": float(np.quantile(implicit_rates, 0.90)),
          "share_above_4pct": float(np.mean(implicit_rates > 0.04 + 1e-12)),
          "share_above_6pct": float(np.mean(implicit_rates > 0.06)),
          "share_above_8pct": float(np.mean(implicit_rates > 0.08)),
      },
      "zero_capital_share_among_retired": float(np.mean(initial_wealth[retired] <= 0.0)),
      "shortfall_probability": float(np.mean(ever_short[retired])),
      "mean_financial_funding_ratio": float(np.mean(funding_ratio[retired])),
      "median_financial_funding_ratio": float(np.median(funding_ratio[retired])),
      "mean_shortfall_share": float(np.mean(shortfall_share[retired])),
      "mean_shortfall_years_conditional": (
          float(np.mean(short_years[ever_short])) if np.any(ever_short) else 0.0),
      "median_shortfall_dollars_conditional": (
          float(np.median(shortfall[ever_short])) if np.any(ever_short) else 0.0),
  }
  if return_events:
    result["events"] = ever_short
  return result


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--output-json", required=True)
  args = parser.parse_args()
  if args.runs < 1:
    raise ValueError("--runs must be positive")
  rows = read_panel(args.panel)
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if len(rows) < 2:
    raise ValueError("The requested historical window is too short")
  all_functions = return_functions(
      rows, DEFAULT_SPREAD, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, 0.0,
      DEFAULT_FX_HEDGE_COST)
  functions = {name: all_functions[name] for name in CENTRAL}
  scenarios = scenarios_for(rows, functions, args.runs, 10.0, args.seed)
  aco_batch = _utility_batch(scenarios, BENCHMARK_NAME)
  target = np.where(np.any(aco_batch.active, axis=0),
                    0.04 * BASE_SAVINGS_RATE * aco_batch.retirement_wealth_unit, 0.0)
  identity = {}
  for name in CENTRAL:
    original = evaluate_batch(scenarios, name, BASE_SAVINGS_RATE)
    own_target = 0.04 * original.retirement_wealth
    check = evaluate(scenarios, name, own_target, return_events=True)
    np.testing.assert_array_equal(check['events'], original.ruined)
    identity[name] = {
        'own_target_event_mismatches': int(np.count_nonzero(check['events'] != original.ruined)),
        'main_rule_ruin_count': int(original.ruined.sum()),
        'main_rule_ruin_all_paths': float(np.mean(original.ruined)),
    }
  with open(os.path.join(HERE, '..', 'results', 'main_ladders_n10000.json')) as handle:
    archived = json.load(handle)
  if args.runs == archived['runs'] and args.seed == archived['seed'] and args.year_from is None:
    archive_by_name = {row['strategy']: row for row in archived['results']}
    for name in CENTRAL:
      np.testing.assert_allclose(identity[name]['main_rule_ruin_all_paths'],
                                 archive_by_name[name]['ruin_probability'], atol=1e-12, rtol=0)
      identity[name]['matches_archived_main_ruin'] = True
  output = {
      "purpose": "Common path-specific ACO planned financial withdrawal",
      "runs": args.runs, "seed": args.seed, "year_from": args.year_from,
      "period": f"{min(row['year'] for row in rows)}-{max(row['year'] for row in rows)}",
      "observations": len(rows), "mean_block_years": 10.0,
      "benchmark": BENCHMARK_NAME, "benchmark_savings_rate": BASE_SAVINGS_RATE,
      "target_withdrawal_rate": 0.04,
      "median_initial_target_dollars": float(np.median(target)),
      "mean_initial_target_dollars": float(np.mean(target)),
      "strategies": {name: evaluate(scenarios, name, target) for name in CENTRAL},
      "own_withdrawal_identity_audit": identity,
  }
  os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(output, handle, indent=2)
    handle.write("\n")
  for name, result in output["strategies"].items():
    print(f"{name:<30} shortfall {result['shortfall_probability']:.2%} "
          f"funded {result['mean_financial_funding_ratio']:.2%}")


if __name__ == "__main__":
  main()
