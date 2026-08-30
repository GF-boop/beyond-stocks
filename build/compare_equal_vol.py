"""Compare Stocks/I a un 60/40 mondial avec et sans ciblage de volatilite.

Le benchmark conserve exactement la convention de Cederburg : 50 % d'actions
du pays tire et 50 % d'actions internationales. Les portefeuilles diversifies
utilisent, eux, les series mondiales du panel : indice actions pondere par
capitalisation, panier d'obligations souveraines et taux court de financement.

Le levier du portefeuille a volatilite ciblee est estime une seule fois sur le
panel passe en argument. Il resout :

  vol[bill + L * (60 % actions + 40 % obligations - bill)] = vol[Stocks/I]

Le spread de financement est un cout constant annuel sur L - 1 ; il modifie le
rendement mais pas la volatilite historique utilisee pour le calibrage.
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

from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
  INCOME,
  MAX_AGE,
  RETIRE_AGE,
  SAVINGS_RATE,
  START_AGE,
  block_bootstrap,
  read_panel,
)


ReturnFunction = Callable[[dict[str, float]], float]


def covariance(left: list[float], right: list[float]) -> float:
  if len(left) != len(right) or len(left) < 2:
    raise ValueError("La covariance demande deux series alignees")
  left_mean = statistics.fmean(left)
  right_mean = statistics.fmean(right)
  return sum((x - left_mean) * (y - right_mean)
             for x, y in zip(left, right)) / (len(left) - 1)


def solve_leverage(target: list[float], bills: list[float],
                   excess: list[float]) -> float:
  """Levier positif qui egale la volatilite d'une serie cible."""
  # Var(b + Lx) = Var(cible), soit une equation quadratique en L.
  a = statistics.variance(excess)
  b = 2.0 * covariance(bills, excess)
  c = statistics.variance(bills) - statistics.variance(target)
  discriminant = b * b - 4.0 * a * c
  if a <= 0.0 or discriminant < 0.0:
    raise ValueError("Impossible de calibrer un levier reel positif")
  roots = ((-b + math.sqrt(discriminant)) / (2.0 * a),
           (-b - math.sqrt(discriminant)) / (2.0 * a))
  positive = [root for root in roots if root > 0.0]
  if not positive:
    raise ValueError("Le calibrage ne produit aucun levier positif")
  return max(positive)


def returns(spread: float, world_leverage: float, local_leverage: float,
            ) -> dict[str, ReturnFunction]:
  def stocks_i(row: dict[str, float]) -> float:
    return 0.5 * (row["domestic"] + row["international"])

  def world(row: dict[str, float]) -> float:
    return row["world_equity"]

  def world_diversified(leverage: float) -> ReturnFunction:
    def calculate(row: dict[str, float]) -> float:
      base_excess = (0.6 * row["world_equity"]
                     + 0.4 * row["world_bond"]
                     - row["world_bill"])
      return (row["world_bill"] + leverage * base_excess
              - max(0.0, leverage - 1.0) * spread)
    return calculate

  def local_diversified(leverage: float) -> ReturnFunction:
    def calculate(row: dict[str, float]) -> float:
      equity = 0.5 * (row["domestic"] + row["international"])
      base_excess = (0.6 * equity + 0.4 * row["bond"] - row["bill"])
      return (row["bill"] + leverage * base_excess
              - max(0.0, leverage - 1.0) * spread)
    return calculate

  return {
    "Stocks/I": stocks_i,
    "World": world,
    "90/60 local": local_diversified(1.5),
    "60/40 local VC": local_diversified(local_leverage),
    "90/60 mondial": world_diversified(1.5),
    "60/40 mondial VC": world_diversified(world_leverage),
  }


def draw_death_age(survival: dict[int, float], rng: random.Random) -> int:
  age = START_AGE
  while age < MAX_AGE:
    if rng.random() > survival.get(age, 0.5):
      return age
    age += 1
  return MAX_AGE


def simulate(path: list[dict[str, float]], last_death: int,
             return_function: ReturnFunction,
             withdrawal_rate: float) -> dict[str, float | bool]:
  wealth = 0.0
  traversed_returns: list[float] = []
  for index in range(RETIRE_AGE - START_AGE):
    growth = return_function(path[index])
    traversed_returns.append(growth)
    wealth = (wealth + INCOME * SAVINGS_RATE) * (1.0 + growth)

  retirement_wealth = wealth
  withdrawal = retirement_wealth * withdrawal_rate
  ruin = False
  consumption = 0.0
  for index, _age in enumerate(range(RETIRE_AGE, last_death + 1),
                               start=RETIRE_AGE - START_AGE):
    if index >= len(path):
      break
    served = min(wealth, withdrawal)
    if served < withdrawal - 0.005:
      ruin = True
    consumption += served
    wealth = max(0.0, wealth - served)
    growth = return_function(path[index])
    traversed_returns.append(growth)
    wealth *= 1.0 + growth

  return {
    "retirement_wealth": retirement_wealth,
    "consumption": consumption,
    "ruined": ruin,
    "bequest": wealth,
    "volatility": statistics.stdev(traversed_returns),
  }


def probability_interval(successes: int, total: int) -> tuple[float, float]:
  """Intervalle de Wilson a 95 % pour une proportion."""
  z = 1.959963984540054
  proportion = successes / total
  denominator = 1.0 + z * z / total
  center = (proportion + z * z / (2.0 * total)) / denominator
  margin = z * math.sqrt(
    proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
  ) / denominator
  return center - margin, center + margin


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=50_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=1.0)
  parser.add_argument("--spread", type=float, default=0.003,
                      help="spread annuel au-dessus du taux court")
  parser.add_argument("--withdrawal-rate", type=float, default=0.04)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  args = parser.parse_args()

  rows = read_panel(args.panel)
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  if len(rows) < 2:
    raise ValueError("La fenetre demandee ne contient pas assez de donnees")

  target = [0.5 * (row["domestic"] + row["international"]) for row in rows]
  local_bills = [row["bill"] for row in rows]
  local_excess = [
    0.6 * target[index] + 0.4 * row["bond"] - row["bill"]
    for index, row in enumerate(rows)
  ]
  world_bills = [row["world_bill"] for row in rows]
  world_excess = [
    0.6 * row["world_equity"] + 0.4 * row["world_bond"] - row["world_bill"]
    for row in rows
  ]
  local_matched = solve_leverage(target, local_bills, local_excess)
  world_matched = solve_leverage(target, world_bills, world_excess)
  functions = returns(args.spread, world_matched, local_matched)
  pooled = {name: [function(row) for row in rows]
            for name, function in functions.items()}

  print(f"Panel : {len(rows)} pays-annees ({min(r['year'] for r in rows)}-"
        f"{max(r['year'] for r in rows)})")
  print(f"Bootstrap : blocs moyens de {args.mean_block:g} an(s), "
        f"{args.runs} trajectoires, spread {args.spread:.2%}")
  print(f"Vol-cible locale   : {local_matched:.3f}x = "
        f"{0.6 * local_matched:.1%} actions + "
        f"{0.4 * local_matched:.1%} obligations")
  print(f"Vol-cible mondiale : {world_matched:.3f}x = "
        f"{0.6 * world_matched:.1%} actions + "
        f"{0.4 * world_matched:.1%} obligations")
  print()
  print(f"{'strategie':<18}{'rendement':>12}{'volatilite':>13}")
  print("-" * 43)
  for name, values in pooled.items():
    print(f"{name:<18}{statistics.fmean(values):>12.2%}"
          f"{statistics.stdev(values):>13.2%}")
  print()

  female = mortality_table("female", "ssa")
  male = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)
  results: dict[str, list[dict[str, float | bool]]] = {
    name: [] for name in functions
  }
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block)
    female_death = draw_death_age(female, rng)
    male_death = draw_death_age(male, rng)
    last_death = max(female_death, male_death)
    for name, function in functions.items():
      results[name].append(simulate(path, last_death, function,
                                    args.withdrawal_rate))

  print(f"{'strategie':<18}{'richesse med.':>16}{'heritage med.':>16}"
        f"{'ruine':>9}{'vol med.':>11}")
  print("-" * 70)
  for name, values in results.items():
    retirement = statistics.median(
      float(value["retirement_wealth"]) for value in values)
    bequest = statistics.median(float(value["bequest"]) for value in values)
    ruin = sum(bool(value["ruined"]) for value in values) / len(values)
    volatility = statistics.median(
      float(value["volatility"]) for value in values)
    print(f"{name:<18}{retirement:>16,.0f}{bequest:>16,.0f}{ruin:>9.2%}"
          f"{volatility:>11.2%}".replace(",", " "))
  print()

  benchmark = results["Stocks/I"]
  print("Victoires appariees face a Stocks/I (intervalle de Wilson a 95 %) :")
  print(f"{'strategie':<18}{'a 65 ans':>24}{'heritage':>24}")
  print("-" * 66)
  for name in ("World", "90/60 local", "60/40 local VC",
               "90/60 mondial", "60/40 mondial VC"):
    values = results[name]
    wealth_wins = sum(
      float(value["retirement_wealth"]) > float(reference["retirement_wealth"])
      for value, reference in zip(values, benchmark)
    )
    bequest_wins = sum(
      float(value["bequest"]) > float(reference["bequest"])
      for value, reference in zip(values, benchmark)
    )
    wealth_ci = probability_interval(wealth_wins, args.runs)
    bequest_ci = probability_interval(bequest_wins, args.runs)
    wealth = wealth_wins / args.runs
    bequest = bequest_wins / args.runs
    print(f"{name:<18}{wealth:>9.2%} [{wealth_ci[0]:.2%}; {wealth_ci[1]:.2%}]"
          f"{bequest:>9.2%} [{bequest_ci[0]:.2%}; {bequest_ci[1]:.2%}]")


if __name__ == "__main__":
  main()
