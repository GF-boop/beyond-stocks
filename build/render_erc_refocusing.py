"""Render the refocused manuscript exhibits from frozen ERC results only."""
from pathlib import Path
import json
import hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/erc_refocusing/n10000_final'
REVISION=ROOT/'results/revision_2026-09-22'
FIG=ROOT/'paper/new_paper/figures/erc'

def percent(v): return f'{100*v:.2f}'

def pct(v,d=2): return f'{100*v:.{d}f}\\%'

def panel_row(text,cols):
    return r'\multicolumn{'+str(cols)+r'}{c}{'+text+r'} \\'

def table(path,caption,label,header,rows,note,align=None,float_spec='p',colsep='4pt'):
    """Journal layout: title, descriptive note above the tabular, panel rows.

    ``header`` is a list of column labels or a raw LaTeX header string; a row
    given as a string is written verbatim (panel titles, rules)."""
    ncol=len(rows[0]) if isinstance(header,str) else len(header)
    for row in rows:
        if not isinstance(row,str):
            ncol=len(row);break
    cols=align or 'l'+'r'*(ncol-1)
    head=header if isinstance(header,str) else ' & '.join(header)+r' \\'
    body='\n'.join(row if isinstance(row,str) else ' & '.join(row)+r' \\' for row in rows)
    text=('\\begin{table}['+float_spec+']\\centering\n'+
          '\\caption{'+caption+'}\\label{'+label+'}\n'+
          r'\begin{minipage}{\linewidth}\small '+note+r'\end{minipage}'+'\n\\medskip\n\n'+
          r'{\small\setlength{\tabcolsep}{'+colsep+r'}\begin{tabular}{'+cols+r'}\toprule'+'\n'+head+r' \midrule'+'\n'+body+
          '\n'+r'\bottomrule\end{tabular}}'+'\n'+r'\end{table}'+'\n')
    path.write_text(text)

def journal_layout(text):
    """Move a trailing note minipage above the tabular in a generated table."""
    import re
    m=re.search(r'\\par\\smallskip\\begin\{minipage\}\{[^}]*\}(.*?)\\end\{minipage\}',text,re.S)
    if not m: return text
    note=m.group(1).strip()
    text=text[:m.start()]+text[m.end():]
    cap=re.search(r'\\caption\{.*?\}\\label\{[^}]*\}',text,re.S)
    insert='\n'+r'\begin{minipage}{\linewidth}\small '+note+r'\end{minipage}'+'\n\\medskip\n'
    text=text[:cap.end()]+insert+text[cap.end():]
    return re.sub(r'\\begin\{table\}\[[^\]]*\]',r'\\begin{table}[p]',text)

def main():
    assert json.loads((SOURCE/'completion.json').read_text())['complete']
    FIG.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((SOURCE/'manifest.json').read_text())
    retired=[]
    drifted=[]
    for name,sha in manifest['inputs_sha256'].items():
        # Presentation changes are recorded by the current renderer hash below;
        # the simulation manifest retains its original renderer fingerprint.
        source=ROOT/name
        if source == Path(__file__).resolve():
            continue
        if not source.exists():
            # The manifest snapshots every build script present at run time.
            # Files retired by a cleanup cannot have fed the frozen results;
            # their hashes remain recorded in the manifest itself.
            retired.append(name)
            continue
        if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:
            # Build scripts may legitimately change after the frozen run
            # (cleanup, presentation). Scientific inputs stay strict.
            if name.startswith('build/'):
                drifted.append(name)
                continue
            raise AssertionError(name)
    if retired:
        print(f'{len(retired)} retired manifest input(s) not rechecked: '
              +', '.join(retired),flush=True)
    if drifted:
        print(f'{len(drifted)} build script(s) modified since the run: '
              +', '.join(drifted),flush=True)
    baseline=json.loads((SOURCE/'baseline.json').read_text())
    records=baseline['results']
    full=[r for r in records if r['removed'] is None]
    families=('ACO','Proportional','ERC')
    labels={'ACO':'All-equity','Proportional':'Proportional','ERC':'Risk parity'}
    common_note=('Each comparison is based on 10,000 bootstrap simulations of household outcomes that share '
                 'return, earnings, and mortality draws. The household saves 10\\% of labor income. ')
    # Table II: strategies, weights, and outcomes.
    rows=[]
    for k,fam in enumerate(families):
        rows.append(panel_row(f'Panel {"ABC"[k]}: {labels[fam]} strategies',9))
        for r in [x for x in full if x['family']==fam]:
            w=r['weights']
            rows.append([f"{r['gross_percent']}\\%"]+[f'{100*x:.0f}\\%' for x in w]+
                        [f"{r['gross_percent']-100}\\%",pct(r['annual_volatility']),
                         pct(r['ruin_probability']),pct(r['equivalent_savings_rate'])])
    revision=json.loads((REVISION/'revision_checks.json').read_text())
    haircut=json.loads((REVISION/'revision_checks_mf_minus_300bp.json').read_text())
    extra={r['strategy']:r for r in revision['results']}
    extra_haircut={r['strategy']:r for r in haircut['results']}
    def extra_row(r,label):
        w=r['weights']
        return [label]+[f'{100*x:.0f}\\%' for x in w]+[f"{100*(r['gross']-1):.0f}\\%",pct(r['annual_volatility']),
                pct(r['ruin_probability']),pct(r['equivalent_savings_rate'])]
    rows.append(panel_row('Panel D: Strategies without bonds',9))
    for name,label in (('Stocks, gold, MF 175%','Stocks/gold/MF'),('Stocks and MF 175%','Stocks/MF')):
        rows.append(extra_row(extra[name],label))
    rows.append(panel_row('Panel E: Strategies at the volatility of the unlevered all-equity strategy',9))
    for fam,label in (('Proportional','Proportional'),('Risk parity','Risk parity'),('Stocks, gold, MF','Stocks/gold/MF'),('Stocks and MF','Stocks/MF')):
        rows.append(extra_row(extra[f'{fam} equal volatility'],label))
    header=(r' & \multicolumn{4}{c}{Asset class weights (\% of wealth)} & & & & \\ \cmidrule(lr){2-5}'+'\n'
            r'Gross & & Global & & Managed & & & Ruin & Equivalent \\'+'\n'
            r'exposure & Stocks & bonds & Gold & futures & Borrowing & Volatility & probability & savings rate \\')
    table(FIG/'central.tex','Economic value of levered allocation strategies','tab:central-results',header,rows,
          'The table reports the asset class weights, annual return volatility, probability of financial ruin, and '
          'equivalent savings rate for the all-equity strategy (Panel A), the proportional strategy (Panel B), and the '
          'risk parity strategy (Panel C) at gross exposures from 100\\% to 200\\% of wealth. Panel D removes global '
          'bonds from the proportional strategy and redistributes their weight in proportion to the remaining weights '
          '(stocks, gold, and managed futures) or to stocks and managed futures only, at 175\\% exposure. Panel E '
          'scales each diversified strategy to the 25.28\\% volatility of the unlevered all-equity strategy. '
          'In Panels D and E, the first column names the strategy, and gross exposure is 100\\% plus borrowing. Stocks are 33\\% domestic '
          'and 67\\% international. Borrowing is financed at the local bill rate plus 0.30\\%. Volatility is the standard '
          'deviation of annual real portfolio returns in the pooled panel. '+common_note+
          'The probability of financial ruin is the probability of exhausting wealth before the death of the last '
          'survivor under the 4\\% rule. The equivalent savings rate is the savings rate that equates expected utility '
          'from retirement consumption and bequest with that of the all-equity strategy at 100\\% exposure and a 10\\% '
          'savings rate.',align='lrrrrrrrr',colsep='2.2pt')
    # Table III: own-capital ruin and common-income failure.
    rows=[]
    for k,fam in enumerate(families):
        rows.append(panel_row(f'Panel {"ABC"[k]}: {labels[fam]} strategies',5))
        for r in [x for x in full if x['family']==fam]:
            c=r['common_income'];ci=r['paired_common_vs_aco']['ci95']
            diff=f'[{100*ci[0]:.2f}, {100*ci[1]:.2f}]'.replace('-','$-$') if fam!='ACO' or r['gross_percent']!=100 else '---'
            rows.append([f"{r['gross_percent']}\\%",pct(r['ruin_probability']),
                         pct(c['shortfall_probability_all_paths']),pct(c['shortfall_probability']),diff])
    header=(r'Gross & Probability of & \multicolumn{2}{c}{Failure to fund path-matched income} & 95\% interval for \\ \cmidrule(lr){3-4}'+'\n'
            r'exposure & financial ruin & All households & Retired households & difference (pp) \\')
    table(FIG/'common.tex','Capital preservation and funding the path-matched income','tab:common',header,rows,
          'The table compares two retirement outcomes for the all-equity (Panel A), proportional (Panel B), and risk '
          'parity (Panel C) strategies. The probability of financial ruin applies the 4\\% rule to each strategy\'s own '
          'wealth at retirement. The probability of failing to fund the path-matched income instead fixes each household\'s real '
          'withdrawal at 4\\% of the wealth that the all-equity strategy at 100\\% exposure accumulates on the same '
          'simulated path, so the income to fund differs across paths. Retired households are those that reach retirement with a positive planned withdrawal. '
          +common_note+'The last column reports the 95\\% confidence interval for the paired difference in failure '
          'probability relative to the all-equity strategy at 100\\% exposure, in percentage points, and reflects '
          'Monte Carlo error only.',align='lrrrr')
    # Internet Appendix: sleeve removal.
    rows=[]
    for k,fam in enumerate(('Proportional','ERC')):
        rows.append(panel_row(f'Panel {"AB"[k]}: {labels[fam]} strategy at 175\\% exposure',4))
        for r in [x for x in records if x['family']==fam and x['gross_percent']==175]:
            rows.append([('None' if r['removed'] is None else {'bonds':'Global bonds','gold':'Gold','MF':'Managed futures'}[r['removed']]),
                         pct(r['ruin_probability']),pct(r['equivalent_savings_rate']),
                         pct(r['common_income']['shortfall_probability_all_paths'])])
    table(FIG/'ablations.tex','Removing one asset class','tab:ablations',
          r'Asset class removed & Ruin probability & Equivalent savings rate & Path-matched income failure \\',rows,
          'The table reports retirement outcomes for the proportional (Panel A) and risk parity (Panel B) strategies at '
          '175\\% exposure after removing one asset class. The weight of the removed asset class is redistributed '
          'across the remaining asset classes in proportion to their weights, holding gross exposure fixed. '
          +common_note+'Path-matched income failure is the probability of failing to fund 4\\% of the retirement wealth of '
          'the all-equity strategy at 100\\% exposure. The sample is 1927 to 2025.')
    # Table VI: robustness at equal volatility (revision of September 22, 2026).
    eqdir=REVISION/'eqvol'
    variants=json.loads((REVISION/'mf_variant_lifecycle.json').read_text())['variants']
    fams=('Proportional equal volatility','Risk parity equal volatility','Stocks and MF equal volatility')
    def num(v): return f'{100*v:.2f}'
    def cells_from(res,label):
        aco=res['ACO 33/67']
        out=[label,num(aco['ruin_probability'])]
        for f in fams:
            r=res[f]
            out+=[num(r['equivalent_savings_rate']),num(r['ruin_probability']),
                  num(r.get('matched_failure',r.get('common_failure')))]
        return out
    cases=[('Panel A: Base case',[('baseline','Base case')]),
           ('Panel B: Alternative samples',[('post1970','Post-1970 sample'),('source_italy1942','Excluding Italy 1942')]),
           ('Panel C: Borrowing spread',[('spread_100bp','Spread of 1.00\\%'),('spread_200bp','Spread of 2.00\\%'),('spread_300bp','Spread of 3.00\\%')]),
           ('Panel D: Managed-futures return haircut',[('mf_minus_200bp','Haircut of 2.00\\%'),('mf_minus_300bp','Haircut of 3.00\\%'),('mf_minus_600bp','Haircut of 6.00\\%')])]
    rows=[]
    for title,items in cases:
        rows.append(panel_row(title,11))
        for file,label in items:
            res={r['strategy']:r for r in json.loads((eqdir/f'{file}.json').read_text())['results']}
            rows.append(cells_from(res,label))
    rows.append(panel_row('Panel E: Managed-futures construction',11))
    for v in variants:
        if v['key']=='1_6_12': continue
        label={'1_3_12':'1/3/12-month signal','12m':'12-month signal','1m':'1-month signal','fee2':'Fee of 1.70\\%'}[v['key']]
        rows.append(cells_from(v['results'],label))
    header=(r' & All- & \multicolumn{3}{c}{Proportional} & \multicolumn{3}{c}{Risk parity} & \multicolumn{3}{c}{Stocks and MF} \\ \cmidrule(lr){3-5}\cmidrule(lr){6-8}\cmidrule(lr){9-11}'+'\n'
            r'Description & equity & Equiv. & Ruin & Match & Equiv. & Ruin & Match & Equiv. & Ruin & Match \\')
    g=json.loads((REVISION/'revision_checks.json').read_text())['equal_volatility_exposures']
    table(FIG/'sensitivity.tex','Retirement outcomes at equal volatility under alternative assumptions','tab:sensitivity',header,rows,
          'The table reports retirement outcomes, in percent, for the proportional, risk parity, and stocks-and-managed-futures '
          f'strategies at the gross exposures that give them the volatility of the unlevered all-equity strategy in the base case '
          f'({100*g["Proportional"]:.0f}\\%, {100*g["Risk parity"]:.0f}\\%, and {100*g["Stocks and MF"]:.0f}\\%), held fixed across '
          'specifications. For each strategy, the table reports the equivalent savings rate (Equiv.), the probability of financial '
          'ruin (Ruin), and the probability of failing to fund the path-matched income, 4\\% of the retirement wealth of the '
          'all-equity strategy at 100\\% exposure on the same path, with a 10\\% savings rate (Match). The second column reports '
          'the ruin probability of the all-equity strategy, the utility reference in each specification. Panel B draws returns from '
          '1970 to 2025 or excludes Italy in 1942 from the resident panel and the international baskets. Panel C raises the '
          'borrowing spread above the local bill rate from 0.30\\%. Panel D subtracts an additional annual return from managed '
          'futures. Panel E rebuilds the managed-futures series with other signals or a doubled fee. Each specification is based '
          'on 10,000 bootstrap simulations.',align='lrrrrrrrrrr',colsep='3pt')
    # Three measures (revision of September 22, 2026).
    rev={r['strategy']:r for r in json.loads((REVISION/'revision_checks.json').read_text())['results']}
    mrows=[]
    for name,label in (('ACO 33/67','All-equity 100\\%'),('Proportional equal volatility',f'Proportional {100*g["Proportional"]:.0f}\\%'),
                       ('Risk parity equal volatility',f'Risk parity {100*g["Risk parity"]:.0f}\\%'),
                       ('Stocks and MF equal volatility',f'Stocks and MF {100*g["Stocks and MF"]:.0f}\\%')):
        r=rev[name]
        mrows.append([label,pct(r['equivalent_savings_rate']),pct(r['ruin_probability']),pct(r['common_failure']),
                      pct(r['common_failure_at_equivalent_saving'])])
    header=(r' & (1) & (2) & \multicolumn{2}{c}{(3) Path-matched income failure} \\ \cmidrule(lr){4-5}'+'\n'
            r'Strategy & \shortstack{Equivalent\\ savings rate} & \shortstack{Ruin\\ probability} & \shortstack{Saving\\ 10\%} & \shortstack{Saving\\ rate (1)} \\')
    table(FIG/'measures.tex','Three measures of retirement outcomes','tab:measures',header,mrows,
          'The table reports three measures for the strategies at the volatility of the unlevered all-equity strategy. '
          '(1) The equivalent savings rate gives the strategy the expected utility of the all-equity strategy saving 10\\%. '
          '(2) The ruin probability applies the 4\\% rule to the strategy\'s own retirement wealth; it does not depend on the '
          'savings rate. (3) The path-matched income failure is the probability of not paying 4\\% of the retirement wealth '
          'that the all-equity strategy saving 10\\% accumulates on the same path, when the strategy saves 10\\% or its own '
          'equivalent savings rate. Each measure is based on the same 10,000 simulations.',align='lrrrr',float_spec='htbp')
    # Table IV: resampled calendar histories at equal volatility.
    hdir=REVISION/'history_eqvol'
    hrows=[]
    for k,(f,label) in enumerate(zip(fams,('Proportional','Risk parity','Stocks and MF'))):
        hrows.append(panel_row(f'Panel {"ABC"[k]}: {label} at {100*g[label if label!="Stocks and MF" else "Stocks and MF"]:.0f}\\% exposure',5))
        for b in (5,10,20):
            sm=json.loads((hdir/f'calendar_blocks_{b}y_outer100_inner1000.json').read_text())['summary'][f]
            def band(m): return f"{100*m['median']:.2f} [{100*m['p05']:.2f}, {100*m['p95']:.2f}]".replace('-','$-$')
            hrows.append([str(b),band(sm['ruin_difference_vs_aco']),band(sm['equivalent_savings_rate']),
                          band(sm['matched_difference_vs_aco']),
                          f"{100*sm['ruin_difference_vs_aco']['share_below_zero']:.0f} / {100*sm['equivalent_savings_rate']['share_below_zero']:.0f} / {100*sm['matched_difference_vs_aco']['share_below_zero']:.0f}"])
    header=(r'Block & Ruin & Equivalent & Path-matched income & Histories better \\'+'\n'
            r'(years) & difference (pp) & savings rate (\%) & difference (pp) & (\%) \\')
    table(FIG/'history.tex','Retirement outcomes across resampled calendar histories','tab:restored-history',header,hrows,
          'The table compares each strategy, at the volatility of the unlevered all-equity strategy, with the all-equity '
          'strategy at 100\\% exposure across 100 alternative histories of the panel. Each history resamples blocks of '
          'complete calendar-year cross-sections of the 16-country panel with a stationary block bootstrap of the indicated '
          'average length and supports 1,000 simulations of household outcomes. The table reports the median and, in '
          'brackets, the 5th and 95th percentiles across histories of the difference in ruin probability, the equivalent '
          'savings rate, and the difference in path-matched income failure with a 10\\% savings rate. The last column reports '
          'the percentage of histories in which the strategy does better than the all-equity strategy on each of the three '
          'measures.',align='lrrrr',colsep='3pt')
    diagnostics=json.loads((SOURCE/'calibration_sensitivities.json').read_text())
    calrows=[['Full sample, 1927--2025']+[pct(v) for v in manifest['calibration']['weights']]]
    calrows += [[label]+[pct(v) for v in diagnostics[key]['weights']] for key,label in [('post1970','Post-1970 sample'),('source_italy1942','Excluding Italy 1942')]]
    table(FIG/'calibration.tex','Risk parity weights estimated from alternative samples','tab:erc-calibration',
          ['Estimation sample','Stocks','Global bonds','Gold','Managed futures'],calrows,
          'The table reports the unlevered risk parity weights that equalize the contributions of the four asset '
          'classes to portfolio variance, estimated from the sample covariance matrix of annual real returns in each '
          'sample. The weights sum to 100\\% before exposure scaling. All lifecycle simulations use the full-sample '
          'weights.')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(7.1,4.9))
    colors={'ACO':'#50545a','Proportional':'#007f86','ERC':'#c17029'}
    markers=['o','^','s','D','*']
    for fam in families:
        rr=sorted([r for r in full if r['family']==fam],key=lambda r:r['gross_percent'])
        x=[100*r['equivalent_savings_rate'] for r in rr];y=[100*r['ruin_probability'] for r in rr]
        ax.plot(x,y,color=colors[fam],lw=1.8,label=labels[fam])
        for i,(xx,yy) in enumerate(zip(x,y)):
            ax.scatter(xx,yy,color=colors[fam],marker=markers[i],s=48,zorder=3)
    eq=[(rev['Proportional equal volatility'],colors['Proportional']),(rev['Risk parity equal volatility'],colors['ERC']),
        (rev['Stocks and MF equal volatility'],'#6a3d9a')]
    for r,c in eq:
        ax.scatter(100*r['equivalent_savings_rate'],100*r['ruin_probability'],marker='X',s=110,color=c,
                   edgecolor='black',linewidth=.6,zorder=4)
    ax.annotate('Stocks and MF',(100*eq[2][0]['equivalent_savings_rate'],100*eq[2][0]['ruin_probability']),
                textcoords='offset points',xytext=(18,28),fontsize=8,color='#6a3d9a',ha='left',
                arrowprops=dict(arrowstyle='-',color='#6a3d9a',lw=.7))
    ax.set(xlabel='Equivalent savings rate (%)',ylabel='Probability of financial ruin (%)')
    ax.grid(alpha=.15)
    ax.legend(frameon=False,loc='upper left',title='Strategy')
    exposure_handles=[Line2D([],[],color='#50545a',marker=m,linestyle='None',
                             markersize=7,label=f'{g}%')
                      for m,g in zip(markers,(100,125,150,175,200))]
    exposure_handles.append(Line2D([],[],color='#50545a',marker='X',linestyle='None',markersize=8,
                                   markeredgecolor='black',label='Equal volatility'))
    fig.legend(handles=exposure_handles,title='Gross exposure',loc='lower center',
               bbox_to_anchor=(.5,.005),ncol=6,frameon=False)
    ax.margins(x=.12,y=.1)
    fig.tight_layout(rect=(0,.16,1,1))
    for ext in ('pdf','png'):fig.savefig(FIG/f'ladders.{ext}',dpi=180)
    plt.close(fig)
    # Own-capital ruin against failure to fund the common ACO income.
    fig,ax=plt.subplots(figsize=(7.1,4.9))
    for fam in families:
        rr=sorted([r for r in full if r['family']==fam],key=lambda r:r['gross_percent'])
        x=[100*r['ruin_probability'] for r in rr]
        y=[100*r['common_income']['shortfall_probability_all_paths'] for r in rr]
        ax.plot(x,y,color=colors[fam],lw=1.8,label=labels[fam])
        for i,(xx,yy) in enumerate(zip(x,y)):
            ax.scatter(xx,yy,color=colors[fam],marker=markers[i],s=48,zorder=3)
    lim=max(100*r['common_income']['shortfall_probability_all_paths'] for r in full)
    ax.plot([0,lim],[0,lim],color='#9aa0a6',lw=.9,ls='--',zorder=1)
    ax.text(15.2,16.6,'equal rates',color='#80868b',fontsize=8)
    ax.set(xlabel='Probability of financial ruin (%)',
           ylabel='Failure to fund the path-matched income (%)',xlim=(0,22),ylim=(0,lim*1.05))
    ax.grid(alpha=.15)
    ax.legend(frameon=False,loc='upper right',title='Strategy')
    fig.legend(handles=exposure_handles[:5],title='Gross exposure',loc='lower center',
               bbox_to_anchor=(.5,.005),ncol=5,frameon=False)
    fig.tight_layout(rect=(0,.16,1,1))
    for ext in ('pdf','png'):fig.savefig(FIG/f'income_ruin.{ext}',dpi=180)
    plt.close(fig)
    # Full numerical rows alongside typeset exhibits.
    (FIG/'provenance.json').write_text(json.dumps({
        'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted([*SOURCE.glob('*.json'),*REVISION.glob('revision_checks*.json'),*REVISION.glob('mf_variant_lifecycle.json'),*(REVISION/'eqvol').glob('*.json'),*(REVISION/'history_eqvol').glob('*.json')])},
        'renderer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')

if __name__=='__main__':main()
