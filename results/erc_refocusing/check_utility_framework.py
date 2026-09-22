"""Deterministic checks of manuscript identities; no sampled households."""
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import brentq

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build'))
from compare_lifecycle_utility import build_scenario, evaluate

def scenario(returns,early=False):
    path=[{'r':float(r)} for r in returns]
    return build_scenario(path,{'test':lambda r:r['r']},
                          50 if early else 88,52 if early else 95,
                          [42000.]*40,[36000.]*40)

def value(returns,s,early=False):
    return evaluate(scenario(returns,early),'test',s).utility

def central(f,x,step=1e-5):
    return (f(x+step)-f(x-step))/(2*step)

def check_close(a,b):
    np.testing.assert_allclose(a,b,rtol=2e-5,atol=1e-19)

def main():
    t=np.arange(76)
    assets=np.column_stack([.06+.09*np.sin(t),.025+.035*np.cos(t),
                            .03+.08*np.sin(t+.9),.045+.05*np.cos(t+.3)])
    bill=.01+.005*np.sin(t/3)
    v=np.array([.4,4/15,1/6,1/6]);gross=1.75;spread=.003;s=.1
    def returns(v,g):return bill+g*(assets@v-bill)-max(g-1,0)*spread
    base=returns(v,gross)
    checks=[]
    for early in (False,True):
        sc=scenario(base,early)
        a=evaluate(sc,'test',s);b=evaluate(sc,'test',2*s)
        check_close(b.bequest,2*a.bequest)
        check_close(b.retirement_wealth,2*a.retirement_wealth)
        assert a.ruined==b.ruined
        assert b.utility>a.utility
        # Marginal utility weights incorporate the retirement-target response
        # because each dated bump rebuilds the original engine's scenario.
        m=np.array([central(lambda z,i=i:value(base+np.eye(1,len(base),i)[0]*z,s,early),0.)
                    for i in range(len(base))])
        h=np.array([-1.,0.,0.,1.])
        direct_h=central(lambda z:value(returns(v+z*h,gross),s,early),0.)
        direct_g=central(lambda g:value(returns(v,g),s,early),gross)
        check_close(direct_h,m@(gross*(assets@h)))
        check_close(direct_g,m@(assets@v-bill-spread))
        vs=central(lambda z:value(base,z,early),s)
        assert vs>0
        target=value(base,s,early)
        def equivalent(z):
            rr=returns(v+z*h,gross)
            return brentq(lambda q:value(rr,q,early)-target,.001,.9,xtol=1e-13)
        implicit=central(equivalent,0.,step=1e-4)
        check_close(implicit,-direct_h/vs)
        checks.append({'early_death':early,'composition_derivative':float(direct_h),
                       'exposure_derivative':float(direct_g),
                       'saving_derivative':float(vs),'equivalent_saving_slope':float(implicit)})
    # Non-smooth depletion branch: homogeneity and failure invariance still hold.
    stressed=base.copy();stressed[40:48]=-.4
    sc=scenario(stressed)
    low=evaluate(sc,'test',.1);high=evaluate(sc,'test',.2)
    assert low.ruined and high.ruined
    check_close(high.bequest,2*low.bequest)
    check_close(high.retirement_wealth,2*low.retirement_wealth)
    print('PASS: wealth scaling, own-target ruin invariance, increasing utility,')
    print('composition/exposure chain rules and implicit saving derivative;')
    print('retired, pre-retirement-death and depleted deterministic paths.')
    print(checks)

if __name__=='__main__':main()
