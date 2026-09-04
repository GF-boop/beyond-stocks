"""Full raw/screened/winsorized comparisons; preserve raw inputs and record exclusions."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from investability import exclusion_reasons

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'results/panel_concentration'

def run(args, label):
    with (OUT / (label + '.log')).open('w') as log:
        subprocess.run([sys.executable, *args], cwd=ROOT, stdout=log,
                       stderr=subprocess.STDOUT, check=True)

def write(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader(); w.writerows(rows)

def main():
    OUT.mkdir(exist_ok=True)
    source = ROOT / 'data/replication-panel-trend.csv'
    raw = list(csv.DictReader(source.open()))
    exclusions = {}
    for row in raw:
        key = (row['country'], int(row['year']))
        reasons = list(exclusion_reasons(*key, float(row['inflation'])))
        if key == ('Italy', 1942):
            reasons.append('Italy 1942 source-conversion influence identified in the audit; not a verified closure')
        if reasons:
            exclusions[key] = reasons
    events = [f'{c}:{y}' for c,y in sorted(exclusions)]
    eqargs = [arg for event in events for arg in ('--exclude-market-year', event)]
    bondargs = [arg for event in events for arg in ('--exclude-bond-issuer-year', event)]
    international = OUT / 'international-screened.csv'
    replication = OUT / 'replication-screened.csv'
    extended = OUT / 'panel-screened-sources.csv'
    run(['build/international_equity.py', '--out', str(international), *eqargs], 'equity')
    run(['build/build_replication_panel.py', '--international', str(international), '--out', str(replication)], 'replication')
    run(['build/panel_replication_tendance.py', '--panel', str(replication), '--out', str(extended), *bondargs], 'sources')
    screened = [r for r in csv.DictReader(extended.open())
                if (r['country'],int(r['year'])) not in exclusions]
    write(OUT / 'panel-screened.csv', screened)
    # Clip sleeve returns, never the already leveraged portfolio; retain cash,
    # inflation, resident identities and bootstrap support.
    fields = ('domestic_equity_real','international_equity_real',
              'world_bond_real_fixed_notional','trend_real_fixed_notional','gold_real')
    winsor = [dict(r) for r in raw]
    limits = {}
    for field in fields:
        lo, hi = np.quantile([float(r[field]) for r in raw], [0.005,0.995])
        limits[field] = [float(lo), float(hi)]
        for row in winsor:
            row[field] = str(float(np.clip(float(row[field]),lo,hi)))
    write(OUT / 'panel-winsorized.csv', winsor)
    provenance = {'raw_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'screened_observations': len(screened), 'raw_observations':len(raw),
        'exclusions':[{'country':c,'year':y,'reasons':v} for (c,y),v in exclusions.items()],
        'winsor_limits':limits,
        'interpretation':'Screen includes retrospective annual inflation and an audit-selected Italy event. It is not a fully ex ante investability rule. Winsorization is a statistical sensitivity, not reconstructed tradable returns. Monthly MF inputs remain fixed.',
        'pairing':'Same seeds within each panel; different supports prevent pathwise pairing of raw and screened samples.'}
    (OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    for name, panel in [('raw',source),('screened',OUT/'panel-screened.csv'),('winsorized',OUT/'panel-winsorized.csv')]:
        run(['build/compare_fixed_stacked_utility.py','--panel',str(panel),'--portfolio-set','all',
             '--runs','10000','--seed','20260827','--output-json',str(OUT/f'{name}_n10000.json')], name)

if __name__ == '__main__':
    main()
