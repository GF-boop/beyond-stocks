"""Build the international-stock series as defined by Anarkulova, Cederburg
and O'Doherty (2023), also used in Anarkulova-Cederburg-O'Doherty ("Beyond
the Status Quo").

Definition of the paper (section 3, pp. 369-370): for a given country, the
nominal international return is the market-capitalisation-weighted mean of the
nominal returns of ALL the other markets of the panel, adjusted for exchange-rate
changes, then converted into real terms with local inflation.

The CSV also contains:

- a world index that includes the market of the country of residence,
  expressed in that country's currency and purchasing power;
- the country's exchange rate against the dollar, needed to convert the other
  world sleeves into the same numeraire;
- a counterfactual
``international_equity_real_constant_real_fx``: the same basket, with the same
markets and weights, but with the change in the real exchange rate (nominal
exchange rate plus inflation differential) neutralised. Freezing only the
nominal exchange rate would create absurd returns during foreign
hyperinflations. This is not the return of a forward hedge (its carry and costs
are not modelled); the series only isolates the real-exchange-rate channel.

The canonical weighting uses the historical market capitalisation of Kuvshinov
and Zimmermann, estimated as comparable GDP times their capitalisation/GDP
ratio. Maddison real GDP is a fallback only for years whose capitalisation
coverage is insufficient. The currency conversion uses `xrusd`, each country's
exchange rate against the dollar from JST, with the dollar as the pivot between
a foreign market and the domestic currency.
"""

from __future__ import annotations

import argparse
import csv
import math
import os

# A foreign market's return and its exchange-rate change must stay coupled:
# during the German hyperinflation of 1923, the local market gains billions of
# percent in nominal terms and the mark loses as much, the two almost cancelling
# out. Neutralising one without the other produces absurd returns.
#
# The filter therefore applies to the converted result, market by market: above
# this threshold, the market's contribution is dropped and the weights are
# renormalised over the remaining markets. The paper reports similar adjustments
# around major breaks (closure of the NYSE in 1914, Greek default of 2012).
# Price or exchange-rate breaks remain in the panel. Removing them on the basis
# of the realised return would use end-of-period information and change the
# investor's basket in hindsight. The quality checks document suspicious
# observations without filtering them here.
MAX_CONVERTED_RETURN: float | None = None

# JST exchange rates cross the Reichsmark--Deutsche Mark reform of 1948-49.
# Combining this parity jump with the 1949 annual equity return would give a
# foreign investor a continuously tradable return across a closure and a forced
# conversion. ACO (2025, Table A.III) document the German closure until 1948;
# our annual frequency cannot cleanly isolate the 1949 reopening. This exclusion
# rests on market availability, never on the return.
UNINVESTABLE_FOREIGN_MARKET_YEARS = {("Germany", 1949)}
MIN_CAP_COVERAGE = 0.75


GMD_NAMES = {"Australia": "Australia", "Belgium": "Belgium",
             "Denmark": "Denmark", "Finland": "Finland", "France": "France",
             "Germany": "Germany", "Italy": "Italy", "Japan": "Japan",
             "Netherlands": "Netherlands", "Norway": "Norway",
             "Portugal": "Portugal", "Spain": "Spain", "Sweden": "Sweden",
             "Switzerland": "Switzerland", "United Kingdom": "UK",
             "United States": "USA"}


def extend_recent(by_country: dict[str, dict[int, dict[str, float]]],
                  equity_path: str, gmd_path: str) -> None:
  """Extend the panel beyond JST with the 2021-2025 series.

  Equity returns come from total-return indexes and locally listed trackers
  (``data/equity-tr-recent.csv``), inflation and exchange rates from the Global
  Macro Database (``data/gmd-cpi-fx.csv``).

  The two sources do not measure exchange rates the same way: JST publishes an
  end-of-year rate, GMD an annual average, with gaps of up to twelve percent.
  Splicing the levels would therefore create a fictitious currency move in
  2021. Only the CHANGES in GMD are used, applied to the last known JST rate.
  """
  if not (os.path.exists(equity_path) and os.path.exists(gmd_path)):
    return

  equity: dict[tuple[str, int], float] = {}
  with open(equity_path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      equity[(row["country"], int(row["year"]))] = float(row["equity_nominal"])

  macro: dict[tuple[str, int], dict[str, float]] = {}
  with open(gmd_path, encoding="utf-8", errors="ignore") as handle:
    for row in csv.DictReader(handle):
      country = GMD_NAMES.get(row["countryname"])
      if not country or not row["year"].isdigit():
        continue
      entry: dict[str, float] = {}
      for source, target in (("CPI", "cpi"), ("USDfx", "fx")):
        value = row.get(source, "").strip()
        if value not in ("", ".", "NA"):
          try:
            entry[target] = float(value)
          except ValueError:
            pass
      if len(entry) == 2:
        macro[(country, int(row["year"]))] = entry

  for country, years in by_country.items():
    pivot = max(years)
    anchor_fx = years[pivot]["xrusd"]
    anchor_cpi = years[pivot]["cpi"]
    for year in range(pivot + 1, pivot + 12):
      if (country, year) not in equity or (country, year) not in macro:
        break
      previous = macro.get((country, year - 1))
      current = macro[(country, year)]
      if not previous:
        break
      # Relative change taken from GMD, applied to the JST level.
      anchor_fx *= current["fx"] / previous["fx"]
      anchor_cpi *= current["cpi"] / previous["cpi"]
      years[year] = {"eq_tr": equity[(country, year)],
                     "cpi": anchor_cpi, "xrusd": anchor_fx}


def read_jst(dta_path: str) -> dict[str, dict[int, dict[str, float]]]:
  import pandas as pd

  frame = pd.read_stata(dta_path)[
    ["year", "country", "eq_tr", "cpi", "xrusd"]].dropna()
  by_country: dict[str, dict[int, dict[str, float]]] = {}
  for record in frame.itertuples(index=False):
    by_country.setdefault(record.country, {})[int(record.year)] = {
      "eq_tr": record.eq_tr, "cpi": record.cpi, "xrusd": record.xrusd,
    }
  return by_country


def read_gdp_weights(dta_path: str) -> dict[tuple[str, int], float]:
  import pandas as pd

  frame = pd.read_stata(dta_path)[["year", "country", "rgdpmad", "pop"]]
  frame = frame.dropna(subset=["rgdpmad", "pop"])
  weights: dict[tuple[str, int], float] = {}
  for record in frame.itertuples(index=False):
    value = record.rgdpmad * record.pop
    if value > 0:
      weights[(record.country, int(record.year))] = value
  return weights


def extend_weights(weights: dict[tuple[str, int], float],
                   gmd_path: str) -> None:
  """Extend the market-size weights beyond Maddison with the real GDP of the
  Global Macro Database, spliced country by country on the last common year."""
  if not os.path.exists(gmd_path):
    return

  recent: dict[tuple[str, int], float] = {}
  with open(gmd_path, encoding="utf-8", errors="ignore") as handle:
    for row in csv.DictReader(handle):
      country = GMD_NAMES.get(row["countryname"])
      if not country or not row["year"].isdigit():
        continue
      value = row.get("rGDP_USD", "").strip()
      if value in ("", ".", "NA"):
        continue
      try:
        number = float(value)
      except ValueError:
        continue
      if number > 0:
        recent[(country, int(row["year"]))] = number

  last = {}
  for country, year in weights:
    last[country] = max(last.get(country, 0), year)

  for country, pivot in last.items():
    if (country, pivot) not in recent:
      continue
    scale = weights[(country, pivot)] / recent[(country, pivot)]
    for (name, year), value in recent.items():
      if name == country and year > pivot:
          weights[(country, year)] = value * scale


def read_mcap_ratios(path: str) -> dict[tuple[str, int], float]:
  """Capitalisation/GDP ratios from the cached Big Bang file."""
  ratios: dict[tuple[str, int], float] = {}
  if not path or not os.path.exists(path):
    return ratios
  with open(path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      try:
        value = float(row["mcap_gdp"])
      except (KeyError, ValueError):
        continue
      if value > 0.0:
        ratios[(row["country"], int(row["year"]))] = value
  return ratios


def capitalization_weights(
    gdp_weights: dict[tuple[str, int], float],
    ratios: dict[tuple[str, int], float],
    ) -> dict[tuple[str, int], float]:
  return {
    key: gdp * ratios[key]
    for key, gdp in gdp_weights.items()
    if key in ratios and gdp > 0.0 and ratios[key] > 0.0
  }


def build(by_country: dict[str, dict[int, dict[str, float]]],
          gdp_weights: dict[tuple[str, int], float],
          cap_weights: dict[tuple[str, int], float],
          excluded_markets: frozenset[str] = frozenset(),
          excluded_market_years: frozenset[tuple[str, int]] = frozenset(),
          ) -> list[dict[str, float | str]]:
  """For each country-year, compute the real return of international stocks
  as seen by an investor of that country."""
  # Keep excluded countries as possible residents so that shared macro inputs
  # (notably U.S. CPI for the MF sleeve) remain available. They are removed
  # from every investable international/world basket below; callers that test
  # a source-country omission also remove their resident rows at simulation.
  countries = list(by_country)
  investable_countries = [country for country in countries
                          if country not in excluded_markets]
  rows: list[dict[str, float | str]] = []

  for domestic in countries:
    for year, entry in sorted(by_country[domestic].items()):
      # Weights known at the end of the previous year fund the current year's
      # return. This avoids a weighting that already knows the measured performance.
      # A year is weighted entirely by capitalisation or entirely by GDP: the two
      # methods are never mixed within one basket.
      weight_year = year - 1
      candidates = [c for c in investable_countries
                    if year in by_country[c] and year - 1 in by_country[c]]
      # The returns panel sometimes starts before the first GDP observation of
      # the previous year. For this edge only, keeping the first year with
      # contemporaneous weights is better than dropping the whole observation; every
      # later year stays lagged.
      if sum((c, weight_year) in gdp_weights for c in candidates) < 5:
        weight_year = year
      cap_coverage = sum((c, weight_year) in cap_weights for c in candidates)
      if (candidates
          and cap_coverage / len(candidates) >= MIN_CAP_COVERAGE):
        weights = cap_weights
        weight_source = "capitalisation"
      else:
        weights = gdp_weights
        weight_source = "PIB proxy"

      others = [c for c in candidates
                if c != domestic and (c, weight_year) in weights]
      if len(others) < 4:
        continue

      shares_raw = [weights[(c, weight_year)] for c in others]
      total_weight = sum(shares_raw)
      if total_weight <= 0:
        continue
      shares = [w / total_weight for w in shares_raw]

      domestic_fx = by_country[domestic][year]["xrusd"]  # domestic currency per USD
      if not domestic_fx:
        continue

      # Nominal return of each foreign market, converted into domestic currency
      # with the dollar as the common pivot.
      nominal_international = 0.0
      real_international_constant_real_fx = 0.0
      retained_weight = 0.0
      for share, country in zip(shares, others):
        if ((country, year) in UNINVESTABLE_FOREIGN_MARKET_YEARS
            or (country, year) in excluded_market_years):
          continue
        foreign = by_country[country][year]
        foreign_fx = foreign["xrusd"]
        if not foreign_fx:
          continue
        # One unit of foreign currency is worth (fx_domestic / fx_foreign) in
        # domestic currency. The change in this rate over the year captures the
        # currency gain or loss added to the market's local return. Because JST
        # publishes only an end-of-period rate, the previous year serves as the
        # reference for the change.
        previous = by_country[domestic].get(year - 1, {})
        previous_foreign = by_country[country].get(year - 1, {})
        if not previous or not previous_foreign:
          continue
        foreign_inflation = foreign["cpi"] / previous_foreign["cpi"] - 1.0
        if foreign_inflation <= -1.0:
          continue
        fx_change = ((domestic_fx / foreign_fx)
                    / (previous["xrusd"] / previous_foreign["xrusd"])) - 1.0
        local_return = foreign["eq_tr"]
        # Total return for the domestic investor: the foreign market compounded
        # with the exchange-rate change.
        converted = (1.0 + local_return) * (1.0 + fx_change) - 1.0
        if (not math.isfinite(converted)
            or (MAX_CONVERTED_RETURN is not None
                and abs(converted) > MAX_CONVERTED_RETURN)):
          continue
        nominal_international += share * converted
        # Same market, same weight and same filter as in the observed basket. The
        # local real return is what the investor would see if the real exchange rate
        # stayed constant. Neutralising only the nominal rate would leave foreign
        # hyperinflations in the series.
        local_real_return = (
          (1.0 + local_return) / (1.0 + foreign_inflation) - 1.0
        )
        real_international_constant_real_fx += share * local_real_return
        retained_weight += share

      # Without enough usable markets, the year no longer represents an
      # international basket.
      if retained_weight < 0.5:
        continue
      nominal_international /= retained_weight
      real_international_constant_real_fx /= retained_weight

      inflation_previous = by_country[domestic].get(year - 1, {}).get("cpi")
      inflation_current = entry["cpi"]
      if not inflation_previous:
        continue
      inflation = inflation_current / inflation_previous - 1.0
      if inflation <= -1.0:
        continue

      real_international = (1.0 + nominal_international) / (1.0 + inflation) - 1.0

      # World index seen by the same resident. Unlike the former common series in
      # real dollars, each market is first converted into the currency of the country
      # of residence, then deflated by its inflation. Every sleeve of a country-year
      # row thus shares the same numeraire. The domestic market is included in this
      # aggregate.
      world_candidates = [
        c for c in candidates if (c, weight_year) in weights
      ]
      world_raw = [weights[(c, weight_year)] for c in world_candidates]
      world_total = sum(world_raw)
      if world_total <= 0.0:
        continue
      world_shares = [value / world_total for value in world_raw]
      nominal_world = 0.0
      retained_world_weight = 0.0
      retained_world_markets = 0
      previous_domestic = by_country[domestic].get(year - 1, {})
      if not previous_domestic:
        continue
      for share, country in zip(world_shares, world_candidates):
        if ((country, year) in UNINVESTABLE_FOREIGN_MARKET_YEARS
            or (country, year) in excluded_market_years):
          continue
        market = by_country[country][year]
        previous_market = by_country[country].get(year - 1, {})
        if not previous_market or not market["xrusd"]:
          continue
        fx_change = ((domestic_fx / market["xrusd"])
                    / (previous_domestic["xrusd"]
                       / previous_market["xrusd"])) - 1.0
        converted = (1.0 + market["eq_tr"]) * (1.0 + fx_change) - 1.0
        if (not math.isfinite(converted)
            or (MAX_CONVERTED_RETURN is not None
                and abs(converted) > MAX_CONVERTED_RETURN)):
          continue
        nominal_world += share * converted
        retained_world_weight += share
        retained_world_markets += 1
      if retained_world_weight < 0.5:
        continue
      nominal_world /= retained_world_weight
      real_world = (1.0 + nominal_world) / (1.0 + inflation) - 1.0

      rows.append({
        "country": domestic, "year": year,
        "international_equity_real": real_international,
        "international_equity_real_constant_real_fx":
          real_international_constant_real_fx,
        "world_equity_real_resident": real_world,
        "resident_xrusd": domestic_fx,
        "markets": len(others),
        "world_markets": retained_world_markets,
        "weight_source": weight_source,
      })

  return rows


def main() -> None:
  here = os.path.dirname(os.path.abspath(__file__))
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--dta", default=os.path.join(
    here, "..", "data", "JSTdatasetR6.dta"))
  parser.add_argument("--equity", default=os.path.join(
    here, "..", "data", "equity-tr-recent.csv"))
  parser.add_argument("--gmd", default=os.path.join(
    here, "..", "data", "gmd-cpi-fx.csv"))
  parser.add_argument("--mcap", default=os.path.join(
    here, "..", "data", "bb-mcap-gdp.csv"))
  parser.add_argument("--out", default=os.path.join(
    here, "..", "data", "international-equity.csv"))
  parser.add_argument("--max-converted-return", type=float,
                      help="legacy diagnostic only: drop a foreign constituent when its absolute converted nominal return exceeds this value")
  parser.add_argument("--exclude-market", action="append", default=[],
                      help="remove a country from every international and world basket (repeatable)")
  parser.add_argument("--exclude-market-year", action="append", default=[],
                      metavar="COUNTRY:YEAR",
                      help="diagnostic only: remove a source country-year from every equity basket")
  args = parser.parse_args()

  by_country = read_jst(args.dta)
  extend_recent(by_country, args.equity, args.gmd)
  gdp_weights = read_gdp_weights(args.dta)
  extend_weights(gdp_weights, args.gmd)
  ratios = read_mcap_ratios(args.mcap)
  cap_weights = capitalization_weights(gdp_weights, ratios)
  global MAX_CONVERTED_RETURN
  MAX_CONVERTED_RETURN = args.max_converted_return
  unknown = sorted(set(args.exclude_market) - set(by_country))
  if unknown:
    raise ValueError(f"unknown market(s): {', '.join(unknown)}")
  excluded_market_years = set()
  for value in args.exclude_market_year:
    try:
      country, year = value.rsplit(":", 1)
      excluded_market_years.add((country, int(year)))
    except ValueError as error:
      raise ValueError("--exclude-market-year must be COUNTRY:YEAR") from error
  rows = build(by_country, gdp_weights, cap_weights,
               frozenset(args.exclude_market), frozenset(excluded_market_years))

  print(f"{len(rows)} observations, {len({r['country'] for r in rows})} countries")
  print(f"mean markets per observation: "
       f"{sum(r['markets'] for r in rows) / len(rows):.1f}")
  sources: dict[str, int] = {}
  for row in rows:
    source = str(row["weight_source"])
    sources[source] = sources.get(source, 0) + 1
  print("weighting: " + ", ".join(
    f"{source}={count}" for source, count in sorted(sources.items())))

  with open(args.out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=[
      "country", "year", "international_equity_real",
      "international_equity_real_constant_real_fx",
      "world_equity_real_resident", "resident_xrusd", "markets",
      "world_markets", "weight_source"])
    writer.writeheader()
    writer.writerows(rows)
  print(f"Written to {os.path.normpath(args.out)}")


if __name__ == "__main__":
  main()
