"""Filtre ex ante des pays-annees non investissables du panel annuel.

Le filtre ne retire pas une observation parce que son rendement est mauvais.
Il retire les lignes pour lesquelles une observation annuelle synchronisee ne
peut pas representer simultanement un marche negociable, une monnaie
convertible et une couverture renouvelable.

Deux criteres publics et reproductibles sont utilises :

1. les fermetures ou restrictions prolongees de marche de la table A.III
   d'Anarkulova, Cederburg et O'Doherty (2025), en ne gardant que les pays de
   notre panel et les evenements posterieurs a 1926 ;
2. une variation annuelle du CPI d'au moins +50 % ou d'au plus -20 %, seuil
   mecanique qui signale un regime dans lequel taux officiel, reforme
   monetaire et pouvoir d'achat ne peuvent pas etre raccordes proprement dans
   notre panel annuel.

Les donnees brutes ne sont jamais modifiees. Le panel integral reste disponible
comme stress historique et le filtre doit etre lu comme une convention
d'investissabilite, non comme une negation du cout economique des guerres.
"""

from __future__ import annotations


# Periodes calendaires recouvertes par les observations multi-mois de la table
# A.III d'ACO (2025). Les bornes sont inclusives. Les evenements de deux mois
# sont conserves : notre frequence annuelle ne permet pas de les synchroniser
# proprement avec les autres classes d'actifs.
ACO_MARKET_DISRUPTIONS: dict[str, tuple[tuple[int, int, str], ...]] = {
  "Belgium": (
    (1940, 1940, "fermeture ou restriction de marche ACO A.III"),
    (1944, 1945, "fermeture ou restriction de marche ACO A.III"),
  ),
  "Denmark": (
    (1940, 1940, "fermeture ou restriction de marche ACO A.III"),
  ),
  "France": (
    (1939, 1941, "fermeture ou restriction de marche ACO A.III"),
    (1974, 1974, "restriction de marche ACO A.III"),
    (1979, 1979, "restriction de marche ACO A.III"),
  ),
  "Germany": (
    (1931, 1932, "crise bancaire et restriction de marche ACO A.III"),
    (1943, 1948, "fermeture de marche et reforme monetaire ACO A.III"),
  ),
  "Japan": (
    (1945, 1949, "fermeture de marche ACO A.III"),
  ),
  "Netherlands": (
    (1940, 1940, "fermeture ou restriction de marche ACO A.III"),
    (1944, 1946, "fermeture ou restriction de marche ACO A.III"),
  ),
  "Norway": (
    (1940, 1940, "fermeture ou restriction de marche ACO A.III"),
  ),
  "Portugal": (
    (1974, 1977, "fermeture ou restriction de marche ACO A.III"),
  ),
  "Switzerland": (
    (1940, 1940, "restriction de marche ACO A.III"),
  ),
}

MAX_INFLATION = 0.50
MAX_DEFLATION = -0.20


def exclusion_reasons(country: str, year: int,
                      inflation: float) -> tuple[str, ...]:
  """Retourne les criteres d'exclusion applicables a une ligne."""
  reasons: list[str] = []
  for first, last, reason in ACO_MARKET_DISRUPTIONS.get(country, ()):
    if first <= year <= last:
      reasons.append(reason)
  if inflation >= MAX_INFLATION:
    reasons.append("inflation annuelle superieure ou egale a 50 %")
  elif inflation <= MAX_DEFLATION:
    reasons.append("deflation annuelle inferieure ou egale a -20 %")
  return tuple(dict.fromkeys(reasons))


def exclusion_reason(country: str, year: int, inflation: float) -> str | None:
  reasons = exclusion_reasons(country, year, inflation)
  return "; ".join(reasons) if reasons else None
