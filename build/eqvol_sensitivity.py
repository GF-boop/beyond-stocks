"""Table VI at equal volatility (revision of September 22, 2026).

The diversified strategies are held at the gross exposures that match the
full-sample volatility of unlevered ACO (``revision_checks.py``), and every
sensitivity case of ``erc_refocusing.py`` is rerun at those fixed exposures:
post-1970 sample, Italy 1942 exclusion, borrowing spreads of 1-3%, and
managed-futures haircuts of 2%, 3%, and 6%. Same seed and engine as the frozen run.

Usage: python3 build/eqvol_sensitivity.py CASE [CASE ...]
"""
from pathlib import Path
import json
import sys
import numpy as np

from erc_refocusing import PANEL, SEED, calibration, source_exclusion_rows
from sleeve_ablation import function_for
from compare_fixed_stacked_utility import BENCHMARK_NAME
from compare_gold_trend_equal_vol import DEFAULT_TREND_FEE, DEFAULT_TREND_COST
from compare_lifecycle_utility import (
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, evaluate_batch,
    equivalent_savings_rate, clear_utility_batches)
from common_consumption_target import evaluate as common_evaluate
from historical_uncertainty import scenarios_for
from replicate_extended import read_panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/equal_volatility/sensitivity'
REVISION = ROOT / 'results/equal_volatility/revision_checks.json'
SOURCE = ROOT / 'results/robustness/source_exclusions/source_event_italy_1942/replication-panel-trend.csv'
RUNS = 10000

CASES = {
    'baseline': dict(), 'post1970': dict(year_from=1970), 'source_italy1942': dict(source=True),
    'spread_100bp': dict(spread=.01), 'spread_200bp': dict(spread=.02), 'spread_300bp': dict(spread=.03),
    'mf_minus_200bp': dict(haircut=.02), 'mf_minus_300bp': dict(haircut=.03), 'mf_minus_600bp': dict(haircut=.06),
}


def portfolio(w, spread, haircut):
  fn = function_for(tuple(w), spread, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, .001)
  return lambda r: fn(r) - w[3] * haircut


def strategies():
  revision = json.loads(REVISION.read_text())
  g = revision['equal_volatility_exposures']
  rows = read_panel(str(PANEL))
  erc = np.array(calibration(rows)['weights'])
  prop = np.array([.4, 4/15, 1/6, 1/6])
  stocks_mf = np.array([.4, 0, 0, 1/6]); stocks_mf /= stocks_mf.sum()
  return {BENCHMARK_NAME: np.array([1., 0, 0, 0]),
          'Proportional equal volatility': prop * g['Proportional'],
          'Risk parity equal volatility': erc * g['Risk parity'],
          'Stocks and MF equal volatility': stocks_mf * g['Stocks and MF']}


def run(case):
  opts = CASES[case]
  rows = source_exclusion_rows(SOURCE) if opts.get('source') else read_panel(str(PANEL))
  if 'year_from' in opts:
    rows = [r for r in rows if r['year'] >= opts['year_from']]
  spread, haircut = opts.get('spread', .003), opts.get('haircut', 0.)
  strat = strategies()
  values = {n: np.array([portfolio(w, spread, haircut)(r) for r in rows]) for n, w in strat.items()}
  for i, r in enumerate(rows): r['_idx'] = i
  functions = {n: (lambda r, v=v: float(v[r['_idx']])) for n, v in values.items()}
  clear_utility_batches()
  scenarios = scenarios_for(rows, functions, RUNS, 10., SEED)
  outcomes = {n: evaluate_batch(scenarios, n, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA) for n in functions}
  reference = outcomes[BENCHMARK_NAME]
  target = float(reference.utility.mean())
  matched = .04 * reference.retirement_wealth
  results = []
  for n, w in strat.items():
    s_eq = equivalent_savings_rate(scenarios, n, target, GAMMA, WITHDRAWAL_RATE)
    at_eq = (common_evaluate(scenarios, n, matched * BASE_SAVINGS_RATE / s_eq, True)
             ['shortfall_probability_all_paths'] if np.isfinite(s_eq) and s_eq > 0 else None)
    results.append({'strategy': n, 'weights': w.tolist(), 'gross': float(w.sum()),
                    'annual_volatility': float(values[n].std(ddof=1)),
                    'ruin_probability': float(outcomes[n].ruined.mean()),
                    'equivalent_savings_rate': s_eq,
                    'matched_failure': float(common_evaluate(scenarios, n, matched, True)
                                             ['shortfall_probability_all_paths']),
                    'matched_failure_at_equivalent_saving': at_eq})
    print(case, n, {k: v for k, v in results[-1].items() if k not in ('weights',)}, flush=True)
  OUT.mkdir(parents=True, exist_ok=True)
  (OUT / f'{case}.json').write_text(json.dumps(
      {'case': case, 'runs': RUNS, 'seed': SEED, 'observations': len(rows), 'spread': spread,
       'mf_haircut': haircut, 'results': results}, indent=2) + '\n')


if __name__ == '__main__':
  for case in sys.argv[1:] or CASES:
    run(case)
