"""Accounting invariants for monthly maintenance tests and sleeve ladders."""
import unittest
import numpy as np
from monthly_margin_diagnostic import equity_ratios
from sleeve_ablation import reallocate

class AccountingTest(unittest.TestCase):
    def test_monthly_crossing_hidden_by_annual_recovery(self):
        returns=np.zeros((1,12,1))
        returns[0,0,0]=-.4
        returns[0,1,0]=1/.6-1
        ratios=equity_ratios(returns,np.zeros((1,12)),np.ones(1),2)
        self.assertLess(ratios[0,0],.25)
        self.assertGreater(ratios[0,-1],.25)

    def test_no_debt_means_full_equity_share(self):
        ratios=equity_ratios(np.full((1,12,1),-.2),np.zeros((1,12)),np.ones(1),1)
        np.testing.assert_allclose(ratios,1)

    def test_ablation_preserves_each_exposure(self):
        for level in (1,1.25,1.5,1.75,2):
            for removed in (1,2,3):
                result=reallocate((level/4,)*4,removed)
                self.assertEqual(result[removed],0)
                self.assertAlmostEqual(sum(result),level)

if __name__=='__main__': unittest.main()
