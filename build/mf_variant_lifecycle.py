"""Lifecycle outcomes under alternative managed-futures constructions.

Revision of September 22, 2026. Restores, on the current engine, the check that
the ranking survives changes in the trend signal: for each variant, the annual
US real gross series is rebuilt from ``data/managed-futures-monthly.csv`` with
the recipe of ``panel_managed_futures.py``, hedged into each resident currency
with ``panel_replication_tendance.build``, and the proportional, risk parity
and stocks-plus-MF strategies are evaluated at their baseline equal-volatility
exposures (held fixed), with the seed of the frozen run. All variants carry the
same flat turnover cost; the fee-doubled variant changes only the fee.

The baseline variant must reproduce the canonical panel and the published
equal-volatility results; the script stops otherwise.
"""
from pathlib import Path
import csv
import json
import numpy as np

from sleeve_ablation import function_for
from compare_fixed_stacked_utility import BENCHMARK_NAME
from compare_gold_trend_equal_vol import DEFAULT_TREND_FEE, DEFAULT_TREND_COST
from compare_lifecycle_utility import (
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, evaluate_batch,
    equivalent_savings_rate, clear_utility_batches)
from common_consumption_target import evaluate as common_evaluate
from historical_uncertainty import scenarios_for
from replicate_extended import read_panel
import panel_replication_tendance as prt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'results/revision_2026-09-22/mf_variant_lifecycle.json'
REVISION = ROOT / 'results/revision_2026-09-22/revision_checks.json'
SEED, RUNS, SPREAD = 20260827, 10000, .003

VARIANTS = [
    ('1_6_12', '1/6/12-month blend (baseline)', 'mf_1_6_12', DEFAULT_TREND_FEE),
    ('1_3_12', '1/3/12-month blend', 'mf_1_3_12', DEFAULT_TREND_FEE),
    ('12m', '12-month signal only', 'signal_12m', DEFAULT_TREND_FEE),
    ('1m', '1-month signal only', 'signal_1m', DEFAULT_TREND_FEE),
    ('fee2', '1/6/12-month blend, fee of 1.70\\%', 'mf_1_6_12', 2 * DEFAULT_TREND_FEE),
]


def month_index(m):
  y, k = m.split('-'); return int(y) * 12 + int(k) - 1


def read_cpi():
  cpi = {r['month']: float(r['cpi']) for r in csv.DictReader(open(DATA / 'cpi-monthly.csv')) if r.get('cpi')}
  months = sorted(cpi)
  for a, b in zip(months, months[1:]):
    if month_index(b) - month_index(a) == 2:   # fill an isolated one-month gap
      n = month_index(b) - 1
      cpi[f'{n // 12:04d}-{n % 12 + 1:02d}'] = (cpi[a] * cpi[b]) ** .5
  return cpi


def annual_series(prefix, cpi):
  gross, cash = {}, {}
  for r in csv.DictReader(open(DATA / 'managed-futures-monthly.csv')):
    g, c = r.get(f'{prefix}_gross_return'), r.get(f'{prefix}_cash_collateral_return')
    n = month_index(r['month']) - 1
    prev = f'{n // 12:04d}-{n % 12 + 1:02d}'
    if not g or not c or r['month'] not in cpi or prev not in cpi:
      continue
    d = cpi[r['month']] / cpi[prev]
    y = int(r['month'][:4])
    gross.setdefault(y, []).append((1 + float(g)) / d)
    cash.setdefault(y, []).append((1 + float(c)) / d)
  keep = [y for y in gross if len(gross[y]) == 12 and len(cash[y]) == 12]
  return ({y: float(np.prod(gross[y]) - 1) for y in keep},
          {y: float(np.prod(cash[y]) - 1) for y in keep})


def panel_for(trend, cash):
  panel = prt.read_rows(str(DATA / 'replication-panel.csv'))
  world = {int(r['year']): r for r in prt.read_rows(str(DATA / 'jst-ntsg-panel-2025.csv'))}
  gold = {int(r['year']): float(r['gold_real']) for r in prt.read_rows(str(DATA / 'gold-annual.csv'))}
  built = prt.build(panel, world, trend, cash, gold)
  tmp = OUT.with_suffix('.tmp.csv')
  with open(tmp, 'w', newline='') as h:
    w = csv.DictWriter(h, fieldnames=list(built[0].keys())); w.writeheader(); w.writerows(built)
  rows = read_panel(str(tmp)); tmp.unlink()
  return rows


def evaluate(rows, fee, weights):
  fns = {n: function_for(tuple(w), SPREAD, fee, DEFAULT_TREND_COST, .001) for n, w in weights.items()}
  values = {n: np.array([f(r) for r in rows]) for n, f in fns.items()}
  for i, r in enumerate(rows): r['_idx'] = i
  functions = {n: (lambda r, v=v: float(v[r['_idx']])) for n, v in values.items()}
  clear_utility_batches()
  scenarios = scenarios_for(rows, functions, RUNS, 10., SEED)
  out = {n: evaluate_batch(scenarios, n, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA) for n in functions}
  ref = out[BENCHMARK_NAME]; target = float(ref.utility.mean()); matched = .04 * ref.retirement_wealth
  res = {}
  for n in functions:
    res[n] = {'ruin_probability': float(out[n].ruined.mean()),
              'equivalent_savings_rate': equivalent_savings_rate(scenarios, n, target, GAMMA, WITHDRAWAL_RATE),
              'matched_failure': float(common_evaluate(scenarios, n, matched, True)['shortfall_probability_all_paths']),
              'annual_volatility': float(values[n].std(ddof=1))}
  return res


def main():
  revision = json.loads(REVISION.read_text())
  published = {r['strategy']: r for r in revision['results']}
  weights = {BENCHMARK_NAME: [1., 0, 0, 0]}
  for name in ('Proportional equal volatility', 'Risk parity equal volatility', 'Stocks and MF equal volatility'):
    weights[name] = published[name]['weights']
  cpi = read_cpi()
  base_trend, _ = annual_series('mf_1_6_12', cpi)
  canonical = {int(r['year']): float(r['trend_real'])
               for r in csv.DictReader(open(DATA / 'managed-futures-annual-real.csv'))}
  gap = max(abs(base_trend[y] - canonical[y]) for y in canonical)
  assert gap < 1e-9, f'baseline trend series differs from the canonical one by {gap}'
  results = []
  for key, label, prefix, fee in VARIANTS:
    trend, cash = annual_series(prefix, cpi)
    common = sorted(set(trend) & set(base_trend))
    corr = float(np.corrcoef([trend[y] for y in common], [base_trend[y] for y in common])[0, 1])
    res = evaluate(panel_for(trend, cash), fee, weights)
    if key == '1_6_12':
      for n in weights:
        for k in ('ruin_probability', 'equivalent_savings_rate'):
          np.testing.assert_allclose(res[n][k], published[n][k], rtol=0, atol=1e-7)
    results.append({'key': key, 'label': label, 'fee': fee, 'corr_with_baseline': corr, 'results': res})
    print(label, f'corr={corr:.2f}', {n: {k: round(v, 4) for k, v in r.items()} for n, r in res.items()}, flush=True)
  OUT.write_text(json.dumps({'runs': RUNS, 'seed': SEED, 'spread': SPREAD, 'variants': results}, indent=2) + '\n')


if __name__ == '__main__':
  main()
