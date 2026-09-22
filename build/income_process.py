"""Stochastic lifecycle incomes used by Cederburg et al.

The process is model 6 of Guvenen, Karahan, Ozkan and Song (2021), with the
published parameters as transcribed in a public implementation. As in the main
case of Cederburg et al. (2025), both spouses have the median permanent types
``alpha = beta = z0 = 0``. What remains random:

* persistent and transitory innovations, mixtures of two normals;
* the probability and duration of non-employment, depending on age and income.

One model unit is worth 1,000 dollars of 2022. This factor directly reproduces
Cederburg's Figure 2: about 28,500 dollars of median household income at 25
and 69,000 dollars at the peak of the profile. Amounts are real.

Upstream sources: DOI 10.3982/ECTA14603 and the file
``DiscretizeEarningsDynamicsModel.m`` of the public repository
https://github.com/robertdkirkby/DiscretizedEarningsDynamics.
"""

from __future__ import annotations

import math
import random


START_AGE = 25
RETIRE_AGE = 65
INCOME_SCALE_2022 = 1_000.0

# Modele 6 de GKOS (2021).
RHO = 0.959
P_ETA_1 = 0.407
MU_ETA_1 = -0.085
SIGMA_ETA_1 = 0.364
SIGMA_ETA_2 = 0.069
MU_ETA_2 = -(P_ETA_1 * MU_ETA_1) / (1.0 - P_ETA_1)

P_EPSILON_1 = 0.130
MU_EPSILON_1 = 0.271
SIGMA_EPSILON_1 = 0.795
SIGMA_EPSILON_2 = 0.020
MU_EPSILON_2 = -(P_EPSILON_1 * MU_EPSILON_1) / (1.0 - P_EPSILON_1)

# Probabilite de non-emploi : logistic(a + b t + c z + d t z), t=(age-24)/10.
NONEMPLOYMENT = (-3.353, -0.859, -5.034, -2.895)
NONEMPLOYMENT_LAMBDA = 0.0001


def _mixture_normal(rng: random.Random, probability: float,
                    mean_one: float, sigma_one: float,
                    mean_two: float, sigma_two: float) -> float:
  if rng.random() < probability:
    return rng.gauss(mean_one, sigma_one)
  return rng.gauss(mean_two, sigma_two)


def deterministic_log_income(age: int) -> float:
  """Quadratic profile ``g(t)`` of model 6, ages 25 to 64."""
  if not START_AGE <= age < RETIRE_AGE:
    raise ValueError("The income profile is defined from age 25 to 64")
  t = (age - 24) / 10.0
  return 2.581 + 0.812 * t - 0.185 * t * t


def nonemployment_probability(age: int, persistent_income: float) -> float:
  t = (age - 24) / 10.0
  a, b, c, d = NONEMPLOYMENT
  xi = a + b * t + c * persistent_income + d * t * persistent_income
  # Stable form of the logistic function in the tails of the process.
  if xi >= 0.0:
    return 1.0 / (1.0 + math.exp(-min(xi, 700.0)))
  exponential = math.exp(max(xi, -700.0))
  return exponential / (1.0 + exponential)


def draw_individual_income(rng: random.Random) -> list[float]:
  """Draw an annual career in real 2022 dollars.

  Cederburg sets ``z0`` to zero; the first persistent innovation is therefore
  drawn between z0 and the income observed at 25. After a non-employment
  shock, the fraction of the year lost is an exponential truncated at one year.
  """
  income: list[float] = []
  persistent = 0.0
  for age in range(START_AGE, RETIRE_AGE):
    innovation = _mixture_normal(
      rng, P_ETA_1, MU_ETA_1, SIGMA_ETA_1, MU_ETA_2, SIGMA_ETA_2)
    persistent = RHO * persistent + innovation
    transitory = _mixture_normal(
      rng, P_EPSILON_1, MU_EPSILON_1, SIGMA_EPSILON_1,
      MU_EPSILON_2, SIGMA_EPSILON_2)

    lost_fraction = 0.0
    if rng.random() < nonemployment_probability(age, persistent):
      lost_fraction = min(1.0, rng.expovariate(NONEMPLOYMENT_LAMBDA))
    log_income = deterministic_log_income(age) + persistent + transitory
    income.append(
      (1.0 - lost_fraction) * math.exp(log_income) * INCOME_SCALE_2022)
  return income


def draw_household_income(
    rng: random.Random) -> tuple[list[float], list[float], list[float]]:
  """Two independent careers and their sum, paired across strategies."""
  first = draw_individual_income(rng)
  second = draw_individual_income(rng)
  return first, second, [left + right for left, right in zip(first, second)]


if __name__ == "__main__":
  import statistics

  generator = random.Random(20260827)
  draws = [draw_household_income(generator)[2] for _ in range(20_000)]
  print(f"{'age':>4}{'p10':>12}{'median':>12}{'mean':>12}{'p90':>12}")
  for age in (25, 30, 35, 40, 45, 50, 55, 60, 64):
    values = [draw[age - START_AGE] for draw in draws]
    deciles = statistics.quantiles(values, n=10)
    print(f"{age:>4}{deciles[0]:>12,.0f}{statistics.median(values):>12,.0f}"
          f"{statistics.fmean(values):>12,.0f}{deciles[8]:>12,.0f}")
