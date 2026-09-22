"""Fees and transaction cost of the managed-futures sleeve.

These two values used to be imported from a module of the sibling repository.
They are now computed directly from ``data/managed-futures-monthly.csv``, the
same series that feeds the proxy, so that no constant silently goes stale if
the signal or the universe changes.

* ``TREND_FEE``: annual fee charged on the sleeve. 0.85%, the median of the
  managed-futures ETFs available in 2026 (iMGP DBi UCITS 0.75%, DBMF 0.85%,
  KMLM 0.90%), which charge fixed fees without a performance fee.
* ``TREND_COST``: annual transaction cost. Mean monthly turnover of the proxy
  (column ``mf_1_6_12_turnover``), annualised (x12), times a round-trip spread
  of 3 basis points. The spread is that of today's liquid futures: the question
  is forward-looking. Turnover is about 20.5x per year for the proxy, which
  rebalances four sectors by inverse volatility, giving a cost of about 0.61%.
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
  """Mean annualized turnover of the managed-futures proxy actually used."""
  with open(path, newline="", encoding="utf-8") as handle:
    values = [float(row["mf_1_6_12_turnover"])
              for row in csv.DictReader(handle)
              if row.get("mf_1_6_12_turnover")]
  if not values:
    raise ValueError(f"turnover not found in {path}")
  return sum(values) / len(values) * 12.0


TREND_TURNOVER = measured_turnover()
TREND_COST = TREND_TURNOVER * TREND_SPREAD

# Compatibility alias for the former import name.
DEFAULT_TREND_FEE = TREND_FEE
DEFAULT_TREND_COST = TREND_COST
