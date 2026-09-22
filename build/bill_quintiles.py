"""Deterministic bill-quintile attribution and MF volatility audit; no simulation."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from compare_fixed_stacked_utility import FIXED_EXPOSURES, read_panel, return_functions
from panel_managed_futures import fill_isolated_gaps, read_cpi, previous_month

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'results/robustness/bill_quintiles'
FIG = ROOT / 'paper/new_paper/figures'


def main():
    baseline = ROOT / 'results/main_ladders_n10000.json'
    panel = ROOT / 'data/replication-panel-trend.csv'
    monthly_path = ROOT / 'data/managed-futures-monthly.csv'
    cpi_path = ROOT / 'data/cpi-monthly.csv'
    meta = json.loads(baseline.read_text())
    rows = read_panel(str(panel))
    assert len(rows) == meta['observations'] == 1561
    assert all(abs(r['bill'] - r['world_bill']) < 1e-12 for r in rows)
    fun = return_functions(rows, meta['spread'], meta['trend_fee'],
                           meta['trend_cost'], meta['trend_haircut'],
                           meta['fx_hedge_cost'], hedge_mode=meta['hedge_mode'])
    # Independent archived reference check for every displayed ladder portfolio.
    for entry in meta['results']:
        values = np.array([fun[entry['strategy']](r) for r in rows])
        assert abs(values.std(ddof=1) - entry['volatility']) < 1e-10
    frame = pd.DataFrame({'country': [r['country'] for r in rows],
                          'year': [r['year'] for r in rows],
                          'bill': [r['bill'] for r in rows]})
    frame['quintile'] = pd.qcut(frame.bill, 5, labels=False) + 1
    families = [('ACO', 'ACO 33/67', 'ACO 33/67 175%', 0.0)]
    for title, weights in [('Proportional', np.array([.6,.4,.25,.25])/1.5),
                           ('Equal-weight', np.repeat(.25,4))]:
        names = [next(n for n,w in FIXED_EXPOSURES.items()
                      if np.allclose(w, weights*g)) for g in (1,1.75)]
        families.append((title, *names, weights[1]+weights[3]))
    records = []
    period_records = []
    for title, low, high, covered in families:
        base = np.array([fun[low](r) for r in rows])
        observed = np.array([fun[high](r)-fun[low](r) for r in rows])
        parts = pd.DataFrame({
            'sleeves': .75*(base + covered*meta['fx_hedge_cost']),
            'bill': -.75*frame.bill,
            'spread': np.repeat(-.75*meta['spread'], len(rows)),
            'hedge': np.repeat(-.75*covered*meta['fx_hedge_cost'], len(rows)),
            'increment': observed,
        })
        np.testing.assert_allclose(parts.iloc[:,:4].sum(axis=1), observed,
                                   atol=1e-12, rtol=0)
        for q in range(1,6):
            mask = frame.quintile == q
            records.append({'family':title, 'quintile':q, 'n':int(mask.sum()),
                            'bill_mean':float(frame.loc[mask,'bill'].mean()),
                            'bill_min':float(frame.loc[mask,'bill'].min()),
                            'bill_max':float(frame.loc[mask,'bill'].max()),
                            **parts.loc[mask].mean().to_dict()})
        for label, mask in [('Full', np.ones(len(rows),dtype=bool)),
                            ('1940s and 1970s', frame.year.between(1940,1949)|frame.year.between(1970,1979)),
                            ('Other years', ~(frame.year.between(1940,1949)|frame.year.between(1970,1979))),
                            ('Post-1970', frame.year >= 1970)]:
            period_records.append({'family':title, 'period':label,'n':int(mask.sum()),
                                   **parts.loc[mask].mean().to_dict(),
                                   'contribution_full_mean':float(parts.loc[mask,'increment'].sum()/len(rows))})
    monthly = pd.read_csv(monthly_path).set_index('month')
    cpi, patched = fill_isolated_gaps(read_cpi(str(cpi_path)))
    monthly = monthly.loc['1927-01':'2025-12'].copy()
    gross = monthly.mf_1_6_12_gross_return
    cash = monthly.mf_1_6_12_cash_collateral_return
    monthly['real'] = [(1+r)/(cpi[m]/cpi[previous_month(m)])-1 for m,r in gross.items()]
    annual = monthly.groupby(monthly.index.str[:4]).agg(
        nominal=('mf_1_6_12_gross_return',lambda x:np.prod(1+x)-1),
        real=('real',lambda x:np.prod(1+x)-1), n=('real','size'))
    assert (annual.n == 12).all() and len(annual)==99
    us = [r for r in rows if r['country']=='USA']
    gross_us = np.array([r['trend_fixed_notional'] for r in us])
    np.testing.assert_allclose(annual.real.to_numpy(),
                              [r['trend_unhedged'] for r in us],atol=1e-10,rtol=0)
    net_us = (1+gross_us)*(1-meta['trend_fee'])-1-meta['trend_cost']
    vol = {
        'monthly_gross_excess_annualized_sd':float(((1+gross)/(1+cash)-1).std()*np.sqrt(12)),
        'monthly_gross_nominal_annualized_sd':float(gross.std()*np.sqrt(12)),
        'monthly_gross_real_annualized_sd':float(monthly.real.std()*np.sqrt(12)),
        'annual_gross_nominal_sd':float(annual.nominal.std()),
        'annual_gross_real_sd':float(annual.real.std()),
        'annual_panel_fixed_notional_gross_real_sd':float(gross_us.std(ddof=1)),
        'annual_net_real_sd':float(net_us.std(ddof=1)),
        'annual_net_real_population_sd':float(net_us.std(ddof=0)),
        'annual_net_real_mean':float(net_us.mean()),
        'scalar_cap_frequency':float(np.isclose(monthly.mf_1_6_12_portfolio_vol_scalar,3).mean()),
        'net_real_sd_1927_1969':float(net_us[np.array([r['year']<1970 for r in us])].std(ddof=1)),
        'net_real_sd_1970_2025':float(net_us[np.array([r['year']>=1970 for r in us])].std(ddof=1)),
        'cpi_interpolated_months':patched,
    }
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[panel,baseline,monthly_path,cpi_path,Path(__file__)]
    result={'inputs_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            'definition':'175% minus 100%, fixed composition; equal-weighted resident country-years; ex-post pooled bill quintiles. Additive arithmetic-return attribution, not utility or causal attribution.',
            'quintiles':records,'periods':period_records,'mf_volatility':vol}
    (OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=[r'\begin{table}[htbp]\centering\scriptsize',
           r'\caption{Incremental leverage returns by ex-post real-bill quintile}\label{tab:bill-quintiles}',
           r'\begin{tabular}{lrrrrrrr}\toprule',
           r'Quintile & $n$ & Mean bill & Sleeves & Bill leg & Spread & Hedge & Total \\',r'\midrule']
    for title,*_ in families:
        lines.append(r'\multicolumn{8}{l}{\textit{'+title+r': 175\% minus 100\% exposure}} \\')
        for r in records:
            if r['family']==title:
                cells=[f"Q{r['quintile']}",str(r['n'])]+[f"{100*r[k]:.2f}" for k in ('bill_mean','sleeves','bill','spread','hedge','increment')]
                lines.append(' & '.join(cells)+r' \\')
        lines.append(r'\addlinespace')
    lines += [r'\bottomrule\end{tabular}',r'\par\smallskip\begin{minipage}{0.97\textwidth}\footnotesize',
              r'1,561 equally weighted country-years, 1927--2025. Q1 contains the lowest realized real bills. Mean bill is in percent; contributions are annual percentage points. For fixed sleeve weights $a_i$ summing to one, the four components are $0.75\sum_i a_iR_i$, $-0.75R_f$, $-0.75\phi$, and $-0.75h\kappa$, with $\phi=0.003$, $\kappa=0.001$, and $h$ the covered share at 100\%. Sleeves include baseline MF fees and turnover costs, before hedge friction. Components add to the observed portfolio-return difference before rounding. Quintiles are ex post and do not define a trading rule. These are annual arithmetic-return effects, not contributions to ruin or utility.',
              r'\end{minipage}\end{table}']
    (FIG/'bill_quintiles.tex').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'periods':period_records,'mf_volatility':vol},indent=2))


if __name__ == '__main__':
    main()
