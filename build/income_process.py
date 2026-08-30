"""Revenus stochastiques de cycle de vie utilises par Cederburg et al.

Le processus est le modele 6 de Guvenen, Karahan, Ozkan et Song (2021), avec
les parametres publies retranscrits dans une implementation publique. Comme
dans le cas central de Cederburg et al. (2025), les deux conjoints ont les types
permanents
medians ``alpha = beta = z0 = 0``. Restent aleatoires :

* les innovations persistantes et transitoires, melanges de deux normales ;
* la probabilite et la duree du non-emploi, dependantes de l'age et du revenu.

Une unite du modele vaut 1 000 dollars 2022. Ce facteur reproduit directement
la Figure 2 de Cederburg : environ 28 500 dollars de revenu median du menage a
25 ans et 69 000 dollars au sommet du profil. Les montants sont reels.

Sources amont : DOI 10.3982/ECTA14603 et fichier
``DiscretizeEarningsDynamicsModel.m`` du depot public
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
  """Profil quadratique ``g(t)`` du modele 6, age 25 a 64 ans."""
  if not START_AGE <= age < RETIRE_AGE:
    raise ValueError("Le profil de revenu est defini de 25 a 64 ans")
  t = (age - 24) / 10.0
  return 2.581 + 0.812 * t - 0.185 * t * t


def nonemployment_probability(age: int, persistent_income: float) -> float:
  t = (age - 24) / 10.0
  a, b, c, d = NONEMPLOYMENT
  xi = a + b * t + c * persistent_income + d * t * persistent_income
  # Forme stable de la fonction logistique dans les queues du processus.
  if xi >= 0.0:
    return 1.0 / (1.0 + math.exp(-min(xi, 700.0)))
  exponential = math.exp(max(xi, -700.0))
  return exponential / (1.0 + exponential)


def draw_individual_income(rng: random.Random) -> list[float]:
  """Tire une carriere annuelle en dollars reels 2022.

  Cederburg fixe ``z0`` a zero ; la premiere innovation persistante est donc
  tiree entre z0 et le revenu observe a 25 ans. En cas de choc de non-emploi,
  la fraction d'annee perdue est une exponentielle tronquee a un an.
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
  """Deux carrieres independantes et leur somme, appariees aux strategies."""
  first = draw_individual_income(rng)
  second = draw_individual_income(rng)
  return first, second, [left + right for left, right in zip(first, second)]


if __name__ == "__main__":
  import statistics

  generator = random.Random(20260827)
  draws = [draw_household_income(generator)[2] for _ in range(20_000)]
  print(f"{'age':>4}{'p10':>12}{'mediane':>12}{'moyenne':>12}{'p90':>12}")
  for age in (25, 30, 35, 40, 45, 50, 55, 60, 64):
    values = [draw[age - START_AGE] for draw in draws]
    deciles = statistics.quantiles(values, n=10)
    print(f"{age:>4}{deciles[0]:>12,.0f}{statistics.median(values):>12,.0f}"
          f"{statistics.fmean(values):>12,.0f}{deciles[8]:>12,.0f}")
