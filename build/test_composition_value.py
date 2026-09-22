#!/usr/bin/env python3
"""Tests for the composition-value experiment."""

from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_lifecycle_utility import (  # noqa: E402
    BASE_SAVINGS_RATE,
    GAMMA,
    WITHDRAWAL_RATE,
    Scenario,
    _utility_batch,
    clear_utility_batches,
    evaluate_batch,
)
from composition_value import (  # noqa: E402
    composition_value,
    default_experiments,
    instrument_series,
    retirement_adjoint,
    scenarios_with_records,
    unit_sleeves,
    working_adjoint,
)
from compare_fixed_stacked_utility import BENCHMARK_NAME  # noqa: E402
from compare_gold_trend_equal_vol import DEFAULT_TREND_COST, DEFAULT_TREND_FEE  # noqa: E402
from replicate_extended import read_panel  # noqa: E402


def _scenario(unit, returns, first_death=80, last_death=85):
    return Scenario(
        first_death=first_death,
        last_death=last_death,
        couple_social_security=20_000.0,
        survivor_social_security=15_000.0,
        retirement_unit_wealth={"base": unit},
        retirement_returns={"base": tuple(returns)},
    )


def test_retirement_adjoint_matches_finite_difference():
    clear_utility_batches()
    returns = [0.08, -0.05, 0.12, 0.03, -0.10, 0.06]
    unit = 1_000_000.0
    gamma = 2.0
    batch = _utility_batch([_scenario(unit, returns)], "base")
    mu = retirement_adjoint(batch, BASE_SAVINGS_RATE, gamma, WITHDRAWAL_RATE)["mu"][:, 0]

    eps = 1e-6
    for index in range(len(returns)):
        plus = list(returns)
        minus = list(returns)
        plus[index] += eps
        minus[index] -= eps
        up = evaluate_batch([_scenario(unit, plus)], "base", BASE_SAVINGS_RATE, WITHDRAWAL_RATE, gamma).utility[0]
        down = evaluate_batch([_scenario(unit, minus)], "base", BASE_SAVINGS_RATE, WITHDRAWAL_RATE, gamma).utility[0]
        finite_difference = (up - down) / (2 * eps)
        assert abs(finite_difference - mu[index]) <= 1e-6 * max(1.0, abs(finite_difference))


def test_utility_slope_matches_finite_difference():
    clear_utility_batches()
    returns = [0.08, -0.05, 0.12, 0.03, -0.10, 0.06]
    unit = 1_000_000.0
    gamma = 2.0
    scenario = _scenario(unit, returns)
    batch = _utility_batch([scenario], "base")
    adjoint = retirement_adjoint(batch, BASE_SAVINGS_RATE, gamma, WITHDRAWAL_RATE)
    analytic = float(np.mean(adjoint["lam_unit"] * batch.retirement_wealth_unit / BASE_SAVINGS_RATE))

    eps = 1e-6
    up = evaluate_batch([scenario], "base", BASE_SAVINGS_RATE + eps, WITHDRAWAL_RATE, gamma).utility[0]
    down = evaluate_batch([scenario], "base", BASE_SAVINGS_RATE - eps, WITHDRAWAL_RATE, gamma).utility[0]
    finite_difference = (up - down) / (2 * eps)
    assert abs(finite_difference - analytic) <= 1e-6 * max(1.0, abs(finite_difference))


def test_working_adjoint_matches_finite_difference():
    clear_utility_batches()
    gamma = 2.0
    working_returns = [0.07, -0.04, 0.10, 0.02, -0.08, 0.05, 0.03, -0.02] * 5
    retirement_returns = [0.06, -0.03, 0.09, 0.01, -0.05]
    contribution = [60_000.0] * len(working_returns)

    def unit_from(returns):
        wealth = 0.0
        for cash, rate in zip(contribution, returns):
            wealth = max(0.0, (wealth + cash) * (1.0 + rate))
        return wealth

    record = {
        "path": [{"domestic": rate} for rate in working_returns],
        "female_death": 64,
        "male_death": 64,
        "female_income": [30_000.0] * 40,
        "male_income": [30_000.0] * 40,
        "last_death": 85,
    }
    baseline_fn = lambda row: row["domestic"]
    batch = _utility_batch([_scenario(unit_from(working_returns), retirement_returns)], "base")
    lam_unit = retirement_adjoint(batch, BASE_SAVINGS_RATE, gamma, WITHDRAWAL_RATE)["lam_unit"]
    mu = working_adjoint([record], baseline_fn, lam_unit, BASE_SAVINGS_RATE)["mu"][:, 0]

    eps = 1e-5
    for index in range(len(working_returns)):
        plus = list(working_returns)
        minus = list(working_returns)
        plus[index] += eps
        minus[index] -= eps
        up = evaluate_batch([_scenario(unit_from(plus), retirement_returns)], "base",
                            BASE_SAVINGS_RATE, WITHDRAWAL_RATE, gamma).utility[0]
        down = evaluate_batch([_scenario(unit_from(minus), retirement_returns)], "base",
                              BASE_SAVINGS_RATE, WITHDRAWAL_RATE, gamma).utility[0]
        finite_difference = (up - down) / (2 * eps)
        assert abs(finite_difference - mu[index]) <= 1e-6 * max(1.0, abs(finite_difference))


def test_composition_value_matches_finite_difference():
    clear_utility_batches()
    panel = os.path.join(HERE, "..", "data", "replication-panel-trend.csv")
    if not os.path.exists(panel):
        return
    rows = read_panel(panel)
    instruments = unit_sleeves(0.003, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, 0.001)
    functions = dict(instruments)
    functions[BENCHMARK_NAME] = instruments["equity"]

    experiment = default_experiments(0.003, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, 0.001)[1]
    transfer = experiment.transfers[0]
    exposures = {name: experiment.baseline_exposures[name] + transfer.weights.get(name, 0.0)
                 for name in experiment.universe}
    eps = 1e-3
    plus = {name: experiment.baseline_exposures[name] + eps * transfer.weights.get(name, 0.0)
            for name in experiment.universe}
    minus = {name: experiment.baseline_exposures[name] - eps * transfer.weights.get(name, 0.0)
             for name in experiment.universe}
    functions["target"] = experiment.compose(exposures)
    functions["plus"] = experiment.compose(plus)
    functions["minus"] = experiment.compose(minus)

    scenarios, records = scenarios_with_records(rows, functions, 400, 10.0, 20260827)
    batch = _utility_batch(scenarios, BENCHMARK_NAME)
    adjoint = retirement_adjoint(batch, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
    working = working_adjoint(records, functions[BENCHMARK_NAME], adjoint["lam_unit"], BASE_SAVINGS_RATE)

    names = ("equity", "bonds")
    work_series = instrument_series(records, functions, names)
    retirement_series = {name: _utility_batch(scenarios, name).returns for name in names}
    value = composition_value(transfer, work_series, retirement_series, working["mu"], adjoint["mu"])["value"]

    up = evaluate_batch(scenarios, "plus", BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA).utility.mean()
    down = evaluate_batch(scenarios, "minus", BASE_SAVINGS_RATE, WITHDRAWAL_RATE, GAMMA).utility.mean()
    finite_difference = (up - down) / (2 * eps)
    assert abs(finite_difference - value) <= 0.10 * max(abs(value), 1e-18)


if __name__ == "__main__":
    test_retirement_adjoint_matches_finite_difference()
    test_utility_slope_matches_finite_difference()
    test_working_adjoint_matches_finite_difference()
    test_composition_value_matches_finite_difference()
    print("all composition-value tests passed")
