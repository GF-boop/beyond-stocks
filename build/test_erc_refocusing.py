import numpy as np
import pytest
from erc_refocusing import erc_weights, build_functions, calibration, PROP, source_exclusion_rows
from sleeve_ablation import function_for
from compare_fixed_stacked_utility import return_functions
from compare_gold_trend_equal_vol import DEFAULT_TREND_FEE, DEFAULT_TREND_COST
from replicate_extended import read_panel
from pathlib import Path

def test_diagonal_inverse_vol():
    sd=np.array([.1,.2,.3,.4])
    np.testing.assert_allclose(erc_weights(np.diag(sd**2)),(1/sd)/(1/sd).sum(),atol=1e-8)

def test_correlated_and_scale_invariance():
    a=np.array([[2.,.1,-.3],[.1,1.,.2],[-.3,.2,3.]])
    w=erc_weights(a)
    np.testing.assert_allclose(w*(a@w)/(w@a@w),np.ones(3)/3,atol=1e-7)
    np.testing.assert_allclose(w,erc_weights(a*100),atol=1e-8)

def test_invalid_covariance():
    with pytest.raises(ValueError): erc_weights(np.array([[1.,2.],[2.,1.]]))

def test_source_exclusion_also_removes_resident_row():
    path=Path(__file__).resolve().parents[1]/'results/method_review/source_exclusions/source_event_italy_1942/replication-panel-trend.csv'
    rows=source_exclusion_rows(path)
    assert len(rows)==1560
    assert not any(r['country']=='Italy' and r['year']==1942 for r in rows)
    assert any(r['country']=='Italy' and r['year']==1943 for r in rows)

def test_panel_accounting_and_gross():
    rows=read_panel(str(Path(__file__).resolve().parents[1]/'data/replication-panel-trend.csv'))
    w=np.array(calibration(rows)['weights'])
    f,d=build_functions(w,ablations=True)
    canonical=return_functions(rows,.003,DEFAULT_TREND_FEE,DEFAULT_TREND_COST,0.,.001)
    for name,old in [('ACO 33/67','ACO 33/67'),('ACO 175%','ACO 33/67 175%'),('Proportional 175%','70/46.67/29.17/29.17 ACO')]:
        np.testing.assert_allclose([f[name](r) for r in rows],[canonical[old](r) for r in rows],atol=1e-12)
    for item in d.values():
        assert abs(sum(item['weights'])-item['gross_percent']/100)<1e-12
    stressed,_=build_functions(w,haircut=.03)
    for r in rows[::100]:
        assert abs(f['ERC 175%'](r)-stressed['ERC 175%'](r)-1.75*w[3]*.03)<1e-12
