"""Descriptive properties of the four net sleeves; no simulation."""
from pathlib import Path
import numpy as np

from sleeve_ablation import function_for
from compare_gold_trend_equal_vol import DEFAULT_TREND_FEE, DEFAULT_TREND_COST
from replicate_extended import read_panel

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / 'data/replication-panel-trend.csv'
OUT = ROOT / 'paper/new_paper/figures/erc/sleeves.tex'
NAMES = (r'\shortstack{Stocks\\ (33/67)}', r'\shortstack{Global\\ bonds}', 'Gold', r'\shortstack{Managed\\ futures}')
HORIZON = 10


def sleeve_returns(rows):
    fns = [function_for(tuple(np.eye(4)[i]), .003, DEFAULT_TREND_FEE,
                        DEFAULT_TREND_COST, .001) for i in range(4)]
    return np.array([[f(r) for f in fns] for r in rows])


def long_horizon(rows, values):
    """Overlapping ten-year log returns within each country's consecutive years."""
    out, infl = [], []
    by_country = {}
    for i, r in enumerate(rows):
        by_country.setdefault(r['country'], []).append(i)
    for idx in by_country.values():
        idx = sorted(idx, key=lambda i: rows[i]['year'])
        for s in range(len(idx) - HORIZON + 1):
            block = idx[s:s + HORIZON]
            if rows[block[-1]]['year'] - rows[block[0]]['year'] != HORIZON - 1:
                continue
            out.append(np.log1p(values[block]).sum(axis=0))
            infl.append(np.log1p([rows[i]['inflation'] for i in block]).sum())
    return np.array(out), np.array(infl)


def panel(rows):
    v = sleeve_returns(rows)
    infl = np.array([r['inflation'] for r in rows])
    bill = np.array([r['world_bill'] for r in rows])
    lh, lh_infl = long_horizon(rows, v)
    worst = v[:, 0] <= np.quantile(v[:, 0], .10)
    stats = {
        'Mean (\\%)': 100 * v.mean(axis=0),
        'Standard deviation (\\%)': 100 * v.std(axis=0, ddof=1),
        'Sharpe ratio (excess of bills)': (v - bill[:, None]).mean(axis=0) / (v - bill[:, None]).std(axis=0, ddof=1),
        'Correlation with stocks (annual)': [np.corrcoef(v[:, 0], v[:, i])[0, 1] for i in range(4)],
        f'Correlation with stocks ({HORIZON}-year)': [np.corrcoef(lh[:, 0], lh[:, i])[0, 1] for i in range(4)],
        'Correlation with inflation (annual)': [np.corrcoef(infl, v[:, i])[0, 1] for i in range(4)],
        f'Correlation with inflation ({HORIZON}-year)': [np.corrcoef(lh_infl, lh[:, i])[0, 1] for i in range(4)],
        'Mean in worst stock decile (\\%)': 100 * v[worst].mean(axis=0),
    }
    return stats, len(rows)


def fmt(label, values):
    pct = '\\%' in label
    cells = [f'{x:.2f}' if pct else f'{x:.2f}' for x in values]
    cells = [c.replace('-', '$-$') for c in cells]
    return label + ' & ' + ' & '.join(cells) + r' \\'


def main():
    rows = read_panel(str(PANEL))
    late = [r for r in rows if r['year'] >= 1970]
    body = []
    for title, sample in (('Panel A: 1927--2025', rows), ('Panel B: 1970--2025', late)):
        stats, n = panel(sample)
        body.append(r'\multicolumn{5}{c}{' + title + f' ({n:,} country-years)' + r'} \\')
        body += [fmt(k, v) for k, v in stats.items()]
    text = (r'\begin{table}[p]\centering' + '\n'
            + r'\caption{Empirical properties of real returns on the four asset classes}\label{tab:sleeves}' + '\n'
            + r'\begin{minipage}{\linewidth}\small The table summarizes the empirical properties of annual real '
            'returns for local investors on the four asset classes available to the household. The underlying data are an annual panel of 16 '
            'developed countries covering 1927 to 2025, described in Section~\\ref{sec:data}. Returns are '
            'net of the managed-futures fee and turnover cost, gold custody, and the currency-hedging '
            'cost. Stocks are 33\\% domestic and 67\\% international. The Sharpe ratio is the mean annual return in excess of the local real bill return divided by its standard deviation. The ten-year statistics use '
            'overlapping ten-year log returns within each country. The last row reports the average '
            'return of each asset class in country-years in the lowest decile of stock returns. Panel B restricts '
            'the sample to 1970 to 2025.\\end{minipage}\n\\medskip\n\n'
            + r'{\small\begin{tabular}{lrrrr}\toprule' + '\n'
            + ' & ' + ' & '.join(NAMES) + r' \\ \midrule' + '\n'
            + '\n'.join(body) + '\n' + r'\bottomrule\end{tabular}}' + '\n' + r'\end{table}' + '\n')
    OUT.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
