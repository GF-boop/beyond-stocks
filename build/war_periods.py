"""War periods by country, for the conflict-free variant of the panel.

An investor today may judge that German sovereign bonds of 1922 or Japanese
ones of 1945 say nothing about current bond risk: those years mix de facto
default, occupation and monetary reconstruction. This variant removes them.

The removal is done country by country, not on global years: Sweden stayed
neutral in both world wars, Spain had its own civil war, and the United States
entered only in 1917 and 1941.

The bounds include the immediate post-war years when the monetary settlement
extends into them -- German hyperinflation peaked in 1923, five years after the
armistice, and the Reichsmark reform dates from 1924.

This split is a documented choice, not a historical truth: other bounds would
be defensible. It measures the sensitivity of the result, not a fact.
"""

from __future__ import annotations

# First World War and the monetary settlement that followed.
WWI = {
  "Australia": (1914, 1921),
  "Belgium": (1914, 1923),
  "Canada": (1914, 1921),
  "Denmark": (1914, 1921),   # neutre, mais economie de guerre et inflation
  "Finland": (1914, 1922),   # independance 1917 puis guerre civile 1918
  "France": (1914, 1926),    # stabilisation Poincare
  "Germany": (1914, 1924),   # hyperinflation until the currency reform
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

# Second World War and the monetary settlement that followed.
WWII = {
  "Australia": (1939, 1948),
  "Belgium": (1940, 1948),
  "Canada": (1939, 1947),
  "Denmark": (1940, 1948),
  "Finland": (1939, 1949),   # guerres d'Hiver et de Continuation, reparations
  "France": (1939, 1949),
  "Germany": (1939, 1950),   # Deutsche Mark reform in 1948
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
  """True if the year falls in a major conflict for this country."""
  for table in (WWI, WWII):
    span = table.get(country)
    if span is not None and span[0] <= year <= span[1]:
      return True
  return False
