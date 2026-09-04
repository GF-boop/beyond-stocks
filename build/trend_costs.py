"""Frais et cout de transaction de la poche managed futures.

Ces deux valeurs etaient auparavant importees d'un module du depot voisin. Elles
sont ici calculees directement depuis ``data/managed-futures-monthly.csv``, la
meme serie que celle qui alimente le proxy, pour qu'aucune constante ne se
perime en silence si le signal ou l'univers change.

* ``TREND_FEE`` : frais annuels preleves sur la poche. 0,85 %, mediane des ETF
  managed futures accessibles en 2026 (iMGP DBi UCITS 0,75 %, DBMF 0,85 %,
  KMLM 0,90 %), a frais fixes sans commission de performance.
* ``TREND_COST`` : cout de transaction annuel. Turnover moyen mensuel du proxy
  (colonne ``mf_1_6_12_turnover``), annualise (x12), multiplie par un spread
  aller-retour de 3 points de base. Le spread est celui des futures liquides
  d'aujourd'hui : la question posee est prospective. Le turnover vaut environ
  20,5x par an pour le proxy, qui rebalance quatre secteurs par inverse-
  volatilite, ce qui donne un cout d'environ 0,61 %.
"""

from __future__ import annotations

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MONTHLY_TURNOVER_PATH = os.path.join(
  HERE, "..", "data", "managed-futures-monthly.csv")

TREND_FEE = 0.0085
TREND_SPREAD = 3e-4


def measured_turnover(path: str = MONTHLY_TURNOVER_PATH) -> float:
  """Turnover annualise moyen du proxy managed futures effectivement utilise."""
  with open(path, newline="", encoding="utf-8") as handle:
    values = [float(row["mf_1_6_12_turnover"])
              for row in csv.DictReader(handle)
              if row.get("mf_1_6_12_turnover")]
  if not values:
    raise ValueError(f"turnover introuvable dans {path}")
  return sum(values) / len(values) * 12.0


TREND_TURNOVER = measured_turnover()
TREND_COST = TREND_TURNOVER * TREND_SPREAD

# Alias de compatibilite avec l'ancien nom d'import.
DEFAULT_TREND_FEE = TREND_FEE
DEFAULT_TREND_COST = TREND_COST
