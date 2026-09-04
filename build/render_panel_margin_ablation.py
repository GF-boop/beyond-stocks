"""Render the complete panel comparison, ablation curves and monthly margin tables."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'paper/new_paper/figures'

def read(path):
    return json.loads((ROOT/path).read_text())

def pct(value):
    return f'{100*value:.2f}'+r'\%'

def display(name):
    labels = {'Actions domestiques':'Domestic equity',
              'Balanced domestique':'Domestic balanced',
              '90/60 local fixe':'90/60 local',
              '90/60 oblig. mondiales':'90/60 global bonds',
              'ACO 33/67, change reel cst':'ACO, constant real FX',
              '60/40 ACO/couvert':'60/40 ACO/covered bonds',
              '60/40 ACO + 33.33 Or':'60/40 ACO + 33.33 gold'}
    for family, names in (
        ('Proportional', ('40/26.67/16.67/16.67','50/33.33/20.83/20.83',
                          '60/40/25/25','70/46.67/29.17/29.17','80/53.33/33.33/33.33')),
        ('Equal-weight', ('25/25/25/25','31.25/31.25/31.25/31.25',
                         '37.5/37.5/37.5/37.5','43.75/43.75/43.75/43.75','50/50/50/50'))):
        labels.update({n+' ACO':f'{family} {g}%' for n,g in zip(names,(100,125,150,175,200))})
    return labels.get(name,name).replace('%',r'\%')

def table(name,caption,label,columns,header,rows,note):
    text=r'\begin{table}[p]\centering\scriptsize'+'\n'
    text+=f'\\caption{{{caption}}}\\label{{{label}}}\n'
    text+=r'\resizebox{\textwidth}{!}{'+'\n'+f'\\begin{{tabular}}{{{columns}}}\\toprule\n'
    text+=header+r' \\'+'\n'+r'\midrule'+'\n'
    text+='\n'.join(' & '.join(row)+r' \\' for row in rows)
    text+='\n'+r'\bottomrule\end{tabular}}'+'\n'+r'\par\smallskip\begin{minipage}{0.97\textwidth}\footnotesize '+note+r'\end{minipage}\end{table}'+'\n'
    (OUT/name).write_text(text)

def panels():
    panels={n:{r['strategy']:r for r in read(f'results/panel_concentration/{n}_n10000.json')['results']} for n in ('raw','screened','winsorized')}
    note=(r'10,000 paths per panel, seed 20260827, 1927--2025. Screened sources exclude documented disruptions, inflation outside $(-20\%,50\%)$, and Italy 1942 identified by the audit. The same exclusions apply to resident rows and reconstructed equity and bond baskets. The screen is retrospective and does not establish a historically implementable trading rule. MF inputs are unchanged. Saving matches each panel\textquotesingle s own unlevered ACO at 10\%; cross-panel saving levels therefore have different utility targets. Common seeds pair strategies within each panel, not identical paths across different panel supports.')
    rows=[]
    for name,r in panels['raw'].items():
        s=panels['screened'][name]
        rows.append([display(name),*(pct(x[k]) for x in (r,s) for k in ('volatility','ruin_probability','equivalent_savings_rate'))])
    table('panel_full_comparison.tex','Complete raw and source-screened portfolio comparison','tab:corrected-main','lrrrrrr',
          'Portfolio & Raw vol. & Raw ruin & Raw saving & Screen vol. & Screen ruin & Screen saving',rows,note)
    rows=[]
    for name,r in panels['raw'].items():
        s=panels['screened'][name]
        rows.append([display(name),*(pct(x[k]) for x in (r,s) for k in ('mean_return','volatility','first_percentile_return'))])
    table('panel_full_moments.tex','Complete annual return moments under both panels','tab:panel-moments','lrrrrrr',
          'Portfolio & Raw mean & Raw vol. & Raw 1st pct. & Screen mean & Screen vol. & Screen 1st pct.',rows,note)
    rows=[[display(n),*(pct(r[k]) for k in ('volatility','ruin_probability','equivalent_savings_rate'))] for n,r in panels['winsorized'].items()]
    table('panel_winsorized.tex',r'Portfolio comparison after 0.5\% sleeve winsorization','tab:panel-winsor','lrrr',
          'Portfolio & Volatility & Ruin & Saving',rows,
          r'Each of the five risky sleeve return columns is clipped at its pooled 0.5th and 99.5th percentiles before leverage and costs. Cash and inflation are unchanged. All 1,561 resident observations remain. Quantiles use the full sample; this is a statistical sensitivity, not an investability screen. Each portfolio is evaluated against the winsorized ACO reference.')

def ablations(stem, output):
    data=read(stem)
    results={r['strategy']:r for r in data['results']}
    fig,axes=plt.subplots(1,2,figsize=(10,4.4),sharey=True)
    colours=['#2166ac','#d95f02','#1b9e77','#7570b3']
    for ax,family in zip(axes,('Proportional','Equal-weight')):
        for suffix,label,c in zip(('', ' without global bonds',' without gold',' without managed futures'),
                                  ('Four sleeves','Without global bonds','Without gold','Without managed futures'),colours):
            pts=[results[f'{family} four-sleeve, {g}%{suffix}'] for g in (100,125,150,175,200)]
            x=[100*r['equivalent_savings_rate'] for r in pts]; y=[100*r['ruin_probability'] for r in pts]
            ax.plot(x,y,'-',color=c,label=label,lw=1.4)
            for marker,a,b in zip(('o','^','s','D','*'),x,y):
                ax.plot(a,b,marker=marker,color=c,ms=5,linestyle='none')
        pts=[results['ACO 33/67' if g==100 else f'ACO 33/67 {g}%'] for g in (100,125,150,175,200)]
        ax.plot([r['equivalent_savings_rate']*100 for r in pts],[r['ruin_probability']*100 for r in pts],'--',color='#333333',label='ACO 33/67',lw=1)
        for marker,r in zip(('o','^','s','D','*'),pts):
            ax.plot(100*r['equivalent_savings_rate'],100*r['ruin_probability'],marker=marker,color='#333333',ms=5,linestyle='none')
        ax.set_title(family); ax.set_xlabel('Equivalent saving (% of income)'); ax.grid(alpha=.2)
        ax.spines[['top','right']].set_visible(False)
    axes[0].set_ylabel('Retirement ruin (%)')
    axes[0].legend(fontsize=7,loc='upper left')
    axes[1].legend(handles=[Line2D([],[],color='#555555',marker=m,linestyle='none',label=f'{g}%') for m,g in zip(('o','^','s','D','*'),(100,125,150,175,200))],title='Gross exposure',fontsize=7,title_fontsize=8,loc='upper left')
    fig.tight_layout();fig.savefig(OUT/f'{output}.pdf');fig.savefig(OUT/f'{output}.png',dpi=180);plt.close(fig)

def margin():
    data=read('results/margin_monthly/results.json')
    rows=[]
    for r in data['results']:
        if r['maintenance'] not in (.25,.4): continue
        rows.append([r['family'],str(r['gross_percent']),pct(r['maintenance']),
                     str(len(r['observed_monthly_breach_years'])),str(len(r['observed_annual_breach_years'])),
                     pct(r['minimum_month_end_equity_ratio'])])
    table('margin_monthly.tex','Month-end and year-end maintenance tests on identical USD proxy paths',
          'tab:monthly-margin','lrrrrr',r'Portfolio & Gross (\%) & Maintenance & Monthly years & Annual years & Min. equity share',rows,
          r'1970--2025, 56 complete years. Entries count historical years with at least one crossing. Sleeve quantities are fixed within each year; exposure resets annually. VTI/VXUS total-return simulations supply 33/67 equities; IEF supplies a US Treasury proxy for global bonds; gold is spot less custody, MF is the reconstructed net USD series. Debt accrues USD cash plus 30 bp/year. The two tests use the same asset and debt paths. Monthly closes do not measure intramonth extrema or simulate forced liquidation. Bootstrap outputs and the 35\% threshold are provided in the replication dataset.')

def main():
    OUT.mkdir(exist_ok=True)
    panels()
    ablations('results/sleeve_ablation_ladders_n10000.json','ablation_saving_ruin')
    ablations('results/panel_concentration/screened_ablation_ladders_n10000.json','ablation_saving_ruin_screened')
    margin()

if __name__=='__main__': main()
