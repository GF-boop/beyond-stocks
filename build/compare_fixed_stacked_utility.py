"""Fixed stacked portfolios, with no retrospective calibration.

Exposures are set before the panel is read and depend on no estimated
volatility. Every extension keeps the same equity sleeve as the ACO benchmark:
33% domestic and 67% international stocks of the resident. The other building
blocks are global sovereign bonds, gold and managed futures. Gross exposure is
capped at 200% of capital. Bonds and managed futures are hedged into the
resident's currency with carry; an explicit hedging friction is deducted.
Financing above 100% costs the resident's short rate plus the spread given as
argument.

The four main proposals are:

* 2/3 of a 90/60 and 1/3 trend: 60/40/33.33, gross 133.33%;
* 2/3 of a 90/60 and 1/3 gold: 60/40/33.33, gross 133.33%;
* 60% of a 90/60, 20% trend and 20% gold: 54/36/20/20, gross 130%;
* 90/60/25/25: gross 200%, the leverage cap.

Two additional ladders apply simple weights at gross exposures of 100%, 125%,
150%, 175% and 200%: a proportional family at 60/40/25/25 and an equal-weight
stocks/bonds/gold/trend family. They are fixed before evaluation and target no
realised volatility.

The script reports historical moments as results only. They are never used to
set weights, leverage or a risk multiplier.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections.abc import Callable

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_gold_trend_equal_vol import (  # noqa: E402
  DEFAULT_TREND_COST,
  DEFAULT_TREND_FEE,
)
from compare_lifecycle_utility import (  # noqa: E402
  BASE_SAVINGS_RATE,
  GAMMA,
  WITHDRAWAL_RATE,
  build_scenario,
  draw_death_age,
  equivalent_savings_rate,
  evaluate_batch,
  expected_utility,
)
from income_process import draw_household_income  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from data_quality import exclusion_reason  # noqa: E402
from investability import exclusion_reason as investability_reason  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  START_AGE,
  block_bootstrap,
  read_panel,
)
from war_periods import is_war_year  # noqa: E402


ReturnFunction = Callable[[dict[str, float]], float]
MAX_GROSS_EXPOSURE = 2.0
DEFAULT_SPREAD = 0.003
DEFAULT_FX_HEDGE_COST = 0.001
DESIGN_PATH = os.path.join(HERE, "..", "data", "fixed-stacked-design.json")
BENCHMARK_NAME = "ACO 33/67"
ACO_LEVERAGE_NAMES = tuple(f"ACO 33/67 {level}%" for level in (125, 150, 175, 200))
# These frozen strategy names are protocol identifiers used in archived outputs.
CORE_EXPOSURE_NAMES = {
  "60/40 ACO/couvert",
  "60/40 ACO + 33.33 MF",
  "60/40 ACO + 33.33 Or",
  "54/36/20/20 ACO",
  "90/60/25/25 ACO",
}


def load_fixed_exposures() -> dict[str, tuple[float, float, float, float]]:
  """Load the single frozen manifest, with no recalibration option."""
  with open(DESIGN_PATH, encoding="utf-8") as handle:
    design = json.load(handle)
  if design.get("calibrated_from_returns") is not False:
    raise ValueError("The manifest must forbid calibration on returns")
  if design.get("exposure_order") != [
      "aco_33_67_equity", "world_bond", "gold", "managed_futures"]:
    raise ValueError("Every extension must keep the ACO 33/67 equity sleeve")
  if not math.isclose(float(design["max_gross_exposure"]),
                      MAX_GROSS_EXPOSURE):
    raise ValueError("The manifest cap must stay fixed at 2x")
  exposures = {}
  for portfolio in design["portfolios"]:
    values = tuple(float(value) for value in portfolio["exposures"])
    if len(values) != 4:
      raise ValueError("Each portfolio must have four exposures")
    exposures[str(portfolio["name"])] = values
  return exposures


# The manifest order is the panel order and defines the frozen design.
FIXED_EXPOSURES = load_fixed_exposures()


def validate_design() -> None:
  for name, exposures in FIXED_EXPOSURES.items():
    if any(exposure < 0.0 for exposure in exposures):
      raise ValueError(f"Exposition negative interdite : {name}")
    gross = sum(exposures)
    if gross > MAX_GROSS_EXPOSURE + 1e-12:
      raise ValueError(
        f"{name} exceeds the cap of {MAX_GROSS_EXPOSURE:.0f}x : {gross:.3f}x")


def empirical_quantile(values: list[float], probability: float) -> float:
  """Linear quantile without external dependencies."""
  ordered = sorted(values)
  position = probability * (len(ordered) - 1)
  lower = int(math.floor(position))
  upper = int(math.ceil(position))
  if lower == upper:
    return ordered[lower]
  weight = position - lower
  return ordered[lower] + weight * (ordered[upper] - ordered[lower])


def return_functions(rows: list[dict[str, float]], spread: float,
                     trend_fee: float, trend_cost: float,
                     trend_haircut: float, fx_hedge_cost: float,
                     gold_reallocation_from_year: int | None = None,
                    include_unhedged_control: bool = False,
                    include_constant_real_fx: bool = True,
                    hedge_mode: str = "fixed_notional",
                    ) -> dict[str, ReturnFunction]:
  """Build the returns without estimating any weight or leverage."""
  if hedge_mode not in {"ideal", "fixed_notional"}:
    raise ValueError("hedge_mode must be ideal or fixed_notional")
  bond_key = "world_bond" if hedge_mode == "ideal" else "world_bond_fixed_notional"
  trend_key = "trend" if hedge_mode == "ideal" else "trend_fixed_notional"
  # Apply the fee and turnover cost to the selected gross return convention.
  selected_trend = [row[trend_key] for row in rows]
  net_trend = [
    (1.0 + value) * (1.0 - trend_fee) - 1.0 - trend_cost - trend_haircut
    for value in selected_trend
  ]
  trend_by_row = {id(row): value for row, value in zip(rows, net_trend)}
  functions: dict[str, ReturnFunction] = {
    "Actions domestiques": lambda row: row["domestic"],
    "ACO 33/67": lambda row: (
      0.33 * row["domestic"] + 0.67 * row["international"]),
    "Stocks/I": lambda row: 0.5 * (row["domestic"] + row["international"]),
    "Balanced domestique": lambda row: (
      0.6 * row["domestic"] + 0.4 * row["bond"]),
    "Balanced/I": lambda row: (
      0.3 * row["domestic"] + 0.3 * row["international"]
      + 0.4 * row["bond"]),
    # Fixed, non-optimised comparator: the equity leg is exactly ACO's 33/67;
    # bonds and financing remain those of the resident.
    "90/60 local fixe": lambda row: (
      0.9 * (0.33 * row["domestic"] + 0.67 * row["international"])
      + 0.6 * row["bond"] - 0.5 * row["bill"] - 0.5 * spread),
    # Identification test: same equity sleeve and weights as the local
    # comparator; only the hedged bonds become global.
    "90/60 oblig. mondiales": lambda row: (
      0.9 * (0.33 * row["domestic"] + 0.67 * row["international"])
      + 0.6 * row[bond_key] - 0.5 * row["world_bill"] - 0.5 * spread
      - 0.6 * fx_hedge_cost),
  }

  # The constant-real-exchange-rate counterfactual is defined only when each
  # row is already in its resident's numeraire. It has no meaning once the
  # same states are converted into a fixed dollar.
  if include_constant_real_fx:
    functions["ACO 33/67, change reel cst"] = lambda row: (
      0.33 * row["domestic"]
      + 0.67 * row["international_constant_real_fx"])

  for level, name in zip((1.25, 1.5, 1.75, 2.0), ACO_LEVERAGE_NAMES):
    functions[name] = lambda row, gross=level: (
        gross * (0.33 * row['domestic'] + 0.67 * row['international'])
        + (1.0 - gross) * row['bill'] - (gross - 1.0) * spread)

  if include_unhedged_control:
    # Secondary check: same test, at the ex post spot exchange rate. It
    # defines neither the main case nor the multi-asset portfolios.
    functions["90/60 oblig. non couvert"] = lambda row: (
      0.9 * (0.33 * row["domestic"] + 0.67 * row["international"])
      + 0.6 * row["world_bond_unhedged"]
      - 0.5 * row["world_bill_unhedged"] - 0.5 * spread)

  for name, exposures in FIXED_EXPOSURES.items():
    equity, bond, gold, trend = exposures
    gross = sum(exposures)
    # Bond and trend returns are hedged with carry. The negative cash weight
    # removes the resident's short rate on the stacked notional before the
    # spread is added; the hedging friction is charged on the hedged sleeves
    # only. Gold and stocks remain unhedged.
    cash_weight = 1.0 - gross
    borrowing = max(0.0, gross - 1.0)

    def calculate(row: dict[str, float], *, e=equity, b=bond, g=gold,
                  t=trend, cash=cash_weight, debt=borrowing,
                  cutoff=gold_reallocation_from_year) -> float:
      # Before 1968 the gold price is administered. In the unavailability
      # variant, its notional is spread equally over the non-gold sleeves
      # already in the recipe. Total leverage and financing are unchanged, and
      # no new asset class enters a portfolio that did not hold it.
      if g > 0.0 and cutoff is not None and row["year"] < cutoff:
        active_non_gold = sum(weight > 0.0 for weight in (e, b, t))
        if active_non_gold == 0:
          raise ValueError("A gold sleeve needs at least one active sleeve")
        reallocated = g / active_non_gold
        effective_equity = e + (reallocated if e > 0.0 else 0.0)
        effective_bond = b + (reallocated if b > 0.0 else 0.0)
        effective_gold = 0.0
        effective_trend = t + (reallocated if t > 0.0 else 0.0)
      else:
        effective_equity = e
        effective_bond = b
        effective_gold = g
        effective_trend = t
      aco_equity = 0.33 * row["domestic"] + 0.67 * row["international"]
      return (effective_equity * aco_equity
              + effective_bond * row[bond_key]
              + effective_gold * row["gold"]
              + effective_trend * trend_by_row[id(row)]
              + cash * row["world_bill"]
              - debt * spread
              - (b + t) * fx_hedge_cost)

    functions[name] = calculate
  return functions


def _fixed_numeraire_unhedged_return(
    return_source: float, inflation_source: float,
    source_xrusd_previous: float, source_xrusd_current: float,
    target_xrusd_previous: float, target_xrusd_current: float,
    inflation_target: float) -> float:
  """Convert a real return of the source country into a real return of the target.

  ``xrusd`` is the number of currency units per dollar. The exchange-rate
  factor of a position in the source currency, seen from the target currency,
  is therefore ``(x_target,t / x_source,t) / (x_target,t-1 / x_source,t-1)``.
  This function is used for unhedged sleeves only.
  """
  return ((1.0 + return_source) * (1.0 + inflation_source)
          * (target_xrusd_current / source_xrusd_current)
          / (target_xrusd_previous / source_xrusd_previous)
          / (1.0 + inflation_target) - 1.0)


def _fixed_numeraire_covered_return(return_source: float, source_bill: float,
                                    target_bill: float) -> float:
  """Replace the source bill with the target country's bill in a hedged sleeve."""
  return ((1.0 + target_bill) * (1.0 + return_source)
          / (1.0 + source_bill) - 1.0)


def fixed_numeraire_rows(rows: list[dict[str, float]],
                         target_country: str) -> list[dict[str, float]]:
  """Keep the country-year states but impose the numeraire of a target country.

  The source country still defines the blocks and the ``domestic`` and
  ``international`` assets. The check is therefore not a literal domestic
  portfolio in the target country: it isolates the change of numeraire in the
  ACO bootstrap. Hedged sleeves keep their excess return but are recombined
  with the target bill; unhedged sleeves are converted at spot and deflated by
  the target CPI.
  """
  target_by_year = {
    row["year"]: row for row in rows if row["country"] == target_country
  }
  if not target_by_year:
    raise ValueError(f"Numeraire country missing from panel: {target_country}")
  by_country_year = {(row["country"], row["year"]): row for row in rows}
  converted = []
  for row in rows:
    previous = by_country_year.get((row["country"], row["year"] - 1))
    target = target_by_year.get(row["year"])
    target_previous = target_by_year.get(row["year"] - 1)
    if previous is None or target is None or target_previous is None:
      continue
    values = (row["xrusd"], previous["xrusd"], target["xrusd"],
              target_previous["xrusd"], row["inflation"],
              target["inflation"], row["bill"], target["bill"])
    if not all(math.isfinite(value) for value in values):
      continue
    if any(1.0 + value <= 0.0 for value in
           (row["inflation"], target["inflation"], row["bill"],
            target["bill"])):
      continue

    def unhedged(key: str) -> float:
      return _fixed_numeraire_unhedged_return(
        row[key], row["inflation"], previous["xrusd"], row["xrusd"],
        target_previous["xrusd"], target["xrusd"], target["inflation"])

    item = dict(row)
    item.update({
      "domestic": unhedged("domestic"),
      "international": unhedged("international"),
      "bond": unhedged("bond"),
      "bill": target["bill"],
      "inflation": target["inflation"],
      "world_equity": unhedged("world_equity"),
      "world_bond": _fixed_numeraire_covered_return(
        row["world_bond"], row["world_bill"], target["bill"]),
      "world_bill": target["bill"],
      "world_bond_unhedged": unhedged("world_bond_unhedged"),
      "world_bill_unhedged": unhedged("world_bill_unhedged"),
      "trend": _fixed_numeraire_covered_return(
        row["trend"], row["world_bill"], target["bill"]),
      "trend_unhedged": unhedged("trend_unhedged"),
      "gold": unhedged("gold"),
    })
    converted.append(item)
  return converted


def usd_numeraire_rows(rows: list[dict[str, float]]) -> list[dict[str, float]]:
  """Compatibility alias for the fixed-USD-numeraire check."""
  return fixed_numeraire_rows(rows, "USA")


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=10.0)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
  parser.add_argument("--fx-hedge-cost", type=float,
                      default=DEFAULT_FX_HEDGE_COST)
  parser.add_argument("--hedge-mode", choices=("ideal", "fixed_notional"),
                      default="fixed_notional",
                      help="fixed_notional hedges beginning-of-year FX notional; ideal is the legacy full-value CIP convention")
  parser.add_argument("--bootstrap-end-treatment", choices=("aco", "restart"),
                      default="aco",
                      help="aco completes a truncated block at a new country's first year; restart is the legacy implementation")
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--trend-haircut", type=float, default=0.0)
  parser.add_argument("--withdrawal-rate", type=float,
                      default=WITHDRAWAL_RATE)
  parser.add_argument("--gamma", type=float, default=GAMMA)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  parser.add_argument("--exclude-country", action="append", default=[])
  parser.add_argument("--exclude-country-year", action="append", default=[],
                      metavar="COUNTRY:YEAR",
                      help="diagnostic only: remove a resident country-year from the bootstrap panel")
  parser.add_argument(
    "--portfolio-set", choices=("all", "core", "ladders"), default="all",
    help=("all (default) evaluates every recipe; core produces the main "
          "tables; ladders produces only the two exposure ladders"))
  parser.add_argument(
    "--sample-mode", choices=("investable", "usa", "full"),
    default="full",
    help=("full (default) keeps the whole historical panel; investable "
          "applies the tradability filter; usa simulates a US resident only"))
  parser.add_argument("--usd-numeraire", action="store_true",
                      help=("keep the international blocks but convert "
                            "every sleeve into real dollars and finance at the "
                            "US bill"))
  parser.add_argument("--usd-common-sample", action="store_true",
                      help=("restrict the resident panel to the subsample "
                            "convertible into real dollars, for a comparison "
                            "paired with --usd-numeraire"))
  parser.add_argument("--exclude-war-years", action="store_true",
                      help="remove documented wars and monetary breaks, "
                           "country by country")
  parser.add_argument("--include-suspect-data", action="store_true",
                      help="historical alias of --sample-mode full")
  parser.add_argument("--include-unhedged-control", action="store_true",
                      help="add the unhedged foreign bonds and cash check; "
                      "robustness only")
  parser.add_argument(
    "--reallocate-administered-gold-from", type=int,
    help=("from this year, gold becomes available again; before it, its "
          "sleeve is spread equally over the active non-gold sleeves "
          "(unavailability variant)"))
  parser.add_argument("--output-json",
                      help="optional machine-readable output")
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs must be strictly positive")
  if args.spread < 0.0:
    raise ValueError("--spread cannot be negative")
  if args.fx_hedge_cost < 0.0:
    raise ValueError("--fx-hedge-cost cannot be negative")
  if (args.usd_numeraire or args.usd_common_sample) and args.sample_mode == "usa":
    raise ValueError("The USD check is redundant with --sample-mode usa")
  validate_design()

  rows = read_panel(args.panel)
  sample_mode = "full" if args.include_suspect_data else args.sample_mode
  quality_flags = [
    {"country": row["country"], "year": row["year"],
     "reason": exclusion_reason(row["country"], row["year"])}
    for row in rows
    if exclusion_reason(row["country"], row["year"]) is not None
  ]
  investability_exclusions = [
    {"country": row["country"], "year": row["year"],
     "inflation": row["inflation"],
     "reason": investability_reason(
       row["country"], row["year"], row["inflation"])}
    for row in rows
    if investability_reason(row["country"], row["year"], row["inflation"])
    is not None
  ]
  if sample_mode == "investable":
    rows = [
      row for row in rows
      if investability_reason(row["country"], row["year"], row["inflation"])
      is None
    ]
  elif sample_mode == "usa":
    rows = [row for row in rows if row["country"] == "USA"]
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  excluded = set(args.exclude_country)
  excluded_country_years = set()
  for value in args.exclude_country_year:
    try:
      country, year = value.rsplit(":", 1)
      excluded_country_years.add((country, int(year)))
    except ValueError as error:
      raise ValueError("--exclude-country-year must be COUNTRY:YEAR") from error
  if excluded:
    rows = [row for row in rows if row["country"] not in excluded]
  if excluded_country_years:
    rows = [row for row in rows
            if (row["country"], row["year"]) not in excluded_country_years]
  if args.exclude_war_years:
    rows = [row for row in rows
            if not is_war_year(row["country"], row["year"])]
  source_observations = len(rows)
  if args.usd_numeraire or args.usd_common_sample:
    converted_rows = usd_numeraire_rows(rows)
    if args.usd_numeraire:
      rows = converted_rows
    else:
      converted_keys = {(row["country"], row["year"]) for row in converted_rows}
      rows = [row for row in rows
              if (row["country"], row["year"]) in converted_keys]
  if len(rows) < 2:
    raise ValueError("The requested window does not contain enough data")
  included_keys = {(row["country"], row["year"]) for row in rows}
  quality_flags = [
    flag for flag in quality_flags
    if (flag["country"], flag["year"]) in included_keys
  ]
  functions = return_functions(
    rows, args.spread, args.trend_fee, args.trend_cost, args.trend_haircut,
    args.fx_hedge_cost, args.reallocate_administered_gold_from,
    args.include_unhedged_control, not args.usd_numeraire, args.hedge_mode)
  if args.portfolio_set != "all":
    baseline_names = {
      "Actions domestiques", "ACO 33/67", "Stocks/I",
      "Balanced domestique", "Balanced/I", "90/60 local fixe",
      "90/60 oblig. mondiales", "ACO 33/67, change reel cst",
      "90/60 oblig. non couvert",
    }
    if args.portfolio_set == "core":
      allowed = baseline_names | CORE_EXPOSURE_NAMES
    else:
      allowed = {BENCHMARK_NAME} | (set(FIXED_EXPOSURES) - CORE_EXPOSURE_NAMES)
    allowed |= set(ACO_LEVERAGE_NAMES)
    functions = {name: function for name, function in functions.items()
                 if name in allowed}

  print("PANEL A -- FIXED EX ANTE DESIGN (no volatility targeting)")
  if sample_mode == "investable":
    print("Investable core sample: "
          f"{len(investability_exclusions)} country-years excluded on "
          "documented criteria.")
  elif sample_mode == "usa":
    print("Consistent check: US resident, returns and flows in real dollars.")
  else:
    print("Full historical stress: no investability exclusion.")
  if args.usd_numeraire:
    print("Numeraire check: same country-year blocks, every sleeve "
          "in real dollars; US bill. "
          f"{len(rows)}/{source_observations} convertible observations.")
  elif args.usd_common_sample:
    print("Sample matched to the USD numeraire check: "
          f"{len(rows)}/{source_observations} convertible observations.")
  print(f"{'strategy':<24}{'stocks':>10}{'bonds':>10}{'gold':>9}"
        f"{'MF':>9}{'gross':>9}{'borrow':>10}")
  print("-" * 81)
  print(f"{'ACO 33/67':<24}{'100%*':>10}{'0.0%':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  for level, name in zip((1.25, 1.5, 1.75, 2.0), ACO_LEVERAGE_NAMES):
    print(f"{name:<24}{level:>10.1%}{0.0:>10.1%}{0.0:>9.1%}"
          f"{0.0:>9.1%}{level:>9.1%}{level-1:>10.1%}")
  print(f"{'Stocks/I 50/50':<24}{'100%*':>10}{'0.0%':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  print(f"{'Domestic stocks':<24}{'100%**':>10}{'0.0%':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  if not args.usd_numeraire:
    print(f"{'ACO 33/67, const. FX':<24}{'100%****':>10}{'0.0%':>10}{'0.0%':>9}"
          f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  print(f"{'90/60 local fixed':<24}{'90%*':>10}{'60%**':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'150.0%':>9}{'50.0%':>10}")
  print(f"{'90/60 global bonds':<24}{'90%*':>10}{'60%***':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'150.0%':>9}{'50.0%':>10}")
  if args.include_unhedged_control:
    print(f"{'90/60 unhedged bonds':<24}{'90%*':>10}{'60%*****':>10}{'0.0%':>9}"
          f"{'0.0%':>9}{'150.0%':>9}{'50.0%':>10}")
  for name, (equity, bond, gold, trend) in FIXED_EXPOSURES.items():
    gross = equity + bond + gold + trend
    print(f"{name:<24}{equity:>10.1%}{bond:>10.1%}{gold:>9.1%}"
          f"{trend:>9.1%}{gross:>9.1%}{max(0.0, gross - 1.0):>10.1%}")
  print("* ACO 33/67 is the optimal fixed portfolio of the 2025 revision;")
  print("  every extension keeps this same equity sleeve.")
  print("  Stocks/I keeps the historical 50/50 convention as a check.")
  print("** Domestic exposure to the path's country of residence.")
  print("*** Hedged global bonds; resident's bill; stocks unchanged.")
  if not args.usd_numeraire:
    print("**** 33/67 domestic/international, real exchange rate neutralised; counterfactual.")
  if args.include_unhedged_control:
    print("***** Secondary check at the spot exchange rate, unhedged.")
  print()

  pooled = {name: [function(row) for row in rows]
            for name, function in functions.items()}
  moment_by_name = {}
  for name, values in pooled.items():
    worst_index = min(range(len(rows)), key=lambda index: values[index])
    worst_row = rows[worst_index]
    moment_by_name[name] = {
      "mean_return": statistics.fmean(values),
      "volatility": statistics.stdev(values),
      "first_percentile_return": empirical_quantile(values, 0.01),
      "worst_year": values[worst_index],
      "worst_country": worst_row["country"],
      "worst_calendar_year": worst_row["year"],
    }
  print("PANEL B -- REALISED MOMENTS (evaluation, never calibration)")
  print(f"{'strategy':<24}{'return':>12}{'volatility':>13}"
        f"{'1st pct.':>12}{'minimum (country-year)':>27}")
  print("-" * 88)
  for name, values in pooled.items():
    moment = moment_by_name[name]
    event = (f"{moment['worst_year']:.2%} "
             f"({moment['worst_country']} {moment['worst_calendar_year']})")
    print(f"{name:<24}{statistics.fmean(values):>12.2%}"
          f"{statistics.stdev(values):>13.2%}"
          f"{moment['first_percentile_return']:>12.2%}{event:>27}")
  print()

  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)
  scenarios = []
  income_at_25: list[float] = []
  income_at_47: list[float] = []
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block,
                           args.bootstrap_end_treatment)
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, household_income = draw_household_income(rng)
    income_at_25.append(household_income[0])
    income_at_47.append(household_income[47 - START_AGE])
    scenarios.append(build_scenario(
      path, functions, female_death, male_death,
      female_income, male_income))

  target_utility = expected_utility(
    scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, args.gamma,
    args.withdrawal_rate)
  print("PANEL C -- LIFECYCLE, CRRA AND EQUIVALENT SAVING")
  print(f"{args.runs} paired paths; {args.mean_block:g}-year blocks; "
        f"spread {args.spread:.2%}; gamma {args.gamma:g}")
  print(f"MF net of fees {args.trend_fee:.2%}, costs {args.trend_cost:.2%} "
        f"and haircut {args.trend_haircut:.2%}")
  print(f"Bonds and MF hedged; FX friction "
        f"{args.fx_hedge_cost:.2%}")
  if args.reallocate_administered_gold_from is not None:
    print("Gold unavailable before "
          f"{args.reallocate_administered_gold_from}: notional spread "
          "equally over active non-gold sleeves.")
  print(f"Median income check: age 25 "
        f"{statistics.median(income_at_25):,.0f}, age 47 "
        f"{statistics.median(income_at_47):,.0f}".replace(",", " "))
  print()
  print(f"Utility reference: {BENCHMARK_NAME} saving 10%.")
  print(f"{'strategy':<27}{'eq. saving':>12}{'median wealth':>16}"
        f"{'mean cons.':>13}{'ruin':>9}  {'delta [CI95]':>22}"
        f"{'median bequest':>14}")
  print("-" * 113)
  outcomes_by_name = {
    name: evaluate_batch(scenarios, name, BASE_SAVINGS_RATE,
                         args.withdrawal_rate, args.gamma)
    for name in functions
  }
  benchmark_ruin = outcomes_by_name[BENCHMARK_NAME].ruined.astype(float)
  machine_results = []
  for name in functions:
    outcomes = outcomes_by_name[name]
    equivalent = equivalent_savings_rate(
      scenarios, name, target_utility, args.gamma, args.withdrawal_rate)
    equivalent_text = (
      "hors borne" if math.isnan(equivalent) else f"{equivalent:.2%}")
    retirement = float(np.median(outcomes.retirement_wealth))
    consumption = float(np.mean(outcomes.retirement_consumption))
    ruin = float(np.mean(outcomes.ruined))
    differences = [
      float(outcome) - reference
      for outcome, reference in zip(outcomes.ruined, benchmark_ruin)
    ]
    delta = statistics.fmean(differences)
    standard_error = (statistics.stdev(differences) / math.sqrt(len(differences))
                      if len(differences) > 1 else 0.0)
    low = delta - 1.96 * standard_error
    high = delta + 1.96 * standard_error
    interval = f"{delta:+.2%} [{low:+.2%};{high:+.2%}]"
    bequest = float(np.median(outcomes.bequest))
    line = (f"{name:<27}{equivalent_text:>12}{retirement:>16,.0f}"
            f"{consumption:>13,.0f}{ruin:>9.2%}  {interval:>22}"
            f"{bequest:>14,.0f}")
    print(line.replace(",", " "))
    machine_results.append({
      "strategy": name,
      **moment_by_name[name],
      "equivalent_savings_rate": None if math.isnan(equivalent) else equivalent,
      "median_retirement_wealth": retirement,
      "mean_retirement_consumption": consumption,
      "ruin_probability": ruin,
      "ruin_difference_vs_benchmark": delta,
      "ruin_difference_ci95": [low, high],
      "median_bequest": bequest,
    })

  if args.output_json:
    payload = {
      "seed": args.seed,
      "runs": args.runs,
      "mean_block": args.mean_block,
      "bootstrap_end_treatment": args.bootstrap_end_treatment,
      "spread": args.spread,
      "fx_hedge_cost": args.fx_hedge_cost,
      "hedge_mode": args.hedge_mode,
      "trend_fee": args.trend_fee,
      "trend_cost": args.trend_cost,
      "trend_haircut": args.trend_haircut,
      "gold_reallocation_from_year": args.reallocate_administered_gold_from,
      "withdrawal_rate": args.withdrawal_rate,
      "gamma": args.gamma,
      "year_from": args.year_from,
      "year_to": args.year_to,
      "excluded_countries": sorted(excluded),
      "excluded_country_years": [
        {"country": country, "year": year}
        for country, year in sorted(excluded_country_years)
      ],
      "excluded_war_years": args.exclude_war_years,
      "included_suspect_data": bool(quality_flags),
      "sample_mode": sample_mode,
      "portfolio_set": args.portfolio_set,
      "usd_numeraire": args.usd_numeraire,
      "usd_common_sample": args.usd_common_sample,
      "source_observations": source_observations,
      "included_unhedged_control": args.include_unhedged_control,
      "data_quality_flags": quality_flags,
      "investability_exclusions": investability_exclusions,
      "observations": len(rows),
      "benchmark": BENCHMARK_NAME,
      "aco_leverage_exposures": dict(zip(ACO_LEVERAGE_NAMES, (1.25, 1.5, 1.75, 2.0))),
      "results": machine_results,
    }
    with open(args.output_json, "w", encoding="utf-8") as handle:
      json.dump(payload, handle, ensure_ascii=False, indent=2)
      handle.write("\n")


if __name__ == "__main__":
  main()
