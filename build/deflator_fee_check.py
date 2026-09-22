"""Impact of two data-construction corrections (revision of September 22, 2026).

1. Deflator consistency. Gold and the managed-futures proxy are deflated by the
   US December-to-December CPI, but ``panel_replication_tendance.build`` used
   the JST annual US inflation to turn them back into nominal dollars before
   converting to each resident's currency. The corrected panel re-nominalizes
   each series with its own deflator, so the nominal dollar return is exact.
2. Bond fee. The panel deducts a 0.10% fund fee from global bonds on top of the
   0.10% hedging cost charged in ``function_for``. The corrected case removes
   the fund fee, leaving the 0.10% hedging cost described in the paper.

For each panel, the risk parity weights and the equal-volatility exposures are
recalibrated as a full rerun would, and ACO 33/67, proportional, risk parity
and stocks-plus-MF are evaluated with the frozen seed. The unchanged panel must
reproduce ``revision_checks.json``.
"""
from pathlib import Path
import csv
import json
import numpy as np

from erc_refocusing import SEED, PROP, calibration
from revision_checks import exposure_for_volatility, volatility, portfolio
from compare_fixed_stacked_utility import BENCHMARK_NAME
from compare_lifecycle_utility import (
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, evaluate_batch,
    equivalent_savings_rate, clear_utility_batches)
from common_consumption_target import evaluate as common_evaluate
from historical_uncertainty import scenarios_for
from replicate_extended import read_panel
from mf_variant_lifecycle import read_cpi
import panel_replication_tendance as prt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUT = ROOT / 'results/audit/deflator_fee_check.json'
REVISION = ROOT / 'results/equal_volatility/revision_checks.json'
RUNS = 10000
GOLD_CUSTODY = .004


def source_inflation():
  cpi = read_cpi()
  trend = {y: cpi[f'{y}-12'] / cpi[f'{y - 1}-12'] - 1
           for y in range(1900, 2030) if f'{y}-12' in cpi and f'{y - 1}-12' in cpi}
  gold = {int(r['year']): (1 + float(r['gold_nominal'])) * (1 - GOLD_CUSTODY)
          / (1 + float(r['gold_real'])) - 1
          for r in csv.DictReader(open(DATA / 'gold-annual.csv'))}
  return {'gold': gold, 'trend': trend}


def build_rows(inflation):
  panel = prt.read_rows(str(DATA / 'replication-panel.csv'))
  world = {int(r['year']): r for r in prt.read_rows(str(DATA / 'jst-ntsg-panel-2025.csv'))}
  mf = prt.read_rows(str(DATA / 'managed-futures-annual-real.csv'))
  trend = {int(r['year']): float(r['trend_real']) for r in mf}
  cash = {int(r['year']): float(r['cash_real']) for r in mf}
  gold = {int(r['year']): float(r['gold_real']) for r in prt.read_rows(str(DATA / 'gold-annual.csv'))}
  built = prt.build(panel, world, trend, cash, gold, source_inflation=inflation)
  tmp = OUT.with_suffix('.tmp.csv')
  with open(tmp, 'w', newline='') as h:
    w = csv.DictWriter(h, fieldnames=list(built[0].keys())); w.writeheader(); w.writerows(built)
  rows = read_panel(str(tmp)); tmp.unlink()
  return rows


def without_bond_fee(rows):
  for r in rows:
    r['world_bond_fixed_notional'] = (1 + r['world_bond_fixed_notional']) / (1 - prt.BOND_FEE) - 1
  return rows


def evaluate(rows):
  erc = np.array(calibration(rows)['weights'])
  stocks_mf = np.array([.4, 0, 0, 1/6]); stocks_mf /= stocks_mf.sum()
  aco_vol = volatility(np.array([1., 0, 0, 0]), rows)
  strategies = {BENCHMARK_NAME: np.array([1., 0, 0, 0])}
  for name, base in (('Proportional', PROP), ('Risk parity', erc), ('Stocks and MF', stocks_mf)):
    strategies[f'{name} equal volatility'] = base * exposure_for_volatility(base, aco_vol, rows)
  values = {n: np.array([portfolio(w)(r) for r in rows]) for n, w in strategies.items()}
  for i, r in enumerate(rows): r['_idx'] = i
  functions = {n: (lambda r, v=v: float(v[r['_idx']])) for n, v in values.items()}
  clear_utility_batches()
  scenarios = scenarios_for(rows, functions, RUNS, 10., SEED)
  outcomes = {n: evaluate_batch(scenarios, n, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA) for n in functions}
  ref = outcomes[BENCHMARK_NAME]
  target = float(ref.utility.mean())
  matched = .04 * ref.retirement_wealth
  res = {}
  for n, w in strategies.items():
    s_eq = equivalent_savings_rate(scenarios, n, target, GAMMA, WITHDRAWAL_RATE)
    res[n] = {'weights': w.tolist(), 'gross': float(w.sum()),
              'annual_volatility': float(values[n].std(ddof=1)),
              'mean_return': float(values[n].mean()),
              'ruin_probability': float(outcomes[n].ruined.mean()),
              'equivalent_savings_rate': s_eq,
              'matched_failure': float(common_evaluate(scenarios, n, matched, True)
                                       ['shortfall_probability_all_paths']),
              'matched_failure_at_equivalent_saving': float(common_evaluate(
                  scenarios, n, matched * BASE_SAVINGS_RATE / s_eq, True)['shortfall_probability_all_paths'])}
    print(n, {k: round(v, 4) for k, v in res[n].items() if k != 'weights'}, flush=True)
  return res


def main():
  published = {r['strategy']: r for r in json.loads(REVISION.read_text())['results']}
  out = {'runs': RUNS, 'seed': SEED, 'cases': {}}
  inflation = source_inflation()
  for case, rows in (('published', read_panel(str(DATA / 'replication-panel-trend.csv'))),
                     ('rebuilt_unchanged', build_rows(None)),
                     ('deflator_fixed', build_rows(inflation)),
                     ('deflator_fixed_no_bond_fee', without_bond_fee(build_rows(inflation)))):
    print('==', case, len(rows), flush=True)
    if case == 'rebuilt_unchanged':
      ref = read_panel(str(DATA / 'replication-panel-trend.csv'))
      gap = max(abs(a[k] - b[k]) for a, b in zip(ref, rows) for k in ('gold', 'trend_fixed_notional', 'world_bond_fixed_notional'))
      assert len(ref) == len(rows) and gap < 1e-12, gap
      continue
    out['cases'][case] = evaluate(rows)
    if case == 'published':
      for n, r in out['cases'][case].items():
        np.testing.assert_allclose(r['equivalent_savings_rate'], published[n]['equivalent_savings_rate'], atol=1e-7)
  OUT.write_text(json.dumps(out, indent=2) + '\n')


if __name__ == '__main__':
  main()
