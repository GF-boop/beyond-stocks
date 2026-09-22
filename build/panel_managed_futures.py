"""Convert the monthly managed-futures proxy into a real annual series.

The engine `managed_futures/run_managed_futures.py` publishes **nominal USD**
returns: its collateral is USD cash and local P&L is converted at the USD spot
rate. The simulation panel works entirely in **real** terms. Plugging one into
the other without deflating would inject a century of US inflation into the
trend sleeve.

The deflator is therefore the monthly **US** CPI, not the world inflation of
the NTSG panel: the currency in which the sleeve is denominated decides, not
the geographic composition of the equity index.

Deflation is done **month by month before compounding**. With twelve complete
months and the same CPI endpoints, it is algebraically equivalent to deflating
the compounded annual nominal return by the annual CPI ratio.

The series used is `mf_1_6_12_gross_return`, **gross**: fees and transaction
costs are applied downstream by the simulation scripts (see `trend_costs.py`),
which avoids double counting and keeps `--trend-fee` adjustable.

Input: `data/managed-futures-monthly.csv` and `data/cpi-monthly.csv`.
Output: `data/managed-futures-annual-real.csv`.

A year is kept only if its twelve months are present. No partial year is
created.
"""

from __future__ import annotations

import csv
import os
import statistics
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
TREND = DATA

VARIANT = "mf_1_6_12_gross_return"


def read_cpi(path: str) -> dict[str, float]:
  """Monthly US price index, to deflate USD returns."""
  with open(path, encoding="utf-8") as handle:
    return {row["month"]: float(row["cpi"])
            for row in csv.DictReader(handle) if row.get("cpi")}


def fill_isolated_gaps(cpi: dict[str, float]) -> tuple[dict[str, float], list[str]]:
  """Fill an isolated missing CPI month with the geometric mean of its neighbours.

  The BLS did not publish October 2025 (government shutdown): without that
  single month, the whole year 2025 would be lost although its twelve MF
  returns exist. Only a gap of exactly one month is filled, and never an
  endpoint of the series: a longer gap stays a gap, and the year is dropped.

  The interpolation applies to the deflator, not to market data: the canonical
  snapshot itself stays strictly free of interpolation.
  """
  filled = dict(cpi)
  patched: list[str] = []
  months = sorted(cpi)
  for index in range(1, len(months)):
    earlier, later = months[index - 1], months[index]
    if month_number(later) - month_number(earlier) != 2:
      continue
    missing = previous_month(later)
    filled[missing] = (cpi[earlier] * cpi[later]) ** 0.5
    patched.append(missing)
  return filled, patched


def month_number(month: str) -> int:
  year, part = month.split("-")
  return int(year) * 12 + int(part) - 1


def previous_month(month: str) -> str:
  number = month_number(month) - 1
  return f"{number // 12:04d}-{number % 12 + 1:02d}"


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--input", default=os.path.join(
      TREND, "managed-futures-monthly.csv"))
  parser.add_argument("--output", default=os.path.join(
      TREND, "managed-futures-annual-real.csv"))
  args = parser.parse_args()
  cpi, patched = fill_isolated_gaps(
      read_cpi(os.path.join(TREND, "cpi-monthly.csv")))

  monthly: dict[int, list[float]] = {}
  monthly_cash: dict[int, list[float]] = {}
  source = args.input
  with open(source, encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      nominal = row.get(VARIANT)
      if not nominal:
        continue
      month = row["month"]
      earlier = previous_month(month)
      if month not in cpi or earlier not in cpi:
        continue
      deflator = cpi[month] / cpi[earlier]
      real = (1.0 + float(nominal)) / deflator - 1.0
      monthly.setdefault(int(month[:4]), []).append(real)
      cash_nominal = row.get("mf_1_6_12_cash_collateral_return")
      if cash_nominal:
        cash_real = (1.0 + float(cash_nominal)) / deflator - 1.0
        monthly_cash.setdefault(int(month[:4]), []).append(cash_real)

  annual = {}
  annual_cash = {}
  for year, values in monthly.items():
    cash_values = monthly_cash.get(year, [])
    if len(values) != 12 or len(cash_values) != 12:
      continue
    compounded = 1.0
    for value in values:
      compounded *= 1.0 + value
    annual[year] = compounded - 1.0
    cash_compounded = 1.0
    for value in cash_values:
      cash_compounded *= 1.0 + value
    annual_cash[year] = cash_compounded - 1.0

  years = sorted(annual)
  out = args.output
  with open(out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["year", "trend_real", "cash_real"])
    for year in years:
      writer.writerow([year, annual[year], annual_cash[year]])

  values = [annual[year] for year in years]
  mean = statistics.fmean(values)
  volatility = statistics.stdev(values)
  print(f"{len(years)} years ({years[0]}-{years[-1]}), "
        f"real return {mean:.2%}, vol {volatility:.2%}, "
        f"Sharpe {mean / volatility:.2f}")
  if patched:
    print(f"CPI filled by interpolation ({len(patched)}): "
          f"{', '.join(patched)}")
  print(f"Written to {os.path.normpath(out)}")


if __name__ == "__main__":
  main()
