"""Generate paper tables directly from matched-leverage replication outputs."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'paper/new_paper/figures'
P = '80/53.33/33.33/33.33 ACO'
E = '50/50/50/50 ACO'
A = 'ACO 33/67 200%'

def read(path):
    return json.loads((ROOT/path).read_text())

def pct(v):
    return '--' if v is None else f'{100*v:.2f}\\%'

def table(filename, caption, label, columns, header, rows, note):
    text = '\\begin{table}[H]\n\\centering\\small\n'
    text += f'\\caption{{{caption}}}\\label{{{label}}}\n'
    text += f'\\begin{{tabular}}{{{columns}}}\\toprule\n{header} \\\\\n\\midrule\n'
    text += '\n'.join(' & '.join(row) + r' \\' for row in rows)
    text += '\n\\bottomrule\\end{tabular}\n'
    text += '\\par\\smallskip\\begin{minipage}{0.96\\textwidth}\\footnotesize\n'+note
    text += '\n\\end{minipage}\\end{table}\n'
    OUT.mkdir(exist_ok=True)
    (OUT/filename).write_text(text)

def main():
    data = {r['strategy']:r for r in read('results/main_ladders_n10000.json')['results']}
    rows=[]
    for level in (100,125,150,175,200):
        name='ACO 33/67' if level==100 else f'ACO 33/67 {level}%'
        r=data[name]
        rows.append([str(level)+r'\%',pct(r['volatility']),pct(r['equivalent_savings_rate']),pct(r['ruin_probability'])])
    table('aco_ladder.tex','Fixed leverage ladder for ACO 33/67','tab:aco-ladder','rrrr',
          'Gross & Volatility & Equiv. saving & Ruin', rows,
          r'10,000 paired paths, 1927--2025. Borrowing costs the resident bill plus the same 30 bp real deduction used for the diversified portfolios. The utility target remains ACO at 100\% exposure and 10\% saving.')
    rows=[]
    legacy=read('paper/figures/gamma_sensitivity.json')['results']
    fixed=read('results/gamma_fixed_theta_n10000.json')['results']
    for mode,results in [('Joint calibration',legacy),('Fixed annual bequest',fixed)]:
        for r in results:
            rows.append([mode,str(r['gamma']),*(pct(r['portfolios'][n]['equivalent_savings_rate']) for n in (A,P,E))])
    table('aco_gamma.tex',r'Risk aversion and the saving requirement at 200\% exposure','tab:aco-gamma','lrrrr',
          r'Calibration & $\gamma$ & ACO & Proportional & Equal-weight',rows,
          r'10,000 paired paths; ACO at 100\% requires 10\% saving at each $\gamma$. The joint calibration uses $\theta=2360\,12^{3.84-\gamma}$; the fixed-annual calibration keeps $\theta=2360$. At $\gamma=3.84$ both coincide. All portfolios keep their weights and exposure fixed. Ruin is identical across preference calibrations; its baseline levels appear in the leverage ladders.')
    policy=read('paper/figures/policy_sensitivity.json')
    rows=[]
    for key,value in policy.items():
        if isinstance(value,list) and value and isinstance(value[0],dict) and 'portfolios' in value[0]:
            for r in value:
                rows.append([pct(r['contribution_rate']),pct(r['withdrawal_rate']),
                             pct(r['portfolios'][A]['ruin']),pct(r['portfolios'][A]['equivalent_savings_rate']),
                             pct(r['portfolios'][P]['equivalent_savings_rate']),pct(r['portfolios'][E]['equivalent_savings_rate'])])
    table('aco_policy.tex','Levered ACO in the household-policy sensitivities','tab:aco-policy','rrrrrr',
          'Saving & Withdrawal & ACO ruin & ACO equiv. & Prop. equiv. & Equal equiv.',rows,
          r'All three portfolios have 200\% exposure. The reference is unlevered ACO at the contribution and withdrawal rates in each row. The diversified ruin rates are reported in Table~\ref{tab:policy-sensitivity}.')
    costs=read('paper/figures/central_cost_sensitivity.json')
    rows=[]
    for key,value in costs.items():
        if isinstance(value,list) and value and isinstance(value[0],dict) and 'portfolios' in value[0]:
            for r in value:
                rows.append([pct(r['spread']),pct(r.get('fx_hedge_cost',r.get('hedge_cost'))),
                             pct(r['portfolios'][A]['ruin_probability']),pct(r['portfolios'][A]['equivalent_savings_rate']),
                             pct(r['portfolios'][P]['ruin_probability']),pct(r['portfolios'][E]['ruin_probability'])])
    table('aco_cost.tex','Financing and hedge-cost sensitivities at matched exposure','tab:aco-cost','rrrrrr',
          'Spread & Hedge cost & ACO ruin & ACO equiv. & Prop. ruin & Equal ruin',rows,
          r'All three portfolios have 200\% exposure. ACO equities are unhedged, so hedge-cost changes affect only the diversified sleeves. Equivalent saving targets unlevered ACO at 10\% saving.')
    rows=[]
    names=['raw_corrected_fixed_notional_aco','raw_corrected_fixed_notional_restart',
           'raw_corrected_ideal_aco','legacy_return_filter_fixed_notional_aco','war_screen_fixed_notional_aco']
    labels=['Baseline','Block restart','Full-value hedge','Return screen','War screen']
    for stem,label in zip(names,labels):
        result={r['strategy']:r for r in read(f'results/method_review/final/{stem}_n10000.json')['results']}
        rows.append([label,*(pct(result[n]['ruin_probability']) for n in ('ACO 33/67',A,P,E))])
    loo=read('paper/figures/source_country_sensitivity.json')['results']
    rows.append(['Source-country range',*(f"{min(r['portfolios'][n]['ruin_probability'] for r in loo)*100:.2f}--{max(r['portfolios'][n]['ruin_probability'] for r in loo)*100:.2f}\\%" for n in ('ACO 33/67',A,P,E))])
    table('aco_methods.tex','Construction checks including levered ACO','tab:aco-methods','lrrrr',
          r'Specification & ACO 100\% & ACO 200\% & Prop. 200\% & Equal 200\%',rows,
          r'Retirement ruin; 10,000 paired paths for construction checks and 5,000 per source-country omission. All other assumptions follow the corresponding diagnostic.')

if __name__=='__main__':
    main()
