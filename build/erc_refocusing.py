"""Retrospective ERC within the existing ACO-style lifecycle experiment."""
from pathlib import Path
import argparse
import hashlib
import json
import time
import subprocess
import numpy as np
from scipy.optimize import minimize

from sleeve_ablation import function_for, reallocate
from compare_fixed_stacked_utility import BENCHMARK_NAME, return_functions
from compare_gold_trend_equal_vol import DEFAULT_TREND_FEE, DEFAULT_TREND_COST
from compare_lifecycle_utility import (
    BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE, evaluate_batch,
    expected_utility, equivalent_savings_rate, clear_utility_batches)
from common_consumption_target import evaluate as common_evaluate
from historical_uncertainty import scenarios_for
from replicate_extended import read_panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/erc_refocusing'
PANEL = ROOT / 'data/replication-panel-trend.csv'
PROP = np.array([.4, 4/15, 1/6, 1/6])
LEVELS = (100,125,150,175,200)
SEED = 20260827

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def erc_weights(cov):
    cov = np.asarray(cov, dtype=float)
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1] or not np.allclose(cov,cov.T):
        raise ValueError('Expected symmetric square covariance')
    if not np.isfinite(cov).all() or np.linalg.eigvalsh(cov).min() <= 0:
        raise ValueError('Positive definite finite covariance required')
    scaled = cov / np.max(np.diag(cov))
    n = len(cov)
    # Positive log coordinates avoid boundary clipping; analytic gradient.
    def fg(y):
        x = np.exp(y)
        sx = scaled @ x
        return .5*x@sx-y.sum()/n, x*sx-1/n
    fit = minimize(fg, np.log(1/np.sqrt(n*np.diag(scaled))), jac=True,
                   method='BFGS', options={'gtol':1e-11,'maxiter':2000})
    x = np.exp(fit.x)
    w = x/x.sum()
    rc = w*(cov@w)/(w@cov@w)
    if not np.isfinite(w).all() or np.max(abs(rc-1/n)) > 1e-7:
        raise RuntimeError(f'ERC failed: {fit.message}; RC={rc}')
    return w

def calibration(rows):
    fns = [function_for(tuple(np.eye(4)[i]),.003,DEFAULT_TREND_FEE,
                        DEFAULT_TREND_COST,.001) for i in range(4)]
    values = np.array([[f(r) for f in fns] for r in rows])
    cov = np.cov(values,rowvar=False,ddof=1)
    w = erc_weights(cov)
    return {'weights':w.tolist(),'covariance':cov.tolist(),
            'risk_shares':(w*(cov@w)/(w@cov@w)).tolist(),
            'eigenvalues':np.linalg.eigvalsh(cov).tolist(),
            'observations':len(rows),'years':[min(r['year'] for r in rows),max(r['year'] for r in rows)]}

def source_exclusion_rows(path):
    # The reconstructed CSV removes the source from global baskets. The old
    # workflow separately excluded its resident row at simulation time.
    rows=read_panel(str(path))
    selected=[r for r in rows if not (r['country']=='Italy' and r['year']==1942)]
    if len(rows)-len(selected)!=1:
        raise ValueError('Expected exactly one Italy 1942 resident observation')
    return selected

def build_functions(erc, levels=LEVELS, spread=.003, haircut=0., ablations=False):
    functions, definitions = {}, {}
    for family, base in [('ACO',np.array([1.,0,0,0])),('Proportional',PROP),('ERC',erc)]:
        for level in levels:
            name = BENCHMARK_NAME if family=='ACO' and level==100 else f'{family} {level}%'
            w = base*level/100
            fn = function_for(tuple(w),spread,DEFAULT_TREND_FEE,DEFAULT_TREND_COST,.001)
            functions[name] = lambda r, fn=fn, h=w[3]*haircut: fn(r)-h
            definitions[name] = {'family':family,'gross_percent':level,'weights':w.tolist(),'removed':None}
            if ablations and level==175 and family!='ACO':
                for i,sleeve in enumerate(('bonds','gold','MF'),1):
                    aw = reallocate(tuple(w),i)
                    an = f'{name} without {sleeve}'
                    af = function_for(aw,spread,DEFAULT_TREND_FEE,DEFAULT_TREND_COST,.001)
                    functions[an] = lambda r, fn=af, h=aw[3]*haircut: fn(r)-h
                    definitions[an] = {'family':family,'gross_percent':level,'weights':list(aw),'removed':sleeve}
    if BENCHMARK_NAME not in functions:
        functions[BENCHMARK_NAME] = function_for((1.,0,0,0),spread,DEFAULT_TREND_FEE,DEFAULT_TREND_COST,.001)
        definitions[BENCHMARK_NAME] = {'family':'ACO','gross_percent':100,'weights':[1,0,0,0],'removed':None}
    return functions, definitions

def interval(events,reference):
    d = events.astype(float)-reference.astype(float)
    mean = float(d.mean()); se = float(d.std(ddof=1)/np.sqrt(len(d)))
    return {'difference':mean,'ci95':[mean-1.96*se,mean+1.96*se]}

def run_case(label,rows,erc,runs,levels=LEVELS,spread=.003,haircut=0.,ablations=False):
    start=time.monotonic()
    functions, definitions=build_functions(erc,levels,spread,haircut,ablations)
    # Cache only return arithmetic; preserve the original RNG draw order exactly.
    for i,r in enumerate(rows): r['_erc_idx']=i
    values={name:np.array([fn(r) for r in rows]) for name,fn in functions.items()}
    functions={name:(lambda r,v=v: float(v[r['_erc_idx']])) for name,v in values.items()}
    clear_utility_batches()
    scenarios=scenarios_for(rows,functions,runs,10.,SEED)
    print(f'{label}: {runs} paired paths in {time.monotonic()-start:.1f}s',flush=True)
    outcomes={n:evaluate_batch(scenarios,n,BASE_SAVINGS_RATE,WITHDRAWAL_RATE,GAMMA) for n in functions}
    reference=outcomes[BENCHMARK_NAME]
    target=float(reference.utility.mean())
    common_target=.04*reference.retirement_wealth
    common={n:common_evaluate(scenarios,n,common_target,True) for n in functions}
    results=[]
    for n in functions:
        o=outcomes[n]
        check=common_evaluate(scenarios,n,.04*o.retirement_wealth,True)
        np.testing.assert_array_equal(check['events'],o.ruined)
        c=common[n]
        record={'strategy':n,**definitions[n],
                'ruin_probability':float(o.ruined.mean()),
                'equivalent_savings_rate':equivalent_savings_rate(scenarios,n,target,GAMMA,WITHDRAWAL_RATE),
                'annual_volatility':float(values[n].std(ddof=1)),
                'mean_return':float(values[n].mean()),
                'nonpositive_gross_rows':int(np.sum(values[n]<=-1)),
                'paired_ruin_vs_aco':interval(o.ruined,reference.ruined),
                'common_income':{k:v for k,v in c.items() if k!='events'},
                'paired_common_vs_aco':interval(c['events'],common[BENCHMARK_NAME]['events']),
                'own_target_event_mismatches':0}
        if definitions[n]['removed']:
            full=f"{definitions[n]['family']} 175%"
            record['ablation_ruin_without_minus_complete']=interval(o.ruined,outcomes[full].ruined)
        results.append(record)
        print(f"{label} {n}: ruin {record['ruin_probability']:.2%}, saving {record['equivalent_savings_rate']:.2%}, common {c['shortfall_probability_all_paths']:.2%}",flush=True)
    audit={}
    if label=='baseline' and runs==10000:
        old=json.loads((ROOT/'results/main_ladders_n10000.json').read_text())
        lookup={r['strategy']:r for r in old['results']}
        prop_names={100:'40/26.67/16.67/16.67 ACO',125:'50/33.33/20.83/20.83 ACO',150:'60/40/25/25 ACO',175:'70/46.67/29.17/29.17 ACO',200:'80/53.33/33.33/33.33 ACO'}
        for r in results:
            if r['removed'] or r['family']=='ERC': continue
            oldname=prop_names[r['gross_percent']] if r['family']=='Proportional' else (BENCHMARK_NAME if r['gross_percent']==100 else f"ACO 33/67 {r['gross_percent']}%")
            for k in ('ruin_probability','equivalent_savings_rate'):
                np.testing.assert_allclose(r[k],lookup[oldname][k],rtol=0,atol=1e-7)
            audit[r['strategy']]='matches archived baseline within 1e-7'
    clear_utility_batches()
    return {'label':label,'runs':runs,'seed':SEED,'observations':len(rows),
            'period':[min(r['year'] for r in rows),max(r['year'] for r in rows)],
            'spread':spread,'mf_haircut':haircut,'weights_reestimated':False,
            'results':results,'baseline_reproduction':audit,'elapsed_seconds':time.monotonic()-start}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--runs',type=int,default=100)
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--tag',default='')
    args=parser.parse_args()
    if args.tag and not args.tag.replace('_','').isalnum(): raise ValueError('Invalid tag')
    dest=OUT/(f'n{args.runs}'+('_'+args.tag if args.tag else ''))
    dest.mkdir(parents=True,exist_ok=False)
    rows=read_panel(str(PANEL)); assert len(rows)==1561
    cal=calibration(rows); erc=np.array(cal['weights'])
    sources=[PANEL,OUT/'PROTOCOL.md',*sorted((ROOT/'build').glob('*.py')),
             *sorted((ROOT/'data').glob('*.json'))]
    manifest={'inputs_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sources},
              'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'git_status':subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),
              'runs':args.runs,'seed':SEED,'trend_fee':DEFAULT_TREND_FEE,'trend_cost':DEFAULT_TREND_COST,
              'calibration':cal,'retrospective':True}
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Frozen ERC weights',erc,flush=True)
    cases=[('baseline',rows,dict(ablations=True))]
    if args.full:
        cases += [(f'spread_{bp}bp',rows,dict(levels=(175,),spread=bp/10000)) for bp in (100,200,300)]
        cases += [(f'mf_minus_{bp}bp',rows,dict(levels=(175,),haircut=bp/10000)) for bp in (300,600)]
        later=[r for r in rows if r['year']>=1970]
        cases.append(('post1970',later,dict(levels=(175,))))
        source=ROOT/'results/method_review/source_exclusions/source_event_italy_1942/replication-panel-trend.csv'
        if not source.exists(): raise FileNotFoundError(source)
        excluded=source_exclusion_rows(source)
        cases.append(('source_italy1942',excluded,dict(levels=(175,))))
        diagnostics={'post1970':calibration(later),'source_italy1942':calibration(excluded),
                     'source_panel_sha256':digest(source)}
        (dest/'calibration_sensitivities.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
    for label,selected,kwargs in cases:
        result=run_case(label,selected,erc,args.runs,**kwargs)
        (dest/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n')
    (dest/'completion.json').write_text(json.dumps({'complete':True,'cases':[c[0] for c in cases]},indent=2)+'\n')

if __name__=='__main__': main()
