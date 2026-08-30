"""Audit : 60/40 mondial + 33,33 % managed futures, couvert contre non couvert.

Meme portefeuille, meme levier implicite, memes trajectoires appariees. Seule
la poche managed futures change de traitement de change :

* couvert : `trend_real`, rendement USD ramene en devise du resident sous
  parite couverte des taux (le collateral cash US est remplace par le bill du
  resident) ;
* non couvert : `trend_real_unhedged`, rendement USD converti au comptant, le
  detenteur portant le risque de change sur toute la position.

L'or et les actions sont deja non couverts dans les deux cas. Le bloc
obligataire mondial reste couvert dans les deux cas : on isole le seul effet du
change sur la brique managed futures.

Sortie : utilite CRRA, taux d'epargne equivalent au 33/67, richesse mediane a
65 ans, consommation moyenne de retraite, probabilite de ruine, legs median, et
la difference de ruine appariee avec son intervalle de Monte-Carlo.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
from collections.abc import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_lifecycle_utility import (  # noqa: E402
  BASE_SAVINGS_RATE,
  GAMMA,
  WITHDRAWAL_RATE,
  build_scenario,
  draw_death_age,
  equivalent_savings_rate,
  evaluate,
  expected_utility,
)
from income_process import draw_household_income  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  START_AGE,
  TREND_DRAG,
  TREND_FEE,
  block_bootstrap,
  read_panel,
)

# Poids fixes du portefeuille compare. 60 % actions mondiales, 40 % obligations
# mondiales, 33,33 % managed futures : somme des sleeves 133,33 %, donc 33,33 %
# d'exposition a financer.
EQUITY_WEIGHT = 0.60
BOND_WEIGHT = 0.40
MF_WEIGHT = 1.0 / 3.0
GROSS = EQUITY_WEIGHT + BOND_WEIGHT + MF_WEIGHT
LEVERAGE = max(0.0, GROSS - 1.0)


def net_trend(raw: float) -> float:
  """Managed futures apres frais de gestion et cout de replication."""
  return (1.0 + raw) * (1.0 - TREND_FEE) - 1.0 - TREND_DRAG


def make_functions(spread: float) -> dict[str, Callable[[dict[str, float]], float]]:
  """Trois strategies sur le meme panel converti au numeraire du resident."""

  def benchmark_3367(row: dict[str, float]) -> float:
    return 0.33 * row["domestic"] + 0.67 * row["international"]

  def mf_portfolio(row: dict[str, float], *, hedged: bool) -> float:
    trend_raw = row["trend"] if hedged else row["trend_unhedged"]
    financing = LEVERAGE * (row["world_bill"] + spread)
    return (EQUITY_WEIGHT * row["world_equity"]
            + BOND_WEIGHT * row["world_bond"]
            + MF_WEIGHT * net_trend(trend_raw)
            - financing)

  return {
    "ACO 33/67": benchmark_3367,
    "60/40W + 33 MF, hedged": lambda row: mf_portfolio(row, hedged=True),
    "60/40W + 33 MF, unhedged": lambda row: mf_portfolio(row, hedged=False),
  }


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=10.0)
  parser.add_argument("--spread", type=float, default=0.003)
  parser.add_argument("--withdrawal-rate", type=float, default=WITHDRAWAL_RATE)
  parser.add_argument("--gamma", type=float, default=GAMMA)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  args = parser.parse_args()

  rows = read_panel(args.panel)
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  if len(rows) < 2:
    raise ValueError("Fenetre trop courte")

  functions = make_functions(args.spread)
  names = list(functions)

  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)

  scenarios = []
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block)
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, _ = draw_household_income(rng)
    scenarios.append(build_scenario(
      path, functions, female_death, male_death,
      female_income, male_income))

  window = (f"{min(r['year'] for r in rows)}-{max(r['year'] for r in rows)}")
  print(f"Panel : {len(rows)} pays-annees ({window})")
  print(f"Simulation : {args.runs} trajectoires appariees, blocs moyens de "
        f"{args.mean_block:g} an(s), spread {args.spread:.2%}")
  print(f"Portefeuille : {EQUITY_WEIGHT:.0%} actions mondiales / "
        f"{BOND_WEIGHT:.0%} obligations mondiales couvertes / "
        f"{MF_WEIGHT:.1%} MF ; brut {GROSS:.1%}, financement {LEVERAGE:.1%}")
  print()

  target = expected_utility(
    scenarios, "ACO 33/67", BASE_SAVINGS_RATE, args.gamma,
    args.withdrawal_rate)

  header = (f"{'strategie':<28}{'E[U] x1e16':>13}{'epargne eq.':>13}"
            f"{'rich. med. 65':>15}{'conso moy.':>13}{'ruine':>9}"
            f"{'legs med.':>14}")
  print(header)
  print("-" * len(header))

  ruin_flags: dict[str, list[float]] = {}
  for name in names:
    outcomes = [evaluate(scenario, name, BASE_SAVINGS_RATE,
                         args.withdrawal_rate, args.gamma)
                for scenario in scenarios]
    utility = statistics.fmean(o.utility for o in outcomes)
    equivalent = equivalent_savings_rate(
      scenarios, name, target, args.gamma, args.withdrawal_rate)
    wealth = statistics.median(o.retirement_wealth for o in outcomes)
    consumption = statistics.fmean(o.retirement_consumption for o in outcomes)
    ruin = statistics.fmean(1.0 if o.ruined else 0.0 for o in outcomes)
    bequest = statistics.median(o.bequest for o in outcomes)
    ruin_flags[name] = [1.0 if o.ruined else 0.0 for o in outcomes]
    equivalent_text = "n/a" if math.isnan(equivalent) else f"{equivalent:.2%}"
    print(f"{name:<28}{utility * 1e16:>13.4f}{equivalent_text:>13}"
          f"{wealth:>15,.0f}{consumption:>13,.0f}{ruin:>9.2%}"
          f"{bequest:>14,.0f}".replace(",", " "))

  print()
  hedged = ruin_flags["60/40W + 33 MF, hedged"]
  unhedged = ruin_flags["60/40W + 33 MF, unhedged"]
  bench = ruin_flags["ACO 33/67"]

  def paired_gap(a: list[float], b: list[float]) -> tuple[float, float, float]:
    diff = [x - y for x, y in zip(a, b)]
    mean = statistics.fmean(diff)
    half = 1.96 * statistics.pstdev(diff) / math.sqrt(len(diff))
    return mean * 100, (mean - half) * 100, (mean + half) * 100

  for label, series in (("hedged", hedged), ("unhedged", unhedged)):
    mean, low, high = paired_gap(series, bench)
    print(f"ruine {label} - 33/67 : {mean:+.2f} pt "
          f"(IC 95 % [{low:+.2f}, {high:+.2f}])")
  mean, low, high = paired_gap(unhedged, hedged)
  print(f"ruine unhedged - hedged : {mean:+.2f} pt "
        f"(IC 95 % [{low:+.2f}, {high:+.2f}])")


if __name__ == "__main__":
  main()
