"""Lifecycle utility and equivalent savings rates at equal risk.

This script adds the three building blocks missing from the public replication:

* two stochastic GKOS incomes, with an individual contribution threshold;
* CRRA utility of retirement consumption and a bequest motive;
* the equivalent savings rate against the benchmark, on paired draws.

Returns and mortality stay annual, because the public panel does not allow the
monthly replication over the 38 countries of Cederburg et al. (2025). For the
utility aggregator only, uniform consumption within the year removes the common
positive factor 12**gamma without changing the rankings. Wealth paths remain an
annual approximation.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_equal_vol import returns, solve_leverage  # noqa: E402
from income_process import draw_household_income  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  RETIRE_AGE,
  START_AGE,
  block_bootstrap,
  read_panel,
)
from social_security import (  # noqa: E402
  SSI_COUPLE,
  SSI_SINGLE,
  household_benefit_from_histories,
)


GAMMA = 3.84
DELTA = 1.0
BEQUEST_STRENGTH = 2_360.0
BEQUEST_SHIFT = 490_000.0
BASE_SAVINGS_RATE = 0.10
MINIMUM_CONTRIBUTION_INCOME = 15_000.0
WITHDRAWAL_RATE = 0.04
DEFAULT_SPREAD = 0.003

STRATEGIES = (
  "Stocks/I",
  "World",
  "90/60 local",
  "90/60 mondial",
  "60/40 mondial VC",
)


@dataclass(slots=True)
class Scenario:
  """All the shocks shared by one comparison of strategies."""

  first_death: int
  last_death: int
  couple_social_security: float
  survivor_social_security: float
  retirement_unit_wealth: dict[str, float]
  retirement_returns: dict[str, tuple[float, ...]]


@dataclass(slots=True)
class Outcome:
  utility: float
  retirement_wealth: float
  bequest: float
  ruined: bool
  retirement_consumption: float


@dataclass(slots=True)
class UtilityBatch:
  """Vectorised representation of a fixed set of scenarios.

  The search for the equivalent savings rate evaluates the same collection of
  scenarios dozens of times. This structure changes neither the draws nor the
  equations: it only avoids walking through the Python objects again at each
  bisection step.
  """

  retirement_wealth_unit: np.ndarray
  returns: np.ndarray
  active: np.ndarray
  household_size: np.ndarray
  social_security: np.ndarray
  ssi: np.ndarray


@dataclass(slots=True)
class BatchOutcome:
  """Per-path outputs of the vectorised evaluation."""

  utility: np.ndarray
  retirement_wealth: np.ndarray
  bequest: np.ndarray
  ruined: np.ndarray
  retirement_consumption: np.ndarray


_UTILITY_BATCHES: dict[tuple[int, str], tuple[list[Scenario], UtilityBatch]] = {}


def _utility_batch(scenarios: list[Scenario], strategy: str) -> UtilityBatch:
  """Prepare the fixed data used by the vectorised utility."""
  key = (id(scenarios), strategy)
  cached = _UTILITY_BATCHES.get(key)
  if cached is not None and cached[0] is scenarios:
    return cached[1]

  count = len(scenarios)
  periods = max((len(s.retirement_returns[strategy]) for s in scenarios),
                default=0)
  wealth = np.asarray(
    [s.retirement_unit_wealth[strategy] for s in scenarios], dtype=float)
  returns = np.zeros((periods, count), dtype=float)
  active = np.zeros((periods, count), dtype=bool)
  household_size = np.ones((periods, count), dtype=float)
  social_security = np.zeros((periods, count), dtype=float)
  ssi = np.zeros((periods, count), dtype=float)
  for column, scenario in enumerate(scenarios):
    sequence = scenario.retirement_returns[strategy]
    for offset, portfolio_return in enumerate(sequence):
      age = RETIRE_AGE + offset
      size = 2.0 if age <= scenario.first_death else 1.0
      returns[offset, column] = portfolio_return
      active[offset, column] = True
      household_size[offset, column] = size
      social_security[offset, column] = (
        scenario.couple_social_security if size == 2.0
        else scenario.survivor_social_security)
      ssi[offset, column] = 12.0 * (
        SSI_COUPLE if size == 2.0 else SSI_SINGLE)
  batch = UtilityBatch(wealth, returns, active, household_size,
                       social_security, ssi)
  # Keeping the owner prevents a list id from being recycled for another set
  # of paths within the same process.
  _UTILITY_BATCHES[key] = (scenarios, batch)
  return batch


def clear_utility_batches() -> None:
  """Explicitly release the caches between two temporary sets of scenarios."""
  _UTILITY_BATCHES.clear()


def draw_death_age(survival: dict[int, float], rng: random.Random) -> int:
  age = START_AGE
  while age < MAX_AGE:
    if rng.random() > survival.get(age, 0.5):
      return age
    age += 1
  return MAX_AGE


def crra(value: float, gamma: float = GAMMA) -> float:
  if value <= 0.0:
    raise ValueError("CRRA utility requires positive consumption")
  if math.isclose(gamma, 1.0):
    return math.log(value)
  return value ** (1.0 - gamma) / (1.0 - gamma)


def build_scenario(path: list[dict[str, float]],
                   functions: dict[str, Callable[[dict[str, float]], float]],
                   female_death: int, male_death: int,
                   female_income: list[float], male_income: list[float],
                   ) -> Scenario:
  """Turn a common draw into a state that is sufficient for every rate."""
  first_death = min(female_death, male_death)
  last_death = max(female_death, male_death)

  alive_female = [value if age <= female_death else 0.0
                  for age, value in zip(range(START_AGE, RETIRE_AGE),
                                        female_income)]
  alive_male = [value if age <= male_death else 0.0
                for age, value in zip(range(START_AGE, RETIRE_AGE),
                                      male_income)]
  couple_ss, survivor_ss = household_benefit_from_histories(
    alive_female, alive_male, apply_ssi=False)
  contribution_base = [
    (female if female >= MINIMUM_CONTRIBUTION_INCOME else 0.0)
    + (male if male >= MINIMUM_CONTRIBUTION_INCOME else 0.0)
    for female, male in zip(alive_female, alive_male)
  ]

  unit: dict[str, float] = {}
  retirement_returns: dict[str, tuple[float, ...]] = {}
  for name, function in functions.items():
    wealth = 0.0
    # If both spouses die before 65, the portfolio stops at the last death
    # and immediately becomes a bequest.
    working_end = min(RETIRE_AGE, last_death + 1)
    for index, age in enumerate(range(START_AGE, working_end)):
      wealth += contribution_base[index]
      wealth = max(0.0, wealth * (1.0 + function(path[index])))
    unit[name] = wealth

    if last_death < RETIRE_AGE:
      retirement_returns[name] = ()
    else:
      start = RETIRE_AGE - START_AGE
      end = min(len(path), last_death - START_AGE + 1)
      retirement_returns[name] = tuple(
        function(path[index]) for index in range(start, end))

  return Scenario(
    first_death=first_death,
    last_death=last_death,
    couple_social_security=couple_ss,
    survivor_social_security=survivor_ss,
    retirement_unit_wealth=unit,
    retirement_returns=retirement_returns,
  )


def evaluate(scenario: Scenario, strategy: str, savings_rate: float,
             withdrawal_rate: float = WITHDRAWAL_RATE,
             gamma: float = GAMMA) -> Outcome:
  """Evaluate a savings rate without drawing new random shocks."""
  wealth = savings_rate * scenario.retirement_unit_wealth[strategy]
  retirement_wealth = wealth if scenario.last_death >= RETIRE_AGE else 0.0
  withdrawal = retirement_wealth * withdrawal_rate
  total_consumption = 0.0
  utility = 0.0
  ruined = False

  for offset, portfolio_return in enumerate(
      scenario.retirement_returns[strategy]):
    age = RETIRE_AGE + offset
    household_size = 2 if age <= scenario.first_death else 1
    social_security = (
      scenario.couple_social_security if household_size == 2
      else scenario.survivor_social_security)
    ssi = 12.0 * (SSI_COUPLE if household_size == 2 else SSI_SINGLE)

    served = min(wealth, withdrawal)
    if served < withdrawal - 0.005:
      ruined = True
    consumption = max(served + social_security, ssi)
    total_consumption += consumption
    utility += (DELTA ** offset) * crra(
      consumption / math.sqrt(household_size), gamma)

    wealth = max(0.0, wealth - served)
    wealth = max(0.0, wealth * (1.0 + portfolio_return))

  utility += BEQUEST_STRENGTH * crra(wealth + BEQUEST_SHIFT, gamma)
  years = max(1, len(scenario.retirement_returns[strategy]))
  return Outcome(
    utility=utility,
    retirement_wealth=retirement_wealth,
    bequest=wealth,
    ruined=ruined,
    retirement_consumption=total_consumption / years,
  )


def expected_utility(scenarios: list[Scenario], strategy: str,
                     savings_rate: float, gamma: float = GAMMA,
                     withdrawal_rate: float = WITHDRAWAL_RATE) -> float:
  """Mean utility, exactly as ``evaluate`` but in batches.

  The withdrawal remains a fixed real amount equal to ``withdrawal_rate`` times
  initial retirement wealth; SSI and Social Security flows stay outside the
  portfolio. This version is identical to the scalar loop and makes tables with
  20,000 paths practical.
  """
  return float(np.mean(evaluate_batch(
    scenarios, strategy, savings_rate, withdrawal_rate, gamma).utility))


def evaluate_batch(scenarios: list[Scenario], strategy: str,
                   savings_rate: float,
                   withdrawal_rate: float = WITHDRAWAL_RATE,
                   gamma: float = GAMMA) -> BatchOutcome:
  """Batch version of ``evaluate`` for a given savings rate."""
  if not scenarios:
    raise ValueError("At least one scenario is required")
  batch = _utility_batch(scenarios, strategy)
  wealth = savings_rate * batch.retirement_wealth_unit.copy()
  has_retirement = np.any(batch.active, axis=0)
  retirement_wealth = np.where(has_retirement, wealth, 0.0)
  withdrawal = retirement_wealth * withdrawal_rate
  utility = np.zeros(len(scenarios), dtype=float)
  total_consumption = np.zeros(len(scenarios), dtype=float)
  ruined = np.zeros(len(scenarios), dtype=bool)
  for offset in range(batch.returns.shape[0]):
    active = batch.active[offset]
    if not np.any(active):
      continue
    served = np.minimum(wealth, withdrawal)
    consumption = np.maximum(
      served + batch.social_security[offset], batch.ssi[offset])
    scaled = consumption / np.sqrt(batch.household_size[offset])
    # Inactive columns (death before retirement) do not contribute to the
    # flow. Giving them a neutral value avoids a power of zero in the
    # vectorised computation, without changing the aggregate utility.
    scaled[~active] = 1.0
    if math.isclose(gamma, 1.0):
      flow_utility = np.log(scaled)
    else:
      flow_utility = scaled ** (1.0 - gamma) / (1.0 - gamma)
    utility[active] += (DELTA ** offset) * flow_utility[active]
    total_consumption[active] += consumption[active]
    ruined[active] |= served[active] < withdrawal[active] - 0.005
    wealth[active] = np.maximum(0.0, wealth[active] - served[active])
    wealth[active] = np.maximum(
      0.0, wealth[active] * (1.0 + batch.returns[offset, active]))
  if math.isclose(gamma, 1.0):
    utility += BEQUEST_STRENGTH * np.log(wealth + BEQUEST_SHIFT)
  else:
    utility += (BEQUEST_STRENGTH
                * (wealth + BEQUEST_SHIFT) ** (1.0 - gamma)
                / (1.0 - gamma))
  years = np.maximum(1, np.sum(batch.active, axis=0))
  return BatchOutcome(
    utility=utility,
    retirement_wealth=retirement_wealth,
    bequest=wealth,
    ruined=ruined,
    retirement_consumption=total_consumption / years,
  )


def equivalent_savings_rate(scenarios: list[Scenario], strategy: str,
                            target_utility: float,
                            gamma: float = GAMMA,
                            withdrawal_rate: float = WITHDRAWAL_RATE) -> float:
  """Savings rate of the strategy that matches the target utility, by bisection."""
  low, high = 0.0, 1.0
  low_utility = expected_utility(
    scenarios, strategy, low, gamma, withdrawal_rate)
  high_utility = expected_utility(
    scenarios, strategy, high, gamma, withdrawal_rate)
  if target_utility <= low_utility:
    return low
  if target_utility > high_utility:
    return math.nan
  # 24 iterations give a precision below 0.01 percentage point while keeping
  # a panel of many fixed strategies practical.
  for _ in range(24):
    middle = (low + high) / 2.0
    if expected_utility(
        scenarios, strategy, middle, gamma, withdrawal_rate) < target_utility:
      low = middle
    else:
      high = middle
  return (low + high) / 2.0


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=10.0)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD,
                      help="annual cost above the short rate (default 0.003)")
  parser.add_argument("--withdrawal-rate", type=float,
                      default=WITHDRAWAL_RATE)
  parser.add_argument("--gamma", type=float, default=GAMMA)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre strictement positif")

  rows = read_panel(args.panel)
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  if len(rows) < 2:
    raise ValueError("The requested window does not contain enough data")

  stocks_i = [0.5 * (row["domestic"] + row["international"])
              for row in rows]
  world_excess = [
    0.6 * row["world_equity"] + 0.4 * row["world_bond"] - row["world_bill"]
    for row in rows]
  local_excess = [
    0.6 * stocks_i[index] + 0.4 * row["bond"] - row["bill"]
    for index, row in enumerate(rows)]
  world_leverage = solve_leverage(
    stocks_i, [row["world_bill"] for row in rows], world_excess)
  local_leverage = solve_leverage(
    stocks_i, [row["bill"] for row in rows], local_excess)
  all_functions = returns(args.spread, world_leverage, local_leverage)
  functions = {name: all_functions[name] for name in STRATEGIES}

  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)
  scenarios: list[Scenario] = []
  income_at_25: list[float] = []
  income_at_47: list[float] = []
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block)
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, household_income = draw_household_income(rng)
    income_at_25.append(household_income[0])
    income_at_47.append(household_income[47 - START_AGE])
    scenarios.append(build_scenario(
      path, functions, female_death, male_death,
      female_income, male_income))

  print(f"Panel public : {len(rows)} country-years "
        f"({min(row['year'] for row in rows)}-"
        f"{max(row['year'] for row in rows)})")
  print(f"Simulation : {args.runs} trajectoires appariees, blocs moyens "
        f"de {args.mean_block:g} an(s), spread {args.spread:.2%}")
  print(f"CRRA gamma={args.gamma:g}, legs theta={BEQUEST_STRENGTH:g}, "
        f"k={BEQUEST_SHIFT:,.0f}, withdrawal={args.withdrawal_rate:.1%}"
        .replace(",", " "))
  print(f"Income check: median household at age 25 = "
        f"{statistics.median(income_at_25):,.0f}, age 47 = "
        f"{statistics.median(income_at_47):,.0f}".replace(",", " "))
  print(f"Leverage: local {local_leverage:.3f}x; global "
        f"{world_leverage:.3f}x")
  print()

  target_utility = expected_utility(
    scenarios, "Stocks/I", BASE_SAVINGS_RATE, args.gamma,
    args.withdrawal_rate)
  print(f"{'strategy':<20}{'E[U] x 1e16':>15}{'equiv. saving':>14}"
        f"{'median wealth':>17}{'mean cons.':>14}{'ruin':>9}"
        f"{'legs med.':>14}")
  print("-" * 103)
  for name in STRATEGIES:
    outcomes = [evaluate(scenario, name, BASE_SAVINGS_RATE,
                         args.withdrawal_rate, args.gamma)
                for scenario in scenarios]
    utility = statistics.fmean(outcome.utility for outcome in outcomes)
    equivalent = equivalent_savings_rate(
      scenarios, name, target_utility, args.gamma, args.withdrawal_rate)
    retirement = statistics.median(
      outcome.retirement_wealth for outcome in outcomes)
    consumption = statistics.fmean(
      outcome.retirement_consumption for outcome in outcomes)
    ruin = sum(outcome.ruined for outcome in outcomes) / len(outcomes)
    bequest = statistics.median(outcome.bequest for outcome in outcomes)
    equivalent_text = "hors borne" if math.isnan(equivalent) else f"{equivalent:.2%}"
    line = (f"{name:<20}{utility * 1e16:>15.5f}{equivalent_text:>14}"
            f"{retirement:>17,.0f}{consumption:>14,.0f}{ruin:>9.2%}"
            f"{bequest:>14,.0f}")
    print(line.replace(",", " "))


if __name__ == "__main__":
  main()
