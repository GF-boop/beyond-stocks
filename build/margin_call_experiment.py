#!/usr/bin/env python3
"""Margin-call experiment for the strategies of the paper.

The personal margin account holds exactly the frozen weights of the levered
families (two families at 200% and the hedged ladder at 150%) and follows the
same discipline as the main engine: ANNUAL rebalancing to the target gross
exposure. The maintenance margin (25% of assets) is tested at year-end — the
granularity of the annual data — before the rebalancing that restores the
margin cushion. Same bootstrap paths as the tables (10,000, seed 20260827).

MECHANICAL CONSEQUENCE: annual rebalancing resets the account to 50% equity
(2x gross) or 67% (1.5x gross) at the start of every year. A year-end call
therefore requires a loss WITHIN A SINGLE YEAR beyond the threshold implied by
the nominal rate: about -31% at 2x gross, -54% at 1.5x gross. A cumulative
multi-year drawdown — which drives an unrebalanced buy-and-hold account — is
erased by rebalancing and cannot trigger a call here.

NOMINAL CONVENTION: a margin account is a nominal contract — the broker
compares the nominal value of the assets with the nominal debt. Since the
panel's returns are real for the resident, exact nominal returns are rebuilt:
R_nom = (1+R_real_per_asset)x(1+pi_resident)-1, where R_real_per_asset is the
real return of the asset book per dollar of assets, and likewise for the
nominal bill. Inflation erodes the nominal debt: hyperinflation episodes do not
trigger calls, contrary to what a test in real terms would wrongly suggest.
"""

import json
import hashlib
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compare_fixed_stacked_utility import (  # noqa: E402
    return_functions,
    DEFAULT_TREND_FEE,
    DEFAULT_TREND_COST,
)
from replicate_extended import (  # noqa: E402
    MAX_AGE,
    START_AGE,
    block_bootstrap,
    read_panel,
)

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = 10000
SEED = 20260827
SPREAD = 0.003
MAINTENANCE = 0.25
# (engine name, label, gross exposure). The two 200% families come from the
# frozen manifest; the hedged 150% ladder is the "90/60 oblig. mondiales"
# lambda (90% ACO stocks + 60% hedged global bonds).
LEVERED = (("80/53.33/33.33/33.33 ACO", "proportional_200", 2.0),
           ("ACO 33/67 175%", "aco_175", 1.75),
           ("ACO 33/67 200%", "aco_200", 2.0),
           ("43.75/43.75/43.75/43.75 ACO", "equal_weight_175", 1.75),
           ("50/50/50/50 ACO", "equal_weight_200", 2.0),
           ("90/60 oblig. mondiales", "covered_150", 1.5))


def nominal(real, pi):
  return (1.0 + real) * (1.0 + pi) - 1.0


def main():
  rows = read_panel(os.path.join(HERE, "..", "data",
                                 "replication-panel-trend.csv"))
  functions = return_functions(
    rows, SPREAD, DEFAULT_TREND_FEE, DEFAULT_TREND_COST, 0.0, 0.001)
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(SEED)

  # Median nominal financing bill, to size the annual loss that would trigger
  # a call.
  bills = sorted(nominal(row["world_bill"], row["inflation"]) for row in rows)
  median_bill = bills[len(bills) // 2]

  stats = {label: {"calls": 0, "paths_with_call": 0, "wipes": 0,
                   "path_years": 0, "min_year_end_ratio": 1.0,
                   "worst_asset_book_year": 0.0}
           for _, label, _ in LEVERED}
  for _ in range(RUNS):
    path = block_bootstrap(rows, horizon, rng, 10.0)
    for name, label, gross in LEVERED:
      fn = functions[name]
      st = stats[label]
      equity = 1.0
      called = wiped = False
      for row in path:
        pi = row["inflation"]
        bill_nom = nominal(row["world_bill"], pi)
        # Return of the asset book per dollar of assets: the engine pays the wealth
        # (equity), we add back the financing bill (G-1)x(bill+spread) and divide by the
        # gross exposure. Nominal returns are rebuilt PER ASSET: nominalising the
        # levered return would give impossible nominal values as soon as
        # G x R < -100%.
        per_asset = (fn(row) + (gross - 1.0)
                     * (row["world_bill"] + SPREAD)) / gross
        gross_nom = nominal(per_asset, pi)
        st["worst_asset_book_year"] = min(st["worst_asset_book_year"],
                                          gross_nom)
        # Start of year: account reset to the target exposure (G of assets, G-1 of
        # debt, per dollar of equity), then one year of returns without intra-year
        # rebalancing.
        assets = gross * equity * (1.0 + gross_nom)
        debt = (gross - 1.0) * equity * (1.0 + bill_nom + SPREAD * (1.0 + pi))
        eq = assets - debt
        assert math.isclose(eq / equity, (1.0 + fn(row)) * (1.0 + pi),
                            rel_tol=1e-10, abs_tol=1e-10)
        ratio = eq / assets if assets > 0 else 0.0
        st["min_year_end_ratio"] = min(st["min_year_end_ratio"], ratio)
        st["path_years"] += 1
        if eq <= 0.0:
          st["calls"] += 1
          wiped = True
          called = True
          break
        if ratio < MAINTENANCE:
          called = True
          st["calls"] += 1
        equity = 1.0  # ratios are scale invariant; normalize after rebalancing
      if called:
        st["paths_with_call"] += 1
      if wiped:
        st["wipes"] += 1

  out = {"seed": SEED, "runs": RUNS, "maintenance_margin": MAINTENANCE,
         "panel_rows": len(rows), "hedge_mode": "fixed_notional",
         "bootstrap_end_treatment": "aco", "mean_block_years": 10,
         "horizon": horizon, "spread_real": SPREAD,
         "panel_sha256": hashlib.sha256(open(os.path.join(HERE, '..', 'data',
                                    'replication-panel-trend.csv'), 'rb').read()).hexdigest(),
         "design": ("account with strategy weights, rebalanced each "
                    "year to target exposure; margin checked at "
                    "year-end; notionals reconstructed by asset"),
         "families": {}}
  for name, label, gross in LEVERED:
    st = stats[label]
    thresholds = sorted((gross - 1.0) * (1.0 + nominal(row['world_bill'], row['inflation'])
                         + SPREAD * (1.0 + row['inflation']))
                        / ((1.0 - MAINTENANCE) * gross) - 1.0 for row in rows)
    threshold = thresholds[len(thresholds) // 2]
    st["gross_exposure"] = gross
    st["single_year_loss_threshold"] = round(threshold, 4)
    out["families"][label] = st
    print(label, f"gross {gross:.0%}",
          {k: v for k, v in st.items() if k != "path_years"},
          f"| account-years: {st['path_years']:,}")
  out["median_nominal_bill"] = round(median_bill, 4)
  print(f"bill nominal median: {median_bill:.3%}")
  path = os.path.join(HERE, "..", "results", "margin_call_n10000.json")
  with open(path, "w") as fh:
    json.dump(out, fh, indent=1)
  print("->", path)


if __name__ == "__main__":
  main()
