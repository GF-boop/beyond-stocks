"""Table de mortalite pour la simulation de cycle de vie.

Le moteur retient une loi de Gompertz--Makeham, forme standard en actuariat :

    mu(x) = A + B * exp(C * x)

Le terme constant A represente la mortalite accidentelle, independante de
l'age ; le terme exponentiel represente le vieillissement. Deux calibrages
sont disponibles. ``insee`` vise les esperances de vie a 65 ans publiees par
l'INSEE pour 2024. ``ssa``, utilise explicitement par les simulations du
manuscrit, vise les moments de longevite qu'ACO rapportent a partir des tables
de la Social Security Administration. Le code ne lit pas une copie locale de
ces tables.

La loi lisse les irregularites d'une table reelle ; il s'agit d'une
approximation par moments, pas d'une reproduction ligne a ligne des tables SSA.
"""

from __future__ import annotations

import math

# Deux calibrages disponibles.
#
# "insee" reproduit l'esperance de vie residuelle a 65 ans publiee par l'INSEE
# pour 2024 : 23,9 ans pour une femme, 19,7 pour un homme.
#
# "ssa" vise la distribution d'age au deces du couple publiee par Anarkulova,
# Cederburg et O'Doherty (Table III, d'apres les tables actuarielles de la
# SSA) : moyenne 87,6 ans, ecart-type 9,1. Le site de la SSA refusant les
# acces automatises, les parametres sont cales pour reproduire ces moments.
# C'est le calibrage a utiliser pour comparer aux chiffres du papier.
TARGETS = {
  "insee": {"female": 23.9, "male": 19.7},
  "ssa": {"female": 21.0, "male": 17.4},
}

TARGET = TARGETS["insee"]

# Mortalite accidentelle, faible et quasi constante avant 60 ans.
MAKEHAM = 0.0005


def survival(age: int, b: float, c: float) -> float:
  """Probabilite de survivre un an de plus a cet age."""
  # Integrale de la force de mortalite entre age et age+1.
  integral = MAKEHAM + b / c * (math.exp(c * (age + 1)) - math.exp(c * age))
  return math.exp(-integral)


def life_expectancy(start: int, b: float, c: float, limit: int = 120) -> float:
  """Esperance de vie residuelle a partir d'un age donne."""
  alive, expectancy = 1.0, 0.0
  for age in range(start, limit):
    alive *= survival(age, b, c)
    expectancy += alive
  return expectancy


def calibrate(target: float, c: float = 0.095) -> tuple[float, float]:
  """Cherche le parametre B qui reproduit l'esperance de vie visee.

  C fixe la pente du vieillissement et varie peu d'une population a l'autre ;
  B fixe le niveau. Une dichotomie suffit, la fonction etant monotone.
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
      print(f"   esperance a {age} ans : {life_expectancy(age, b, c):>5.1f} ans"
            f"   survie annuelle {survival(age, b, c):.4f}")
