"""Compare le bootstrap ACO sous plusieurs numeraires fixes.

Les blocs pays-annee restent ceux du panel historique integral par defaut. Chaque etat est
reexprime dans le pouvoir d'achat du pays cible, sans transformer la poche
``domestic`` en veritable action domestique de ce pays. C'est donc un diagnostic
de numeraire, pas une simulation litterale d'un menage americain, allemand ou
japonais.

Les pays cibles sont volontairement des pays disposant d'une longue histoire
monetaire dans le panel. ``Germany`` ne pretend pas reconstruire l'euro avant
1999 : il represente le numeraire allemand observe.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_fixed_stacked_utility import fixed_numeraire_rows  # noqa: E402
from compare_lifecycle_utility import (  # noqa: E402
  BASE_SAVINGS_RATE,
  GAMMA,
  WITHDRAWAL_RATE,
  build_scenario,
  draw_death_age,
  evaluate,
)
from income_process import draw_household_income  # noqa: E402
from investability import exclusion_reason as investability_reason  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  START_AGE,
  block_bootstrap,
  read_panel,
)


DEFAULT_TARGETS = ("USA", "Germany", "Japan")
STRATEGY = "ACO 33/67"


def aco_return(row: dict[str, float]) -> float:
  return 0.33 * row["domestic"] + 0.67 * row["international"]


def _moments(rows: list[dict[str, float]]) -> dict[str, float]:
  values = [aco_return(row) for row in rows]
  return {
    "mean_return": statistics.fmean(values),
    "volatility": statistics.stdev(values),
  }


def _common_rows(
    rows: list[dict[str, float]], targets: tuple[str, ...],
) -> tuple[list[dict[str, float]], dict[str, list[dict[str, float]]]]:
  """Retourne des panneaux strictement apparies par etat pays-annee."""
  converted = {
    target: fixed_numeraire_rows(rows, target) for target in targets
  }
  common_keys = set.intersection(*(
    {(row["country"], row["year"]) for row in panel}
    for panel in converted.values()
  ))
  resident = [row for row in rows
              if (row["country"], row["year"]) in common_keys]
  by_target = {}
  for target, panel in converted.items():
    mapped = {(row["country"], row["year"]): row for row in panel}
    by_target[target] = [mapped[(row["country"], row["year"])]
                         for row in resident]
  return resident, by_target


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS,
                      help="pays dont le numeraire reste fixe")
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=10.0)
  parser.add_argument(
    "--sample-mode", choices=("full", "investable"), default="full",
    help=("full (defaut) conserve tous les pays-annees ; investable applique "
          "le filtre de negociabilite comme sensibilite"))
  parser.add_argument("--output-json")
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre strictement positif")
  targets = tuple(args.targets)
  if len(set(targets)) != len(targets):
    raise ValueError("Chaque pays cible doit apparaitre une seule fois")

  source_rows = read_panel(args.panel)
  if args.sample_mode == "investable":
    source_rows = [
      row for row in source_rows
      if investability_reason(row["country"], row["year"], row["inflation"])
      is None
    ]
  resident_rows, fixed_rows = _common_rows(source_rows, targets)
  if len(resident_rows) < 2:
    raise ValueError("Le sous-echantillon commun est vide")

  panels = {"resident": resident_rows, **fixed_rows}
  panel_by_key = {
    name: {(row["country"], row["year"]): row for row in panel}
    for name, panel in panels.items()
  }
  functions = {STRATEGY: aco_return}
  ruined = {name: [] for name in panels}
  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)

  for _ in range(args.runs):
    source_path = block_bootstrap(resident_rows, horizon, rng, args.mean_block)
    keys = [(row["country"], row["year"]) for row in source_path]
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, _ = draw_household_income(rng)
    for name, mapping in panel_by_key.items():
      path = [mapping[key] for key in keys]
      scenario = build_scenario(
        path, functions, female_death, male_death, female_income, male_income)
      outcome = evaluate(scenario, STRATEGY, BASE_SAVINGS_RATE,
                         WITHDRAWAL_RATE, GAMMA)
      ruined[name].append(float(outcome.ruined))

  reference = ruined["resident"]
  results = []
  for name, panel in panels.items():
    differences = [value - ref for value, ref in zip(ruined[name], reference)]
    delta = statistics.fmean(differences)
    standard_error = statistics.stdev(differences) / math.sqrt(args.runs)
    results.append({
      "numeraire": name,
      **_moments(panel),
      "ruin_probability": statistics.fmean(ruined[name]),
      "ruin_difference_vs_resident": delta,
      "ruin_difference_ci95": [
        delta - 1.96 * standard_error,
        delta + 1.96 * standard_error,
      ],
    })

  print(f"Etats communs : {len(resident_rows)}/{len(source_rows)} pays-annees")
  print(f"{args.runs} trajectoires appariees ; blocs {args.mean_block:g} ans")
  print(f"{'numeraire':<12}{'rendement':>12}{'volatilite':>13}"
        f"{'ruine':>10}{'delta vs resident [IC95]':>30}")
  print("-" * 80)
  for row in results:
    low, high = row["ruin_difference_ci95"]
    print(f"{row['numeraire']:<12}{row['mean_return']:>12.2%}"
          f"{row['volatility']:>13.2%}{row['ruin_probability']:>10.2%}"
          f"  {row['ruin_difference_vs_resident']:+.2%} "
          f"[{low:+.2%};{high:+.2%}]")

  if args.output_json:
    with open(args.output_json, "w", encoding="utf-8") as handle:
      json.dump({
        "targets": targets,
        "runs": args.runs,
        "seed": args.seed,
        "mean_block": args.mean_block,
        "sample_mode": args.sample_mode,
        "source_observations": len(source_rows),
        "common_observations": len(resident_rows),
        "results": results,
      }, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
  main()
