#!/usr/bin/env python3
"""Grille d'optimisation ACO sur le panel public, avec le constructeur de
scenarios du moteur principal et le meme flux aleatoire que main() :
mix domestique/international non leve, 100% brut, utilite moyenne maximale."""

import json
import os
import random
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from compare_fixed_stacked_utility import BENCHMARK_NAME  # noqa: E402
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
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
    MAX_AGE,
    START_AGE,
    block_bootstrap,
    read_panel,
)

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = 10000
SEED = 20260827
GRID = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.33, 0.35,
        0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]


def mix_fn(w: float):
  def fn(row):
    return w * row["domestic"] + (1.0 - w) * row["international"]
  return fn


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--runs", type=int, default=RUNS)
  parser.add_argument("--panel", default=os.path.join(
      HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--output-json", default=os.path.join(
      HERE, "..", "results", "grid_equity_n10000.json"))
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs must be positive")
  rows = read_panel(args.panel)
  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1

  names = {weight: f"mix_{weight:.2f}" for weight in GRID}
  functions = {name: mix_fn(weight) for weight, name in names.items()}
  functions[BENCHMARK_NAME] = mix_fn(0.33)
  rng = random.Random(SEED)
  scenarios = []
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, 10.0)
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, _ = draw_household_income(rng)
    scenarios.append(build_scenario(
      path, functions, female_death, male_death, female_income, male_income))
  util_b = expected_utility(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE)
  results = []
  for w in GRID:
    name = names[w]
    util = expected_utility(scenarios, name, BASE_SAVINGS_RATE)
    eq = equivalent_savings_rate(scenarios, name, util_b, GAMMA,
                                 WITHDRAWAL_RATE)
    ruined = float(np.mean(evaluate_batch(
      scenarios, name, BASE_SAVINGS_RATE).ruined))
    row = {"domestic_pct": round(w * 100, 1),
           "international_pct": round((1 - w) * 100, 1),
           "mean_utility": util,
           "benchmark_utility": util_b,
           "equivalent_saving_vs_3367_pct": round(eq * 100, 2),
           "ruin_pct": round(ruined * 100, 2)}
    results.append(row)
    print(f"w={w * 100:5.1f}%  ruine={ruined * 100:5.2f}%  "
          f"saving éq. vs 33/67={eq * 100:6.2f}%", flush=True)

  best = max(results, key=lambda r: r["mean_utility"])
  out = {"seed": SEED, "runs": args.runs, "grid": results, "argmax": best}
  path = args.output_json
  with open(path, "w") as f:
    json.dump(out, f, indent=1)
  print(f"argmax : {best['domestic_pct']}% domestique / "
        f"{best['international_pct']}% international -> {path}")


if __name__ == "__main__":
  main()
