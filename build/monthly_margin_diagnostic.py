"""Month-end versus year-end maintenance tests on identical USD proxy paths.

Annual allocation reset; no within-year rebalancing. This is a threshold
diagnostic, not a liquidation model or a monthly replication of 16 residents.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'results/margin_monthly'
UPSTREAM = ROOT.parent / 'CTO_vs_PEA/data/trend/canonical/data'

def prepare_inputs():
    snapshot = UPSTREAM / 'all-assets-monthly.csv'
    cached = OUT / 'inputs.csv'
    if not snapshot.exists():
        if cached.exists():
            provenance = json.loads((OUT/'input_provenance.json').read_text())
            current = hashlib.sha256((ROOT/'data/managed-futures-monthly.csv').read_bytes()).hexdigest()
            if provenance['mf_sha256'] != current:
                raise ValueError('Frozen monthly control uses a different MF snapshot; refresh its inputs')
            return cached
        raise FileNotFoundError('Monthly total-return proxy snapshot or frozen inputs required')
    selected = {'BM_VTISIM':'domestic', 'BM_VXUSSIM':'international',
                'BM_IEFSIM':'bond', 'METAL_GOLD':'gold'}
    months = {}
    for r in csv.DictReader(snapshot.open()):
        if r['asset_id'] in selected and r['month'] >= '1970-01':
            months.setdefault(r['month'],{})[selected[r['asset_id']]] = float(r['return'])
    for r in csv.DictReader((ROOT/'data/managed-futures-monthly.csv').open()):
        if r['month'] in months and r['mf_1_6_12_net_return']:
            months[r['month']]['mf'] = float(r['mf_1_6_12_net_return'])
            months[r['month']]['cash'] = float(r['mf_1_6_12_cash_collateral_return'])
    with cached.open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=['month','domestic','international','bond','gold','mf','cash'],lineterminator='\n')
        writer.writeheader()
        writer.writerows({'month':m,**r} for m,r in sorted(months.items()) if len(r)==6)
    (OUT/'input_provenance.json').write_text(json.dumps({
        'snapshot':str(snapshot), 'snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        'mf_sha256':hashlib.sha256((ROOT/'data/managed-futures-monthly.csv').read_bytes()).hexdigest(),
        'series':selected,'interpretation':'VTI/VXUS/IEF historical total-return simulations, gold spot, reconstructed MF net, USD collateral; IEF replaces global bonds; US resident only.'},indent=2)+'\n')
    return cached

def equity_ratios(returns, cash, weights, gross):
    """Unit equity, fixed sleeve quantities, interest-bearing nominal debt."""
    growth = np.cumprod(1 + returns, axis=1)
    assets = gross * np.sum(growth * weights, axis=2)
    debt = (gross-1) * np.cumprod(1 + cash + 0.003/12, axis=1)
    return (assets-debt)/assets

def main():
    OUT.mkdir(exist_ok=True)
    path=prepare_inputs()
    rows={r['month']:r for r in csv.DictReader(path.open())}
    years=[y for y in range(1970,2026) if all(f'{y}-{m:02}' in rows for m in range(1,13))]
    returns=np.array([[[float(rows[f'{y}-{m:02}'][k]) for k in ('domestic','international','bond','gold','mf')]
                       for m in range(1,13)] for y in years])
    cash=np.array([[float(rows[f'{y}-{m:02}']['cash']) for m in range(1,13)] for y in years])
    returns[:,:,3] -= 0.001/12  # same gold custody rate, in monthly units
    rng=np.random.default_rng(20260827)
    draws=np.empty((10000,86),dtype=int)
    draws[:,0]=rng.integers(len(years),size=10000)
    for t in range(1,86):
        nxt=draws[:,t-1]+1
        restart=(rng.random(10000)<0.1)|(nxt>=len(years))
        draws[:,t]=np.where(restart,rng.integers(len(years),size=10000),nxt)
    families={'ACO':np.array([.33,.67,0,0,0]),
              'Proportional':np.array([.4*.33,.4*.67,4/15,1/6,1/6]),
              'Equal-weight':np.array([.25*.33,.25*.67,.25,.25,.25])}
    results=[]
    for family,weights in families.items():
        for level in (100,125,150,175,200):
            ratios=equity_ratios(returns,cash,weights,level/100)
            for threshold in (.25,.35,.40):
                monthly=np.any(ratios<threshold,axis=1)
                annual=ratios[:,-1]<threshold
                assert np.all(~annual|monthly)
                sampled=monthly[draws]; sampled_annual=annual[draws]
                results.append({'family':family,'gross_percent':level,'maintenance':threshold,
                    'observed_monthly_breach_years':[y for y,v in zip(years,monthly) if v],
                    'observed_annual_breach_years':[y for y,v in zip(years,annual) if v],
                    'observed_monthly_only_years':[y for y,m,a in zip(years,monthly,annual) if m and not a],
                    'minimum_month_end_equity_ratio':float(ratios.min()),
                    'sampled_monthly_breach_year_fraction':float(sampled.mean()),
                    'sampled_annual_breach_year_fraction':float(sampled_annual.mean()),
                    'sampled_paths_any_monthly_breach':float(sampled.any(axis=1).mean())})
    payload={'years':years,'runs':10000,'horizon_years':86,'seed':20260827,
             'mean_block_years':10,'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'design':'USD proxy control; nominal debt; annual resets, fixed quantities within year; monthly and annual tests share paths. Threshold crossings do not simulate liquidation. Synthetic pre-inception total returns; no inferred intra-month extrema.',
             'results':results}
    (OUT/'results.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(f'Monthly margin diagnostic: {len(years)} complete years, {len(results)} specifications')

if __name__=='__main__':
    main()
