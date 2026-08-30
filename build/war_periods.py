"""Periodes de guerre par pays, pour la variante hors conflit du panel.

Un investisseur d'aujourd'hui peut juger que les obligations souveraines
allemandes de 1922 ou japonaises de 1945 ne renseignent pas sur le risque
obligataire actuel : ces annees melangent defaut de fait, occupation et
reconstruction monetaire. Cette variante permet de les retirer.

Le retrait est fait pays par pays et non sur des annees globales : la Suede est
restee neutre pendant les deux guerres mondiales, l'Espagne a connu sa propre
guerre civile, et les Etats-Unis n'entrent qu'en 1917 et 1941.

Les bornes incluent les annees d'apres-guerre immediates lorsque le reglement
monetaire s'y prolonge -- l'hyperinflation allemande culmine en 1923, cinq ans
apres l'armistice, et la reforme du Reichsmark date de 1924.

Ce decoupage est un choix documente, pas une verite historique : d'autres
bornes seraient defendables. Il sert a mesurer la sensibilite du resultat, pas
a etablir un fait.
"""

from __future__ import annotations

# Premiere Guerre mondiale et reglement monetaire qui la suit.
WWI = {
  "Australia": (1914, 1921),
  "Belgium": (1914, 1923),
  "Canada": (1914, 1921),
  "Denmark": (1914, 1921),   # neutre, mais economie de guerre et inflation
  "Finland": (1914, 1922),   # independance 1917 puis guerre civile 1918
  "France": (1914, 1926),    # stabilisation Poincare
  "Germany": (1914, 1924),   # hyperinflation jusqu'a la reforme monetaire
  "Italy": (1915, 1922),
  "Japan": (1914, 1920),
  "Netherlands": (1914, 1921),  # neutre
  "Norway": (1914, 1921),       # neutre
  "Portugal": (1916, 1924),
  "Spain": (1914, 1921),        # neutre
  "Sweden": (1914, 1921),       # neutre
  "Switzerland": (1914, 1921),  # neutre
  "UK": (1914, 1921),
  "USA": (1917, 1920),
}

# Seconde Guerre mondiale et reglement monetaire qui la suit.
WWII = {
  "Australia": (1939, 1948),
  "Belgium": (1940, 1948),
  "Canada": (1939, 1947),
  "Denmark": (1940, 1948),
  "Finland": (1939, 1949),   # guerres d'Hiver et de Continuation, reparations
  "France": (1939, 1949),
  "Germany": (1939, 1950),   # reforme du Deutsche Mark en 1948
  "Italy": (1940, 1948),
  "Japan": (1937, 1951),     # guerre en Chine, occupation, traite de 1951
  "Netherlands": (1940, 1948),
  "Norway": (1940, 1948),
  "Portugal": (1939, 1946),  # neutre, mais economie de guerre
  "Spain": (1936, 1945),     # guerre civile puis autarcie
  "Sweden": (1939, 1946),    # neutre
  "Switzerland": (1939, 1946),  # neutre
  "UK": (1939, 1949),
  "USA": (1941, 1946),
}


def is_war_year(country: str, year: int) -> bool:
  """Vrai si l'annee tombe dans un conflit majeur pour ce pays."""
  for table in (WWI, WWII):
    span = table.get(country)
    if span is not None and span[0] <= year <= span[1]:
      return True
  return False
