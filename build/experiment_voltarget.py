"""Experience : levier par vol-cible glissante ex ante, et frontiere ruine-vol.

Deux tests, sur la meme machinerie que compare_lifecycle_utility (revenus GKOS,
utilite CRRA, Social Security, mortalite, trajectoires appariees ; change traite
comme dans le panel courant : bloc obligataire couvert CIP, actions / or / MF
non couverts sauf indication).

--- Option 2 : vol-cible glissante ---
Chaque annee de la trajectoire, le levier applique au portefeuille diversifie
est choisi pour viser une volatilite cible, estimee UNIQUEMENT sur les rendements
des annees anterieures du portefeuille (fenetre glissante de 36 observations,
minimum 10). Aucune information future. Le portefeuille cible ainsi la meme
volatilite que le benchmark 33/67 EN MOYENNE, sans jamais lire l'echantillon
complet. On compare alors ruine, richesse mediane, epargne equivalente.

--- Option 4 : frontiere ruine-vol ---
Pour chaque portefeuille diversifie, on balaie un levier FIXE de 1.0x a 2.0x et
on trace (volatilite realisee, ruine). Si la courbe du diversifie passe sous
celle du 33/67 sur toute la plage, la dominance ne depend pas du choix d'un
point de levier -- donc pas de biais look-ahead.

Regle de comparaison : le sleeve actions reste EXACTEMENT le 33/67 d'ACO dans
tous les portefeuilles. Seuls le bloc obligataire (couvert CIP), les
diversificateurs et le levier changent. Cela isole l'effet de la
diversification obligataire / alternative, sans melanger un changement de home
bias actions.

Portefeuilles diversifies testes (sleeve actions = 33/67 partout) :
* 90/60 : 90 % 33/67 + 60 % obligations monde couvertes ;
* 90/60 + 33 MF : idem plus 33.33 % managed futures couverts ;
* 90/60 + 33 or : idem plus 33.33 % or.
Le "90/60" n'est pas un poids sacre : le ciblage de vol ajuste le multiplicateur
autour de ce profil. Ce qui est fixe ex ante, c'est le RATIO actions/obligations
(3:2) et la composition des sleeves, pas le levier.
Benchmark : ACO 33/67, non leve.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
from collections.abc import Callable

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_lifecycle_utility import (  # noqa: E402
  BASE_SAVINGS_RATE,
  GAMMA,
  WITHDRAWAL_RATE,
  build_scenario,
  clear_utility_batches,
  draw_death_age,
  equivalent_savings_rate,
  evaluate,
  evaluate_batch,
  expected_utility,
)
from income_process import draw_household_income  # noqa: E402
from investability import exclusion_reason as investability_reason  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  RETIRE_AGE,
  START_AGE,
  TREND_DRAG,
  TREND_FEE,
  block_bootstrap,
  read_panel,
)

ROLL_WINDOW = 36
ROLL_MIN = 10
MAX_LEVERAGE = 3.0


def net_trend(raw: float) -> float:
  return (1.0 + raw) * (1.0 - TREND_FEE) - 1.0 - TREND_DRAG


def benchmark_3367(row: dict[str, float]) -> float:
  return 0.33 * row["domestic"] + 0.67 * row["international"]


def diversified_excess(name: str) -> Callable[[dict[str, float]], float]:
  """Rendement du sleeve risque diversifie, en exces du financement local.

  Le sleeve actions est le 33/67 d'ACO dans tous les cas. Le ratio
  actions/obligations est 3:2 (d'ou "90/60" a levier 1.5x, mais le levier lui
  est fixe par le ciblage de vol, pas ici). Le financement (jambe courte) est
  TOUJOURS le bill du resident : `world_bill` est deja ce bill dans le panel
  couvert.
  """
  def equity_3367(row: dict[str, float]) -> float:
    return 0.33 * row["domestic"] + 0.67 * row["international"]

  if name == "90/60":
    def excess(row: dict[str, float]) -> float:
      # sleeve unitaire (somme des poids = 1) : 0.6 actions + 0.4 obligations,
      # le ciblage de vol l'amplifie ensuite.
      sleeve = 0.6 * equity_3367(row) + 0.4 * row["world_bond"]
      return sleeve - row["world_bill"]
  elif name == "90/60 + 33 MF":
    def excess(row: dict[str, float]) -> float:
      sleeve = (0.6 * equity_3367(row) + 0.4 * row["world_bond"]
                + (1.0 / 3.0) * net_trend(row["trend"]))
      gross = 0.6 + 0.4 + 1.0 / 3.0
      return sleeve - gross * row["world_bill"]
  elif name == "90/60 + 33 gold":
    def excess(row: dict[str, float]) -> float:
      sleeve = (0.6 * equity_3367(row) + 0.4 * row["world_bond"]
                + (1.0 / 3.0) * row["gold"])
      gross = 0.6 + 0.4 + 1.0 / 3.0
      return sleeve - gross * row["world_bill"]
  else:
    raise ValueError(name)
  return excess


def levered_return(row: dict[str, float], excess: float, leverage: float,
                   spread: float) -> float:
  """bill resident + L * exces - cout de financement sur (L - 1)."""
  return (row["world_bill"] + leverage * excess
          - max(0.0, leverage - 1.0) * spread)


# ---------------------------------------------------------------------------
# Option 2 : vol-cible glissante ex ante
# ---------------------------------------------------------------------------

def rolling_voltarget_path(path: list[dict[str, float]], excess_fn,
                           target_vol: float, spread: float) -> list[float]:
  """Rendement annee par annee, levier choisi sur le passe de la trajectoire."""
  history: list[float] = []
  out: list[float] = []
  for row in path:
    ex = excess_fn(row)
    if len(history) >= ROLL_MIN:
      window = history[-ROLL_WINDOW:]
      realized = statistics.pstdev(window)
      leverage = target_vol / realized if realized > 1e-6 else 1.0
      leverage = max(0.0, min(MAX_LEVERAGE, leverage))
    else:
      leverage = 1.0
    r = levered_return(row, ex, leverage, spread)
    out.append(r)
    # L'historique suit le rendement du sleeve NON leve, pour estimer sa vol
    # propre ; c'est cette vol que la cible ramene a `target_vol`.
    history.append(row["world_bill"] + ex)
  return out


def make_voltarget_functions(target_vol: float, spread: float):
  names = ["90/60", "90/60 + 33 MF", "90/60 + 33 gold"]
  excess_fns = {n: diversified_excess(n) for n in names}

  functions: dict[str, Callable[[list[dict[str, float]]], list[float]]] = {}
  functions["ACO 33/67"] = lambda p: [benchmark_3367(r) for r in p]
  for n in names:
    fn = excess_fns[n]
    functions[n] = (lambda p, fn=fn: rolling_voltarget_path(
      p, fn, target_vol, spread))
  return functions


# ---------------------------------------------------------------------------
# Machinerie commune : scenarios apparies
# ---------------------------------------------------------------------------

def build_scenarios(rows, runs, seed, mean_block):
  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(seed)
  paths = []
  deaths = []
  incomes = []
  for _ in range(runs):
    paths.append(block_bootstrap(rows, horizon, rng, mean_block))
    deaths.append((draw_death_age(female_survival, rng),
                   draw_death_age(male_survival, rng)))
    fi, mi, _ = draw_household_income(rng)
    incomes.append((fi, mi))
  return paths, deaths, incomes


def scenarios_from_pathfns(paths, deaths, incomes, path_functions):
  """path_functions : nom -> (path -> liste de rendements annuels)."""
  # build_scenario attend des fonctions row->float ; on adapte en indexant
  # une liste pre-calculee par trajectoire.
  scenarios = []
  for path, (fd, md), (fi, mi) in zip(paths, deaths, incomes):
    precomputed = {name: fn(path) for name, fn in path_functions.items()}

    def make_row_fn(name, series=precomputed):
      counter = {"i": 0}
      seq = series[name]

      def row_fn(_row, seq=seq, counter=counter):
        i = counter["i"]
        counter["i"] += 1
        return seq[i] if i < len(seq) else seq[-1]
      return row_fn

    row_functions = {name: make_row_fn(name) for name in precomputed}
    scenarios.append(build_scenario(
      path, row_functions, fd, md, fi, mi))
  return scenarios


def summarize(scenarios, names, gamma, withdrawal_rate):
  target = expected_utility(scenarios, "ACO 33/67", BASE_SAVINGS_RATE,
                            gamma, withdrawal_rate)
  header = (f"{'strategie':<22}{'epargne eq.':>13}{'rich. med. 65':>15}"
            f"{'conso moy.':>13}{'ruine':>9}{'legs med.':>14}"
            f"{'vol trav.':>11}")
  print(header)
  print("-" * len(header))
  flags = {}
  for name in names:
    outs = [evaluate(s, name, BASE_SAVINGS_RATE, withdrawal_rate, gamma)
            for s in scenarios]
    eqs = equivalent_savings_rate(scenarios, name, target, gamma,
                                  withdrawal_rate)
    wealth = statistics.median(o.retirement_wealth for o in outs)
    cons = statistics.fmean(o.retirement_consumption for o in outs)
    ruin = statistics.fmean(1.0 if o.ruined else 0.0 for o in outs)
    beq = statistics.median(o.bequest for o in outs)
    flags[name] = [1.0 if o.ruined else 0.0 for o in outs]
    # Vol du portefeuille reellement traverse : ecart-type des rendements de
    # retraite, moyenne sur les trajectoires.
    vols = []
    for s in scenarios:
      seq = s.retirement_returns[name]
      if len(seq) >= 2:
        vols.append(statistics.pstdev(seq))
    vol = statistics.fmean(vols) if vols else float("nan")
    eqs_txt = "n/a" if math.isnan(eqs) else f"{eqs:.2%}"
    print(f"{name:<22}{eqs_txt:>13}{wealth:>15,.0f}{cons:>13,.0f}"
          f"{ruin:>9.2%}{beq:>14,.0f}{vol:>11.2%}".replace(",", " "))
  print()
  base = flags["ACO 33/67"]
  for name in names:
    if name == "ACO 33/67":
      continue
    diff = [a - b for a, b in zip(flags[name], base)]
    mean = statistics.fmean(diff) * 100
    half = 1.96 * statistics.pstdev(diff) / math.sqrt(len(diff)) * 100
    print(f"  ruine {name} - 33/67 : {mean:+.2f} pt "
          f"(IC 95 % [{mean - half:+.2f}, {mean + half:+.2f}])")


# ---------------------------------------------------------------------------
# Option 4 : frontiere ruine-vol
# ---------------------------------------------------------------------------

def frontier(rows, paths, deaths, incomes, gamma, withdrawal_rate, spread):
  names = ["90/60", "90/60 + 33 MF", "90/60 + 33 gold"]
  excess_fns = {n: diversified_excess(n) for n in names}
  leverages = [1.0, 1.15, 1.3, 1.5, 1.7, 1.85, 2.0]

  # Reference 33/67.
  clear_utility_batches()
  ref_fns = {"ACO 33/67": lambda p: [benchmark_3367(r) for r in p]}
  ref_scen = scenarios_from_pathfns(paths, deaths, incomes, ref_fns)
  ref_ruin = float(np.mean(evaluate_batch(
    ref_scen, "ACO 33/67", BASE_SAVINGS_RATE,
    withdrawal_rate, gamma).ruined))
  ref_vols = [statistics.pstdev(s.retirement_returns["ACO 33/67"])
              for s in ref_scen
              if len(s.retirement_returns["ACO 33/67"]) >= 2]
  ref_vol = statistics.fmean(ref_vols)
  print(f"Reference ACO 33/67 : vol traversee {ref_vol:.2%}, "
        f"ruine {ref_ruin:.2%}")
  print()

  for name in names:
    fn = excess_fns[name]
    print(f"--- {name} : frontiere levier / vol / ruine ---")
    print(f"{'levier':>8}{'vol trav.':>12}{'ruine':>10}"
          f"{'vs 33/67':>11}")
    for lev in leverages:
      clear_utility_batches()
      path_fns = {name: (lambda p, fn=fn, lev=lev: [
        levered_return(r, fn(r), lev, spread) for r in p])}
      scen = scenarios_from_pathfns(paths, deaths, incomes, path_fns)
      ruin = float(np.mean(evaluate_batch(
        scen, name, BASE_SAVINGS_RATE, withdrawal_rate, gamma).ruined))
      vols = [statistics.pstdev(s.retirement_returns[name]) for s in scen
              if len(s.retirement_returns[name]) >= 2]
      vol = statistics.fmean(vols)
      mark = "  <=" if ruin <= ref_ruin else ""
      print(f"{lev:>8.2f}{vol:>12.2%}{ruin:>10.2%}"
            f"{(ruin - ref_ruin) * 100:>+9.2f}pt{mark}")
    print()


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=10.0)
  parser.add_argument("--spread", type=float, default=0.003)
  parser.add_argument("--withdrawal-rate", type=float, default=WITHDRAWAL_RATE)
  parser.add_argument("--gamma", type=float, default=GAMMA)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  parser.add_argument("--mode", choices=["voltarget", "frontier", "both"],
                      default="both")
  parser.add_argument(
    "--sample-mode", choices=("investable", "usa", "full"),
    default="full",
    help=("full (defaut) conserve le panel historique integral ; investable "
          "applique le filtre de negociabilite ex ante ; usa restreint les blocs "
          "aux annees des Etats-Unis (menage US, numeraire dollar constant, "
          "pas de changement de pays)."))
  args = parser.parse_args()

  rows = read_panel(args.panel)
  excluded = 0
  if args.sample_mode == "investable":
    kept = [
      r for r in rows
      if investability_reason(r["country"], r["year"], r["inflation"]) is None
    ]
    excluded = len(rows) - len(kept)
    rows = kept
  elif args.sample_mode == "usa":
    kept = [r for r in rows if r["country"] == "USA"]
    excluded = len(rows) - len(kept)
    rows = kept
  if args.year_from is not None:
    rows = [r for r in rows if r["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [r for r in rows if r["year"] <= args.year_to]

  # Cible : volatilite realisee du 33/67 sur le panel pooled. Sert uniquement
  # de valeur ronde pour le ciblage glissant ; le ciblage lui-meme n'y accede
  # pas trajectoire par trajectoire.
  pooled_3367 = [benchmark_3367(r) for r in rows]
  target_vol = statistics.pstdev(pooled_3367)

  span = f"{min(r['year'] for r in rows)}-{max(r['year'] for r in rows)}"
  print(f"Panel : {len(rows)} pays-annees ({span}), "
        f"filtre {args.sample_mode} ({excluded} exclus)")
  print(f"Runs : {args.runs} trajectoires appariees, blocs {args.mean_block:g} "
        f"an(s), spread {args.spread:.2%}")
  print(f"Vol cible (= vol pooled du 33/67) : {target_vol:.2%}")
  print()

  paths, deaths, incomes = build_scenarios(
    rows, args.runs, args.seed, args.mean_block)

  if args.mode in ("voltarget", "both"):
    print("=" * 70)
    print("OPTION 2 : levier par vol-cible glissante ex ante")
    print("=" * 70)
    fns = make_voltarget_functions(target_vol, args.spread)
    scen = scenarios_from_pathfns(paths, deaths, incomes, fns)
    summarize(scen, list(fns), args.gamma, args.withdrawal_rate)
    print()

  if args.mode in ("frontier", "both"):
    print("=" * 70)
    print("OPTION 4 : frontiere ruine-vol (levier fixe balaye)")
    print("=" * 70)
    frontier(rows, paths, deaths, incomes, args.gamma,
             args.withdrawal_rate, args.spread)


if __name__ == "__main__":
  main()
