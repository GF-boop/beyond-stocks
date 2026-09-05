import unittest

import numpy as np

from common_consumption_target import evaluate
from compare_lifecycle_utility import Scenario, clear_utility_batches, evaluate_batch


class CommonTargetTests(unittest.TestCase):
  def tearDown(self):
    clear_utility_batches()

  def test_own_capital_target_reproduces_main_failure_events(self):
    scenarios = [
        Scenario(64, 64, 20000, 15000, {"test": 1000}, {"test": ()}),
        Scenario(67, 67, 20000, 15000, {"test": 1000}, {"test": (-1., 0., 0.)}),
        Scenario(67, 67, 20000, 15000, {"test": 2000}, {"test": (.1, .1, .1)}),
    ]
    main = evaluate_batch(scenarios, 'test', .1)
    common = evaluate(scenarios, 'test', .04 * main.retirement_wealth, return_events=True)
    np.testing.assert_array_equal(common['events'], main.ruined)
    self.assertAlmostEqual(common['shortfall_probability_all_paths'], 1/3)
    self.assertAlmostEqual(common['shortfall_probability'], 1/2)

  def test_pre_retirement_death_is_excluded_and_funding_conserves_target(self):
    scenarios = [
        Scenario(64, 64, 0, 0, {"test": 1000}, {"test": ()}),
        Scenario(66, 66, 0, 0, {"test": 1000}, {"test": (0, 0)}),
    ]
    result = evaluate(scenarios, "test", np.array([60., 60.]))
    self.assertEqual(result["retired_path_share"], 0.5)
    self.assertEqual(result["shortfall_probability"], 1.)
    self.assertAlmostEqual(result["mean_financial_funding_ratio"], 100/120)
    self.assertAlmostEqual(result["mean_shortfall_share"], 20/120)
    self.assertAlmostEqual(
        result["implicit_withdrawal_rate_positive_capital"]["median"], .6)


if __name__ == "__main__":
  unittest.main()
