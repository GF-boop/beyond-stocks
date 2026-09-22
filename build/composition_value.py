#!/usr/bin/env python3
"""Utility-weighted value of composition changes in the lifecycle experiment.

Section 3 of the paper defines, for a constant feasible composition direction
``h`` with ``sum(h) == 0``,

    V_h = E[ sum_t M_t h^T R~_t ],      M_t = dU / dR_t,

where ``R~_t`` are the resident-real sleeve returns net of stated fees and hedge
deductions.  This script computes ``M_t`` by reverse-mode differentiation of the
exact lifecycle recursion used in the simulations (accumulation, withdrawal,
consumption floor, mortality, terminal bequest) and evaluates ``V_h``, together
with its decomposition into a mean-return part ``E[M_t] E[dR_t]`` and a
covariance part ``Cov(M_t, dR_t)``.

The design is configuration driven.  Instruments are return functions and each
``Experiment`` names a baseline composition plus a list of raw weight transfers,
so a new sleeve or asset universe is added by appending one entry, not by
writing new code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_fixed_stacked_utility import (  # noqa: E402
    BENCHMARK_NAME,
    DEFAULT_FX_HEDGE_COST,
    DEFAULT_SPREAD,
)
from compare_gold_trend_equal_vol import (  # noqa: E402
    DEFAULT_TREND_COST,
    DEFAULT_TREND_FEE,
)
from compare_lifecycle_utility import (  # noqa: E402
    BASE_SAVINGS_RATE,
    BEQUEST_SHIFT,
    BEQUEST_STRENGTH,
    DELTA,
    GAMMA,
    MINIMUM_CONTRIBUTION_INCOME,
    WITHDRAWAL_RATE,
    Scenario,
    UtilityBatch,
    _utility_batch,
    build_scenario,
    draw_death_age,
    equivalent_savings_rate,
    evaluate_batch,
)
from income_process import draw_household_income  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
    MAX_AGE,
    RETIRE_AGE,
    START_AGE,
    block_bootstrap,
    read_panel,
)
from sleeve_ablation import function_for  # noqa: E402


# ---------------------------------------------------------------------------
# Instruments and experiment configuration
# ---------------------------------------------------------------------------
def unit_sleeves(spread: float, trend_fee: float, trend_cost: float,
                 hedge_cost: float) -> dict[str, Callable[[dict[str, float]], float]]:
    """Unit-notional sleeve returns ``R~_k``, net of fees and hedge deductions."""
    return {
        "equity": function_for((1.0, 0.0, 0.0, 0.0), spread, trend_fee, trend_cost, hedge_cost),
        "bonds": function_for((0.0, 1.0, 0.0, 0.0), spread, trend_fee, trend_cost, hedge_cost),
        "gold": function_for((0.0, 0.0, 1.0, 0.0), spread, trend_fee, trend_cost, hedge_cost),
        "mf": function_for((0.0, 0.0, 0.0, 1.0), spread, trend_fee, trend_cost, hedge_cost),
        "domestic": lambda row: row["domestic"],
        "international": lambda row: row["international"],
    }


@dataclass(frozen=True)
class Transfer:
    """A raw exposure direction ``h`` (sum of weights zero) away from the baseline."""

    label: str
    weights: dict[str, float]


@dataclass(frozen=True)
class Experiment:
    label: str
    universe: tuple[str, ...]
    baseline_name: str
    baseline_exposures: dict[str, float]
    compose: Callable[[dict[str, float]], Callable[[dict[str, float]], float]]
    transfers: tuple[Transfer, ...] = ()
    exposure_deltas: tuple[float, ...] = ()
    value_sign: float = 1.0


def exposure_instrument(baseline_exposures: dict[str, float], universe: tuple[str, ...],
                        functions: dict[str, Callable[[dict[str, float]], float]],
                        spread: float) -> Callable[[dict[str, float]], float]:
    """Return the exposure-margin instrument ``v^T R~_t - R_{f,t} - phi``.

    Raising gross exposure from ``G`` to ``G + dG`` scales every sleeve by
    ``dG / G``; with cash and borrowing adjusting, the induced return change is
    ``dG`` times this instrument (Section 3, ``eq:exposure-value``).
    """
    gross = sum(baseline_exposures.values())
    normalized = {name: baseline_exposures.get(name, 0.0) / gross for name in universe}

    def margin(row):
        total = sum(weight * functions[name](row) for name, weight in normalized.items())
        return total - row["world_bill"] - spread

    return margin


def default_experiments(spread: float, trend_fee: float, trend_cost: float,
                        hedge_cost: float) -> list[Experiment]:
    """Three composition experiments: equity mix, four-sleeve at G=1 and G=1.75."""
    bond_w, gold_w, mf_w = 4.0 / 15.0, 1.0 / 6.0, 1.0 / 6.0

    def multi(weights):
        return function_for(
            (weights["equity"], weights["bonds"], weights["gold"], weights["mf"]),
            spread, trend_fee, trend_cost, hedge_cost,
        )

    def equity(weights):
        return lambda row: weights["domestic"] * row["domestic"] + weights["international"] * row["international"]

    def equity_only(weights):
        return function_for((weights["equity"], 0.0, 0.0, 0.0),
                            spread, trend_fee, trend_cost, hedge_cost)

    proportional_100 = {"equity": 0.40, "bonds": bond_w, "gold": gold_w, "mf": mf_w}
    proportional_175 = {name: 1.75 * value for name, value in proportional_100.items()}
    erc_100 = {"equity": 0.1453, "bonds": 0.4747, "gold": 0.1205, "mf": 0.2595}
    erc_175 = {name: 1.75 * value for name, value in erc_100.items()}

    def removals(baseline):
        """Transfers that strip one sleeve and reallocate its weight to equities."""
        return tuple(
            Transfer(f"remove {name}",
                     {"equity": baseline[name], name: -baseline[name]})
            for name in ("bonds", "gold", "mf")
        ) + (
            Transfer("remove bonds and gold",
                     {"equity": baseline["bonds"] + baseline["gold"],
                      "bonds": -baseline["bonds"], "gold": -baseline["gold"]}),
            Transfer("remove package",
                     {"equity": sum(baseline[name] for name in ("bonds", "gold", "mf")),
                      **{name: -baseline[name] for name in ("bonds", "gold", "mf")}}),
        )

    return [
        Experiment(
            label="Equity diversification",
            universe=("domestic", "international"),
            baseline_name="Equity: domestic only",
            baseline_exposures={"domestic": 1.0, "international": 0.0},
            compose=equity,
            transfers=(Transfer("international 33/67", {"domestic": -0.67, "international": 0.67}),),
        ),
        Experiment(
            label="Four-sleeve composition at 100% exposure",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name=BENCHMARK_NAME,
            baseline_exposures={"equity": 1.0, "bonds": 0.0, "gold": 0.0, "mf": 0.0},
            compose=multi,
            transfers=(
                Transfer("bonds 4/15", {"equity": -bond_w, "bonds": bond_w}),
                Transfer("gold 1/6", {"equity": -gold_w, "gold": gold_w}),
                Transfer("managed futures 1/6", {"equity": -mf_w, "mf": mf_w}),
                Transfer("proportional package", {"equity": -(bond_w + gold_w + mf_w),
                                                  "bonds": bond_w, "gold": gold_w, "mf": mf_w}),
            ),
        ),
        Experiment(
            label="Four-sleeve composition at 175% exposure",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="ACO 175%",
            baseline_exposures={"equity": 1.75, "bonds": 0.0, "gold": 0.0, "mf": 0.0},
            compose=multi,
            transfers=(
                Transfer("bonds", {"equity": -1.75 * bond_w, "bonds": 1.75 * bond_w}),
                Transfer("gold", {"equity": -1.75 * gold_w, "gold": 1.75 * gold_w}),
                Transfer("managed futures", {"equity": -1.75 * mf_w, "mf": 1.75 * mf_w}),
                Transfer("proportional package", {"equity": -1.75 * (bond_w + gold_w + mf_w),
                                                  "bonds": 1.75 * bond_w, "gold": 1.75 * gold_w,
                                                  "mf": 1.75 * mf_w}),
            ),
        ),
        Experiment(
            label="Leverage of the equity benchmark",
            universe=("equity",),
            baseline_name=BENCHMARK_NAME,
            baseline_exposures={"equity": 1.0},
            compose=equity_only,
            exposure_deltas=(0.25, 0.75),
        ),
        Experiment(
            label="Leverage of the proportional portfolio",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="Proportional 100%",
            baseline_exposures=dict(proportional_100),
            compose=multi,
            exposure_deltas=(0.25, 0.75),
        ),
        Experiment(
            label="Leverage of the equity benchmark at 175%",
            universe=("equity",),
            baseline_name="ACO 175%",
            baseline_exposures={"equity": 1.75},
            compose=equity_only,
            exposure_deltas=(0.25,),
        ),
        Experiment(
            label="Leverage of the proportional portfolio at 175%",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="Proportional 175%",
            baseline_exposures=dict(proportional_175),
            compose=multi,
            exposure_deltas=(0.25,),
        ),
        Experiment(
            label="Four-sleeve composition at 175% exposure (proportional)",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="Proportional 175%",
            baseline_exposures=dict(proportional_175),
            compose=multi,
            transfers=removals(proportional_175),
        ),
        Experiment(
            label="Four-sleeve composition at 175% exposure (ERC)",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="ERC 175%",
            baseline_exposures=dict(erc_175),
            compose=multi,
            transfers=removals(erc_175),
        ),
        Experiment(
            label="Leverage of the ERC portfolio",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="ERC 100%",
            baseline_exposures=dict(erc_100),
            compose=multi,
            exposure_deltas=(0.25, 0.75),
        ),
        Experiment(
            label="Leverage of the ERC portfolio at 175%",
            universe=("equity", "bonds", "gold", "mf"),
            baseline_name="ERC 175%",
            baseline_exposures=dict(erc_175),
            compose=multi,
            exposure_deltas=(0.25,),
        ),
    ]


# ---------------------------------------------------------------------------
# Paired-path construction (identical RNG order to historical_uncertainty)
# ---------------------------------------------------------------------------
def scenarios_with_records(rows, functions, runs, mean_block, seed):
    female_survival = mortality_table("female", "ssa")
    male_survival = mortality_table("male", "ssa")
    horizon = MAX_AGE - START_AGE + 1
    rng = random.Random(seed)
    scenarios: list[Scenario] = []
    records: list[dict] = []
    for _ in range(runs):
        path = block_bootstrap(rows, horizon, rng, mean_block)
        female_death = draw_death_age(female_survival, rng)
        male_death = draw_death_age(male_survival, rng)
        female_income, male_income, _ = draw_household_income(rng)
        scenarios.append(build_scenario(path, functions, female_death, male_death,
                                        female_income, male_income))
        records.append({
            "path": path,
            "first_death": min(female_death, male_death),
            "last_death": max(female_death, male_death),
            "female_death": female_death,
            "male_death": male_death,
            "female_income": female_income,
            "male_income": male_income,
        })
    return scenarios, records


def contribution_stream(record: dict) -> list[float]:
    alive_female = [value if age <= record["female_death"] else 0.0
                    for age, value in zip(range(START_AGE, RETIRE_AGE), record["female_income"])]
    alive_male = [value if age <= record["male_death"] else 0.0
                  for age, value in zip(range(START_AGE, RETIRE_AGE), record["male_income"])]
    return [(female if female >= MINIMUM_CONTRIBUTION_INCOME else 0.0)
            + (male if male >= MINIMUM_CONTRIBUTION_INCOME else 0.0)
            for female, male in zip(alive_female, alive_male)]


def working_length(record: dict) -> int:
    return min(RETIRE_AGE, record["last_death"] + 1) - START_AGE


# ---------------------------------------------------------------------------
# Reverse-mode sensitivities M_t = dU / dR_t
# ---------------------------------------------------------------------------
def retirement_adjoint(batch: UtilityBatch, savings_rate: float,
                       gamma: float = GAMMA,
                       withdrawal_rate: float = WITHDRAWAL_RATE) -> dict:
    """Return ``mu[t] = dU / dR_t`` over retirement dates plus ``lam_unit = dU/dunit``."""
    periods, count = batch.returns.shape
    has_retirement = np.any(batch.active, axis=0)
    wealth = savings_rate * batch.retirement_wealth_unit.copy()
    retirement_wealth = np.where(has_retirement, wealth, 0.0)
    withdrawal = retirement_wealth * withdrawal_rate

    Wr = np.zeros((periods + 1, count), dtype=float)
    Wr[0] = wealth
    served = np.zeros((periods, count), dtype=float)
    consumption = np.zeros((periods, count), dtype=float)
    post = np.zeros((periods, count), dtype=float)
    for t in range(periods):
        active = batch.active[t]
        serv = np.minimum(Wr[t], withdrawal)
        served[t] = serv
        consumption[t] = np.maximum(serv + batch.social_security[t], batch.ssi[t])
        post[t] = np.maximum(0.0, Wr[t] - serv)
        Wr[t + 1] = Wr[t]
        Wr[t + 1][active] = np.maximum(0.0, post[t][active] * (1.0 + batch.returns[t, active]))

    lam = BEQUEST_STRENGTH * (Wr[periods] + BEQUEST_SHIFT) ** (-gamma)
    mu = np.zeros((periods, count), dtype=float)
    omega = np.zeros(count, dtype=float)
    for t in range(periods - 1, -1, -1):
        active = batch.active[t]
        ret = batch.returns[t]
        depleted = Wr[t] <= withdrawal
        scaled = consumption[t] / np.sqrt(batch.household_size[t])
        uprime = np.zeros_like(scaled)
        positive_consumption = scaled > 0.0
        uprime[positive_consumption] = scaled[positive_consumption] ** (-gamma)
        floor_binding = served[t] + batch.social_security[t] >= batch.ssi[t]
        g_served = (DELTA ** t) * uprime / np.sqrt(batch.household_size[t]) * floor_binding
        positive = post[t] * (1.0 + ret) > 0.0
        transition = (1.0 - depleted) * (1.0 + ret) * positive
        g = np.where(active, g_served * depleted, 0.0)
        transition = np.where(active, transition, 1.0)
        mu[t] = np.where(active, lam * post[t] * positive, 0.0)
        omega += np.where(active, g_served * (1.0 - depleted)
                          - lam * (1.0 + ret) * positive * (1.0 - depleted), 0.0)
        lam = g + lam * transition

    lam_unit = savings_rate * lam + withdrawal_rate * savings_rate * has_retirement * omega
    return {"mu": mu, "lam_unit": lam_unit, "withdrawal": withdrawal,
            "has_retirement": has_retirement, "Wr": Wr}


def working_adjoint(records, baseline_fn, lam_unit, savings_rate):
    """Return ``mu[j] = dU / dR_j`` over accumulation dates (contributions unscaled)."""
    count = len(records)
    lengths = np.array([working_length(record) for record in records])
    max_length = int(lengths.max()) if count else 0
    contribution = np.zeros((max_length, count), dtype=float)
    returns = np.zeros((max_length, count), dtype=float)
    active = np.zeros((max_length, count), dtype=bool)
    for index, record in enumerate(records):
        stream = contribution_stream(record)
        for j in range(lengths[index]):
            contribution[j, index] = stream[j]
            returns[j, index] = baseline_fn(record["path"][j])
            active[j, index] = True

    Wb = np.zeros((max_length + 1, count), dtype=float)
    for j in range(max_length):
        act = active[j]
        base = Wb[j] + contribution[j]
        Wb[j + 1] = Wb[j]
        Wb[j + 1][act] = np.maximum(0.0, base[act] * (1.0 + returns[j, act]))

    mu = np.zeros((max_length, count), dtype=float)
    lam = lam_unit.copy()
    for j in range(max_length - 1, -1, -1):
        act = active[j]
        base = Wb[j] + contribution[j]
        positive = base * (1.0 + returns[j]) > 0.0
        mu[j] = np.where(act, lam * base * positive, 0.0)
        lam = np.where(act, lam * (1.0 + returns[j]) * positive, lam)
    return {"mu": mu, "returns": returns, "active": active, "Wb": Wb}


def instrument_series(records, functions, names):
    """Accumulation-date returns for each instrument, aligned with ``working_adjoint``."""
    count = len(records)
    lengths = np.array([working_length(record) for record in records])
    max_length = int(lengths.max()) if count else 0
    series = {}
    for name in names:
        fn = functions[name]
        arr = np.zeros((max_length, count), dtype=float)
        for index, record in enumerate(records):
            for j in range(lengths[index]):
                arr[j, index] = fn(record["path"][j])
        series[name] = arr
    return series


# ---------------------------------------------------------------------------
# Composition value and its decomposition
# ---------------------------------------------------------------------------
def composition_value(transfer: Transfer, work_series, retirement_series,
                      mu_work, mu_ret) -> dict:
    h = transfer.weights
    dwork = sum(weight * work_series[name] for name, weight in h.items())
    dret = sum(weight * retirement_series[name] for name, weight in h.items())

    work_part = float(np.mean(np.sum(mu_work * dwork, axis=0)))
    ret_part = float(np.mean(np.sum(mu_ret * dret, axis=0)))

    def split(mu, delta):
        mean_m = mu.mean(axis=1, keepdims=True)
        mean_r = delta.mean(axis=1, keepdims=True)
        mean_part = float(np.sum(mean_m[:, 0] * mean_r[:, 0]))
        cov_part = float(np.sum(np.mean((mu - mean_m) * (delta - mean_r), axis=1)))
        return mean_part, cov_part

    mean_work, cov_work = split(mu_work, dwork)
    mean_ret, cov_ret = split(mu_ret, dret)
    return {
        "value": work_part + ret_part,
        "value_work": work_part,
        "value_retirement": ret_part,
        "mean_part": mean_work + mean_ret,
        "covariance_part": cov_work + cov_ret,
        "mean_part_work": mean_work,
        "mean_part_retirement": mean_ret,
        "covariance_part_work": cov_work,
        "covariance_part_retirement": cov_ret,
        "mean_return_difference_retirement": float(np.mean(dret)) if dret.size else 0.0,
    }


def utility_slope(batch: UtilityBatch, lam_unit, savings_rate: float) -> float:
    """Analytic ``dE[U]/ds`` implied by the adjoint (``dU/dunit * unit / s``)."""
    return float(np.mean(lam_unit * batch.retirement_wealth_unit / savings_rate))


def exact_change(scenarios, baseline_name, target_name, target_utility, baseline_saving):
    baseline_u = float(evaluate_batch(scenarios, baseline_name, BASE_SAVINGS_RATE,
                                      WITHDRAWAL_RATE, GAMMA).utility.mean())
    target_u = float(evaluate_batch(scenarios, target_name, BASE_SAVINGS_RATE,
                                    WITHDRAWAL_RATE, GAMMA).utility.mean())
    saving = equivalent_savings_rate(scenarios, target_name, target_utility, GAMMA, WITHDRAWAL_RATE)
    return {
        "exact_utility_change": target_u - baseline_u,
        "exact_saving": saving,
        "exact_saving_change": saving - baseline_saving,
    }


# ---------------------------------------------------------------------------
# Fast expected utility for arbitrary compositions (used to locate the optimum)
# ---------------------------------------------------------------------------
def contribution_matrix(records):
    count = len(records)
    lengths = np.array([working_length(record) for record in records])
    max_length = int(lengths.max()) if count else 0
    matrix = np.zeros((max_length, count), dtype=float)
    for index, record in enumerate(records):
        stream = contribution_stream(record)
        for j in range(lengths[index]):
            matrix[j, index] = stream[j]
    return matrix


def accumulate_wealth(work_returns, contribution):
    wealth = np.zeros(work_returns.shape[1], dtype=float)
    for j in range(work_returns.shape[0]):
        wealth = np.maximum(0.0, (wealth + contribution[j]) * (1.0 + work_returns[j]))
    return wealth


def portfolio_return(stack, bill, weights, gross, spread):
    total = np.tensordot(weights, stack, axes=(0, 0))
    return total + (1.0 - gross) * bill - (gross - 1.0) * spread


def fast_expected_utility(retirement_returns, unit_wealth, batch, savings_rate,
                          gamma=GAMMA, withdrawal_rate=WITHDRAWAL_RATE):
    """Vectorised expected utility for a composition supplied as return arrays."""
    wealth = savings_rate * unit_wealth
    has_retirement = np.any(batch.active, axis=0)
    retirement_wealth = np.where(has_retirement, wealth, 0.0)
    withdrawal = retirement_wealth * withdrawal_rate
    utility = np.zeros(retirement_returns.shape[1], dtype=float)
    for offset in range(retirement_returns.shape[0]):
        active = batch.active[offset]
        if not np.any(active):
            continue
        served = np.minimum(wealth, withdrawal)
        consumption = np.maximum(served + batch.social_security[offset], batch.ssi[offset])
        scaled = consumption / np.sqrt(batch.household_size[offset])
        scaled[~active] = 1.0
        flow = scaled ** (1.0 - gamma) / (1.0 - gamma)
        utility[active] += (DELTA ** offset) * flow[active]
        wealth[active] = np.maximum(0.0, wealth[active] - served[active])
        wealth[active] = np.maximum(0.0, wealth[active] * (1.0 + retirement_returns[offset, active]))
    utility += BEQUEST_STRENGTH * (wealth + BEQUEST_SHIFT) ** (1.0 - gamma) / (1.0 - gamma)
    return float(utility.mean())


def fast_equivalent_savings_rate(retirement_returns, unit_wealth, batch, target_utility,
                                 gamma=GAMMA, withdrawal_rate=WITHDRAWAL_RATE,
                                 iterations: int = 60) -> float:
    low, high = 0.0, 1.0
    for _ in range(iterations):
        middle = 0.5 * (low + high)
        value = fast_expected_utility(retirement_returns, unit_wealth, batch, middle,
                                      gamma, withdrawal_rate)
        if value > target_utility:
            high = middle
        else:
            low = middle
    return 0.5 * (low + high)


def optimal_composition(work_series, retirement_series, batch, contribution, gross, spread,
                        savings_rate=BASE_SAVINGS_RATE, gamma=GAMMA,
                        withdrawal_rate=WITHDRAWAL_RATE) -> dict:
    """Maximise expected utility over the four sleeve weights at fixed gross exposure."""
    from scipy.optimize import minimize

    names = ("equity", "bonds", "gold", "mf")
    ret_stack = np.stack([retirement_series[name] for name in names])
    work_stack = np.stack([work_series[name] for name in names])
    bill_ret = retirement_series["bill"]
    bill_work = work_series["bill"]

    def evaluate_weights(weights):
        ret = portfolio_return(ret_stack, bill_ret, weights, gross, spread)
        work = portfolio_return(work_stack, bill_work, weights, gross, spread)
        unit = accumulate_wealth(work, contribution)
        return ret, unit

    def objective(weights):
        ret, unit = evaluate_weights(weights)
        return -fast_expected_utility(ret, unit, batch, savings_rate, gamma, withdrawal_rate) * 1e16

    starts = (
        np.array([gross, 0.0, 0.0, 0.0]),
        np.array([gross * 0.40, gross * 4.0 / 15.0, gross / 6.0, gross / 6.0]),
        np.array([gross / 4.0] * 4),
        np.array([gross / 2.0, 0.0, 0.0, gross / 2.0]),
    )
    constraint = {"type": "eq", "fun": lambda w: float(np.sum(w) - gross)}
    best = None
    for start in starts:
        result = minimize(objective, start, method="SLSQP",
                          bounds=[(0.0, gross)] * 4, constraints=[constraint],
                          options={"maxiter": 400, "ftol": 1e-10})
        if best is None or result.fun < best.fun:
            best = result
    weights = np.clip(best.x, 0.0, None)
    weights = weights * gross / weights.sum()
    ret, unit = evaluate_weights(weights)
    return {"weights": dict(zip(names, weights.tolist())),
            "retirement_returns": ret, "unit_wealth": unit}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", default=os.path.join(HERE, "..", "data", "replication-panel-trend.csv"))
    parser.add_argument("--runs", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260827)
    parser.add_argument("--mean-block", type=float, default=10.0)
    parser.add_argument("--year-from", type=int, default=None)
    parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
    parser.add_argument("--fx-hedge-cost", type=float, default=DEFAULT_FX_HEDGE_COST)
    parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
    parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
    parser.add_argument("--output-json",
                        default=os.path.join(HERE, "..", "results", "composition_value_n10000.json"))
    args = parser.parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be positive")

    rows = read_panel(args.panel)
    if args.year_from is not None:
        rows = [row for row in rows if row["year"] >= args.year_from]
    instruments = unit_sleeves(args.spread, args.trend_fee, args.trend_cost, args.fx_hedge_cost)
    instruments["bill"] = lambda row: row["world_bill"]
    functions = dict(instruments)
    functions[BENCHMARK_NAME] = function_for((1.0, 0.0, 0.0, 0.0), args.spread,
                                             args.trend_fee, args.trend_cost, args.fx_hedge_cost)
    experiments = default_experiments(args.spread, args.trend_fee, args.trend_cost,
                                      args.fx_hedge_cost)
    target_names = {}
    exposure_names = {}
    for experiment in experiments:
        if experiment.baseline_name not in functions:
            functions[experiment.baseline_name] = experiment.compose(experiment.baseline_exposures)
        for transfer in experiment.transfers:
            exposures = {name: experiment.baseline_exposures.get(name, 0.0)
                         + transfer.weights.get(name, 0.0)
                         for name in experiment.universe}
            name = f"{experiment.label} | {transfer.label}"
            functions[name] = experiment.compose(exposures)
            target_names[(experiment.label, transfer.label)] = name
        if experiment.exposure_deltas:
            margin_name = f"{experiment.label} | exposure margin"
            functions[margin_name] = exposure_instrument(
                experiment.baseline_exposures, experiment.universe, functions, args.spread)
            exposure_names[experiment.label] = margin_name
            gross = sum(experiment.baseline_exposures.values())
            for delta in experiment.exposure_deltas:
                scaled = {name: value * (gross + delta) / gross
                          for name, value in experiment.baseline_exposures.items()}
                label = f"leverage {delta:+.2f}"
                functions[f"{experiment.label} | {label}"] = experiment.compose(scaled)
                target_names[(experiment.label, label)] = f"{experiment.label} | {label}"

    scenarios, records = scenarios_with_records(rows, functions, args.runs, args.mean_block, args.seed)
    target_utility = float(evaluate_batch(scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE,
                                          WITHDRAWAL_RATE, GAMMA).utility.mean())

    instrument_names = tuple(instruments)
    series_names = instrument_names + tuple(exposure_names.values())
    work_series = instrument_series(records, functions, series_names)
    retirement_series = {name: _utility_batch(scenarios, name).returns for name in series_names}

    contribution = contribution_matrix(records)
    aco175_batch = _utility_batch(scenarios, "ACO 175%")
    optimum = optimal_composition(work_series, retirement_series, aco175_batch,
                                  contribution, 1.75, args.spread)

    output = {
        "purpose": "Utility-weighted value of composition changes, Section 3 (V_h = E[sum_t M_t h^T R~_t]).",
        "panel": os.path.relpath(os.path.abspath(args.panel), os.path.join(HERE, "..")),
        "panel_sha256": _sha256(args.panel),
        "observations": len(rows),
        "runs": args.runs,
        "seed": args.seed,
        "mean_block_years": args.mean_block,
        "savings_rate": BASE_SAVINGS_RATE,
        "withdrawal_rate": WITHDRAWAL_RATE,
        "gamma": GAMMA,
        "spread": args.spread,
        "fx_hedge_cost": args.fx_hedge_cost,
        "trend_fee": args.trend_fee,
        "trend_cost": args.trend_cost,
        "target_utility": target_utility,
        "experiments": [],
    }

    for experiment in experiments:
        batch = _utility_batch(scenarios, experiment.baseline_name)
        adjoint = retirement_adjoint(batch, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
        working = working_adjoint(records, functions[experiment.baseline_name],
                                  adjoint["lam_unit"], BASE_SAVINGS_RATE)
        slope = utility_slope(batch, adjoint["lam_unit"], BASE_SAVINGS_RATE)
        baseline_utility = float(evaluate_batch(scenarios, experiment.baseline_name, BASE_SAVINGS_RATE,
                                                WITHDRAWAL_RATE, GAMMA).utility.mean())
        baseline_saving = equivalent_savings_rate(scenarios, experiment.baseline_name,
                                                  target_utility, GAMMA, WITHDRAWAL_RATE)
        result = {
            "label": experiment.label,
            "universe": list(experiment.universe),
            "baseline_name": experiment.baseline_name,
            "baseline_exposures": experiment.baseline_exposures,
            "baseline_utility": baseline_utility,
            "utility_slope": slope,
            "baseline_saving": baseline_saving,
            "transfers": [],
            "exposure": [],
        }

        def build_record(label, weights, value, exact, scale):
            record = {"label": label, "weights": weights, **value, **exact}
            record["reallocation"] = scale
            record["implied_saving_change"] = (-value["value"] / slope) if slope else math.nan
            record["local_saving_change"] = record["implied_saving_change"]
            record["local_mean_component"] = (-value["mean_part"] / slope) if slope else math.nan
            record["local_covariance_component"] = (-value["covariance_part"] / slope) if slope else math.nan
            record["exact_saving_change_per_10pp"] = (exact["exact_saving_change"] / scale * 0.10
                                                      if scale else math.nan)
            return record

        for transfer in experiment.transfers:
            value = composition_value(transfer, work_series, retirement_series,
                                      working["mu"], adjoint["mu"])
            exact = exact_change(scenarios, experiment.baseline_name,
                                 target_names[(experiment.label, transfer.label)],
                                 target_utility, baseline_saving)
            if experiment.value_sign != 1.0:
                sign = experiment.value_sign
                value = {key: (sign * val if isinstance(val, (int, float)) else val)
                         for key, val in value.items()}
                exact = {**exact,
                         "exact_utility_change": sign * exact["exact_utility_change"],
                         "exact_saving_change": sign * exact["exact_saving_change"]}
            reallocation = sum(weight for weight in transfer.weights.values() if weight > 0.0)
            result["transfers"].append(build_record(transfer.label, transfer.weights,
                                                    value, exact, reallocation))

        if experiment.exposure_deltas:
            margin_name = exposure_names[experiment.label]
            margin_work = dict(work_series)
            margin_retirement = dict(retirement_series)
            margin_work["_exposure"] = work_series[margin_name]
            margin_retirement["_exposure"] = retirement_series[margin_name]
            for delta in experiment.exposure_deltas:
                label = f"leverage {delta:+.2f}"
                transfer = Transfer(label, {"_exposure": delta})
                value = composition_value(transfer, margin_work, margin_retirement,
                                          working["mu"], adjoint["mu"])
                exact = exact_change(scenarios, experiment.baseline_name,
                                     target_names[(experiment.label, label)],
                                     target_utility, baseline_saving)
                record = build_record(label, transfer.weights, value, exact, delta)
                record["delta_g"] = delta
                result["exposure"].append(record)

        output["experiments"].append(result)

    aco175_label = "Four-sleeve composition at 175% exposure"
    aco175_result = next(result for result in output["experiments"] if result["label"] == aco175_label)
    aco175_batch = _utility_batch(scenarios, aco175_result["baseline_name"])
    aco175_adjoint = retirement_adjoint(aco175_batch, BASE_SAVINGS_RATE, GAMMA, WITHDRAWAL_RATE)
    aco175_working = working_adjoint(records, functions[aco175_result["baseline_name"]],
                                     aco175_adjoint["lam_unit"], BASE_SAVINGS_RATE)
    baseline_exposures = aco175_result["baseline_exposures"]
    optimal_weights = optimum["weights"]
    optimal_transfer = Transfer(
        "optimal mix",
        {name: optimal_weights[name] - baseline_exposures.get(name, 0.0)
         for name in ("equity", "bonds", "gold", "mf")})
    optimal_value = composition_value(optimal_transfer, work_series, retirement_series,
                                      aco175_working["mu"], aco175_adjoint["mu"])
    optimal_saving = fast_equivalent_savings_rate(optimum["retirement_returns"],
                                                  optimum["unit_wealth"], aco175_batch,
                                                  target_utility, GAMMA, WITHDRAWAL_RATE)
    aco175_slope = aco175_result["utility_slope"]
    names4 = ("equity", "bonds", "gold", "mf")
    ret_stack4 = np.stack([retirement_series[name] for name in names4])
    work_stack4 = np.stack([work_series[name] for name in names4])
    check_weights = np.array([1.75, 0.0, 0.0, 0.0])
    check_ret = portfolio_return(ret_stack4, retirement_series["bill"], check_weights, 1.75, args.spread)
    check_work = portfolio_return(work_stack4, work_series["bill"], check_weights, 1.75, args.spread)
    check_unit = accumulate_wealth(check_work, contribution)
    fast_u = fast_expected_utility(check_ret, check_unit, aco175_batch, BASE_SAVINGS_RATE,
                                   GAMMA, WITHDRAWAL_RATE)
    slow_u = float(evaluate_batch(scenarios, aco175_result["baseline_name"], BASE_SAVINGS_RATE,
                                  WITHDRAWAL_RATE, GAMMA).utility.mean())
    print(f"\n  validation fast/slow objective: {fast_u:.6e} vs {slow_u:.6e} "
          f"(rel {abs(fast_u - slow_u) / abs(slow_u):.2e})")
    output["optimal_composition"] = {
        "gross": 1.75,
        "weights": optimal_weights,
        "reallocation": sum(weight for weight in optimal_transfer.weights.values() if weight > 0.0),
        "saving": optimal_saving,
        "saving_change_vs_aco175": optimal_saving - aco175_result["baseline_saving"],
        "value": optimal_value["value"],
        "mean_part": optimal_value["mean_part"],
        "covariance_part": optimal_value["covariance_part"],
        "local_saving_change": -optimal_value["value"] / aco175_slope,
        "local_mean_component": -optimal_value["mean_part"] / aco175_slope,
        "local_covariance_component": -optimal_value["covariance_part"] / aco175_slope,
    }

    stressed = []
    for haircut_bp, haircut in ((300, 0.03), (600, 0.05)):
        stressed_work = dict(work_series)
        stressed_retirement = dict(retirement_series)
        stressed_work["mf"] = work_series["mf"] - haircut
        stressed_retirement["mf"] = retirement_series["mf"] - haircut
        stressed_optimum = optimal_composition(stressed_work, stressed_retirement, aco175_batch,
                                               contribution, 1.75, args.spread)
        stressed_saving = fast_equivalent_savings_rate(
            stressed_optimum["retirement_returns"], stressed_optimum["unit_wealth"],
            aco175_batch, target_utility, GAMMA, WITHDRAWAL_RATE)
        stressed_weights = stressed_optimum["weights"]
        stressed.append({
            "haircut_bp": haircut_bp,
            "weights": stressed_weights,
            "reallocation": sum(weight for name, weight in stressed_weights.items()
                                if weight > baseline_exposures.get(name, 0.0)),
            "saving": stressed_saving,
            "saving_change_vs_aco175": stressed_saving - aco175_result["baseline_saving"],
        })
    output["optimal_composition_stressed"] = stressed

    os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, sort_keys=False)
        handle.write("\n")

    print(f"wrote {os.path.relpath(args.output_json, os.path.join(HERE, '..'))}")
    print(f"runs={args.runs} seed={args.seed} observations={len(rows)}")
    for result in output["experiments"]:
        print(f"\n{result['label']}  (baseline {result['baseline_name']}, "
              f"slope={result['utility_slope']:.3e}, saving={result['baseline_saving']:.4f})")
        for transfer in result["transfers"]:
            print(f"  {transfer['label']:<26} V={transfer['value']:+.4e}  "
                  f"mean={transfer['mean_part']:+.4e} cov={transfer['covariance_part']:+.4e}  "
                  f"dS*={transfer['implied_saving_change']:+.4f}  "
                  f"exact_dS*={transfer['exact_saving_change']:+.4f}")
        for exposure in result["exposure"]:
            print(f"  {exposure['label']:<26} V={exposure['value']:+.4e}  "
                  f"mean={exposure['mean_part']:+.4e} cov={exposure['covariance_part']:+.4e}  "
                  f"dS*={exposure['implied_saving_change']:+.4f}  "
                  f"exact_dS*={exposure['exact_saving_change']:+.4f}")
    optimal = output["optimal_composition"]
    print("\nOptimal composition at 175% (vs ACO 175%):")
    print("  weights=" + ", ".join(f"{name}={weight:.4f}" for name, weight in optimal["weights"].items()))
    print(f"  saving={optimal['saving']:.4f}  exact_dS*={optimal['saving_change_vs_aco175']:+.4f}  "
          f"local_dS*={optimal['local_saving_change']:+.4f}")
    for entry in output["optimal_composition_stressed"]:
        print(f"  MF -{entry['haircut_bp']}bp: weights=" +
              ", ".join(f"{name}={weight:.4f}" for name, weight in entry["weights"].items()) +
              f"  saving={entry['saving']:.4f}  exact_dS*={entry['saving_change_vs_aco175']:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
