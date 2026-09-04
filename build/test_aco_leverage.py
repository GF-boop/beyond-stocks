"""Accounting checks independent of the simulated outcome rankings."""
import unittest
import math
from compare_fixed_stacked_utility import return_functions

class LeverageAccounting(unittest.TestCase):
    def test_borrowing_is_resident_cash_and_spread_only(self):
        row = dict(domestic=-0.4, international=0.2, bill=0.07,
                   world_bill=0.99, world_bond_fixed_notional=0.1,
                   trend_fixed_notional=0.1)
        aco = .33*(-.4) + .67*.2
        for spread in (0, .003, .03):
            f = return_functions([row], spread, .0085, .005, 0, .001)
            for percent in (125, 150, 175, 200):
                gross = percent/100
                self.assertAlmostEqual(f[f'ACO 33/67 {percent}%'](row),
                    gross*aco-(gross-1)*(.07+spread))
                self.assertAlmostEqual(f[f'ACO 33/67 {percent}%'](row)-aco,
                    (gross-1)*(aco-.07-spread))

    def test_friction_does_not_charge_unhedged_equity(self):
        row = dict(domestic=.05, international=.1, bill=.02,
                   trend_fixed_notional=.1)
        a = return_functions([row], .003, 0, 0, 0, 0)
        b = return_functions([row], .003, .5, .5, .5, .5)
        self.assertEqual(a['ACO 33/67 200%'](row), b['ACO 33/67 200%'](row))

if __name__ == '__main__':
    unittest.main()
