"""Mortality table for the lifecycle simulation.

The engine uses a Gompertz--Makeham law, a standard actuarial form:

    mu(x) = A + B * exp(C * x)

The constant term A is accidental mortality, independent of age; the
exponential term is ageing. Two calibrations are available. ``insee`` targets
the life expectancies at 65 published by INSEE for 2024. ``ssa``, used
explicitly by the simulations of the paper, targets the longevity moments that
ACO report from the Social Security Administration tables. The code does not
read a local copy of these tables.

The law smooths the irregularities of an actual table; it is an approximation
by moments, not a line-by-line reproduction of the SSA tables.
"""

from __future__ import annotations

import math

# Two calibrations are available.
#
# "insee" reproduces the remaining life expectancy at 65 published by INSEE for
# 2024: 23.9 years for a woman, 19.7 for a man.
#
# "ssa" targets the distribution of the couple's age at last death reported by
# Anarkulova, Cederburg and O'Doherty (Table III, from the SSA actuarial tables):
# mean 87.6 years, standard deviation 9.1. The SSA website refuses automated
# access, so the parameters are set to approximate these moments (the simulated
# couple gives a mean of 88.1 and a standard deviation of 9.2). This is the
# calibration to use when comparing with the paper.
TARGETS = {
  "insee": {"female": 23.9, "male": 19.7},
  "ssa": {"female": 21.0, "male": 17.4},
}

TARGET = TARGETS["insee"]

# Accidental mortality is low and nearly constant before age 60.
MAKEHAM = 0.0005


def survival(age: int, b: float, c: float) -> float:
  """Probabilite de survivre un an de plus a cet age."""
  # Integral of the force of mortality between age and age+1.
  integral = MAKEHAM + b / c * (math.exp(c * (age + 1)) - math.exp(c * age))
  return math.exp(-integral)


def life_expectancy(start: int, b: float, c: float, limit: int = 120) -> float:
  """Remaining life expectancy from a given age."""
  alive, expectancy = 1.0, 0.0
  for age in range(start, limit):
    alive *= survival(age, b, c)
    expectancy += alive
  return expectancy


def calibrate(target: float, c: float = 0.095) -> tuple[float, float]:
  """Find the parameter B that reproduces the target life expectancy.

  C sets the slope of ageing and varies little across populations; B sets the
  level. A bisection is enough because the function is monotonic.
  """
  low, high = 1e-9, 1e-2
  for _ in range(200):
    middle = (low + high) / 2
    if life_expectancy(65, middle, c) > target:
      low = middle
    else:
      high = middle
  return (low + high) / 2, c


def table(sex: str, calibration: str = "insee") -> dict[int, float]:
  """Probabilite de survie annuelle, par age."""
  b, c = calibrate(TARGETS[calibration][sex])
  return {age: survival(age, b, c) for age in range(20, 121)}


if __name__ == "__main__":
  for sex in ("female", "male"):
    b, c = calibrate(TARGET[sex])
    print(f"{sex:<8} B={b:.3e} C={c}")
    for age in (65, 75, 85, 95):
      print(f"   life expectancy at {age} years: {life_expectancy(age, b, c):>5.1f} years"
            f"   survie annuelle {survival(age, b, c):.4f}")
