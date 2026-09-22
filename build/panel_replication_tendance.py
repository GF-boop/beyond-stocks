"""Complete the replication panel in the numeraire of each resident.

Every sleeve of a country-year row measures the change in purchasing power of a
household that lives in that country. The former version attached to each
country world returns deflated by US CPI or by each issuer's own CPI, and so
mixed numeraires.

World stocks and gold stay unhedged: their nominal return is converted into the
resident's currency, then deflated by the resident's inflation. The main case
hedges global bonds and managed futures instead. Under covered interest parity,
it keeps the asset's excess return over the cash actually embedded in the
source series and replaces it with the resident's real bill. For bonds, this
cash is the issuer's bill; for managed futures, it is the US collateral
observed in the source series. The carry is therefore explicit and the ex post
spot exchange rate does not enter the main case. Unhedged versions are kept in
separate columns for sensitivity analysis.

The bond basket requires at least eight issuers. Over 1927--2025 this floor
removes no observation: the basket actually produced contains 13 to 16
sovereigns, 16 in most of the panel.
"""

from __future__ import annotations

import csv
import math
import os
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
# Every sovereign of the panel enters the basket, including the resident's
# own: a real global bond index does contain the debt of the investor's country,
# and the basket is then identical for all residents, as covered interest parity
# requires. A basket restricted to the four largest issuers would be misnamed and
# concentrate diversification on a handful of sovereign histories.
BOND_ISSUERS = (
  "Australia", "Belgium", "Denmark", "Finland", "France", "Germany",
  "Italy", "Japan", "Netherlands", "Norway", "Portugal", "Spain",
  "Sweden", "Switzerland", "UK", "USA",
)
# At least eight issuers for a year to count as global. Over 1927-2025 this
# floor costs no observation: the only years dropped are before 1882.
MIN_BOND_ISSUERS = 8
BOND_FEE = 0.001
EQUITY_FEE_BEFORE_1970 = 0.002
WORLD_FROM = 1970


def read_rows(path: str) -> list[dict[str, str]]:
  with open(path, newline="", encoding="utf-8") as handle:
    return list(csv.DictReader(handle))


def convert_local_real_return(
    local_real: float,
    issuer_inflation: float,
    issuer_fx: float,
    issuer_previous_fx: float,
    resident_inflation: float,
    resident_fx: float,
    resident_previous_fx: float,
    ) -> float:
  """Convert a local real return into the resident's real return."""
  nominal_local = (1.0 + local_real) * (1.0 + issuer_inflation) - 1.0
  currency = ((resident_fx / issuer_fx)
              / (resident_previous_fx / issuer_previous_fx))
  return (1.0 + nominal_local) * currency / (1.0 + resident_inflation) - 1.0


def convert_us_real_return(
    us_real: float,
    us_inflation: float,
    resident_inflation: float,
    resident_fx: float,
    resident_previous_fx: float,
    ) -> float:
  """Convert a real USD return into the resident's real return."""
  nominal_us = (1.0 + us_real) * (1.0 + us_inflation) - 1.0
  usd_currency_return = resident_fx / resident_previous_fx
  return ((1.0 + nominal_us) * usd_currency_return
          / (1.0 + resident_inflation) - 1.0)


def covered_real_return(asset_real: float, foreign_bill_real: float,
                        resident_bill_real: float) -> float:
  """Hedged real return, carry included, under covered interest parity."""
  if foreign_bill_real <= -1.0:
    raise ValueError("The foreign bill return must be above -100%")
  return ((1.0 + resident_bill_real)
          * (1.0 + asset_real) / (1.0 + foreign_bill_real) - 1.0)


def fixed_notional_hedged_real_return(
    asset_real: float, foreign_bill_real: float, resident_bill_real: float,
    foreign_inflation: float, resident_inflation: float,
    foreign_fx: float, foreign_previous_fx: float,
    resident_fx: float, resident_previous_fx: float,
    ) -> float:
  """Real return of a foreign asset with a forward on the initial notional.

  The ``covered_real_return`` convention implicitly assumes that the terminal
  value of the whole asset is hedged. A fund more usually hedges the notional
  known at the start of the period, then rolls the forward. This function
  therefore adds the payoff of the forward on one unit of foreign currency to
  the realised local return. The forward is priced under CIP from the observed
  nominal bills; the rest of the terminal value keeps an FX exposure.
  """
  foreign_bill_nominal = ((1.0 + foreign_bill_real)
                          * (1.0 + foreign_inflation))
  resident_bill_nominal = ((1.0 + resident_bill_real)
                           * (1.0 + resident_inflation))
  asset_nominal = (1.0 + asset_real) * (1.0 + foreign_inflation)
  currency = ((resident_fx / foreign_fx)
              / (resident_previous_fx / foreign_previous_fx))
  gross_resident_nominal = (
      resident_bill_nominal / foreign_bill_nominal
      + (asset_nominal - 1.0) * currency)
  return gross_resident_nominal / (1.0 + resident_inflation) - 1.0


def build(
    panel: list[dict[str, str]],
    world: dict[int, dict[str, str]],
    trend_us_real: dict[int, float],
    trend_us_cash_real: dict[int, float],
    gold_us_real: dict[int, float],
    excluded_bond_issuers: frozenset[str] = frozenset(),
    excluded_bond_issuer_years: frozenset[tuple[str, int]] = frozenset(),
    source_inflation: dict[str, dict[int, float]] | None = None,
    ) -> list[dict[str, str | float]]:
  """``source_inflation`` gives, for ``"gold"`` and ``"trend"``, the US
  inflation used to deflate each source series (December-to-December CPI). It
  recovers the exact nominal USD return before conversion into the resident's
  currency. Without it, the conversion re-nominalises with the US inflation of
  the JST panel, which is not the source deflator."""
  by_country_year = {
    (row["country"], int(row["year"])): row for row in panel
  }
  us_inflation = {
    year: float(row["inflation"])
    for (country, year), row in by_country_year.items()
    if country == "USA"
  }
  result: list[dict[str, str | float]] = []
  for row in panel:
    country = row["country"]
    year = int(row["year"])
    previous = by_country_year.get((country, year - 1))
    gold_inflation = trend_inflation = us_inflation.get(year)
    if source_inflation is not None:
      gold_inflation = source_inflation["gold"].get(year)
      trend_inflation = source_inflation["trend"].get(year)
    if (gold_inflation is None or trend_inflation is None
        or previous is None or year not in trend_us_real
        or year not in trend_us_cash_real
        or year not in gold_us_real or year not in us_inflation):
      continue

    resident_inflation = float(row["inflation"])
    resident_fx = float(row["xrusd"])
    resident_previous_fx = float(previous["xrusd"])
    if (resident_inflation <= -1.0 or resident_fx <= 0.0
        or resident_previous_fx <= 0.0):
      continue

    resident_bill = float(row["bill_real"])
    covered_bonds: list[float] = []
    fixed_notional_bonds: list[float] = []
    unhedged_bonds: list[float] = []
    unhedged_bills: list[float] = []
    for issuer in BOND_ISSUERS:
      if (issuer in excluded_bond_issuers
          or (issuer, year) in excluded_bond_issuer_years):
        continue
      issuer_row = by_country_year.get((issuer, year))
      issuer_previous = by_country_year.get((issuer, year - 1))
      if issuer_row is None or issuer_previous is None:
        continue
      issuer_fx = float(issuer_row["xrusd"])
      issuer_previous_fx = float(issuer_previous["xrusd"])
      if issuer_fx <= 0.0 or issuer_previous_fx <= 0.0:
        continue
      arguments = (
        float(issuer_row["inflation"]), issuer_fx, issuer_previous_fx,
        resident_inflation, resident_fx, resident_previous_fx,
      )
      issuer_bond = float(issuer_row["bond_real"])
      issuer_bill = float(issuer_row["bill_real"])
      covered_bonds.append(covered_real_return(
        issuer_bond, issuer_bill, resident_bill))
      fixed_notional_bonds.append(fixed_notional_hedged_real_return(
        issuer_bond, issuer_bill, resident_bill,
        float(issuer_row["inflation"]), resident_inflation,
        issuer_fx, issuer_previous_fx, resident_fx, resident_previous_fx))
      unhedged_bonds.append(convert_local_real_return(
        issuer_bond, *arguments))
      unhedged_bills.append(convert_local_real_return(
        issuer_bill, *arguments))

    if len(covered_bonds) < MIN_BOND_ISSUERS:
      continue
    world_bond = sum(covered_bonds) / len(covered_bonds)
    world_bond = (1.0 + world_bond) * (1.0 - BOND_FEE) - 1.0
    world_bond_fixed_notional = sum(fixed_notional_bonds) / len(fixed_notional_bonds)
    world_bond_fixed_notional = ((1.0 + world_bond_fixed_notional)
                                 * (1.0 - BOND_FEE) - 1.0)
    world_bill = resident_bill
    world_bond_unhedged = sum(unhedged_bonds) / len(unhedged_bonds)
    world_bond_unhedged = ((1.0 + world_bond_unhedged)
                           * (1.0 - BOND_FEE) - 1.0)
    world_bill_unhedged = sum(unhedged_bills) / len(unhedged_bills)

    if year >= WORLD_FROM and year in world:
      world_equity = convert_us_real_return(
        float(world[year]["equity_real"]), us_inflation[year],
        resident_inflation, resident_fx, resident_previous_fx)
      world_equity_source = "MSCI World, resident currency"
    else:
      world_equity = float(
        row["world_equity_real_resident_reconstructed"])
      world_equity = ((1.0 + world_equity)
                      * (1.0 - EQUITY_FEE_BEFORE_1970) - 1.0)
      world_equity_source = "reconstructed, resident currency"

    trend_hedged = covered_real_return(
      trend_us_real[year], trend_us_cash_real[year], resident_bill)
    trend_fixed_notional = fixed_notional_hedged_real_return(
      trend_us_real[year], trend_us_cash_real[year], resident_bill,
      trend_inflation, resident_inflation,
      1.0, 1.0, resident_fx, resident_previous_fx)
    trend_unhedged = convert_us_real_return(
      trend_us_real[year], trend_inflation, resident_inflation,
      resident_fx, resident_previous_fx)
    converted_gold = convert_us_real_return(
      gold_us_real[year], gold_inflation, resident_inflation,
      resident_fx, resident_previous_fx)

    output = dict(row)
    output.update({
      "world_equity_real": world_equity,
      "world_equity_source": world_equity_source,
      "world_bond_real": world_bond,
      "world_bond_real_fixed_notional": world_bond_fixed_notional,
      "world_bill_real": world_bill,
      "world_bond_real_unhedged": world_bond_unhedged,
      "world_bill_real_unhedged": world_bill_unhedged,
      "world_bond_issuers": len(covered_bonds),
      "trend_real": trend_hedged,
      "trend_real_fixed_notional": trend_fixed_notional,
      "trend_cash_us_real": trend_us_cash_real[year],
      "trend_real_unhedged": trend_unhedged,
      "gold_real": converted_gold,
    })
    if not all(math.isfinite(float(output[column])) for column in (
        "world_equity_real", "world_bond_real", "world_bond_real_fixed_notional", "world_bill_real",
        "world_bond_real_unhedged", "world_bill_real_unhedged",
        "trend_real", "trend_real_fixed_notional", "trend_cash_us_real", "trend_real_unhedged",
        "gold_real")):
      continue
    result.append(output)
  return result


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", help="input replication panel")
  parser.add_argument("--out", help="output extended panel")
  parser.add_argument("--trend", help="annual managed-futures input")
  parser.add_argument("--world", help="world-equity input")
  parser.add_argument("--gold", help="gold input")
  parser.add_argument("--exclude-bond-issuer", action="append", default=[],
                      help="remove an issuer from every global bond basket (repeatable)")
  parser.add_argument("--exclude-bond-issuer-year", action="append", default=[],
                      metavar="COUNTRY:YEAR",
                      help="diagnostic only: remove a source country-year from global bond baskets")
  args = parser.parse_args()
  data = os.path.join(HERE, "..", "data")
  trend_path = args.trend or os.path.join(data, "managed-futures-annual-real.csv")
  panel_path = args.panel or os.path.join(data, "replication-panel.csv")
  out = args.out or os.path.join(data, "replication-panel-trend.csv")
  world_path = args.world or os.path.join(data, "jst-ntsg-panel-2025.csv")
  gold_path = args.gold or os.path.join(data, "gold-annual.csv")

  trend_rows = read_rows(trend_path)
  trend = {int(row["year"]): float(row["trend_real"])
           for row in trend_rows}
  trend_cash = {int(row["year"]): float(row["cash_real"])
                for row in trend_rows}
  world = {int(row["year"]): row for row in read_rows(world_path)}
  gold = {int(row["year"]): float(row["gold_real"])
          for row in read_rows(gold_path)}
  unknown = sorted(set(args.exclude_bond_issuer) - set(BOND_ISSUERS))
  if unknown:
    raise ValueError(f"unknown bond issuer(s): {', '.join(unknown)}")
  excluded_bond_issuer_years = set()
  for value in args.exclude_bond_issuer_year:
    try:
      country, year = value.rsplit(":", 1)
      if country not in BOND_ISSUERS:
        raise ValueError(f"unknown bond issuer: {country}")
      excluded_bond_issuer_years.add((country, int(year)))
    except ValueError:
      raise
  rows = build(read_rows(panel_path), world, trend, trend_cash, gold,
               frozenset(args.exclude_bond_issuer),
               frozenset(excluded_bond_issuer_years))

  fieldnames = [
    "country", "year", "domestic_equity_real", "international_equity_real",
    "international_equity_real_constant_real_fx",
    "world_equity_real_resident_reconstructed", "xrusd",
    "world_equity_real", "world_equity_source", "bond_real", "bill_real",
    "world_bond_real", "world_bond_real_fixed_notional", "world_bill_real", "world_bond_real_unhedged",
    "world_bill_real_unhedged", "world_bond_issuers", "inflation",
    "trend_real", "trend_real_fixed_notional", "trend_cash_us_real", "trend_real_unhedged", "gold_real",
  ]
  with open(out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

  years = [int(row["year"]) for row in rows]
  issuers = sorted({int(row["world_bond_issuers"]) for row in rows})
  print(f"{len(rows)} country-years ({min(years)}-{max(years)}), "
        f"emetteurs obligataires {issuers} "
        f"-> {os.path.normpath(out)}")


if __name__ == "__main__":
  main()
