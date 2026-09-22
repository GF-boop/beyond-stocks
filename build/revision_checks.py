"""Targeted checks for the September 22, 2026 revision.

Reuses the frozen engine, panel and seed of ``erc_refocusing.py`` so that every
new strategy is paired with the published baseline:

* excess-return Sharpe ratios of the four sleeves (full and post-1970 panels);
* simpler diversified strategies (stocks + gold + MF, stocks + MF) at 175%;
* all diversified strategies levered to the volatility of unlevered ACO;
* the median dollar value of the common income, and the failure to fund it
  when each strategy saves its own equivalent savings rate;
* optionally (argument: annual haircut), the same strategies with a
  managed-futures haircut, exposures held at their no-haircut values;
* the proxy versus commercial trend indexes, when the licensed files exist.

The baseline ACO and proportional outcomes are checked against
``results/erc_refocusing/n10000_final/baseline.json`` before anything is written.
"""
from pathlib import Path
import json
import numpy as np

from erc_refocusing import (PANEL, PROP, SEED, erc_weights, calibration,
                            interval)
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
OUT = ROOT / 'results/revision_2026-09-22'
BASELINE = ROOT / 'results/erc_refocusing/n10000_final/baseline.json'
RUNS = 10000
SPREAD = .003


def portfolio(w, haircut=0.):
  fn = function_for(tuple(w), SPREAD, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, .001)
  return lambda r: fn(r) - w[3] * haircut


def benchmark_comparison():
  """Proxy versus commercial indexes, 2000-2025 (derived statistics only)."""
  import csv, math
  src = ROOT / 'data/benchmarks-externes/official-index-returns-monthly.csv'
  if not src.exists(): return None
  mf = {r['month']: r for r in csv.DictReader(open(ROOT / 'data/managed-futures-monthly.csv'))}
  rows = list(csv.DictReader(open(src)))
  out = {}
  for w0, w1 in (('2000-01', '2025-12'), ('2000-01', '2009-12'), ('2010-01', '2025-12')):
    sel = [r for r in rows if w0 <= r['month'] <= w1]
    cash = np.array([float(mf[r['month']]['mf_1_6_12_cash_collateral_return']) for r in sel])
    series = {'proxy': np.array([float(mf[r['month']]['mf_1_6_12_net_return']) for r in sel])}
    for c in ('sg_cta', 'sg_trend', 'btop50'):
      series[c] = np.array([float(r[c]) for r in sel])
    out[f'{w0}_{w1}'] = {k: {'geometric_mean': float(np.prod(1 + x) ** (12 / len(x)) - 1),
                             'volatility': float(x.std(ddof=1) * math.sqrt(12)),
                             'sharpe': float((x - cash).mean() / (x - cash).std(ddof=1) * math.sqrt(12))}
                         for k, x in series.items()}
  return out


def sleeve_properties(rows):
  out = {}
  for i, name in enumerate(('stocks', 'bonds', 'gold', 'mf')):
    fn = portfolio(np.eye(4)[i])
    excess = np.array([fn(r) - r['world_bill'] for r in rows])
    out[name] = {'mean_excess': float(excess.mean()),
                 'sd_excess': float(excess.std(ddof=1)),
                 'sharpe': float(excess.mean() / excess.std(ddof=1))}
  return out


def volatility(w, rows):
  fn = portfolio(w)
  return float(np.std([fn(r) for r in rows], ddof=1))


def exposure_for_volatility(base, target, rows):
  lo, hi = 1., 4.
  for _ in range(60):
    mid = (lo + hi) / 2
    if volatility(base * mid, rows) < target: lo = mid
    else: hi = mid
  return (lo + hi) / 2


def main():
  import sys
  haircut = float(sys.argv[1]) if len(sys.argv) > 1 else 0.
  OUT.mkdir(parents=True, exist_ok=True)
  rows = read_panel(str(PANEL)); assert len(rows) == 1561
  later = [r for r in rows if r['year'] >= 1970]
  sleeves = {'full': sleeve_properties(rows), 'post1970': sleeve_properties(later)}

  erc = np.array(calibration(rows)['weights'])
  no_bonds = np.array([.4, 0, 1/6, 1/6]); no_bonds /= no_bonds.sum()
  stocks_mf = np.array([.4, 0, 0, 1/6]); stocks_mf /= stocks_mf.sum()
  families = {'Proportional': PROP, 'Risk parity': erc,
              'Stocks, gold, MF': no_bonds, 'Stocks and MF': stocks_mf}
  aco_vol = volatility(np.array([1., 0, 0, 0]), rows)

  strategies = {BENCHMARK_NAME: np.array([1., 0, 0, 0]),
                'ACO 175%': np.array([1.75, 0, 0, 0])}
  exposures = {}
  for name, base in families.items():
    strategies[f'{name} 175%'] = base * 1.75
    g = exposure_for_volatility(base, aco_vol, rows)
    exposures[name] = g
    strategies[f'{name} equal volatility'] = base * g

  values = {n: np.array([portfolio(w, haircut)(r) for r in rows]) for n, w in strategies.items()}
  for i, r in enumerate(rows): r['_idx'] = i
  functions = {n: (lambda r, v=v: float(v[r['_idx']])) for n, v in values.items()}
  clear_utility_batches()
  scenarios = scenarios_for(rows, functions, RUNS, 10., SEED)
  outcomes = {n: evaluate_batch(scenarios, n, BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA)
              for n in functions}
  reference = outcomes[BENCHMARK_NAME]
  target = float(reference.utility.mean())
  common_target = .04 * reference.retirement_wealth
  common = {n: common_evaluate(scenarios, n, common_target, True) for n in functions}

  results = []
  for n, w in strategies.items():
    o, c = outcomes[n], common[n]
    results.append({
        'strategy': n, 'weights': w.tolist(), 'gross': float(w.sum()),
        'annual_volatility': float(values[n].std(ddof=1)),
        'ruin_probability': float(o.ruined.mean()),
        'equivalent_savings_rate': equivalent_savings_rate(scenarios, n, target, GAMMA, WITHDRAWAL_RATE),
        'common_failure': float(c['shortfall_probability_all_paths']),
        # Wealth is proportional to the savings rate, so saving s against the
        # 10% target equals saving 10% against the target scaled by 0.10/s.
        'common_failure_at_equivalent_saving': None,
        'paired_ruin_vs_aco': interval(o.ruined, reference.ruined),
        'paired_common_vs_aco': interval(c['events'], common[BENCHMARK_NAME]['events'])})
    print(n, f"G={w.sum():.3f} vol={results[-1]['annual_volatility']:.2%} "
          f"ruin={results[-1]['ruin_probability']:.2%} "
          f"saving={results[-1]['equivalent_savings_rate']:.2%} "
          f"common={results[-1]['common_failure']:.2%}", flush=True)

  for r in results:
    s_eq = r['equivalent_savings_rate']
    if np.isfinite(s_eq) and s_eq > 0:
      c = common_evaluate(scenarios, r['strategy'], common_target * BASE_SAVINGS_RATE / s_eq, True)
      r['common_failure_at_equivalent_saving'] = float(c['shortfall_probability_all_paths'])
      # Where do these failures occur? Share with an all-equity retirement
      # wealth above its median, i.e. a larger-than-median income to fund.
      events = np.asarray(c['events'], dtype=bool)
      high = reference.retirement_wealth > np.median(reference.retirement_wealth[reference.retirement_wealth > 0])
      r['failures_above_median_income_share'] = float(high[events].mean()) if events.any() else None

  # The new runs must reproduce the published baseline exactly.
  baseline_file = BASELINE if haircut == 0 else BASELINE.with_name(f'mf_minus_{round(haircut*1e4)}bp.json')
  published = {r['strategy']: r for r in json.loads(baseline_file.read_text())['results']}
  pairs = [('Proportional 175%', 'Proportional 175%'), ('Risk parity 175%', 'ERC 175%')]
  if haircut == 0: pairs += [(BENCHMARK_NAME, 'ACO 33/67'), ('ACO 175%', 'ACO 175%')]
  for mine, theirs in pairs:
    got = next(r for r in results if r['strategy'] == mine)
    for k in ('ruin_probability', 'equivalent_savings_rate'):
      np.testing.assert_allclose(got[k], published[theirs][k], rtol=0, atol=1e-7)

  retired = reference.retirement_wealth > 0
  income = {'median_retirement_wealth': float(np.median(reference.retirement_wealth[retired])),
            'median_common_income': float(np.median(common_target[retired]))}
  out = {'mf_haircut': haircut, 'benchmarks': benchmark_comparison() if haircut == 0 else None,
         'runs': RUNS, 'seed': SEED, 'spread': SPREAD, 'aco_volatility': aco_vol,
         'equal_volatility_exposures': exposures, 'sleeves': sleeves,
         'common_income_dollars': income, 'results': results}
  (OUT / ('revision_checks.json' if haircut == 0 else f'revision_checks_mf_minus_{round(haircut*1e4)}bp.json')).write_text(json.dumps(out, indent=2) + '\n')
  print(json.dumps({'exposures': exposures, 'sleeves': sleeves, 'income': income}, indent=2))


if __name__ == '__main__':
  main()
