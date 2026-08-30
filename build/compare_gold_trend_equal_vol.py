"""Ajoute or et managed futures au 60/40, a volatilite egale a Stocks/I.

Les quatre formes de portefeuille risqué totalisent 100 % avant calibrage :

- 60 % actions / 40 % obligations ;
- 60 % actions / 30 % obligations / 10 % or ;
- 60 % actions / 30 % obligations / 10 % managed futures ;
- 60 % actions / 20 % obligations / 10 % or / 10 % managed futures.

Chaque forme est ensuite multipliee par le levier qui egale exactement la
volatilite historique du panier Cederburg 50 % local / 50 % international.
L'or est deja net de ses frais de garde dans le panel. La tendance est rendue
nette des frais, couts de transaction et d'un haircut prospectif optionnel.
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
# Frais et cout de transaction du proxy MF : le cout est derive du turnover
# mesure sur la serie mensuelle, jamais recopie en dur (voir trend_costs.py).
from trend_costs import (  # noqa: E402
  DEFAULT_TREND_COST, DEFAULT_TREND_FEE,
)

from compare_equal_vol import (  # noqa: E402
  draw_death_age,
  probability_interval,
  simulate,
  solve_leverage,
)
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  START_AGE,
  block_bootstrap,
  read_panel,
)


ReturnFunction = Callable[[dict[str, float]], float]

SHAPES: dict[str, tuple[float, float, float, float]] = {
  "60/40": (0.60, 0.40, 0.00, 0.00),
  "60/30/10 or": (0.60, 0.30, 0.10, 0.00),
  "60/30/10 MF": (0.60, 0.30, 0.00, 0.10),
  "60/20/10 or+MF": (0.60, 0.20, 0.10, 0.10),
}


def trend_returns(rows: list[dict[str, float]], fee: float, cost: float,
                  haircut: float, volatility_multiplier: float,
                  ) -> list[float]:
  net = [
    (1.0 + row["trend"]) * (1.0 - fee) - 1.0 - cost - haircut
    for row in rows
  ]
  mean = statistics.fmean(net)
  return [mean + volatility_multiplier * (value - mean) for value in net]


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=50_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=1.0)
  parser.add_argument("--spread", type=float, default=0.003)
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--trend-haircut", type=float, default=0.0)
  parser.add_argument("--trend-vol-multiplier", type=float, default=1.0)
  parser.add_argument("--withdrawal-rate", type=float, default=0.04)
  args = parser.parse_args()

  rows = read_panel(args.panel)
  target = [0.5 * (row["domestic"] + row["international"]) for row in rows]
  bills = [row["world_bill"] for row in rows]
  trends = trend_returns(rows, args.trend_fee, args.trend_cost,
                         args.trend_haircut, args.trend_vol_multiplier)

  leverages: dict[str, float] = {}
  functions: dict[str, ReturnFunction] = {
    "Stocks/I": lambda row: 0.5 * (row["domestic"] + row["international"]),
  }

  # Le rendement de tendance stresse est indexe par l'identite de la ligne.
  trend_by_row = {id(row): value for row, value in zip(rows, trends)}
  for name, (equity, bond, gold, trend) in SHAPES.items():
    risky = [
      equity * row["world_equity"] + bond * row["world_bond"]
      + gold * row["gold"] + trend * trends[index]
      for index, row in enumerate(rows)
    ]
    excess = [risky[index] - bills[index] for index in range(len(rows))]
    leverage = solve_leverage(target, bills, excess)
    leverages[name] = leverage

    def calculate(row: dict[str, float], *, weights=(equity, bond, gold, trend),
                  level=leverage) -> float:
      e, b, g, t = weights
      risky_return = (e * row["world_equity"] + b * row["world_bond"]
                      + g * row["gold"] + t * trend_by_row[id(row)])
      excess_return = risky_return - row["world_bill"]
      return (row["world_bill"] + level * excess_return
              - max(0.0, level - 1.0) * args.spread)

    functions[name] = calculate

  print(f"Panel : {len(rows)} pays-annees ({rows[0]['year']}-{rows[-1]['year']})")
  print(f"Bootstrap : blocs moyens de {args.mean_block:g} an(s), "
        f"{args.runs} trajectoires, spread {args.spread:.2%}")
  print(f"Managed futures : frais {args.trend_fee:.2%}, couts "
        f"{args.trend_cost:.2%}, haircut {args.trend_haircut:.2%}, "
        f"vol x{args.trend_vol_multiplier:.2f}")
  print()
  print(f"{'strategie':<20}{'levier':>8}{'expositions a vol egale':>42}")
  print("-" * 70)
  for name, weights in SHAPES.items():
    level = leverages[name]
    exposures = [level * weight for weight in weights]
    labels = ("A", "O", "Or", "MF")
    shown = " ".join(f"{label} {value:.1%}" for label, value in zip(labels, exposures)
                     if value > 0.0)
    print(f"{name:<20}{level:>7.3f}x{shown:>42}")
  print()

  pooled = {name: [function(row) for row in rows]
            for name, function in functions.items()}
  print(f"{'strategie':<20}{'rendement':>12}{'volatilite':>13}")
  print("-" * 45)
  for name, values in pooled.items():
    print(f"{name:<20}{statistics.fmean(values):>12.2%}"
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
    last_death = max(draw_death_age(female, rng), draw_death_age(male, rng))
    for name, function in functions.items():
      results[name].append(simulate(path, last_death, function,
                                    args.withdrawal_rate))

  print(f"{'strategie':<20}{'richesse med.':>16}{'heritage med.':>16}"
        f"{'ruine':>9}{'gagne a 65':>13}{'gagne heritage':>16}")
  print("-" * 90)
  benchmark = results["Stocks/I"]
  for name, values in results.items():
    retirement = statistics.median(
      float(value["retirement_wealth"]) for value in values)
    bequest = statistics.median(float(value["bequest"]) for value in values)
    ruin = sum(bool(value["ruined"]) for value in values) / len(values)
    if name == "Stocks/I":
      wealth_text = bequest_text = "reference"
    else:
      wealth_wins = sum(
        float(value["retirement_wealth"]) > float(ref["retirement_wealth"])
        for value, ref in zip(values, benchmark)
      )
      bequest_wins = sum(
        float(value["bequest"]) > float(ref["bequest"])
        for value, ref in zip(values, benchmark)
      )
      wealth_ci = probability_interval(wealth_wins, args.runs)
      bequest_ci = probability_interval(bequest_wins, args.runs)
      wealth_text = f"{wealth_wins / args.runs:.1%}"
      bequest_text = f"{bequest_wins / args.runs:.1%}"
      # Les intervalles sont imprimes sous la table pour ne pas l'elargir.
      print_ci = (name, wealth_ci, bequest_ci)
    print(f"{name:<20}{retirement:>16,.0f}{bequest:>16,.0f}{ruin:>9.2%}"
          f"{wealth_text:>13}{bequest_text:>16}".replace(",", " "))
    if name != "Stocks/I":
      _, wealth_ci, bequest_ci = print_ci
      print(f"  IC95 victoires : retraite [{wealth_ci[0]:.1%}; {wealth_ci[1]:.1%}], "
            f"heritage [{bequest_ci[0]:.1%}; {bequest_ci[1]:.1%}]")


if __name__ == "__main__":
  main()
