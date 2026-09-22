"""Render the monthly maintenance-margin table used by the current paper."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'paper/new_paper/figures'

def read(path):
    return json.loads((ROOT/path).read_text())

def pct(value):
    return f'{100*value:.2f}'+r'\%'

def table(name,caption,label,columns,header,rows,note):
    text=r'\begin{table}[p]\centering\scriptsize'+'\n'
    text+=f'\\caption{{{caption}}}\\label{{{label}}}\n'
    text+=r'\resizebox{\textwidth}{!}{'+'\n'+f'\\begin{{tabular}}{{{columns}}}\\toprule\n'
    text+=header+r' \\'+'\n'+r'\midrule'+'\n'
    text+='\n'.join(' & '.join(row)+r' \\' for row in rows)
    text+='\n'+r'\bottomrule\end{tabular}}'+'\n'+r'\par\smallskip\begin{minipage}{0.97\textwidth}\footnotesize '+note+r'\end{minipage}\end{table}'+'\n'
    (OUT/name).write_text(text)

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
    margin()

if __name__=='__main__': main()
