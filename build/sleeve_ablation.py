#!/usr/bin/env python3
"""Ablation des poches des portefeuilles diversifies a exposition constante.

Chaque experience retire une poche (obligations mondiales, or ou managed
futures) et realloue son notionnel entre les trois autres au prorata de leurs
poids. L'exposition brute, le financement, la couverture fixe et les couts
restent donc identiques a ceux de la recette complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
from collections.abc import Callable

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_fixed_stacked_utility import (  # noqa: E402
    BENCHMARK_NAME, DEFAULT_FX_HEDGE_COST, DEFAULT_SPREAD,
    return_functions,
)
from compare_gold_trend_equal_vol import (  # noqa: E402
    DEFAULT_TREND_COST, DEFAULT_TREND_FEE,
)
from compare_lifecycle_utility import (  # noqa: E402
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, build_scenario,
    draw_death_age, equivalent_savings_rate, evaluate_batch, expected_utility,
)
from income_process import draw_household_income  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
    MAX_AGE, START_AGE, block_bootstrap, read_panel,
)

Component = tuple[float, float, float, float]
FAMILIES: dict[str, Component] = {
    "Proportional four-sleeve, 175%": (0.70, 0.4666666666666667,
                                        0.2916666666666667,
                                        0.2916666666666667),
    "Equal-weight four-sleeve, 175%": (0.4375, 0.4375, 0.4375, 0.4375),
}
SLEEVES = ("global bonds", "gold", "managed futures")


def reallocate(exposures: Component, removed_index: int) -> Component:
  """Remove one sleeve and preserve gross exposure by pro-rata reallocation."""
  removed = exposures[removed_index]
  remaining = sum(exposures) - removed
  if removed <= 0.0 or remaining <= 0.0:
    raise ValueError("The requested ablation requires a positive sleeve")
  scale = sum(exposures) / remaining
  return tuple(0.0 if index == removed_index else value * scale
               for index, value in enumerate(exposures))  # type: ignore[return-value]


def function_for(exposures: Component, spread: float, trend_fee: float,
                 trend_cost: float, hedge_cost: float) -> Callable:
  equity, bond, gold, trend = exposures
  gross = sum(exposures)
  cash = 1.0 - gross
  borrowing = gross - 1.0

  def portfolio(row: dict[str, float]) -> float:
    aco = 0.33 * row["domestic"] + 0.67 * row["international"]
    net_trend = ((1.0 + row["trend_fixed_notional"]) * (1.0 - trend_fee)
                 - 1.0 - trend_cost)
    return (equity * aco + bond * row["world_bond_fixed_notional"]
            + gold * row["gold"] + trend * net_trend + cash * row["world_bill"]
            - borrowing * spread - (bond + trend) * hedge_cost)
  return portfolio


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--panel", default=os.path.join(HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--year-from", type=int,
                      help="retain calendar years greater than or equal to this value")
  parser.add_argument("--year-to", type=int,
                      help="retain calendar years less than or equal to this value")
  parser.add_argument("--ladder", action="store_true", help="Evaluate five exposures for every complete and ablated composition")
  parser.add_argument("--output-json", default=os.path.join(
      HERE, "..", "results", "sleeve_ablation_n10000.json"))
  args = parser.parse_args()
  if args.runs < 1:
    raise ValueError("--runs must be positive")

  panel_path = args.panel
  rows = read_panel(panel_path)
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  if len(rows) < 2:
    raise ValueError("The requested historical window is too short")
  functions: dict[str, Callable] = {
      BENCHMARK_NAME: function_for((1.0, 0.0, 0.0, 0.0), DEFAULT_SPREAD,
                                   DEFAULT_TREND_FEE, DEFAULT_TREND_COST,
                                   DEFAULT_FX_HEDGE_COST),
  }
  definitions: dict[str, dict] = {}
  functions['ACO 33/67 175%'] = return_functions(
      rows, DEFAULT_SPREAD, DEFAULT_TREND_FEE, DEFAULT_TREND_COST,
      0.0, DEFAULT_FX_HEDGE_COST)['ACO 33/67 175%']
  families = FAMILIES if not args.ladder else {
      family.replace("175%", f"{level}%"): tuple(x * level / 175 for x in weights)
      for family, weights in FAMILIES.items() for level in (100,125,150,175,200)
  }
  if args.ladder:
    all_functions = return_functions(rows, DEFAULT_SPREAD, DEFAULT_TREND_FEE,
                                    DEFAULT_TREND_COST, 0.0, DEFAULT_FX_HEDGE_COST)
    functions.update({name: fn for name, fn in all_functions.items() if name.startswith("ACO 33/67 ") and name.endswith("%")})
  for family, exposures in families.items():
    functions[family] = function_for(exposures, DEFAULT_SPREAD,
                                     DEFAULT_TREND_FEE, DEFAULT_TREND_COST,
                                     DEFAULT_FX_HEDGE_COST)
    definitions[family] = {"complete_exposures": exposures, "ablations": {}}
    for index, sleeve in enumerate(SLEEVES, start=1):
      ablated = reallocate(exposures, index)
      name = f"{family} without {sleeve}"
      functions[name] = function_for(ablated, DEFAULT_SPREAD,
                                     DEFAULT_TREND_FEE, DEFAULT_TREND_COST,
                                     DEFAULT_FX_HEDGE_COST)
      definitions[family]["ablations"][sleeve] = {"strategy": name,
                                                    "exposures": ablated}

  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)
  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  scenarios = []
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, 10.0, "aco")
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, _ = draw_household_income(rng)
    scenarios.append(build_scenario(
        path, functions, female_death, male_death, female_income, male_income))

  target = expected_utility(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE,
                            GAMMA, WITHDRAWAL_RATE)
  benchmark = evaluate_batch(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE,
                             WITHDRAWAL_RATE, GAMMA)
  outcomes_by_name = {
      name: evaluate_batch(scenarios, name, BASE_SAVINGS_RATE,
                           WITHDRAWAL_RATE, GAMMA)
      for name in functions
  }
  payload_results = []
  for name, function in functions.items():
    returns = [function(row) for row in rows]
    outcomes = outcomes_by_name[name]
    ruin = float(np.mean(outcomes.ruined))
    difference = outcomes.ruined.astype(float) - benchmark.ruined.astype(float)
    se = statistics.stdev(difference) / math.sqrt(args.runs)
    payload_results.append({
        "strategy": name,
        "annual_volatility": statistics.stdev(returns),
        "equivalent_savings_rate": equivalent_savings_rate(
            scenarios, name, target, GAMMA, WITHDRAWAL_RATE),
        "ruin_probability": ruin,
        "ruin_difference_vs_aco": float(np.mean(difference)),
        "ruin_difference_ci95": [float(np.mean(difference) - 1.96 * se),
                                     float(np.mean(difference) + 1.96 * se)],
    })
  ablation_effects = {}
  for family, definition in definitions.items():
    complete = outcomes_by_name[family].ruined.astype(float)
    ablation_effects[family] = {}
    for sleeve, specification in definition["ablations"].items():
      difference = outcomes_by_name[specification["strategy"]].ruined.astype(float) - complete
      mean = float(np.mean(difference))
      se = statistics.stdev(difference) / math.sqrt(args.runs)
      ablation_effects[family][sleeve] = {
          "ruin_difference_without_minus_complete": mean,
          "ruin_difference_ci95": [mean - 1.96 * se, mean + 1.96 * se],
      }
  payload = {
      "purpose": "Constant-gross-exposure sleeve ablation",
      "ablation_rule": "Remove one sleeve and reallocate its notional pro rata among the remaining sleeves.",
      "seed": args.seed, "runs": args.runs, "observations": len(rows),
      "period": f"{min(row['year'] for row in rows)}-{max(row['year'] for row in rows)}",
      "year_from": args.year_from, "year_to": args.year_to,
      "mean_block_years": 10.0,
      "bootstrap_end_treatment": "aco", "hedge_mode": "fixed_notional",
      "spread": DEFAULT_SPREAD, "fx_hedge_cost": DEFAULT_FX_HEDGE_COST,
      "trend_fee": DEFAULT_TREND_FEE, "trend_cost": DEFAULT_TREND_COST,
      "panel_sha256": hashlib.sha256(open(panel_path, "rb").read()).hexdigest(),
      "definitions": definitions, "results": payload_results,
      "ablation_effects": ablation_effects,
  }
  with open(args.output_json, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
  for result in payload_results:
    print(f"{result['strategy']:<65} vol {result['annual_volatility']:.2%} "
          f"saving {result['equivalent_savings_rate']:.2%} "
          f"ruin {result['ruin_probability']:.2%}")


if __name__ == "__main__":
  main()
