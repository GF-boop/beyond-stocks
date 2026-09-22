"""Ex ante filter of non-investable country-years in the annual panel.

The filter never removes an observation because its return is bad. It removes
the rows for which a synchronised annual observation cannot simultaneously
represent a tradable market, a convertible currency and a rollable hedge.

Two public and reproducible criteria are used:

1. the long market closures or restrictions of Table A.III of Anarkulova,
   Cederburg and O'Doherty (2025), keeping only the countries of our panel and
   the events after 1926;
2. an annual CPI change of at least +50% or at most -20%, a mechanical
   threshold that flags a regime in which the official rate, the monetary
   reform and purchasing power cannot be cleanly spliced in our annual panel.

Raw data are never modified. The full panel remains available as a historical
stress test, and the filter should be read as an investability convention, not
as a denial of the economic cost of wars.
"""

from __future__ import annotations


# Calendar periods covered by the multi-month observations of Table A.III of
# ACO (2025). Bounds are inclusive. Two-month events are kept: our annual
# frequency cannot synchronise them cleanly with the other asset classes.
ACO_MARKET_DISRUPTIONS: dict[str, tuple[tuple[int, int, str], ...]] = {
  "Belgium": (
    (1940, 1940, "market closure or restriction ACO A.III"),
    (1944, 1945, "market closure or restriction ACO A.III"),
  ),
  "Denmark": (
    (1940, 1940, "market closure or restriction ACO A.III"),
  ),
  "France": (
    (1939, 1941, "market closure or restriction ACO A.III"),
    (1974, 1974, "market restriction ACO A.III"),
    (1979, 1979, "market restriction ACO A.III"),
  ),
  "Germany": (
    (1931, 1932, "banking crisis and market restriction ACO A.III"),
    (1943, 1948, "market closure and currency reform ACO A.III"),
  ),
  "Japan": (
    (1945, 1949, "market closure ACO A.III"),
  ),
  "Netherlands": (
    (1940, 1940, "market closure or restriction ACO A.III"),
    (1944, 1946, "market closure or restriction ACO A.III"),
  ),
  "Norway": (
    (1940, 1940, "market closure or restriction ACO A.III"),
  ),
  "Portugal": (
    (1974, 1977, "market closure or restriction ACO A.III"),
  ),
  "Switzerland": (
    (1940, 1940, "market restriction ACO A.III"),
  ),
}

MAX_INFLATION = 0.50
MAX_DEFLATION = -0.20


def exclusion_reasons(country: str, year: int,
                      inflation: float) -> tuple[str, ...]:
  """Return the exclusion criteria that apply to a row."""
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
