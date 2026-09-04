#!/usr/bin/env python3
"""Describe concentration of pooled variance; exclusions are diagnostics only."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from compare_fixed_stacked_utility import read_panel, return_functions

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='results/main_ladders_n10000.json')
    parser.add_argument('--panel', default='data/replication-panel-trend.csv')
    parser.add_argument('--output', default='results/method_review/variance_concentration.json')
    args = parser.parse_args()
    panel = ROOT / args.panel
    baseline = ROOT / args.baseline
    metadata = json.loads(baseline.read_text())
    rows = read_panel(str(panel))
    if len(rows) != metadata['observations']:
        raise ValueError('This diagnostic requires the full baseline panel')
    functions = return_functions(rows, metadata['spread'], metadata['trend_fee'],
        metadata['trend_cost'], metadata['trend_haircut'], metadata['fx_hedge_cost'],
        hedge_mode=metadata['hedge_mode'])
    output = {'definition': 'Shares of sum of squared deviations from full-sample mean; deletion diagnostics are not proposed sample screens.',
        'panel_sha256': hashlib.sha256(panel.read_bytes()).hexdigest(),
        'baseline_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
        'observations': len(rows), 'portfolios': []}
    for result in metadata['results']:
        name = result['strategy']
        values = [functions[name](row) for row in rows]
        mean = statistics.mean(values)
        squares = [(value-mean)**2 for value in values]
        total = sum(squares)
        ordered = sorted(range(len(rows)), key=lambda i: squares[i], reverse=True)
        volatility = statistics.stdev(values)
        if abs(volatility-result['volatility']) > 1e-10:
            raise ValueError(f'Baseline mismatch: {name}')
        output['portfolios'].append({'strategy': name, 'volatility': volatility,
            'largest_contributors': [{'country': rows[i]['country'], 'year': rows[i]['year'],
                'return': values[i], 'variance_share': squares[i]/total} for i in ordered[:10]],
            'deletion_diagnostics': [{'count': k, 'variance_share': sum(squares[i] for i in ordered[:k])/total,
                'remaining_volatility': statistics.stdev(values[i] for i in range(len(rows)) if i not in set(ordered[:k]))}
                for k in (1, 5, 10)]})
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2)+'\n')
    print(target)


if __name__ == '__main__':
    main()
