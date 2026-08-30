"""Decompose l'ecart de ruine entre actions domestiques et Stocks/I.

Trois portefeuilles sont simules sur les memes trajectoires et avec les memes
deces :

1. 100 % actions domestiques ;
2. 50 % domestiques / 50 % internationales, a change reel constant ;
3. 50 % domestiques / 50 % internationales, change observe (Stocks/I).

Le passage 1 -> 2 mesure l'effet de diversification geographique dans ce
contrefactuel. Le passage 2 -> 3 mesure l'effet supplementaire des variations
de change. La decomposition est exacte pour l'ordre retenu, mais le scenario a
change reel constant n'est pas une strategie couverte investissable : ni carry
de couverture, ni cout de transaction ne sont inclus.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import statistics
import sys
from collections.abc import Callable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mortality import table as mortality_table  # noqa: E402
from replicate_cederburg import (  # noqa: E402
  INCOME,
  MAX_AGE,
  RETIRE_AGE,
  SAVINGS_RATE,
  START_AGE,
  block_bootstrap,
  draw_death_age,
)


ReturnFunction = Callable[[dict[str, float]], float]

DOMESTIC = "Domestique"
CONSTANT_FX = "International, change reel constant"
OBSERVED_FX = "International, change observe"


def read_panel(path: str) -> list[dict[str, float]]:
  rows: list[dict[str, float]] = []
  with open(path, newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    required = {
      "country", "year", "domestic_equity_real",
      "international_equity_real",
      "international_equity_real_constant_real_fx",
    }
    missing = required.difference(reader.fieldnames or ())
    if missing:
      raise ValueError(
        "Colonnes absentes du panel : " + ", ".join(sorted(missing))
        + ". Reconstruire international-equity.csv puis replication-panel.csv."
      )
    for row in reader:
      rows.append({
        "country": row["country"],
        "year": int(row["year"]),
        "domestic": float(row["domestic_equity_real"]),
        "international": float(row["international_equity_real"]),
        "international_constant_real_fx": float(
          row["international_equity_real_constant_real_fx"]),
        "inflation": float(row["inflation"]),
      })
  rows.sort(key=lambda row: (row["country"], row["year"]))
  return rows


def return_functions() -> dict[str, ReturnFunction]:
  return {
    DOMESTIC: lambda row: row["domestic"],
    CONSTANT_FX: lambda row: 0.5 * (
      row["domestic"] + row["international_constant_real_fx"]),
    OBSERVED_FX: lambda row: 0.5 * (
      row["domestic"] + row["international"]),
  }


def covariance(left: list[float], right: list[float]) -> float:
  if len(left) != len(right) or len(left) < 2:
    raise ValueError("La covariance demande deux series alignees")
  mean_left = statistics.fmean(left)
  mean_right = statistics.fmean(right)
  return sum((x - mean_left) * (y - mean_right)
             for x, y in zip(left, right)) / (len(left) - 1)


def correlation(left: list[float], right: list[float]) -> float:
  denominator = statistics.stdev(left) * statistics.stdev(right)
  if denominator == 0.0:
    return math.nan
  return covariance(left, right) / denominator


def simulate_ruin(path: list[dict[str, float]], last_death: int,
                  return_function: ReturnFunction,
                  withdrawal_rate: float) -> bool:
  """Reprend exactement la convention de ``replicate_cederburg.simulate``."""
  wealth = 0.0
  for index in range(RETIRE_AGE - START_AGE):
    wealth += INCOME * SAVINGS_RATE
    wealth *= 1.0 + return_function(path[index])

  withdrawal = wealth * withdrawal_rate
  for index, _age in enumerate(range(RETIRE_AGE, last_death + 1),
                               start=RETIRE_AGE - START_AGE):
    if index >= len(path):
      break
    served = min(wealth, withdrawal)
    if served < withdrawal - 0.005:
      return True
    wealth = max(0.0, wealth - served)
    wealth *= 1.0 + return_function(path[index])
  return False


def parse_rates(value: str) -> list[float]:
  try:
    rates = [float(item.strip()) for item in value.split(",") if item.strip()]
  except ValueError as error:
    raise argparse.ArgumentTypeError(
      "les taux doivent etre des nombres separes par des virgules") from error
  if not rates or any(rate <= 0.0 or rate >= 1.0 for rate in rates):
    raise argparse.ArgumentTypeError("chaque taux doit etre compris entre 0 et 1")
  return sorted(set(rates))


def paired_difference(left: list[bool], right: list[bool],
                      ) -> tuple[float, float, float]:
  """P(right) - P(left), avec IC normal apparie a 95 %."""
  differences = [float(right_value) - float(left_value)
                 for left_value, right_value in zip(left, right)]
  estimate = statistics.fmean(differences)
  if len(differences) < 2:
    return estimate, math.nan, math.nan
  margin = 1.959963984540054 * statistics.stdev(differences) / math.sqrt(
    len(differences))
  return estimate, estimate - margin, estimate + margin


def describe_returns(rows: list[dict[str, float]],
                     functions: dict[str, ReturnFunction]) -> None:
  pooled = {name: [function(row) for row in rows]
            for name, function in functions.items()}
  domestic = [row["domestic"] for row in rows]
  print("Rendements reels annuels du panel :")
  print(f"{'portefeuille':<38}{'moyenne':>11}{'volatilite':>13}"
        f"{'corr. domestique':>19}")
  print("-" * 81)
  for name, values in pooled.items():
    print(f"{name:<38}{statistics.fmean(values):>11.2%}"
          f"{statistics.stdev(values):>13.2%}"
          f"{correlation(domestic, values):>19.2f}")
  print()

  fx_contribution = [
    0.5 * (row["international"] - row["international_constant_real_fx"])
    for row in rows
  ]
  cutoff = sorted(domestic)[max(0, math.ceil(0.10 * len(domestic)) - 1)]
  crash_fx = [effect for effect, value in zip(fx_contribution, domestic)
              if value <= cutoff]
  inflation_fx = [effect for effect, row in zip(fx_contribution, rows)
                  if row["inflation"] >= 0.10]
  print("Diagnostic de protection du change (contribution au 50/50) :")
  print(f"  correlation avec les actions domestiques : "
        f"{correlation(domestic, fx_contribution):+.2f}")
  print(f"  contribution moyenne, toutes observations : "
        f"{statistics.fmean(fx_contribution):+.2%}")
  print(f"  dans les 10 % pires observations domestiques ({len(crash_fx)} obs.) : "
        f"{statistics.fmean(crash_fx):+.2%}")
  if inflation_fx:
    print(f"  quand l'inflation domestique depasse 10 % ({len(inflation_fx)} obs.) : "
          f"{statistics.fmean(inflation_fx):+.2%}")
  print()


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=1.0,
                      help="longueur moyenne des blocs en annees ; 1 pour IID")
  parser.add_argument("--withdrawal-rates", type=parse_rates,
                      default=parse_rates("0.03,0.04,0.05,0.06"),
                      help="taux separes par des virgules (defaut : 0.03,...,0.06)")
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  args = parser.parse_args()
  if args.runs < 2:
    parser.error("--runs doit etre au moins egal a 2")
  if args.mean_block <= 0.0:
    parser.error("--mean-block doit etre strictement positif")

  rows = read_panel(args.panel)
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  if len(rows) < 2:
    raise ValueError("La fenetre demandee ne contient pas assez de donnees")

  functions = return_functions()
  print(f"Panel : {len(rows)} pays-annees ({min(row['year'] for row in rows)}-"
        f"{max(row['year'] for row in rows)})")
  print(f"Bootstrap : blocs moyens de {args.mean_block:g} an(s), "
        f"{args.runs} trajectoires appariees")
  print("Change reel constant : change nominal et ecart d'inflation neutralises; "
        "hors carry et cout de couverture.")
  print()
  describe_returns(rows, functions)

  female = mortality_table("female", "ssa")
  male = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)
  results = {
    rate: {name: [] for name in functions} for rate in args.withdrawal_rates
  }

  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block)
    last_death = max(draw_death_age(female, rng), draw_death_age(male, rng))
    for rate in args.withdrawal_rates:
      for name, function in functions.items():
        results[rate][name].append(
          simulate_ruin(path, last_death, function, rate))

  print("Decomposition de la probabilite de ruine :")
  print(f"{'retrait':>8}{'domestique':>13}{'intl. chg reel cst':>19}"
        f"{'intl. observe':>16}{'diversification':>17}{'change':>10}"
        f"{'total':>10}")
  print("-" * 93)
  for rate in args.withdrawal_rates:
    domestic = results[rate][DOMESTIC]
    constant = results[rate][CONSTANT_FX]
    observed = results[rate][OBSERVED_FX]
    domestic_probability = statistics.fmean(domestic)
    constant_probability = statistics.fmean(constant)
    observed_probability = statistics.fmean(observed)
    geography = constant_probability - domestic_probability
    currency = observed_probability - constant_probability
    total = observed_probability - domestic_probability
    print(f"{rate:>8.1%}{domestic_probability:>13.2%}"
          f"{constant_probability:>19.2%}{observed_probability:>16.2%}"
          f"{geography:>+16.2%}{currency:>+10.2%}{total:>+10.2%}")
  print("  Une variation negative reduit la probabilite de ruine.")
  print()

  focus_rate = min(args.withdrawal_rates, key=lambda rate: abs(rate - 0.04))
  domestic = results[focus_rate][DOMESTIC]
  constant = results[focus_rate][CONSTANT_FX]
  observed = results[focus_rate][OBSERVED_FX]
  geography = paired_difference(domestic, constant)
  currency = paired_difference(constant, observed)
  total = paired_difference(domestic, observed)

  def transition(left: list[bool], right: list[bool]) -> tuple[float, float]:
    saved = sum(left_value and not right_value
                for left_value, right_value in zip(left, right)) / len(left)
    harmed = sum(not left_value and right_value
                 for left_value, right_value in zip(left, right)) / len(left)
    return saved, harmed

  geography_saved, geography_harmed = transition(domestic, constant)
  currency_saved, currency_harmed = transition(constant, observed)
  print(f"Comparaisons appariees au taux de retrait {focus_rate:.1%} :")
  print(f"  diversification : evite {geography_saved:.2%} des ruines, en cree "
        f"{geography_harmed:.2%}; effet net {geography[0]:+.2%} "
        f"[IC 95 % {geography[1]:+.2%}; {geography[2]:+.2%}]")
  print(f"  change          : evite {currency_saved:.2%} des ruines, en cree "
        f"{currency_harmed:.2%}; effet net {currency[0]:+.2%} "
        f"[IC 95 % {currency[1]:+.2%}; {currency[2]:+.2%}]")
  print(f"  effet total     : {total[0]:+.2%} "
        f"[IC 95 % {total[1]:+.2%}; {total[2]:+.2%}]")


if __name__ == "__main__":
  main()
