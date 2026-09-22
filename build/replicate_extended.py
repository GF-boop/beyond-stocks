"""Extension of the replication: the paper's strategies against levered and
trend-following portfolios.

The paper compares allocations that do not carry the same risk, then concludes
that the riskiest one "dominates". The conclusion is partly circular: over a
forty-year saving horizon, the allocation most exposed to stocks almost always
ends ahead, and the target-date fund loses mainly because it carries less risk
-- not because it is badly built.

This module therefore adds strategies that seek return other than through a
larger equity exposure: a 90/60 levered fund, and combinations with a trend
sleeve. It also reports the volatility of the portfolio actually held and a
return per unit of risk, so that the comparison is not made in levels only.

Based on the faithful replication of Anarkulova, Cederburg and O'Doherty
(2023), "Beyond the Status Quo: A Critical Assessment of Lifecycle Investment
Advice".

Confirmed by reading the manuscript (Netspar working paper, 21 Sept. 2023):

- thesis: a basket of 50% domestic / 50% international stocks, held constant
  at all ages ("Stocks/I"), dominates glide paths towards bonds -- including
  for capital preservation;
- household: saves 10% of income from 25 to 65, withdraws 4% of initial
  capital at retirement, indexed to inflation afterwards;
- stationary bootstrap, geometric block lengths, mean 120 months;
- four asset classes drawn together by country-month: domestic stocks,
  international stocks (capitalisation-weighted mean of the other markets,
  adjusted for exchange rates), bonds, bills;
- mortality: SSA tables by sex.

Deliberate differences of this replication:

- JST (16 countries, 1871-2020, annual) replaces the paper's proprietary
  GFDatabase (about 38 countries, 1890-2019, monthly). On the pooled domestic
  equity return, our panel gives 2.92% real per year against 4.53% (converted
  from 0.37% per month) in theirs -- a difference in level that comes from the
  sources, not from the method;
- international stocks are rebuilt from JST (see international_equity.py)
  rather than measured directly;
- mortality follows a Gompertz--Makeham law set to the SSA moments reported by
  ACO (see mortality.py), not the proprietary monthly table;
- no Social Security or stochastic income model in this module: the household
  saves a constant share of a fixed real income. The paper shows that this
  choice shifts the levels without changing the ranking of the strategies.

The paper compares MEANS, not medians -- this module follows that convention
to allow a direct comparison.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mortality import table as mortality_table  # noqa: E402
from trend_costs import (  # noqa: E402
  DEFAULT_TREND_COST, DEFAULT_TREND_FEE,
)
from social_security import household_benefit  # noqa: E402

START_AGE = 25
RETIRE_AGE = 65
MAX_AGE = 110
SAVINGS_RATE = 0.10
# The paper draws incomes from a stochastic model (Guvenen et al.) and obtains
# a mean retirement wealth of 0.81 million dollars for the TDF. This constant
# income is set to reproduce that order of magnitude, since the income model
# itself cannot be replicated here.
INCOME = 31_500.0
WITHDRAWAL_RATE = 0.04  # remplace par --withdrawal-rate si fourni
MEAN_BLOCK_MONTHS_EQUIVALENT = 10.0  # 120 months -> 10 years, the panel is annual

# Financing cost of the exposure above one hundred percent, and fees of the
# trend sleeve. A listed fund delivering the performance of a trend strategy
# must finance its exposure like any levered fund.
#
# The fee is 0.85% per year, the median of the managed-futures ETFs available in
# 2026 (iMGP DBi UCITS 0.75%, DBMF 0.85%, KMLM 0.90%), which charge fixed fees
# without a performance fee. The transaction drag is derived from the turnover
# ACTUALLY measured on the managed-futures proxy (about 19x per year) and a
# round-trip spread of 3 basis points, about 0.57%.
#
# Both values come from trend_costs.py, where the cost is recomputed from the
# turnover measured on data/managed-futures-monthly.csv rather than hard-coded:
# the previous version coded 0.17%, a value inherited from the former trend
# index, which silently went stale when the series changed.
# The main case uses 0.30% above short rates as the cost of leverage.
# Cederburg's 0.37% remains a replication sensitivity and 1.40% a more expensive
# margin scenario.
FINANCING_SPREAD = 0.003
TREND_FEE = DEFAULT_TREND_FEE
TREND_DRAG = DEFAULT_TREND_COST

# Panel A -- "safe harbor" strategies (glide path or fixed allocation).
# Panel B -- pure capital preservation.
# Panel C -- all-equity strategies, non-QDIA.
# Each strategy gives (domestic, international, bonds, bills) at 25 and at 65;
# glide paths interpolate linearly between the two, fixed allocations repeat the
# same pair.
# Weights are (domestic, international, bonds, bills, trend).
# The first five strategies come from the paper, the next ones extend it.
STRATEGIES: dict[str, dict] = {
  "TDF": {"young": (0.54, 0.36, 0.10, 0.00), "old": (0.18, 0.12, 0.55, 0.15)},
  "Balanced": {"young": (0.60, 0.00, 0.40, 0.00), "old": (0.60, 0.00, 0.40, 0.00)},
  "Balanced/I": {"young": (0.30, 0.30, 0.40, 0.00), "old": (0.30, 0.30, 0.40, 0.00)},
  "Age": {"glide_120": True, "international_share": 0.0},
  "Age/I": {"glide_120": True, "international_share": 0.5},
  "Bills": {"young": (0.00, 0.00, 0.00, 1.00), "old": (0.00, 0.00, 0.00, 1.00)},
  "Stocks": {"young": (1.00, 0.00, 0.00, 0.00), "old": (1.00, 0.00, 0.00, 0.00)},
  "Stocks/I": {"young": (0.50, 0.50, 0.00, 0.00), "old": (0.50, 0.50, 0.00, 0.00)},
  # 90% stocks and 60% bonds per hundred euros invested: the fund seeks return
  # through leverage rather than more stocks. The equity sleeve is diversified like
  # Stocks/I, so that the comparison does not mix the effect of leverage with that
  # of geographic diversification.
  "90/60/I": {"young": (0.45, 0.45, 0.60, 0.00), "old": (0.45, 0.45, 0.60, 0.00)},
  # Trend replaces the bond sleeve.
  "90/60 MF": {"young": (0.45, 0.45, 0.00, 0.00, 0.60),
               "old": (0.45, 0.45, 0.00, 0.00, 0.60)},
  # All three sleeves together, giving 210% exposure.
  "90/60/60": {"young": (0.45, 0.45, 0.60, 0.00, 0.60),
               "old": (0.45, 0.45, 0.60, 0.00, 0.60)},
  # A set-up feasible with two listed funds: 60% of capital in a 90/60 fund,
  # 40% in a trend fund.
  "60 NTSG/40 MF": {"young": (0.27, 0.27, 0.36, 0.00, 0.40),
                    "old": (0.27, 0.27, 0.36, 0.00, 0.40)},
  # Portfolios with gold. The sixth weight is the gold sleeve.
  # A classic 60/40 with part of it replaced by gold.
  "50/30/20 Gold": {"young": (0.25, 0.25, 0.30, 0.00, 0.00, 0.20),
                  "old": (0.25, 0.25, 0.30, 0.00, 0.00, 0.20)},
  # Artemis's Dragon, without its long-volatility sleeve: its five building
  # blocks are stocks, bonds, gold, trend and long volatility at 20% each. The last
  # one needs historical option data that are not public, so the other four are
  # reweighted to 25%.
  "Dragon (no volatility targeting)": {"young": (0.125, 0.125, 0.25, 0.00, 0.25, 0.25),
                        "old": (0.125, 0.125, 0.25, 0.00, 0.25, 0.25)},
  # The two-fund set-up, with a gold sleeve added.
  "NTSG/MF/Gold": {"young": (0.225, 0.225, 0.30, 0.00, 0.30, 0.20),
                 "old": (0.225, 0.225, 0.30, 0.00, 0.30, 0.20)},
  # The Dragon has the lowest volatility of the table apart from bills, which
  # makes it the natural candidate for leverage: raising it to 150% or 200% brings
  # it to the risk level of the all-equity strategies, and allows a comparison at
  # comparable risk rather than comparable exposure.
  "Dragon x1.5": {"young": (0.1875, 0.1875, 0.375, 0.00, 0.375, 0.375),
                  "old": (0.1875, 0.1875, 0.375, 0.00, 0.375, 0.375)},
  "Dragon x2": {"young": (0.25, 0.25, 0.50, 0.00, 0.50, 0.50),
                "old": (0.25, 0.25, 0.50, 0.00, 0.50, 0.50)},
}

PANEL_A = ("TDF", "Balanced", "Balanced/I", "Age", "Age/I")
PANEL_B = ("Bills",)
PANEL_C = ("Stocks", "Stocks/I")
PANEL_D = ("90/60/I", "90/60 MF", "90/60/60", "60 NTSG/40 MF")
PANEL_E = ("50/30/20 Gold", "Dragon (no volatility targeting)", "NTSG/MF/Gold",
           "Dragon x1.5", "Dragon x2")


def read_panel(path: str) -> list[dict[str, float]]:
  rows = []
  with open(path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      rows.append({
        "country": row["country"],
        "year": int(row["year"]),
        # Number of resident currency units per dollar. It lets the fixed-USD
        # numeraire check re-express the same country-year states without changing the
        # bootstrap.
        "xrusd": float(row.get("xrusd", "nan")),
        "domestic": float(row["domestic_equity_real"]),
        "international": float(row["international_equity_real"]),
        "international_constant_real_fx": float(row.get(
          "international_equity_real_constant_real_fx",
          row["international_equity_real"])),
        "bond": float(row["bond_real"]),
        "bill": float(row["bill_real"]),
        "inflation": float(row["inflation"]),
        # Global bond sleeve: all the sovereigns available in the panel (up to 16),
        # equally weighted, then converted into the currency and purchasing power of the
        # resident carried by this row.
        "world_bond": float(row.get("world_bond_real", row["bond_real"])),
        "world_bond_fixed_notional": float(row.get(
          "world_bond_real_fixed_notional", row.get("world_bond_real", row["bond_real"]))),
        "world_bill": float(row.get("world_bill_real", row["bill_real"])),
        "world_bond_unhedged": float(row.get(
          "world_bond_real_unhedged", row.get("world_bond_real",
                                                row["bond_real"]))),
        "world_bill_unhedged": float(row.get(
          "world_bill_real_unhedged", row.get("world_bill_real",
                                                row["bill_real"]))),
        # Global equity sleeve: MSCI World from 1970, weighted reconstruction before
        # that date, in both cases converted into the numeraire of the row's resident.
        "world_equity": float(row.get("world_equity_real",
                                      row["domestic_equity_real"])),
        "trend": float(row.get("trend_real", 0.0)),
        "trend_fixed_notional": float(row.get(
          "trend_real_fixed_notional", row.get("trend_real", 0.0))),
        "trend_unhedged": float(row.get(
          "trend_real_unhedged", row.get("trend_real", 0.0))),
        # Gold pays no income: its return is the price change alone, net of the
        # custody fees of a physical holder.
        "gold": float(row.get("gold_real", 0.0)),
      })
  rows.sort(key=lambda r: (r["country"], r["year"]))
  return rows


def block_bootstrap(rows: list[dict[str, float]], horizon: int,
                    rng: random.Random,
                    mean_block: float = MEAN_BLOCK_MONTHS_EQUIVALENT,
                    end_treatment: str = "aco",
                    ) -> list[dict[str, float]]:
  """Geometric-length blocks. A mean length of 1 amounts to an independent
  draw year by year, which reproduces the IID bootstrap that the paper shows for
  comparison. A block stays in the same country. When it reaches a gap or the
  end of the series, it is completed with a new country and that country's first
  available observation, as in ACO (2025, section 4.4). This rule avoids
  underweighting the start of the series."""
  if end_treatment not in {"aco", "restart"}:
    raise ValueError("end_treatment must be aco or restart")
  if mean_block <= 1.0:
    return [rows[rng.randrange(len(rows))] for _ in range(horizon)]
  probability = 1.0 / mean_block
  by_country_year = {(row["country"], row["year"]): row for row in rows}
  path: list[dict[str, float]] = []
  while len(path) < horizon:
    length = max(1, int(math.ceil(
      math.log(1.0 - rng.random()) / math.log(1.0 - probability))))
    start = rows[rng.randrange(len(rows))]
    country, year = start["country"], start["year"]
    for _ in range(length):
      observation = by_country_year.get((country, year))
      if observation is None:
        if end_treatment == "restart":
          break
        # ACO splice an incomplete block to the start of the history of a randomly
        # drawn country. Rows are sorted by country then year, so the minimum is that
        # country's first usable observation.
        country = rows[rng.randrange(len(rows))]["country"]
        year = min(item["year"] for item in rows if item["country"] == country)
        observation = by_country_year[(country, year)]
      path.append(observation)
      year += 1
      if len(path) >= horizon:
        break
  return path[:horizon]


def weights_at(name: str, age: int) -> tuple[float, ...]:
  """Weights (domestic, international, bonds, bills, trend).

  The paper's strategies have no trend sleeve; their four-element tuples are
  padded with a zero.
  """
  spec = STRATEGIES[name]
  progress = min(1.0, max(0.0, (age - START_AGE) / (RETIRE_AGE - START_AGE)))

  if spec.get("glide_120"):
    # The "120 minus age" rule: the equity share declines linearly with age and
    # is no longer a simple interpolation between two fixed bounds.
    stock_share = max(0.0, (120 - age) / 100.0)
    bond_share = 1.0 - stock_share
    share = spec["international_share"]
    return (stock_share * (1.0 - share), stock_share * share, bond_share,
            0.0, 0.0, 0.0)

  young = tuple(spec["young"]) + (0.0,) * (6 - len(spec["young"]))
  old = tuple(spec["old"]) + (0.0,) * (6 - len(spec["old"]))
  return tuple(y + (o - y) * progress for y, o in zip(young, old))


def portfolio_return(observation: dict[str, float], weights: tuple[float, ...],
                     world_bonds: bool = False) -> float:
  """Annual real return of the portfolio.

  Exposure above one hundred percent is financed at the short rate plus the
  spread, whichever sleeve carries the excess. Trend also bears its management
  fee and its replication cost.

  `world_bonds` separates the two families of strategies. The paper's
  strategies hold the debt and stocks of the country of residence, as their
  authors model them: their equity sleeve is a 50/50 domestic and international
  basket. The levered funds hold a world index and a sovereign basket, because
  that is what real instruments do. Leverage financing follows the same sleeve
  as the bonds.
  """
  domestic, international, bond, bill, trend, gold = weights
  leverage = max(0.0,
                 domestic + international + bond + bill + trend + gold - 1.0)
  net_trend = (1.0 + observation["trend"]) * (1.0 - TREND_FEE) - 1.0 - TREND_DRAG

  if world_bonds:
    # Domestic and international equity weights are added: the fund does not
    # separate the two, it follows a single world index.
    equity = (domestic + international) * observation["world_equity"]
    bond_return = observation["world_bond"]
    short_rate = observation["world_bill"]
  else:
    equity = (domestic * observation["domestic"]
             + international * observation["international"])
    bond_return = observation["bond"]
    short_rate = observation["bill"]

  return (equity
         + bond * bond_return
         + bill * observation["bill"]
         + trend * net_trend
         + gold * observation["gold"]
         - leverage * (short_rate + FINANCING_SPREAD))


def draw_death_age(survival: dict[int, float], rng: random.Random) -> int:
  age = START_AGE
  while age < MAX_AGE:
    if rng.random() > survival.get(age, 0.5):
      return age
    age += 1
  return MAX_AGE


def simulate(name: str, path: list[dict[str, float]], last_death: int,
             first_death: int, pensions: tuple[float, float] | None = None,
             ) -> dict[str, float]:
  # Strategies outside the paper use the global bond sleeve.
  world_bonds = name in PANEL_D or name in PANEL_E
  wealth = 0.0
  portfolio_returns: list[float] = []
  for index, age in enumerate(range(START_AGE, RETIRE_AGE)):
    growth = portfolio_return(path[index], weights_at(name, age), world_bonds)
    portfolio_returns.append(growth)
    wealth += INCOME * SAVINGS_RATE
    wealth *= 1.0 + growth

  at_retirement = wealth
  withdrawal = at_retirement * WITHDRAWAL_RATE
  consumed, ruin_age = 0.0, None
  peak, retirement_drawdown = at_retirement, 0.0

  for index, age in enumerate(range(RETIRE_AGE, last_death + 1),
                              start=RETIRE_AGE - START_AGE):
    if index >= len(path):
      break
    served = min(wealth, withdrawal)
    # Ruin is the exhaustion of financial capital. The pension keeps being paid
    # afterwards, so a ruined household is not without resources -- this is the
    # paper's definition.
    if served < withdrawal - 0.005 and ruin_age is None:
      ruin_age = age
    wealth = max(0.0, wealth - served)

    if pensions is not None:
      couple_pension, survivor_pension = pensions
      pension = couple_pension if age <= first_death else survivor_pension
      consumed += served + pension
    else:
      consumed += served

    growth = portfolio_return(path[index], weights_at(name, age), world_bonds)
    portfolio_returns.append(growth)
    wealth *= 1.0 + growth
    peak = max(peak, wealth)
    if peak > 0:
      retirement_drawdown = min(retirement_drawdown, wealth / peak - 1.0)

  years = max(1, last_death - RETIRE_AGE + 1)
  return {
    "retirement_wealth": at_retirement,
    "consumption": consumed / years,
    "ruined": ruin_age is not None,
    "bequest": wealth,
    "retirement_drawdown": retirement_drawdown,
    "portfolio_vol": (statistics.stdev(portfolio_returns)
                      if len(portfolio_returns) > 1 else 0.0),
    "portfolio_return": statistics.fmean(portfolio_returns),
  }


def main() -> None:
  global FINANCING_SPREAD, WITHDRAWAL_RATE
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--no-social-security", action="store_true",
                      help="disable pensions, for comparison")
  parser.add_argument("--mean-block", type=float,
                      default=MEAN_BLOCK_MONTHS_EQUIVALENT,
                      help="mean block length in years; 1 for IID")
  parser.add_argument("--withdrawal-rate", type=float,
                      default=WITHDRAWAL_RATE,
                      help="annuity rate in %% of the capital reached by "
                           "each strategy at its own retirement "
                           "(default: 0.04, the paper's rule)")
  parser.add_argument("--financing-spread", type=float,
                      default=FINANCING_SPREAD,
                      help="annual spread above bills to finance "
                           "leverage (default: 0.003)")
  args = parser.parse_args()
  WITHDRAWAL_RATE = args.withdrawal_rate
  FINANCING_SPREAD = args.financing_spread

  rows = read_panel(args.panel)
  # SSA calibration: the distribution of the couple's age at death targets
  # Table III of the paper (mean 87.6 years, standard deviation 9.1).
  female = mortality_table("female", "ssa")
  male = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1

  print(f"Panel: {len(rows)} country-years ({rows[0]['year']}-{rows[-1]['year']})")
  print(f"Household: saves {SAVINGS_RATE:.0%} from 25 to 65, "
       f"{WITHDRAWAL_RATE:.0%} rule")
  print(f"Simulations: {args.runs}")
  print()

  names = list(STRATEGIES)
  rng = random.Random(args.seed)
  results: dict[str, list[dict[str, float]]] = {n: [] for n in names}

  pensions = None if args.no_social_security else household_benefit(INCOME)
  if pensions:
    print(f"Social Security: {pensions[0]:,.0f} per year for the couple, "
          f"{pensions[1]:,.0f} for the survivor".replace(",", " "))
    print()

  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block)
    female_death = draw_death_age(female, rng)
    male_death = draw_death_age(male, rng)
    first = min(female_death, male_death)
    last = max(female_death, male_death)
    for name in names:
      results[name].append(simulate(name, path, last, first, pensions))

  order = (list(PANEL_A) + list(PANEL_B) + list(PANEL_C) + list(PANEL_D)
           + list(PANEL_E))
  def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")

  def group_of(name: str) -> str:
    if name in PANEL_E:
      return "gold"
    if name in PANEL_D:
      return "added"
    return "paper"

  print("=" * 96)
  print("TABLE 1 -- PERFORMANCE (real dollars)")
  print("=" * 96)
  header = (f"{'strategy':<17}{'':>8}{'median wealth':>15}{'mean wealth':>15}"
           f"{'cons./yr':>12}{'median bequest':>16}")
  print(header)
  print("-" * len(header))
  previous = None
  for name in order:
    rows_ = results[name]
    if previous and group_of(name) != previous:
      print("-" * len(header))
    previous = group_of(name)
    median_wealth = statistics.median(r["retirement_wealth"] for r in rows_)
    mean_wealth = statistics.fmean(r["retirement_wealth"] for r in rows_)
    consumption = statistics.fmean(r["consumption"] for r in rows_)
    bequest = statistics.median(r["bequest"] for r in rows_)
    tag = "gold" if name in PANEL_E else ("added" if name in PANEL_D else "")
    print(f"{name:<17}{tag:>8}{money(median_wealth):>15}"
          f"{money(mean_wealth):>15}{money(consumption):>12}"
          f"{money(bequest):>16}")
  print()
  print("Reading: MEDIAN wealth is the statistic to use. The paper compares")
  print("  means, but on an annual panel the tails are too fat for a mean to be")
  print("  meaningful: forty-year growth of Stocks/I has a median of x10 and a")
  print("  mean of x140. 'cons./yr' includes the Social Security pension.")
  print()

  print("=" * 96)
  print("TABLE 2 -- RISK")
  print("=" * 96)
  header = (f"{'strategy':<17}{'':>8}{'vol':>9}{'ret/vol':>12}"
           f"{'ruin':>9}{'retire. DD':>14}")
  print(header)
  print("-" * len(header))
  previous = None
  for name in order:
    rows_ = results[name]
    if previous and group_of(name) != previous:
      print("-" * len(header))
    previous = group_of(name)
    vol = statistics.median(r["portfolio_vol"] for r in rows_)
    mean_return = statistics.median(r["portfolio_return"] for r in rows_)
    ratio = mean_return / vol if vol > 0 else 0.0
    ruin = sum(r["ruined"] for r in rows_) / len(rows_)
    dd = statistics.fmean(r["retirement_drawdown"] for r in rows_)
    tag = "gold" if name in PANEL_E else ("added" if name in PANEL_D else "")
    print(f"{name:<17}{tag:>8}{vol:>9.1%}{ratio:>12.2f}{ruin:>9.1%}"
          f"{dd:>14.1%}")
  print()
  print("Reading: 'vol' is the standard deviation of the annual returns ACTUALLY")
  print("  experienced by the household, not that of the target allocation -- a")
  print("  glide path holds stocks when young and bonds when old.")
  print("  'ret/vol' relates the return to this risk: this column answers the")
  print("  objection that the paper's strategies do not carry the same risk.")
  print("  'ruin' is the probability of exhausting capital before the death of")
  print("  the last survivor.")
  print()
  print("Rows marked 'added' are not in the paper. Their equity sleeve follows a")
  print("world index and their bond sleeve a sovereign basket, like listed")
  print("instruments; the paper's rows hold the assets of the country of")
  print("residence.")
  print()

  # Table X of the paper, Panel A, block bootstrap on the developed sample.
  PUBLISHED_RUIN = {
    "TDF": 0.169, "Balanced": 0.157, "Balanced/I": 0.109, "Age": 0.168,
    "Age/I": 0.133, "Bills": 0.357, "Stocks": 0.174, "Stocks/I": 0.082,
  }
  print("Ruin probability, the eight strategies of the paper (Table X):")
  print(f"{'strategy':<12}{'our JST':>12}{'paper':>10}{'diff.':>10}")
  print("-" * 44)
  for name in PUBLISHED_RUIN:
    ours = sum(r["ruined"] for r in results[name]) / len(results[name])
    published = PUBLISHED_RUIN[name]
    print(f"{name:<12}{ours:>11.1%}{published:>10.1%}{ours - published:>+10.1f}"
          .replace(f"{ours - published:>+10.1f}",
                   f"{(ours - published) * 100:>+9.1f}pt"))
  print()

  tdf_median = statistics.median(
    r["retirement_wealth"] for r in results["TDF"])
  print("Median wealth difference versus target-date fund (TDF):")
  for name in order:
    if name == "TDF":
      continue
    median = statistics.median(r["retirement_wealth"] for r in results[name])
    reference = "   (paper: +30%)" if name == "Stocks" else (
      "   (paper: +32%)" if name == "Stocks/I" else "")
    print(f"  {name:<17}{median / tdf_median - 1:>+8.1%}{reference}")


if __name__ == "__main__":
  main()
