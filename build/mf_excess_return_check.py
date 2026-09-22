"""Does the managed-futures proxy overstate futures returns? (revision of September 22, 2026)

The engine ``managed_futures/run_managed_futures.py`` feeds equity price
returns and commodity and precious-metal spot returns into the trend rule, then
adds the USD collateral yield to the whole NAV. A futures position does not
earn that: an equity future earns the price return plus dividends less the
local bill rate, and a commodity future earns the spot return less the cost of
carry. Long positions are therefore overstated by roughly (bill - yield) and
short positions understated by the same amount. Bond and currency legs are
already excess returns.

This script rebuilds the proxy with futures-consistent excess returns:

* equities: price return + JST dividend return / 12 - local bill (lagged cash
  of the snapshot; EUR bill from 1999), with FX applied to the P&L only;
* commodities and metals: spot return - USD bill (zero net convenience yield).

Dividend returns come from JST R6 (``eq_div_rtn``), carried forward after
2020. Everything else is the engine, unchanged. The rebuilt series are then
hedged into each resident's currency as in the panel and run through the
lifecycle model at the published equal-volatility exposures.
"""
from pathlib import Path
import csv
import json
import math
import statistics
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build' / 'managed_futures'))
import run_managed_futures as rmf
from mf_variant_lifecycle import read_cpi, panel_for, evaluate, REVISION
from compare_fixed_stacked_utility import BENCHMARK_NAME
from compare_gold_trend_equal_vol import DEFAULT_TREND_FEE

INPUTS = ROOT / 'data/mf-inputs'
OUT = ROOT / 'results/audit/mf_excess_return_check.json'


def dividends():
  jst = pd.read_stata(ROOT / 'data/JSTdatasetR6.dta')
  out = {}
  for iso, g in jst.groupby('iso'):
    g = g.sort_values('year')
    col = g['eq_div_rtn'].where(g['eq_div_rtn'].notna(), g['eq_dp'])
    series = {int(y): float(v) for y, v in zip(g['year'], col) if pd.notna(v)}
    if series:
      last = max(series)
      for y in range(last + 1, 2026): series[y] = series[last]
    out[iso] = series
  return out


def cash_table():
  return {r['month']: {k: float(v) for k, v in r.items() if k != 'month' and v}
          for r in csv.DictReader(open(INPUTS / 'cash-returns-monthly.csv'))}


def to_excess(markets, fix_equity, fix_commodity):
  div, cash = dividends(), cash_table()
  out = {}
  for asset, m in markets.items():
    if fix_equity and m.sector == 'equity':
      c = asset.removeprefix('EQ_')
      values = {}
      for month, p in m.returns.items():
        bills = cash.get(month, {})
        bill = bills.get(c, bills.get('EUR') if month >= '1999-01' else None)
        d = div.get(c, {}).get(int(month[:4]))
        if bill is None or d is None: continue
        values[month] = p + d / 12 - bill
      out[asset] = rmf.Market(asset, m.sector, values, m.signal_skip_months, 'synthetic_excess_return')
    elif fix_commodity and m.sector == 'commodity':
      values = {month: r - cash[month]['USA'] for month, r in m.returns.items()
                if 'USA' in cash.get(month, {})}
      out[asset] = rmf.Market(asset, m.sector, values, m.signal_skip_months, 'synthetic_excess_return')
    else:
      out[asset] = m
  return out


def run_engine(fix_equity, fix_commodity):
  months, markets = rmf.load_markets(rmf.DEFAULT_INPUT)
  markets = to_excess(markets, fix_equity, fix_commodity)
  markets = rmf.normalize_local_pnl_to_usd(markets, rmf.load_fx_spot_returns(rmf.DEFAULT_FX_SPOT), True)
  months = sorted({mo for m in markets.values() for mo in m.returns})
  markets = rmf.select_universe(markets, 'all_four_sectors')
  raw, weights, *_ = rmf.build_raw_variants(months, markets, 1, 'inverse_vol')
  collateral = rmf.load_usd_collateral(rmf.DEFAULT_COLLATERAL)
  return rmf.target_and_cost(months, raw['mf_1_6_12'], weights['mf_1_6_12'], collateral, True, .0085, 3.)


def annual_real(monthly, cpi):
  gross, cash = {}, {}
  for month, v in monthly.items():
    n = rmf.month_number(month) - 1
    prev = f'{n // 12:04d}-{n % 12 + 1:02d}'
    if month not in cpi or prev not in cpi: continue
    d = cpi[month] / cpi[prev]
    y = int(month[:4])
    gross.setdefault(y, []).append((1 + v['gross_return']) / d)
    cash.setdefault(y, []).append((1 + v['cash_collateral_return']) / d)
  keep = [y for y in gross if len(gross[y]) == 12]
  return ({y: float(np.prod(gross[y]) - 1) for y in keep}, {y: float(np.prod(cash[y]) - 1) for y in keep})


def stats(monthly, start='0000', end='9999'):
  sel = [v for m, v in sorted(monthly.items()) if start <= m <= end]
  ex = np.array([v['gross_return'] - v['cash_collateral_return'] for v in sel])
  net = np.array([v['net_return'] for v in sel])
  return {'months': len(sel), 'gross_excess_mean': float(ex.mean() * 12),
          'gross_excess_vol': float(ex.std(ddof=1) * math.sqrt(12)),
          'gross_sharpe': float(ex.mean() / ex.std(ddof=1) * math.sqrt(12)),
          'net_cagr': float(np.prod(1 + net) ** (12 / len(net)) - 1)}


def main():
  cpi = read_cpi()
  canonical = {int(r['year']): float(r['trend_real'])
               for r in csv.DictReader(open(ROOT / 'data/managed-futures-annual-real.csv'))}
  revision = json.loads(REVISION.read_text())
  published = {r['strategy']: r for r in revision['results']}
  weights = {BENCHMARK_NAME: [1., 0, 0, 0]}
  for n in ('Proportional equal volatility', 'Risk parity equal volatility', 'Stocks and MF equal volatility'):
    weights[n] = published[n]['weights']
  out = {}
  for key, fe, fc in (('engine', False, False), ('equity_excess', True, False),
                      ('commodity_excess', False, True), ('both_excess', True, True)):
    monthly = run_engine(fe, fc)
    trend, cash = annual_real(monthly, cpi)
    if key == 'engine':
      gap = max(abs(trend[y] - canonical[y]) for y in canonical)
      assert gap < 1e-9, gap
    periods = {p: stats(monthly, *b) for p, b in (('full', ('0000', '9999')), ('1927-1969', ('1927', '1969-12')),
                                                    ('1970-1999', ('1970', '1999-12')), ('2000-2025', ('2000', '9999')))}
    common = sorted(set(trend) & set(canonical))
    diff = np.array([trend[y] - canonical[y] for y in common])
    res = evaluate(panel_for(trend, cash), DEFAULT_TREND_FEE, weights)
    out[key] = {'periods': periods, 'annual_real_gross_mean': float(np.mean([trend[y] for y in common])),
                'mean_annual_difference_vs_canonical': float(diff.mean()),
                'corr_with_canonical': float(np.corrcoef([trend[y] for y in common], [canonical[y] for y in common])[0, 1]),
                'lifecycle': res}
    print(key, json.dumps({'periods': periods, 'diff': float(diff.mean())}), flush=True)
    for n, r in res.items(): print('  ', n, {k: round(v, 4) for k, v in r.items()}, flush=True)
  OUT.write_text(json.dumps(out, indent=2) + '\n')


if __name__ == '__main__':
  main()
