"""Exclusions de qualite du panel annuel de cycle de vie.

Les donnees brutes ne sont jamais modifiees. Cette liste retire seulement des
simulations les pays-annees pour lesquels l'agregation annuelle ne represente
pas une observation investissable et synchronisee entre classes d'actifs.

Japon 1945--1949 : ACO (2025), tableau A.III, documente une fermeture de la
bourse de septembre 1945 a mai 1949 et lisse l'evenement dans son panel
mensuel. JST conserve en 1945 une inflation de 975,6 % et un change officiel
encore administre, puis ne fournit aucun rendement actions en 1946--1947. Le
panel annuel final garderait ainsi l'effondrement de 1945 tout en perdant la
transition monetaire et une partie de la reouverture. Il ne faut pas traiter ce
point comme un rendement annuel ordinaire d'un portefeuille mondial.
"""

from __future__ import annotations


SUSPECT_PERIODS = {
  "Japan": ((1945, 1949,
             "fermeture de marche, change administre et transition annuelle "
             "incomplete"),),
}


def exclusion_reason(country: str, year: int) -> str | None:
  for first, last, reason in SUSPECT_PERIODS.get(country, ()):
    if first <= year <= last:
      return reason
  return None

