"""Cheap deterministic boundary checks; no simulation or upstream writes."""
import unittest

from historical_availability import STARTS, eligible
from sleeve_ablation import reallocate


class AvailabilityTests(unittest.TestCase):
    def test_sector_boundaries(self):
        for sector, before, first in [('currency','1972-05','1972-06'),
                                      ('bond','1977-08','1977-09'),
                                      ('equity','1982-04','1982-05')]:
            self.assertFalse(eligible('asset',sector,before,False,True))
            self.assertTrue(eligible('asset',sector,first,False,True))
            self.assertEqual(STARTS[sector],first)

    def test_gold_inside_mf(self):
        self.assertFalse(eligible('METAL_GOLD','commodity','1974-12',True,True))
        self.assertTrue(eligible('METAL_GOLD','commodity','1975-01',True,True))
        self.assertTrue(eligible('WHEAT','commodity','1927-01',True,True))

    def test_no_mask(self):
        for sector in STARTS:
            self.assertTrue(eligible('METAL_GOLD',sector,'1927-01',False,False))

    def test_joint_reallocation(self):
        w = (.7, .4666666666666667, .2916666666666667, .2916666666666667)
        new = reallocate(reallocate(w,2),3)
        self.assertAlmostEqual(sum(new),1.75)
        self.assertEqual(new[2:],(0.,0.))
        self.assertAlmostEqual(new[0]/new[1],w[0]/w[1])


if __name__ == '__main__':
    unittest.main()
