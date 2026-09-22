"""Quality exclusions for the annual lifecycle panel.

Raw data are never modified. This list only removes from the simulations the
country-years whose annual aggregation does not represent an investable
observation synchronised across asset classes.

Japan 1945--1949: ACO (2025), Table A.III, documents a closure of the stock
exchange from September 1945 to May 1949 and smooths the event in its monthly
panel. JST keeps in 1945 an inflation of 975.6% and an official exchange rate
that is still administered, then provides no equity return in 1946--1947. The
final annual panel would thus keep the 1945 collapse while losing the monetary
transition and part of the reopening. This point must not be treated as an
ordinary annual return of a global portfolio.
"""

from __future__ import annotations


SUSPECT_PERIODS = {
  "Japan": ((1945, 1949,
             "market closure, administered exchange rate, and incomplete annual "
             "transition"),),
}


def exclusion_reason(country: str, year: int) -> str | None:
  for first, last, reason in SUSPECT_PERIODS.get(country, ()):
    if first <= year <= last:
      return reason
  return None

