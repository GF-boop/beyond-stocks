#!/usr/bin/env python3
"""Nested calendar bootstrap at equal volatility (revision of September 22, 2026).

Same outer resampling, seeds and inner simulation as
``historical_panel_bootstrap.py``, but evaluates the proportional, risk parity
and stocks-plus-MF strategies at their baseline equal-volatility exposures
(``results/equal_volatility/revision_checks.json``), held fixed across
histories, and also records the path-matched income failure.

Usage: python3 build/historical_panel_bootstrap_eqvol.py --outer-mean-block 10
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
from pathlib import Path

import numpy as np

from historical_panel_bootstrap import outer_years, resampled_panel, percentile
from sleeve_ablation import function_for
from compare_fixed_stacked_utility import BENCHMARK_NAME
from compare_gold_trend_equal_vol import DEFAULT_TREND_COST, DEFAULT_TREND_FEE
from compare_lifecycle_utility import (
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, clear_utility_batches,
    equivalent_savings_rate, evaluate_batch)
from common_consumption_target import evaluate as common_evaluate
from historical_uncertainty import scenarios_for
from replicate_extended import read_panel

ROOT = Path(__file__).resolve().parents[1]
REVISION = ROOT / 'results/equal_volatility/revision_checks.json'
OUT = ROOT / 'results/equal_volatility/histories'
NAMES = ('Proportional equal volatility', 'Risk parity equal volatility', 'Stocks and MF equal volatility')


def evaluate(rows, runs, seed, weights):
  fns = {n: function_for(tuple(w), .003, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, .001)
         for n, w in weights.items()}
  scenarios = scenarios_for(rows, fns, runs, 10.0, seed)
  outcomes = {n: evaluate_batch(scenarios, n, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA) for n in fns}
  ref = outcomes[BENCHMARK_NAME]
  target = float(ref.utility.mean())
  matched = .04 * ref.retirement_wealth
  out = {'benchmark_ruin': float(ref.ruined.mean()), 'strategies': {}}
  for n in NAMES:
    o = outcomes[n]
    out['strategies'][n] = {
        'ruin_difference_vs_aco': float(np.mean(o.ruined.astype(float) - ref.ruined.astype(float))),
        'equivalent_savings_rate': equivalent_savings_rate(scenarios, n, target, GAMMA, WITHDRAWAL_RATE),
        'matched_difference_vs_aco': float(common_evaluate(scenarios, n, matched, True)
                                           ['shortfall_probability_all_paths'] - ref.ruined.mean()),
    }
  clear_utility_batches()
  return out


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--outer-replicates', type=int, default=100)
  parser.add_argument('--inner-runs', type=int, default=1000)
  parser.add_argument('--outer-mean-block', type=float, default=10.0)
  parser.add_argument('--seed', type=int, default=20260905)
  args = parser.parse_args()
  published = {r['strategy']: r['weights'] for r in json.loads(REVISION.read_text())['results']}
  weights = {BENCHMARK_NAME: [1., 0, 0, 0], **{n: published[n] for n in NAMES}}
  rows = read_panel(str(ROOT / 'data/replication-panel-trend.csv'))
  years = sorted({int(r['year']) for r in rows})
  rng = random.Random(args.seed)
  replicates = []
  for index in range(args.outer_replicates):
    sampled = outer_years(years, args.outer_mean_block, rng)
    result = evaluate(resampled_panel(rows, years, sampled), args.inner_runs, args.seed + index + 1, weights)
    result['replicate'] = index + 1
    replicates.append(result)
    print(f"{index + 1}/{args.outer_replicates}", flush=True)
  summary = {}
  for n in NAMES:
    summary[n] = {}
    for metric in ('ruin_difference_vs_aco', 'equivalent_savings_rate', 'matched_difference_vs_aco'):
      values = [item['strategies'][n][metric] for item in replicates]
      summary[n][metric] = {'median': float(statistics.median(values)),
                            'p05': percentile(values, .05), 'p95': percentile(values, .95),
                            'share_below_zero': float(np.mean(np.asarray(values) < 0))
                            if metric != 'equivalent_savings_rate' else
                            float(np.mean(np.asarray(values) < BASE_SAVINGS_RATE))}
  OUT.mkdir(parents=True, exist_ok=True)
  path = OUT / f'calendar_blocks_{args.outer_mean_block:g}y_outer{args.outer_replicates}_inner{args.inner_runs}.json'
  path.write_text(json.dumps({'outer_replicates': args.outer_replicates, 'inner_runs': args.inner_runs,
                              'outer_mean_block_years': args.outer_mean_block, 'seed': args.seed,
                              'weights': weights, 'summary': summary, 'replicates': replicates},
                             indent=2) + '\n')


if __name__ == '__main__':
  main()
