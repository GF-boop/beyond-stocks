"""Time-indexed sector availability, frozen inputs and paired lifecycle paths.

The upstream engine is read-only. Its signal/volatility functions are reused;
the no-mask reconstruction must reproduce the canonical monthly snapshot.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from compare_fixed_stacked_utility import BENCHMARK_NAME, return_functions
from compare_lifecycle_utility import (
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, build_scenario, draw_death_age,
    equivalent_savings_rate, evaluate_batch, expected_utility,
)
from income_process import draw_household_income
from mortality import table as mortality_table
from panel_managed_futures import fill_isolated_gaps, previous_month, read_cpi
from panel_replication_tendance import fixed_notional_hedged_real_return
from replicate_extended import MAX_AGE, START_AGE, block_bootstrap, read_panel
from sleeve_ablation import function_for, reallocate
from trend_costs import TREND_COST, TREND_FEE

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'results/historical_availability'
ENGINE = ROOT / 'build/managed_futures/run_managed_futures.py'
STARTS = {'commodity': '0000-01', 'currency': '1972-06',
          'bond': '1977-09', 'equity': '1982-05'}
LEVELS = (100, 125, 150, 175, 200)
MODES = ('Baseline', 'Gold restriction', 'MF restriction', 'Joint restriction')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eligible(asset, sector, month, gold, sectors):
    return ((not gold or asset != 'METAL_GOLD' or month >= '1975-01')
            and (not sectors or month >= STARTS[sector]))


def raw_strategy(engine, months, markets, gold=False, sectors=False):
    """Same lagged signal and inverse-vol rule, with a position-entry gate.

    Pre-entry source price history can inform signals, but unavailable
    positions cannot enter sector or aggregate realized-return histories.
    A single commodity sector is explicitly permitted in this experiment.
    """
    raw, weights, history, audit = {}, {}, {}, []
    for index, month in enumerate(months):
        past = engine.previous_calendar_months(months, index, engine.VOL_WINDOW)
        if len(past) != engine.VOL_WINDOW:
            continue
        candidates = defaultdict(list)
        for asset, market in markets.items():
            if not eligible(asset, market.sector, month, gold, sectors):
                continue
            if month not in market.returns:
                continue
            skip = 0 if market.signal_skip_months == 0 else 1
            signal_past = engine.previous_calendar_months(months, index-skip, engine.VOL_WINDOW)
            if len(signal_past) != engine.VOL_WINDOW:
                continue
            vol = engine.lagged_volatility(market.returns, past)
            if vol is None:
                continue
            signals = [engine.momentum_signal(market.returns, signal_past, h)
                       for h in (1, 6, 12)]
            if any(s is None for s in signals):
                continue
            exposure = statistics.fmean(signals) * min(engine.ASSET_VOL_TARGET/vol,
                                                       engine.MAX_ASSET_LEVERAGE)
            candidates[market.sector].append((asset, exposure, exposure*market.returns[month]))
        if len(candidates) < (1 if gold or sectors else engine.MIN_ACTIVE_SECTORS):
            continue
        returns = {s: statistics.fmean(x[2] for x in members)
                   for s, members in candidates.items()}
        allocation = engine.sector_allocation(returns, history, past, 'inverse_vol')
        weights[month] = {asset: exposure*allocation[s]/len(members)
                          for s, members in candidates.items() for asset, exposure, _ in members}
        raw[month] = sum(allocation[s]*r for s, r in returns.items())
        history[month] = returns
        audit.append({'month': month, **{s+'_count': len(candidates.get(s, [])) for s in STARTS},
                      **{s+'_weight': allocation.get(s, 0.0) for s in STARTS},
                      'gold_count': int('METAL_GOLD' in weights[month])})
    return raw, weights, audit


def write_csv(path, records):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def prepare():
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('availability_mf_engine', ENGINE)
    engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = engine
    spec.loader.exec_module(engine)
    months, markets = engine.load_markets(engine.DEFAULT_INPUT)
    markets = engine.normalize_local_pnl_to_usd(
        markets, engine.load_fx_spot_returns(engine.DEFAULT_FX_SPOT), True)
    months = sorted({m for market in markets.values() for m in market.returns})
    markets = engine.select_universe(markets, 'all_four_sectors')
    cash = engine.load_usd_collateral(engine.DEFAULT_COLLATERAL)
    cpi, patched = fill_isolated_gaps(read_cpi(str(ROOT/'data/cpi-monthly.csv')))
    canonical = {r['month']: r for r in csv.DictReader((ROOT/'data/managed-futures-monthly.csv').open())
                 if r['mf_1_6_12_gross_return']}
    annual_records, monthly_records, checks, costs = [], [], {}, {}
    for mode, gold, sectors in [('Baseline', False, False),
                                ('Gold restriction', True, False),
                                ('MF restriction', False, True),
                                ('Joint restriction', True, True)]:
        raw, weights, audit = raw_strategy(engine, months, markets, gold, sectors)
        targeted = engine.target_and_cost(months, raw, weights, cash, True, TREND_FEE, 3.0)
        if mode == 'Baseline':
            assert set(canonical) == set(targeted)
            for field in ('gross_return', 'turnover', 'portfolio_vol_scalar'):
                error = max(abs(targeted[m][field]-float(r['mf_1_6_12_'+field]))
                            for m,r in canonical.items())
                assert error < 1e-8, (field, error)
                checks[field+'_max_absolute_error'] = error
        costs[mode] = statistics.fmean(v['turnover'] for v in targeted.values())*12*3e-4
        if mode == 'Baseline':
            assert abs(costs[mode]-TREND_COST) < 1e-10
        grouped = defaultdict(list)
        for m, v in targeted.items():
            if m not in cpi or previous_month(m) not in cpi:
                continue
            d = cpi[m]/cpi[previous_month(m)]
            grouped[int(m[:4])].append(((1+v['gross_return'])/d,
                                        (1+v['cash_collateral_return'])/d))
            monthly_records.append({'mode': mode, 'month': m, **v})
        for year in range(1927, 2026):
            values = grouped.get(year, [])
            complete = len(values) == 12
            annual_records.append({'mode': mode, 'year': year,
                'available_months':len(values), 'available':int(complete),
                'trend_real': math.prod(v[0] for v in values)-1 if complete else '',
                'cash_real': math.prod(v[1] for v in values)-1 if complete else ''})
        assert sum(r['mode'] == mode for r in annual_records) == 99
        for r in audit:
            assert not (gold and r['month'] < '1975-01' and r['gold_count'])
            for sector, start in STARTS.items():
                assert not (sectors and r['month'] < start and r[sector+'_count'])
            assert abs(sum(r[s+'_weight'] for s in STARTS)-1) < 1e-12
        write_csv(OUT/(mode.lower().replace(' ', '-')+'-positions-summary.csv'), audit)
        print(f'{mode}: {len(targeted)} months; annual turnover cost {costs[mode]:.4%}', flush=True)
    write_csv(OUT/'monthly.csv', monthly_records)
    write_csv(OUT/'annual.csv', annual_records)
    inputs = [ENGINE, engine.DEFAULT_INPUT, engine.DEFAULT_FX_SPOT, engine.DEFAULT_COLLATERAL,
              ROOT/'data/cpi-monthly.csv', ROOT/'data/managed-futures-monthly.csv',
              ROOT/'data/replication-panel-trend.csv', ROOT/'data/replication-panel.csv',
              Path(__file__)]
    metadata = {'inputs_sha256': {str(p.relative_to(ROOT.parent)): digest(p) for p in inputs},
                'sector_entry_months': STARTS, 'gold_entry_month': '1975-01',
                'checks': checks, 'turnover_costs': costs, 'cpi_patched': patched,
                'incomplete_years': {mode:[r['year'] for r in annual_records
                                           if r['mode']==mode and not r['available']]
                                     for mode in MODES},
                'prepare_seconds': time.monotonic()-started,
                'scope': 'Sector-level U.S. launch milestones; not contract-by-contract or country-specific investability. Pre-entry price histories may inform lagged signals. One active commodity sector allowed. Contemporary costs and no personal taxes.'}
    (OUT/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(f'Prepared in {metadata["prepare_seconds"]:.1f}s', flush=True)


def run(runs, allow_incomplete=False):
    started = time.monotonic()
    manifest = json.loads((OUT/'manifest.json').read_text())
    if any(manifest['incomplete_years'].values()) and not allow_incomplete:
        raise ValueError('Incomplete MF years: confirm pro-rata reallocation before running.')
    # Refuse stale inputs, including the research script itself.
    for path, sha in manifest['inputs_sha256'].items():
        assert digest(ROOT.parent/path) == sha, path
    rows = read_panel(str(ROOT/'data/replication-panel-trend.csv'))
    assert len(rows) == 1561
    annual = {(r['mode'], int(r['year'])): r for r in csv.DictReader((OUT/'annual.csv').open())}
    original = {(r['country'], int(r['year'])): r for r in csv.DictReader((ROOT/'data/replication-panel.csv').open())}
    for i, r in enumerate(rows):
        r['_idx'] = i
        y, c = r['year'], r['country']
        prev = original[(c, y-1)]
        us = original[('USA', y)]
        for mode in MODES:
            v = annual[mode,y]
            r['mf_available_'+mode] = bool(int(v['available']))
            r['mf_'+mode] = fixed_notional_hedged_real_return(
                float(v['trend_real']), float(v['cash_real']), r['bill'],
                float(us['inflation']), r['inflation'], 1., 1., r['xrusd'], float(prev['xrusd'])) if r['mf_available_'+mode] else 0.
        assert abs(r['mf_Baseline']-r['trend_fixed_notional']) < 1e-8
    canonical = return_functions(rows, .003, TREND_FEE, TREND_COST, 0., .001)
    functions = {n: f for n,f in canonical.items()
                 if n == BENCHMARK_NAME or (n.startswith('ACO 33/67 ') and n.endswith('%'))}
    definitions = {}
    for family, base in [('Proportional', (.4, .4/1.5, .25/1.5, .25/1.5)),
                          ('Equal-weight', (.25, .25, .25, .25))]:
        for g in LEVELS:
            w = tuple(x*g/100 for x in base)
            for mode in MODES:
                name = f'{family} {g}% | {mode}'
                cost = manifest['turnover_costs'][mode]
                values = []
                for row in rows:
                    effective = reallocate(w, 2) if mode in ('Gold restriction','Joint restriction') and row['year'] < 1975 else w
                    if not row['mf_available_'+mode]:
                        effective = reallocate(effective, 3)
                    assert abs(sum(effective)-g/100) < 1e-12
                    altered = dict(row, trend_fixed_notional=row['mf_'+mode])
                    values.append(function_for(effective, .003, TREND_FEE, cost, .001)(altered))
                functions[name] = lambda row, v=values: v[row['_idx']]
                definitions[name] = {'family':family, 'gross_percent':g, 'mode':mode,
                                      'post1974_weights':w, 'trend_cost':cost}
    rng = random.Random(20260827)
    female, male = mortality_table('female','ssa'), mortality_table('male','ssa')
    scenarios = []
    for i in range(runs):
        path = block_bootstrap(rows, MAX_AGE-START_AGE+1, rng, 10., 'aco')
        fd, md = draw_death_age(female,rng), draw_death_age(male,rng)
        fi, mi, _ = draw_household_income(rng)
        scenarios.append(build_scenario(path, functions, fd, md, fi, mi))
        if (i+1) % 1000 == 0:
            print(f'Paths {i+1}/{runs}: {time.monotonic()-started:.1f}s', flush=True)
    target = expected_utility(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
    outcomes = {n: evaluate_batch(scenarios,n,BASE_SAVINGS_RATE,WITHDRAWAL_RATE,GAMMA)
                for n in functions}
    results = []
    for name, fn in functions.items():
        outcome = outcomes[name]
        difference = outcome.ruined.astype(float)-outcomes[BENCHMARK_NAME].ruined.astype(float)
        se = statistics.stdev(difference)/math.sqrt(runs)
        result = {'strategy':name, **definitions.get(name, {}),
                  'annual_volatility':statistics.stdev(fn(r) for r in rows),
                  'mean_return':statistics.fmean(fn(r) for r in rows),
                  'ruin_probability':float(np.mean(outcome.ruined)),
                  'equivalent_savings_rate':equivalent_savings_rate(scenarios,name,target,GAMMA,WITHDRAWAL_RATE),
                  'ruin_difference_vs_aco':float(np.mean(difference)),
                  'ruin_difference_ci95':[float(np.mean(difference)-1.96*se),float(np.mean(difference)+1.96*se)]}
        if name in definitions:
            baseline_name = name.split(' | ')[0]+' | Baseline'
            diff = outcome.ruined.astype(float)-outcomes[baseline_name].ruined.astype(float)
            se = statistics.stdev(diff)/math.sqrt(runs)
            result['ruin_difference_vs_same_baseline'] = float(np.mean(diff))
            result['same_baseline_ci95'] = [float(np.mean(diff)-1.96*se),float(np.mean(diff)+1.96*se)]
        results.append(result)
        print(f'{name}: ruin {result["ruin_probability"]:.2%}, saving {result["equivalent_savings_rate"]:.2%}', flush=True)
    archive = ROOT/'results/sleeve_ablation_ladders_n10000.json'
    if runs == 10000 and archive.exists():
        archived = {r['strategy']:r for r in json.loads(archive.read_text())['results']}
        for r in results:
            if r.get('mode') == 'Baseline':
                other = archived[f'{r["family"]} four-sleeve, {r["gross_percent"]}%']
            elif r['strategy'] in archived:
                other = archived[r['strategy']]
            else:
                continue
            for key in ('ruin_probability', 'equivalent_savings_rate', 'annual_volatility'):
                assert abs(r[key]-other[key]) < 1e-7, (r['strategy'],key,r[key],other[key])
    payload = {'runs':runs, 'seed':20260827, 'observations':len(rows), 'period':'1927–2025',
               'mean_block_years':10, 'spread':.003, 'hedge_cost':.001, 'trend_fee':TREND_FEE,
               'gamma':GAMMA, 'withdrawal_rate':WITHDRAWAL_RATE, 'results':results,
               'manifest_sha256':digest(OUT/'manifest.json'), 'annual_sha256':digest(OUT/'annual.csv'),
               'incomplete_mf_year_rule':'Zero MF weight and pro-rata annual reallocation; calendar data-coverage screen, not an ex-ante trading rule.' if allow_incomplete else 'None',
               'elapsed_seconds':time.monotonic()-started}
    (OUT/f'results_n{runs}.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(f'Finished {runs} paths in {payload["elapsed_seconds"]:.1f}s', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--runs', type=int)
    parser.add_argument('--allow-incomplete-mf-reallocation', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.runs:
        if args.runs < 2:
            parser.error('At least two paths required')
        run(args.runs, args.allow_incomplete_mf_reallocation)
