"""Build the canonical monthly snapshot used by the MF simulations.

This audit script never goes online. The simulations do not need to run it:
they read the frozen CSV files directly (``data/mf-inputs/`` in this
repository).

Principles:
- nominal monthly returns, no inflation, no fees;
- no interpolation;
- no return computed across a change of source, unless stated;
- national equity indexes in price terms, Testfol total-return benchmarks kept
  separate;
- bonds converted into carry/price returns, never treated as mere yield
  changes;
- commodities and metals based on spot prices: these are not futures rolls.
"""

from __future__ import annotations

import csv
import hashlib
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
TREND_DIR = HERE.parent
DATA_DIR = HERE / "data"
MONTHLY_DERIVED = TREND_DIR / "raw" / "monthly" / "derived"
JST_REAL_RETURNS = TREND_DIR.parents[1] / "data" / "jst-real-returns-2025.csv"

START_MONTH = "1921-01"
END_MONTH = "2025-12"

COUNTRIES = (
    ("AUS", "Australia"), ("BEL", "Belgium"), ("CAN", "Canada"),
    ("CHE", "Switzerland"), ("DEU", "Germany"), ("DNK", "Denmark"),
    ("ESP", "Spain"), ("FIN", "Finland"), ("FRA", "France"),
    ("GBR", "United Kingdom"), ("IRL", "Ireland"), ("ITA", "Italy"),
    ("JPN", "Japan"), ("NLD", "Netherlands"), ("NOR", "Norway"),
    ("PRT", "Portugal"), ("SWE", "Sweden"), ("USA", "United States"),
)

OECD_CODE = {
    "AUS": "AU", "BEL": "BE", "CAN": "CA", "CHE": "CH", "DEU": "DE",
    "DNK": "DK", "ESP": "ES", "FIN": "FI", "FRA": "FR", "GBR": "GB",
    "IRL": "IE", "ITA": "IT", "JPN": "JP", "NLD": "NL", "NOR": "NO",
    "PRT": "PT", "SWE": "SE", "USA": "US",
}


@dataclass(frozen=True)
class AssetInfo:
  asset_id: str
  asset_class: str
  market: str
  return_kind: str
  default_universe: bool
  currency_basis: str
  important_limit: str


@dataclass(frozen=True)
class Segment:
  asset_id: str
  segment_id: str
  provider: str
  source_series: str
  transformation: str
  start: str
  end: str
  notes: str = ""
  coupon: float | None = None


def read_wide(path: Path) -> dict[str, dict[str, float]]:
  with path.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    columns = [name for name in (reader.fieldnames or []) if name != "month"]
    result: dict[str, dict[str, float]] = {name: {} for name in columns}
    for row in reader:
      month = row["month"]
      for name in columns:
        if row.get(name):
          result[name][month] = float(row[name])
  return result


def month_number(month: str) -> int:
  year, number = map(int, month.split("-"))
  return year * 12 + number - 1


def month_range(first: str = START_MONTH, last: str = END_MONTH) -> list[str]:
  current = month_number(first)
  end = month_number(last)
  return [f"{value // 12:04d}-{value % 12 + 1:02d}"
          for value in range(current, end + 1)]


def clip(values: dict[str, float], start: str, end: str) -> dict[str, float]:
  return {month: value for month, value in values.items()
          if start <= month <= end}


def price_returns(values: dict[str, float]) -> dict[str, float]:
  ordered = sorted(values)
  result: dict[str, float] = {}
  for previous, current in zip(ordered, ordered[1:]):
    if month_number(current) != month_number(previous) + 1:
      continue
    result[current] = values[current] / values[previous] - 1.0
  return result


def fixed_coupon_returns(values: dict[str, float], coupon: float) -> dict[str, float]:
  """Price per 100 of face value, annual coupon smoothed over twelve months."""
  ordered = sorted(values)
  result: dict[str, float] = {}
  for previous, current in zip(ordered, ordered[1:]):
    if month_number(current) != month_number(previous) + 1:
      continue
    result[current] = (
        values[current] - values[previous] + 100.0 * coupon / 12.0
    ) / values[previous]
  return result


def par_bond_monthly_return(yield_previous: float, yield_current: float) -> float:
  """Exact return of a ten-year proxy bond with semi-annual coupons.

  Yields are in percent. The coupon of the bond bought at t-1 equals the yield
  at t-1, which prices it at par. One month later, the twenty cash flows are
  discounted at the new yield at maturities of 5, 11, ..., 119 months. The
  formula stays defined with the negative yields observed in Europe.
  """
  coupon = yield_previous / 100.0
  discount_yield = yield_current / 100.0
  base = 1.0 + discount_yield / 2.0
  if base <= 0:
    raise ValueError(f"yield incompatible with discounting: {yield_current}")
  exponents = [(5 + 6 * index) / 6 for index in range(20)]
  price = sum((coupon / 2.0) * base ** (-exponent)
              for exponent in exponents[:-1])
  price += (1.0 + coupon / 2.0) * base ** (-exponents[-1])
  return price - 1.0


def par_bond_returns(values: dict[str, float]) -> dict[str, float]:
  ordered = sorted(values)
  result: dict[str, float] = {}
  for previous, current in zip(ordered, ordered[1:]):
    if month_number(current) != month_number(previous) + 1:
      continue
    result[current] = par_bond_monthly_return(values[previous], values[current])
  return result


def consol_returns(values: dict[str, float]) -> dict[str, float]:
  """Total-return proxy of a perpetuity from its current yield."""
  ordered = sorted(values)
  result: dict[str, float] = {}
  for previous, current in zip(ordered, ordered[1:]):
    if month_number(current) != month_number(previous) + 1:
      continue
    old_yield = values[previous] / 100.0
    new_yield = values[current] / 100.0
    if old_yield <= 0 or new_yield <= 0:
      raise ValueError("a Consol requires strictly positive yields")
    result[current] = old_yield / new_yield - 1.0 + old_yield / 12.0
  return result


def lagged_monthly_cash_from_rate(values: dict[str, float]) -> dict[str, float]:
  """Turn an annualised rate into a monthly return known the month before."""
  ordered = sorted(values)
  result: dict[str, float] = {}
  for previous, current in zip(ordered, ordered[1:]):
    if month_number(current) != month_number(previous) + 1:
      continue
    annualized = values[previous] / 100.0
    if annualized <= -1.0:
      raise ValueError(f"incompatible short rate: {previous}={annualized}")
    result[current] = (1.0 + annualized) ** (1.0 / 12.0) - 1.0
  return result


def jst_annual_cash_fallback(path: Path) -> dict[str, dict[str, float]]:
  """Monthly fallback, without look-ahead, from the annual JST/GMD short rate.

  The annual nominal rate is rebuilt from the real return and inflation. Its
  value for year y is applied monthly to y+1: information therefore never
  crosses a future annual release. This fallback is less precise than a monthly
  fixing and is always replaced by OECD/FRED when available.
  """
  names = {
      "Australia": "AUS", "Belgium": "BEL", "Canada": "CAN",
      "Switzerland": "CHE", "Germany": "DEU", "Denmark": "DNK",
      "Spain": "ESP", "Finland": "FIN", "France": "FRA",
      "United Kingdom": "GBR", "UK": "GBR", "Ireland": "IRL", "Italy": "ITA",
      "Japan": "JPN", "Netherlands": "NLD", "Norway": "NOR",
      "Portugal": "PRT", "Sweden": "SWE", "United States": "USA", "USA": "USA",
  }
  annual: dict[str, dict[int, float]] = defaultdict(dict)
  with path.open(newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      iso = names.get(row["country"])
      if not iso:
        continue
      real = float(row["short_real"])
      inflation = float(row["inflation"])
      nominal = (1.0 + real) * (1.0 + inflation) - 1.0
      if nominal <= -1.0:
        raise ValueError(f"JST cash incompatible {iso} {row['year']}")
      annual[iso][int(row["year"])] = nominal
  result: dict[str, dict[str, float]] = defaultdict(dict)
  for iso, values in annual.items():
    for year, annualized in values.items():
      monthly = (1.0 + annualized) ** (1.0 / 12.0) - 1.0
      for number in range(1, 13):
        result[iso][f"{year + 1:04d}-{number:02d}"] = monthly
  return dict(result)


def combine_cash_returns(
    oecd_rates: dict[str, dict[str, float]],
    euro_rates: dict[str, float],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, str]]]:
  fallback = jst_annual_cash_fallback(JST_REAL_RETURNS)
  values = {iso: dict(series) for iso, series in fallback.items()}
  sources = {
      iso: {month: "JST/GMD annual prior-year fallback" for month in series}
      for iso, series in fallback.items()
  }
  for iso, rates in oecd_rates.items():
    for month, cash_return in lagged_monthly_cash_from_rate(rates).items():
      values.setdefault(iso, {})[month] = cash_return
      sources.setdefault(iso, {})[month] = "OECD 3m interbank rate, lagged"
  values["EUR"] = lagged_monthly_cash_from_rate(euro_rates)
  sources["EUR"] = {
      month: "OECD euro-area 3m interbank rate, lagged"
      for month in values["EUR"]
  }
  return values, sources


def transform(values: dict[str, float], segment: Segment) -> dict[str, float]:
  selected = clip(values, segment.start, segment.end)
  if segment.transformation == "price_return":
    return price_returns(selected)
  if segment.transformation == "fixed_coupon_total_return":
    assert segment.coupon is not None
    return fixed_coupon_returns(selected, segment.coupon)
  if segment.transformation == "par_10y_total_return":
    return par_bond_returns(selected)
  if segment.transformation == "consol_total_return":
    return consol_returns(selected)
  if segment.transformation == "already_monthly_return":
    return selected
  raise ValueError(f"unknown transformation: {segment.transformation}")


def add_segment(
    returns_by_asset: dict[str, dict[str, float]],
    source_by_asset: dict[str, dict[str, str]],
    segment_rows: list[dict[str, str | int]],
    segment: Segment,
    source_values: dict[str, float],
) -> None:
  selected = clip(source_values, segment.start, segment.end)
  generated = transform(source_values, segment)
  destination = returns_by_asset.setdefault(segment.asset_id, {})
  sources = source_by_asset.setdefault(segment.asset_id, {})
  overlap = set(destination) & set(generated)
  if overlap:
    raise ValueError(f"{segment.asset_id}: overlapping segments {sorted(overlap)[:3]}")
  destination.update(generated)
  sources.update({month: segment.segment_id for month in generated})
  segment_rows.append({
      "asset_id": segment.asset_id,
      "segment_id": segment.segment_id,
      "provider": segment.provider,
      "source_series": segment.source_series,
      "transformation": segment.transformation,
      "start_month": min(selected) if selected else "",
      "end_month": max(selected) if selected else "",
      "source_observations": len(selected),
      "return_observations": len(generated),
      "reset_at_start": "yes",
      "notes": segment.notes,
  })


def write_wide(path: Path, assets: list[str], values: dict[str, dict[str, float]]) -> None:
  with path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["month", *assets])
    for month in month_range():
      writer.writerow([month, *[
          f"{values.get(asset, {}).get(month):.12g}"
          if month in values.get(asset, {}) else ""
          for asset in assets
      ]])


def write_dicts(path: Path, rows: list[dict], fields: list[str]) -> None:
  with path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def measuringworth_gold_monthly(path: Path) -> dict[str, float]:
  annual: dict[int, float] = {}
  with path.open(newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      if not row["year"].isdigit() or not row.get("us_price"):
        continue
      year = int(row["year"])
      if 1920 <= year <= 1959:
        annual[year] = float(row["us_price"])
  return {f"{year:04d}-{month:02d}": annual[year]
          for year in sorted(annual) for month in range(1, 13)}


def correlation(left: list[float], right: list[float]) -> float:
  mean_left = statistics.fmean(left)
  mean_right = statistics.fmean(right)
  covariance = sum((a - mean_left) * (b - mean_right)
                   for a, b in zip(left, right))
  variance_left = sum((a - mean_left) ** 2 for a in left)
  variance_right = sum((b - mean_right) ** 2 for b in right)
  return covariance / math.sqrt(variance_left * variance_right)


def main() -> None:
  DATA_DIR.mkdir(parents=True, exist_ok=True)

  oecd_equity = read_wide(MONTHLY_DERIVED / "oecd-equity-price-monthly.csv")
  oecd_yield = read_wide(MONTHLY_DERIVED / "oecd-government-yield-monthly.csv")
  oecd_short_rate = read_wide(MONTHLY_DERIVED / "oecd-short-rate-monthly.csv")
  euro_short_rate = read_wide(MONTHLY_DERIVED / "fx-short-rate-monthly.csv")
  nber_equity = read_wide(MONTHLY_DERIVED / "nber-equity-price-monthly.csv")
  nber_bond_price = read_wide(MONTHLY_DERIVED / "nber-bond-price-monthly.csv")
  nber_bond_yield = read_wide(MONTHLY_DERIVED / "nber-bond-yield-monthly.csv")
  uk_yield = read_wide(MONTHLY_DERIVED / "supplementary-government-yield-monthly.csv")
  fx_spot_eom = read_wide(MONTHLY_DERIVED / "fx-spot-eom-monthly.csv")
  testfol = read_wide(MONTHLY_DERIVED / "testfol-total-return-monthly.csv")
  old_commodities = read_wide(TREND_DIR / "commodities-monthly.csv")
  wb_commodities = read_wide(TREND_DIR / "commodities-worldbank.csv")
  cash_returns, cash_sources = combine_cash_returns(
      oecd_short_rate, euro_short_rate["EUR"],
  )

  returns: dict[str, dict[str, float]] = {}
  sources: dict[str, dict[str, str]] = {}
  infos: dict[str, AssetInfo] = {}
  segment_rows: list[dict[str, str | int]] = []

  # Equities: only price indexes in the default universe.
  for iso, name in COUNTRIES:
    asset = f"EQ_{iso}"
    infos[asset] = AssetInfo(
        asset, "equity", name, "price_return", True, "local",
        "Dividends excluded; price proxy, not total return.",
    )
    if iso not in {"DEU", "FRA", "GBR", "USA"}:
      add_segment(returns, sources, segment_rows, Segment(
          asset, f"{asset}_OECD", "OECD via FRED",
          f"SPASTT01{OECD_CODE[iso]}M661N", "price_return",
          START_MONTH, END_MONTH,
          "Monthly national price index."), oecd_equity[iso])

  equity_segments = (
      ("EQ_GBR", "EQ_GBR_NBER_B", "NBER Macrohistory", "m11012b", "1921-01", "1924-12", nber_equity["m11012b"]),
      ("EQ_GBR", "EQ_GBR_NBER_C", "NBER Macrohistory", "m11012c", "1925-01", "1934-12", nber_equity["m11012c"]),
      ("EQ_GBR", "EQ_GBR_OECD", "OECD via FRED", "SPASTT01GBM661N", "1957-12", END_MONTH, oecd_equity["GBR"]),
      ("EQ_DEU", "EQ_DEU_NBER", "NBER Macrohistory", "m11023b", "1924-01", "1935-12", nber_equity["m11023b"]),
      ("EQ_DEU", "EQ_DEU_OECD", "OECD via FRED", "SPASTT01DEM661N", "1960-01", END_MONTH, oecd_equity["DEU"]),
      ("EQ_FRA", "EQ_FRA_NBER", "NBER Macrohistory", "m11024", START_MONTH, "1939-12", nber_equity["m11024"]),
      ("EQ_FRA", "EQ_FRA_OECD", "OECD via FRED", "SPASTT01FRM661N", "1955-01", END_MONTH, oecd_equity["FRA"]),
      ("EQ_USA", "EQ_USA_NBER_A", "NBER Macrohistory", "m11025a", START_MONTH, "1944-12", nber_equity["m11025a"]),
      ("EQ_USA", "EQ_USA_NBER_B", "NBER Macrohistory", "m11025b", "1945-01", "1956-12", nber_equity["m11025b"]),
      ("EQ_USA", "EQ_USA_OECD", "OECD via FRED", "SPASTT01USM661N", "1957-01", END_MONTH, oecd_equity["USA"]),
  )
  for asset, segment_id, provider, source_id, start, end, values in equity_segments:
    add_segment(returns, sources, segment_rows, Segment(
        asset, segment_id, provider, source_id, "price_return", start, end,
        "Returns computed only within this segment."), values)

  # Bonds: ten-year total-return proxy from yields. Three markets have an
  # additional historical segment before the OECD yields.
  for iso, name in COUNTRIES:
    asset = f"BOND_{iso}_10Y"
    infos[asset] = AssetInfo(
        asset, "bond", name, "synthetic_excess_return", True, "local",
        "Bond proxy in excess of cash; neither an observed index nor a rolled future.",
    )
    start = START_MONTH
    if iso == "USA":
      start = "1953-04"
    elif iso == "GBR":
      start = "1960-01"
    elif iso == "FRA":
      start = "1960-01"
    add_segment(returns, sources, segment_rows, Segment(
        asset, f"{asset}_OECD", "OECD via FRED",
        f"IRLTLT01{OECD_CODE[iso]}M156N",
        "par_10y_total_return", start, END_MONTH,
        "Coupon fixed at the preceding month's yield; initial maturity ten years."),
        oecd_yield[iso])

  # United States: two NBER vintages then OECD, with a reset at each seam.
  add_segment(returns, sources, segment_rows, Segment(
      "BOND_USA_10Y", "BOND_USA_NBER_A", "NBER Macrohistory", "m13033a",
      "par_10y_total_return", START_MONTH, "1941-09",
      "Long yields partly tax-exempt; varying maturity and callability."),
      nber_bond_yield["m13033a"])
  add_segment(returns, sources, segment_rows, Segment(
      "BOND_USA_10Y", "BOND_USA_NBER_B", "NBER Macrohistory", "m13033b",
      "par_10y_total_return", "1941-10", "1953-03",
      "NBER long yields converted using a ten-year proxy maturity."),
      nber_bond_yield["m13033b"])

  # United Kingdom: Consol through 1934, then a ten-year yield series.
  add_segment(returns, sources, segment_rows, Segment(
      "BOND_GBR_10Y", "BOND_GBR_CONSOL", "Bank of England via FRED", "YCLTUK",
      "consol_total_return", START_MONTH, "1934-12",
      "Long perpetuity; explicit duration change before 1935."),
      uk_yield["YCLTUK"])
  add_segment(returns, sources, segment_rows, Segment(
      "BOND_GBR_10Y", "BOND_GBR_BOE_10Y", "Bank of England via FRED", "MTGB10UKM",
      "par_10y_total_return", "1935-01", "1959-12",
      "BoE ten-year series; reset between Consol and ten-year series."),
      uk_yield["MTGB10UKM"])

  # France: observed return of the 3% rente, then OECD ten-year proxy.
  add_segment(returns, sources, segment_rows, Segment(
      "BOND_FRA_10Y", "BOND_FRA_RENTE_3", "NBER Macrohistory", "m11021",
      "fixed_coupon_total_return", START_MONTH, "1940-04",
      "Perpetual 3% rente; annual coupon spread evenly by month.", 0.03),
      nber_bond_price["m11021"])

  # A bond future earns the bond's excess return over cash in its currency. The
  # monthly OECD short rate is preferred; before it is available, the previous
  # year's annual JST/GMD rate is applied uniformly, without using future
  # information.
  for iso, _name in COUNTRIES:
    asset = f"BOND_{iso}_10Y"
    for month in list(returns[asset]):
      cash_return = cash_returns.get(iso, {}).get(month)
      if cash_return is None:
        del returns[asset][month]
        del sources[asset][month]
      else:
        returns[asset][month] -= cash_return
  for row in segment_rows:
    if str(row["asset_id"]).startswith("BOND_"):
      row["transformation"] = "par_10y_excess_return"
      row["notes"] = (
          f"{row['notes']} Three-month cash return subtracted (monthly OECD or annual JST/GMD fallback)."
      )

  # Spot commodities. The four long series change source in 1960; the first
  # return of each new segment is left empty.
  commodity_names = {
      "aluminum": "Aluminum", "barley": "Barley", "coal": "Coal",
      "cocoa": "Cocoa", "coffee": "Coffee", "copper": "Copper",
      "corn": "Corn", "crude_oil": "Crude oil", "lead": "Lead",
      "natural_gas": "Natural gas", "nickel": "Nickel",
      "palm_oil": "Palm oil", "pig_iron": "Pig iron",
      "soybeans": "Soybeans", "sugar": "Sugar", "tea": "Tea",
      "tin": "Tin", "wheat": "Wheat", "zinc": "Zinc",
  }
  old_to_wb = {
      "copper": ("copper", "copper_wb"),
      "corn": ("corn", "maize"),
      "sugar": ("sugar", "sugar_wb"),
      "wheat": ("wheat", "wheat_wb"),
  }
  wb_only = {
      "aluminum", "barley", "coal", "cocoa", "coffee", "crude_oil",
      "lead", "natural_gas", "nickel", "palm_oil", "soybeans", "tea",
      "tin", "zinc",
  }
  for key, label in commodity_names.items():
    asset = f"CMD_{key.upper()}"
    infos[asset] = AssetInfo(
        asset, "commodity", label, "spot_price_return", True, "USD/source unit",
        "Spot/cash price; futures carry, collateral, and roll returns absent.",
    )
    if key in old_to_wb:
      old_name, wb_name = old_to_wb[key]
      add_segment(returns, sources, segment_rows, Segment(
          asset, f"{asset}_NBER", "NBER/BLS via FRED", old_name,
          "price_return", START_MONTH, "1959-12",
          "Long historical series; no return across the 1960 source seam."),
          old_commodities[old_name])
      add_segment(returns, sources, segment_rows, Segment(
          asset, f"{asset}_WB", "World Bank Pink Sheet", wb_name,
          "price_return", "1960-01", END_MONTH,
          "Monthly market price; first month of segment has no return."),
          wb_commodities[wb_name])
    elif key == "pig_iron":
      add_segment(returns, sources, segment_rows, Segment(
          asset, f"{asset}_NBER", "NBER via FRED", "pig_iron",
          "price_return", START_MONTH, "1958-04",
          "Historical series ended; no artificial extension."),
          old_commodities["pig_iron"])
    elif key in wb_only:
      add_segment(returns, sources, segment_rows, Segment(
          asset, f"{asset}_WB", "World Bank Pink Sheet", key,
          "price_return", "1960-01", END_MONTH,
          "Monthly spot/cash price."), wb_commodities[key])

  # Precious metals: the official gold price, constant monthly before 1960, then
  # the monthly World Bank price. No custody fee is applied to the data.
  gold_asset = "METAL_GOLD"
  silver_asset = "METAL_SILVER"
  infos[gold_asset] = AssetInfo(
      gold_asset, "precious_metal", "Gold", "spot_price_return", True, "USD",
      "Official US price before 1960, then spot; no custody fee.")
  infos[silver_asset] = AssetInfo(
      silver_asset, "precious_metal", "Silver", "spot_price_return", True, "USD",
      "World Bank spot price from 1960; no futures roll return.")
  add_segment(returns, sources, segment_rows, Segment(
      gold_asset, "METAL_GOLD_OFFICIAL", "MeasuringWorth", "us_price",
      "price_return", START_MONTH, "1959-12",
      "Official annual price repeated monthly; the 1934 rise is placed in January."),
      measuringworth_gold_monthly(
          TREND_DIR.parent / "gold" / "measuringworth_gold.csv"))
  add_segment(returns, sources, segment_rows, Segment(
      gold_asset, "METAL_GOLD_WB", "World Bank Pink Sheet", "gold",
      "price_return", "1960-01", END_MONTH,
      "Monthly USD/ounce price; fully includes the 1968 liberalization."),
      wb_commodities["gold"])
  add_segment(returns, sources, segment_rows, Segment(
      silver_asset, "METAL_SILVER_WB", "World Bank Pink Sheet", "silver",
      "price_return", "1960-01", END_MONTH,
      "Monthly USD/ounce price."), wb_commodities["silver"])

  # Currencies: last H.10 fixing actually available in the month. These levels
  # are treated separately from monthly average prices: their signal can use t-1
  # without creating the overlap that affects the other sources.
  fx_names = {
      "FX_AUD": "Australian dollar", "FX_CAD": "Canadian dollar",
      "FX_EUR": "Euro", "FX_JPY": "Japanese yen",
      "FX_CHF": "Swiss franc", "FX_GBP": "Pound sterling",
  }
  fx_source_ids = {
      "FX_AUD": "DEXUSAL", "FX_CAD": "DEXCAUS", "FX_EUR": "DEXUSEU",
      "FX_JPY": "DEXJPUS", "FX_CHF": "DEXSZUS", "FX_GBP": "DEXUSUK",
  }
  for asset, label in fx_names.items():
    infos[asset] = AssetInfo(
        asset, "currency", label, "forward_excess_return", True,
        "USD per foreign-currency unit",
        "Synthetic forward: month-end H.10 spot plus three-month rate differential.",
    )
    add_segment(returns, sources, segment_rows, Segment(
        asset, f"{asset}_FRED_H10", "Board of Governors H.10 via FRED", fx_source_ids[asset],
        "price_return", START_MONTH, END_MONTH,
        "Last available daily fixing each month, USD per unit."),
        fx_spot_eom[asset])

  fx_cash_country = {
      "FX_AUD": "AUS", "FX_CAD": "CAN", "FX_EUR": "EUR",
      "FX_JPY": "JPN", "FX_CHF": "CHE", "FX_GBP": "GBR",
  }
  for asset, foreign in fx_cash_country.items():
    for month in list(returns[asset]):
      foreign_cash = cash_returns.get(foreign, {}).get(month)
      dollar_cash = cash_returns.get("USA", {}).get(month)
      if foreign_cash is None or dollar_cash is None:
        del returns[asset][month]
        del sources[asset][month]
      else:
        # Retour exact d'un forward long en devise etrangere, finance en USD.
        returns[asset][month] = (
            (1.0 + returns[asset][month]) * (1.0 + foreign_cash)
            / (1.0 + dollar_cash) - 1.0
        )
  for row in segment_rows:
    if str(row["asset_id"]).startswith("FX_"):
      row["transformation"] = "synthetic_forward_excess_return"
      row["notes"] = (
          f"{row['notes']} Three-month rate differential added, known in the previous month."
      )

  # Testfol benchmarks, excluded from the default universe to avoid double
  # counting with the national markets and across US maturities.
  benchmark_map = {
      "SPYSIM": ("equity_benchmark", "S&P 500 TR"),
      "VTISIM": ("equity_benchmark", "US total-market TR"),
      "VXUSSIM": ("equity_benchmark", "Ex-US equities TR"),
      "URTHSIM": ("equity_benchmark", "MSCI World TR"),
      "VTSIM": ("equity_benchmark", "Monde total TR"),
      "SHYSIM": ("bond_benchmark", "Treasuries US 1-3 ans"),
      "IEISIM": ("bond_benchmark", "Treasuries US 3-7 ans"),
      "IEFSIM": ("bond_benchmark", "Treasuries US 7-10 ans"),
      "TLTSIM": ("bond_benchmark", "Treasuries US longs"),
  }
  for ticker, (asset_class, label) in benchmark_map.items():
    asset = f"BM_{ticker}"
    infos[asset] = AssetInfo(
        asset, asset_class, label, "reconstructed_total_return", False, "USD",
        "Reconstructed, overlapping benchmark; excluded from the default MF universe.")
    add_segment(returns, sources, segment_rows, Segment(
        asset, f"{asset}_TESTFOL", "Testfol", ticker,
        "already_monthly_return", START_MONTH, END_MONTH,
        "SIM total return; checks and sensitivities only."), testfol[ticker])

  # Validate numbers before writing files.
  for asset, values in returns.items():
    for month, value in values.items():
      if not START_MONTH <= month <= END_MONTH:
        raise ValueError(f"{asset}: month outside snapshot {month}")
      if not math.isfinite(value) or value <= -1.0:
        raise ValueError(f"{asset}: invalid return {month}={value}")
      if infos[asset].asset_class == "bond" and abs(value) > 1.0:
        raise ValueError(f"{asset}: implausible bond return {month}={value}")

  # The FX spot return is kept separate from the forward return: it converts the
  # local P&L of equities and bonds into USD, without reusing the P&L of the
  # currency sector as an exchange rate.
  fx_spot_returns = {
      asset: price_returns(values)
      for asset, values in fx_spot_eom.items()
  }
  write_wide(
      DATA_DIR / "fx-spot-returns-monthly.csv",
      sorted(fx_spot_returns), fx_spot_returns,
  )

  # Fichiers larges, directement consommables.
  classes = {
      "equity": "equity-returns-monthly.csv",
      "bond": "bond-returns-monthly.csv",
      "commodity": "commodity-returns-monthly.csv",
      "precious_metal": "precious-metals-returns-monthly.csv",
      "currency": "currency-returns-monthly.csv",
      "equity_benchmark": "equity-benchmarks-monthly.csv",
      "bond_benchmark": "bond-benchmarks-monthly.csv",
  }
  for asset_class, filename in classes.items():
    assets = sorted(asset for asset, info in infos.items()
                    if info.asset_class == asset_class)
    write_wide(DATA_DIR / filename, assets, returns)

  # The collateral is an explicit, versioned series rather than an assumption
  # hidden in the managed-futures engine. Its rates are already lagged by one
  # month in ``combine_cash_returns``.
  write_wide(DATA_DIR / "cash-returns-monthly.csv", sorted(cash_returns), cash_returns)
  cash_source_rows = [
      {
          "month": month,
          "currency": currency,
          "cash_return": f"{cash_returns[currency][month]:.12g}",
          "source": cash_sources[currency][month],
      }
      for currency in sorted(cash_returns)
      for month in sorted(cash_returns[currency])
  ]
  write_dicts(
      DATA_DIR / "cash-return-sources-monthly.csv", cash_source_rows,
      ["month", "currency", "cash_return", "source"],
  )

  # Universal long format: a single file is enough for a future implementation.
  long_rows: list[dict[str, str]] = []
  for month in month_range():
    for asset in sorted(returns):
      if month not in returns[asset]:
        continue
      info = infos[asset]
      long_rows.append({
          "month": month,
          "asset_id": asset,
          "asset_class": info.asset_class,
          "market": info.market,
          "return": f"{returns[asset][month]:.12g}",
          "return_kind": info.return_kind,
          "source_segment": sources[asset][month],
          "default_universe": "yes" if info.default_universe else "no",
      })
  write_dicts(
      DATA_DIR / "all-assets-monthly.csv", long_rows,
      ["month", "asset_id", "asset_class", "market", "return",
       "return_kind", "source_segment", "default_universe"],
  )

  metadata_rows: list[dict[str, str | int]] = []
  for asset, info in sorted(infos.items()):
    months = sorted(returns[asset])
    metadata_rows.append({
        "asset_id": asset,
        "asset_class": info.asset_class,
        "market": info.market,
        "return_kind": info.return_kind,
        "default_universe": "yes" if info.default_universe else "no",
        "currency_basis": info.currency_basis,
        "first_return_month": months[0],
        "last_return_month": months[-1],
        "observations": len(months),
        "important_limit": info.important_limit,
    })
  write_dicts(
      DATA_DIR / "series-metadata.csv", metadata_rows,
      ["asset_id", "asset_class", "market", "return_kind",
       "default_universe", "currency_basis", "first_return_month",
       "last_return_month", "observations", "important_limit"],
  )
  write_dicts(
      DATA_DIR / "source-segments.csv", segment_rows,
      ["asset_id", "segment_id", "provider", "source_series",
       "transformation", "start_month", "end_month", "source_observations",
       "return_observations", "reset_at_start", "notes"],
  )

  # Extreme values kept but made visible for human review.
  thresholds = {"equity": 0.40, "bond": 0.15,
                "commodity": 0.50, "precious_metal": 0.50, "currency": 0.25}
  outlier_rows: list[dict[str, str]] = []
  for asset, values in sorted(returns.items()):
    info = infos[asset]
    threshold = thresholds.get(info.asset_class)
    if threshold is None or not info.default_universe:
      continue
    for month, value in sorted(values.items()):
      if abs(value) >= threshold:
        outlier_rows.append({
            "month": month,
            "asset_id": asset,
            "asset_class": info.asset_class,
            "return": f"{value:.12g}",
            "threshold": f"{threshold:.2f}",
            "source_segment": sources[asset][month],
            "action": "retained; requires robustness check",
        })
  write_dicts(
      DATA_DIR / "flagged-outliers.csv", outlier_rows,
      ["month", "asset_id", "asset_class", "return", "threshold",
       "source_segment", "action"],
  )

  # Diagnostics before freezing the version.
  common = sorted(set(returns["BOND_USA_10Y"]) & set(testfol["IEFSIM"]))
  left = [returns["BOND_USA_10Y"][month] for month in common]
  right = [testfol["IEFSIM"][month] for month in common]
  bond_corr = correlation(left, right)
  bond_vol = statistics.stdev(left) * math.sqrt(12)
  ief_vol = statistics.stdev(right) * math.sqrt(12)

  gold_1968 = math.prod(
      1 + returns[gold_asset][month]
      for month in sorted(returns[gold_asset]) if month.startswith("1968-")
  ) - 1

  coverage_lines = []
  for month in ("1921-12", "1960-12", "1990-12", "2025-12"):
    counts = {
        asset_class: sum(
            1 for asset, info in infos.items()
            if info.default_universe and info.asset_class == asset_class
            and month in returns[asset]
        )
        for asset_class in ("equity", "bond", "commodity", "precious_metal", "currency")
    }
    coverage_lines.append(
        f"Coverage {month}: equities={counts['equity']}, bonds={counts['bond']}, "
        f"commodities={counts['commodity']}, metals={counts['precious_metal']}, "
        f"currencies={counts['currency']}."
    )

  report = [
      "CANONICAL MF SNAPSHOT",
      f"Fixed period: {START_MONTH} -> {END_MONTH} ({len(month_range())} months)",
      f"Series: {len(infos)}, of which {sum(i.default_universe for i in infos.values())} in the default universe",
      f"Non-missing returns: {len(long_rows):,}",
      "",
      "Checks passed: unique keys, finite returns > -100%,",
      "no return computed across a source seam, no interpolation.",
      f"USA 10-year proxy vs IEFSIM ({common[0]}->{common[-1]}): corr={bond_corr:.3f}, vol={bond_vol:.2%} vs {ief_vol:.2%}.",
      f"Gold spot return 1968 kept: {gold_1968:+.2%}.",
      *coverage_lines,
      f"Extreme moves flagged, not removed: {len(outlier_rows)} (flagged-outliers.csv).",
      "",
      "Warning: national equities = price return; commodities/metals = spot return;",
      "currencies = synthetic forward (EOM spot + rate differential);",
      "bonds = ten-year proxy in excess of cash. None of these files contains",
      "commodity futures rolls, fees, spreads or a trend signal.",
  ]
  (DATA_DIR / "VALIDATION.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

  manifest_rows = []
  for path in sorted(DATA_DIR.iterdir()):
    if path.name == "snapshot-manifest.csv" or not path.is_file():
      continue
    data = path.read_bytes()
    manifest_rows.append({
        "file": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "snapshot_start": START_MONTH,
        "snapshot_end": END_MONTH,
    })
  write_dicts(
      DATA_DIR / "snapshot-manifest.csv", manifest_rows,
      ["file", "bytes", "sha256", "snapshot_start", "snapshot_end"],
  )

  print("\n".join(report))
  print()
  for row in manifest_rows:
    print(f"{row['file']:<38} {row['bytes']:>9,} octets")


if __name__ == "__main__":
  main()
