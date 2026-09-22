"""Restore selected archived numerical evidence; no simulation or estimation."""
from pathlib import Path
import json
import hashlib
from render_erc_refocusing import table, percent, journal_layout

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'paper/new_paper/figures/restored'
PROP='80/53.33/33.33/33.33 ACO'
ACO='ACO 33/67 200%'
SOURCES={}

def read(path):
    p=ROOT/path
    SOURCES[path]=hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text())

def project_tex(path,output,excluded):
    p=ROOT/path
    SOURCES[path]=hashlib.sha256(p.read_bytes()).hexdigest()
    text=p.read_text()
    text='\n'.join(line for line in text.splitlines() if not any(x in line for x in excluded))+'\n'
    (DEST/output).write_text(text)

SHORT_FUNDS=('AHLT','IMF','ISMF','APEX')  # fewer than 60 monthly observations

def project_matrix(path,output,excluded):
    """Drop the rows and columns of excluded series from a generated tabular."""
    p=ROOT/path
    SOURCES[path]=hashlib.sha256(p.read_bytes()).hexdigest()
    lines=p.read_text().splitlines()
    header=next(i for i,l in enumerate(lines) if l.startswith(' & '))
    names=[c.strip().rstrip('\\').strip() for c in lines[header].split('&')]
    keep=[i for i,n in enumerate(names) if n not in excluded]
    out=[]
    for i,line in enumerate(lines):
        if '&' in line and line.rstrip().endswith('\\\\'):
            cells=[c.strip() for c in line.rstrip()[:-2].split('&')]
            if cells[0] in excluded:
                continue
            if len(cells)==len(names):
                line=' & '.join(cells[j] for j in keep)+' \\\\'
        elif line.startswith('\\begin{tabular}') and len(names)>0:
            line='\\begin{tabular}{l'+'r'*(len(keep)-1)+'}'
        out.append(line)
    (DEST/output).write_text('\n'.join(out)+'\n')

def main():
    DEST.mkdir(exist_ok=True)
    project_matrix('paper/figures/mf_pack_corr.tex','mf_pack_corr.tex',SHORT_FUNDS)
    project_tex('paper/figures/mf_pack_regressions.tex','mf_pack_regressions.tex',
                tuple(f'{n} &' for n in SHORT_FUNDS))
    gammas=[]
    for path,label in [('paper/figures/gamma_sensitivity.json','Joint calibration'),
                       ('results/gamma_fixed_theta_n10000.json','Fixed annual bequest')]:
        obj=read(path)
        for r in obj['results']:
            if r['gamma']==3.84:
                assert abs(r['portfolios'][PROP]['equivalent_savings_rate']-.0472)<.0001
                assert abs(r['benchmark_ruin']-.0698)<1e-10
            gammas.append([label,f"{r['gamma']:g}",percent(r['portfolios'][ACO]['equivalent_savings_rate']),
                           percent(r['portfolios'][PROP]['equivalent_savings_rate'])])
    table(DEST/'preferences.tex','Equivalent savings rates under alternative risk aversion','tab:restored-gamma',
          ['Bequest intensity',r'$\gamma$','All-equity 200\\%','Proportional 200\\%'],gammas,
          'The table reports equivalent savings rates for the all-equity and proportional strategies at 200\\% '
          'exposure under alternative coefficients of relative risk aversion. The reference is the all-equity '
          'strategy at 100\\% exposure and a 10\\% savings rate under the same preferences. The joint calibration '
          'sets the annual bequest intensity to $\\theta(\\gamma)=2{,}360\\times12^{3.84-\\gamma}$, which holds '
          'fixed the monthly intensity used by Anarkulova, Cederburg, and O\'Doherty (2025); the fixed calibration '
          'holds the annual intensity at $\\theta=2{,}360$. Ruin probabilities do not depend on preferences and '
          'equal 6.98\\%, 20.28\\%, and 1.80\\% for the all-equity strategy at 100\\% and 200\\% and the '
          'proportional strategy at 200\\%. Each entry is based on 10,000 bootstrap simulations and solves for '
          'the equivalent savings rate by bisection on $[0\\%,100\\%]$; no solution lies at a bound.')
    obj=read('paper/figures/policy_sensitivity.json')
    rows=[]
    for axis in ('contribution_axis','withdrawal_axis'):
        for r in obj[axis]:
            rows.append([percent(r['contribution_rate']),percent(r['withdrawal_rate']),
                         percent(r['benchmark_ruin']),percent(r['portfolios'][ACO]['ruin']),
                         percent(r['portfolios'][ACO]['equivalent_savings_rate']),
                         percent(r['portfolios'][PROP]['ruin']),percent(r['portfolios'][PROP]['equivalent_savings_rate'])])
    table(DEST/'policy.tex','Equivalent savings rates under alternative contribution and withdrawal rates','tab:restored-policy',
          [r'\shortstack{Savings\\ rate}',r'\shortstack{Withdrawal\\ rate}',r'\shortstack{All-equity\\ 100\% ruin}',r'\shortstack{All-equity\\ 200\% ruin}',r'\shortstack{All-equity\\ 200\% equiv.}',r'\shortstack{Proportional\\ 200\% ruin}',r'\shortstack{Proportional\\ 200\% equiv.}'],rows,
          'The table reports ruin probabilities and equivalent savings rates for the all-equity and proportional '
          'strategies at 200\\% exposure under alternative savings and withdrawal rates. The first three rows vary '
          'the savings rate with a 4\\% withdrawal rate; the last three rows vary the withdrawal rate with a 10\\% '
          'savings rate. The base case appears in both groups. In each row, the reference is the all-equity '
          'strategy at 100\\% exposure with the savings and withdrawal rates of that row. Each row is based on '
          '10,000 bootstrap simulations.')
    rows=[]
    for length in (5,10,20):
        obj=read(f'results/method_review/historical_panel_bootstrap/calendar_blocks_{length}y_outer100_inner1000.json')
        assert obj['source_observations']==1561
        s=obj['summary']['70/46.67/29.17/29.17 ACO']
        d=s['ruin_difference_vs_aco'];e=s['equivalent_savings_rate']
        rows.append([str(length),f"{percent(d['median'])} [{percent(d['p05'])}, {percent(d['p95'])}]",
                     f"{percent(e['median'])} [{percent(e['p05'])}, {percent(e['p95'])}]",percent(d['share_better_than_aco'])])
    table(DEST/'history.tex','Retirement outcomes across resampled calendar histories','tab:restored-history',
          [r'\shortstack{Average outer block\\ length (years)}',r'\shortstack{Difference in ruin\\ probability (pp)}',r'\shortstack{Equivalent savings\\ rate (\%)}',r'\shortstack{Histories with\\ lower ruin}'],
          [[r[0],r[1].replace('-','$-$'),r[2],r[3]+'\\%'] for r in rows],
          'The table compares the proportional strategy at 175\\% exposure with the all-equity strategy at 100\\% '
          'exposure across alternative histories of the panel. Each history resamples blocks of complete '
          'calendar-year cross-sections of the 16-country panel using a stationary block bootstrap with the '
          'indicated average block length, and each history supports 1,000 bootstrap simulations of household '
          'outcomes. The table reports the median and, in brackets, the 5th and 95th percentiles across 100 '
          'histories of the difference in ruin probability and of the equivalent savings rate. The last column '
          'reports the percentage of histories in which the proportional strategy has the lower ruin probability. '
          'The risk parity strategy is not included in this analysis.')
    obj=read('results/margin_call_n10000.json');assert obj['panel_rows']==1561
    rows=[]
    for key,label in [('aco_175','ACO'),('aco_200','ACO'),('proportional_200','Proportional')]:
        r=obj['families'][key]
        rows.append([label,percent(r['gross_exposure']),f"{r['calls']:,}",percent(r['min_year_end_ratio'])])
    table(DEST/'margin.tex','Year-end maintenance margin breaches','tab:restored-margin',
          ['Strategy','Gross exposure','Breaches','Minimum equity share'],[[{'ACO':'All-equity'}.get(r[0],r[0]),r[1]+'\\%',r[2],r[3]+'\\%'] for r in rows],
          'The table reports the number of year-end breaches of a 25\\% maintenance margin requirement across '
          '10,000 simulated 86-year account paths (860,000 account-years) with annual rebalancing to the target '
          'exposure. Asset and debt values are nominal. The simulation excludes contributions, withdrawals, and '
          'mortality, and the account returns to its target exposure after each breach. The last column reports '
          'the lowest year-end ratio of equity to assets.')
    project_tex('paper/new_paper/figures/margin_monthly.tex','monthly.tex',('Equal-weight &',))
    p=DEST/'monthly.tex'
    p.write_text(journal_layout(p.read_text()).replace('Bootstrap outputs and the 35\\% threshold are provided in the replication dataset.',
                    'Bootstrap outputs and a 35\\% threshold are reported in the replication files.').replace(
                    'Monthly closes do not measure intramonth extrema or simulate forced liquidation.',
                    'Crossings are measured at monthly closes, with annual exposure resets.'))
    src=ROOT/'paper/new_paper/figures/bill_quintiles.tex'
    SOURCES[str(src.relative_to(ROOT))]=hashlib.sha256(src.read_bytes()).hexdigest()
    body=src.read_text()
    start=body.index(r'\multicolumn{8}{l}{\textit{Equal-weight:')
    end=body.index(r'\bottomrule',start)
    (DEST/'bills.tex').write_text(journal_layout((body[:start]+body[end:])).replace(
        'Quintiles are ex post and do not define a trading rule. These are annual arithmetic-return effects, not contributions to ruin or utility.',
        'Quintiles group observations by their ex-post real bill return.'))
    import re
    def renote(name,caption,note):
        f=DEST/name; t=f.read_text()
        t=re.sub(r'\\caption\{.*?\}(\\label)',lambda m:'\\caption{'+caption+'}'+m.group(1),t,count=1,flags=re.S)
        t=re.sub(r'\\begin\{minipage\}\{\\linewidth\}\\small .*?\\end\{minipage\}',
                 lambda m:r'\begin{minipage}{\linewidth}\small '+note+r'\end{minipage}',t,count=1,flags=re.S)
        t=t.replace('& Sleeves &','& Asset classes &').replace('{ACO: ','{All-equity: ').replace('\nACO &','\nAll-equity &')
        f.write_text(t.replace(r'\centering\scriptsize',r'\centering'))
    renote('monthly.tex','Month-end and year-end maintenance margin breaches',
           'The table reports the number of calendar years with at least one breach of a 25\\% or 40\\% '
           'maintenance margin requirement for the all-equity and proportional strategies, measured at month-end '
           '(Monthly years) or at year-end (Annual years) on the same asset and debt paths. The sample covers the 56 '
           'complete years from 1970 to 2025 in US dollars. Stocks are 33/67 US and non-US total-return series, '
           'global bonds are proxied by intermediate US Treasuries, gold is the spot price less custody, and '
           'managed futures are the net proxy. Debt accrues the US bill rate plus 0.30\\% per year. Asset '
           'quantities are fixed within each year, and exposure returns to target at each year-end. The last '
           'column reports the lowest equity-to-asset ratio.')
    renote('bills.tex','Incremental returns from leverage by real bill rate quintile',
           'The table decomposes the difference in annual real return between each strategy at 175\\% and at '
           '100\\% exposure into contributions from the asset classes, the bill leg of borrowing, the borrowing '
           'spread, and the currency-hedge friction. Country-years are sorted into quintiles by their ex post real '
           'bill return, with Q1 containing the lowest real bill returns. For weights $a_i$ summing to one, the '
           'four components are $0.75\\sum_i a_iR_i$, $-0.75R_f$, $-0.75\\phi$, and $-0.75h\\kappa$, with '
           '$\\phi=0.30\\%$, $\\kappa=0.10\\%$, and $h$ the hedged share at 100\\% exposure. The sample is the '
           '1,561 country-years from 1927 to 2025, and entries are in percentage points.')
    (DEST/'provenance.json').write_text(json.dumps({'sources_sha256':SOURCES,
        'selection':'Retained ACO and proportional columns only; no equal-capital or inferred ERC results.',
        'renderer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')

if __name__=='__main__':main()
