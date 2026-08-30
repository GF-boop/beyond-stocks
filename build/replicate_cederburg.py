"""Replication fidele d'Anarkulova, Cederburg et O'Doherty (2023), "Beyond the
Status Quo: A Critical Assessment of Lifecycle Investment Advice".

Confirme par lecture du manuscrit (Netspar working paper, 21 sept. 2023) :

- these : un panier 50 % actions domestiques / 50 % actions internationales,
  maintenu constant a tout age ("Stocks/I"), domine les strategies a glidepath
  vers les obligations -- y compris en preservation du capital ;
- menage : epargne 10 % du revenu de 25 a 65 ans, retraite des 4 % du capital
  initial a la retraite, indexee sur l'inflation ensuite ;
- bootstrap stationnaire, blocs de longueur geometrique, moyenne 120 mois ;
- quatre classes d'actifs tirees ensemble par pays-mois : actions domestiques,
  actions internationales (moyenne ponderee par capitalisation des autres
  marches, ajustee du change), obligations, bills ;
- mortalite : tables SSA par sexe.

Ecarts assumes de cette replication :

- JST (16 pays, 1871-2020, annuel) remplace le GFDatabase proprietaire du
  papier (38 pays environ, 1890-2019, mensuel). Sur le rendement pooled des
  actions domestiques, notre panel donne 2,92 % reel annuel contre 4,53 %
  (converti depuis 0,37 %/mois) chez eux -- un ecart de niveau qui vient des
  sources, pas de la methode ;
- les actions internationales sont reconstruites depuis JST (voir
  international_equity.py) plutot que mesurees directement ;
- la mortalite suit une Gompertz--Makeham calee sur les moments SSA rapportes
  par ACO (voir mortality.py), et non leur table mensuelle ;
- pas de Social Security ni de modele de revenus stochastique : le menage
  epargne une part constante d'un revenu reel fixe. Le papier montre que ce
  choix deplace les niveaux sans changer le classement des strategies.

Le papier compare des MOYENNES, pas des medianes -- ce module suit cette
convention pour permettre la comparaison directe.
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
from social_security import household_benefit  # noqa: E402

START_AGE = 25
RETIRE_AGE = 65
MAX_AGE = 110
SAVINGS_RATE = 0.10
# Le papier tire les revenus d'un modele stochastique (Guvenen et alii) et
# obtient une richesse moyenne a la retraite de 0,81 million de dollars pour le
# TDF. Ce revenu constant est cale pour reproduire cet ordre de grandeur, faute
# de pouvoir repliquer le modele de revenus lui-meme.
INCOME = 31_500.0
WITHDRAWAL_RATE = 0.04
MEAN_BLOCK_MONTHS_EQUIVALENT = 10.0  # 120 mois -> 10 annees, le panel est annuel

# Panel A -- strategies "safe harbor" (glidepath ou allocation fixe).
# Panel B -- preservation du capital pure.
# Panel C -- strategies tout-actions, non-QDIA.
# Chaque strategie donne (domestique, international, obligations, bills) a
# 25 ans et a 65 ans ; les glidepaths interpolent lineairement entre les deux,
# les allocations fixes repetent la meme paire.
STRATEGIES: dict[str, dict] = {
  "TDF": {"young": (0.54, 0.36, 0.10, 0.00), "old": (0.18, 0.12, 0.55, 0.15)},
  "Balanced": {"young": (0.60, 0.00, 0.40, 0.00), "old": (0.60, 0.00, 0.40, 0.00)},
  "Balanced/I": {"young": (0.30, 0.30, 0.40, 0.00), "old": (0.30, 0.30, 0.40, 0.00)},
  "Age": {"glide_120": True, "international_share": 0.0},
  "Age/I": {"glide_120": True, "international_share": 0.5},
  "Bills": {"young": (0.00, 0.00, 0.00, 1.00), "old": (0.00, 0.00, 0.00, 1.00)},
  "Stocks": {"young": (1.00, 0.00, 0.00, 0.00), "old": (1.00, 0.00, 0.00, 0.00)},
  "Stocks/I": {"young": (0.50, 0.50, 0.00, 0.00), "old": (0.50, 0.50, 0.00, 0.00)},
}

PANEL_A = ("TDF", "Balanced", "Balanced/I", "Age", "Age/I")
PANEL_B = ("Bills",)
PANEL_C = ("Stocks", "Stocks/I")


def read_panel(path: str) -> list[dict[str, float]]:
  rows = []
  with open(path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      rows.append({
        "country": row["country"],
        "year": int(row["year"]),
        "domestic": float(row["domestic_equity_real"]),
        "international": float(row["international_equity_real"]),
        "bond": float(row["bond_real"]),
        "bill": float(row["bill_real"]),
      })
  rows.sort(key=lambda r: (r["country"], r["year"]))
  return rows


def block_bootstrap(rows: list[dict[str, float]], horizon: int,
                    rng: random.Random,
                    mean_block: float = MEAN_BLOCK_MONTHS_EQUIVALENT,
                    ) -> list[dict[str, float]]:
  """Blocs de longueur geometrique. Une longueur moyenne de 1 revient a un
  tirage independant annee par annee, ce qui reproduit le bootstrap IID que le
  papier presente en comparaison. Un bloc reste dans le meme pays et s'arrete
  a la premiere lacune de sa serie, conformement au bootstrap du papier."""
  if mean_block <= 1.0:
    return [rows[rng.randrange(len(rows))] for _ in range(horizon)]
  probability = 1.0 / mean_block
  by_country_year = {(row["country"], row["year"]): row for row in rows}
  path: list[dict[str, float]] = []
  while len(path) < horizon:
    length = max(1, int(math.ceil(
      math.log(1.0 - rng.random()) / math.log(1.0 - probability))))
    start = rows[rng.randrange(len(rows))]
    for offset in range(length):
      observation = by_country_year.get(
        (start["country"], start["year"] + offset))
      if observation is None:
        break
      path.append(observation)
      if len(path) >= horizon:
        break
  return path[:horizon]


def weights_at(name: str, age: int) -> tuple[float, float, float, float]:
  spec = STRATEGIES[name]
  progress = min(1.0, max(0.0, (age - START_AGE) / (RETIRE_AGE - START_AGE)))

  if spec.get("glide_120"):
    # La regle "120 moins l'age" : la part actions decroit lineairement avec
    # l'age et n'est plus une simple interpolation entre deux bornes fixees.
    stock_share = max(0.0, (120 - age) / 100.0)
    bond_share = 1.0 - stock_share
    share = spec["international_share"]
    return (stock_share * (1.0 - share), stock_share * share, bond_share, 0.0)

  young, old = spec["young"], spec["old"]
  return tuple(y + (o - y) * progress for y, o in zip(young, old))


def portfolio_return(observation: dict[str, float],
                     weights: tuple[float, float, float, float]) -> float:
  domestic, international, bond, bill = weights
  return (domestic * observation["domestic"]
         + international * observation["international"]
         + bond * observation["bond"]
         + bill * observation["bill"])


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
  wealth = 0.0
  for index, age in enumerate(range(START_AGE, RETIRE_AGE)):
    wealth += INCOME * SAVINGS_RATE
    wealth *= 1.0 + portfolio_return(path[index], weights_at(name, age))

  at_retirement = wealth
  withdrawal = at_retirement * WITHDRAWAL_RATE
  consumed, ruin_age = 0.0, None
  peak, retirement_drawdown = at_retirement, 0.0

  for index, age in enumerate(range(RETIRE_AGE, last_death + 1),
                              start=RETIRE_AGE - START_AGE):
    if index >= len(path):
      break
    served = min(wealth, withdrawal)
    # La ruine est l'epuisement du capital financier. La pension continue
    # d'etre versee ensuite, si bien qu'un menage ruine n'est pas sans
    # ressources -- c'est la definition du papier.
    if served < withdrawal - 0.005 and ruin_age is None:
      ruin_age = age
    wealth = max(0.0, wealth - served)

    if pensions is not None:
      couple_pension, survivor_pension = pensions
      pension = couple_pension if age <= first_death else survivor_pension
      consumed += served + pension
    else:
      consumed += served

    wealth *= 1.0 + portfolio_return(path[index], weights_at(name, age))
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
  }


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--no-social-security", action="store_true",
                      help="desactive les pensions, pour comparer")
  parser.add_argument("--mean-block", type=float,
                      default=MEAN_BLOCK_MONTHS_EQUIVALENT,
                      help="longueur moyenne des blocs en annees ; 1 pour IID")
  args = parser.parse_args()

  rows = read_panel(args.panel)
  # Calibrage SSA : la distribution d'age au deces du couple vise celle de la
  # Table III du papier (moyenne 87,6 ans, ecart-type 9,1).
  female = mortality_table("female", "ssa")
  male = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1

  print(f"Panel : {len(rows)} pays-annees ({rows[0]['year']}-{rows[-1]['year']})")
  print(f"Menage : epargne {SAVINGS_RATE:.0%} de 25 a 65 ans, "
       f"regle des {WITHDRAWAL_RATE:.0%}")
  print(f"Simulations : {args.runs}")
  print()

  names = list(STRATEGIES)
  rng = random.Random(args.seed)
  results: dict[str, list[dict[str, float]]] = {n: [] for n in names}

  pensions = None if args.no_social_security else household_benefit(INCOME)
  if pensions:
    print(f"Social Security : {pensions[0]:,.0f} EUR/an pour le couple, "
          f"{pensions[1]:,.0f} pour le survivant".replace(",", " "))
    print()

  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block)
    female_death = draw_death_age(female, rng)
    male_death = draw_death_age(male, rng)
    first = min(female_death, male_death)
    last = max(female_death, male_death)
    for name in names:
      results[name].append(simulate(name, path, last, first, pensions))

  def show(group: tuple[str, ...], caption: str) -> None:
    print(caption)
    print(f"{'strategie':<12}{'richesse moy.':>15}{'richesse med.':>15}"
         f"{'conso moy./an':>15}{'ruine':>8}{'DD retraite':>13}")
    print("-" * 78)
    for name in group:
      rows_ = results[name]
      wealth = statistics.fmean(r["retirement_wealth"] for r in rows_)
      median_wealth = statistics.median(r["retirement_wealth"] for r in rows_)
      consumption = statistics.fmean(r["consumption"] for r in rows_)
      ruin = sum(r["ruined"] for r in rows_) / len(rows_)
      dd = statistics.fmean(r["retirement_drawdown"] for r in rows_)
      print(f"{name:<12}{wealth:>14,.0f}{median_wealth:>15,.0f}"
           f"{consumption:>15,.0f}{ruin:>8.1%}{dd:>13.1%}".replace(",", " "))
    print()

  show(PANEL_A, "Panel A -- strategies a horizon (safe harbor) :")
  show(PANEL_B, "Panel B -- preservation du capital :")
  show(PANEL_C, "Panel C -- strategies tout-actions :")

  tdf_wealth = statistics.fmean(r["retirement_wealth"] for r in results["TDF"])
  tdf_ruin = sum(r["ruined"] for r in results["TDF"]) / len(results["TDF"])
  stocks_i_wealth = statistics.fmean(
    r["retirement_wealth"] for r in results["Stocks/I"])
  stocks_i_ruin = sum(r["ruined"] for r in results["Stocks/I"]) / len(
    results["Stocks/I"])
  stocks_wealth = statistics.fmean(
    r["retirement_wealth"] for r in results["Stocks"])
  stocks_ruin = sum(r["ruined"] for r in results["Stocks"]) / len(
    results["Stocks"])

  tdf_median = statistics.median(
    r["retirement_wealth"] for r in results["TDF"])
  stocks_median = statistics.median(
    r["retirement_wealth"] for r in results["Stocks"])
  stocks_i_median = statistics.median(
    r["retirement_wealth"] for r in results["Stocks/I"])

  # Table X du papier, Panel A, block bootstrap sur l'echantillon developpe.
  PUBLISHED_RUIN = {
    "TDF": 0.169, "Balanced": 0.157, "Balanced/I": 0.109, "Age": 0.168,
    "Age/I": 0.133, "Bills": 0.357, "Stocks": 0.174, "Stocks/I": 0.082,
  }
  print("Probabilite de ruine, les huit strategies (Table X, Panel A) :")
  print(f"{'strategie':<12}{'notre JST':>12}{'papier':>10}{'ecart':>10}")
  print("-" * 44)
  for name in names:
    ours = sum(r["ruined"] for r in results[name]) / len(results[name])
    published = PUBLISHED_RUIN[name]
    print(f"{name:<12}{ours:>11.1%}{published:>10.1%}{ours - published:>+10.1f}"
          .replace(f"{ours - published:>+10.1f}",
                   f"{(ours - published) * 100:>+9.1f}pt"))
  print()

  print("Comparaison au papier (chiffres publies entre parentheses) :")
  print(f"  Stocks   vs TDF, richesse moyenne : "
       f"{stocks_wealth / tdf_wealth - 1:>+7.1%}   (papier : +30%)")
  print(f"  Stocks/I vs TDF, richesse moyenne : "
       f"{stocks_i_wealth / tdf_wealth - 1:>+7.1%}   (papier : +32%)")
  print(f"  Stocks   vs TDF, richesse mediane : "
       f"{stocks_median / tdf_median - 1:>+7.1%}")
  print(f"  Stocks/I vs TDF, richesse mediane : "
       f"{stocks_i_median / tdf_median - 1:>+7.1%}")
  print(f"  ruine TDF                 : {tdf_ruin:>7.1%}   (papier : 16.9%)")
  print(f"  ruine Stocks              : {stocks_ruin:>7.1%}   (papier : 17.4%)")
  print(f"  ruine Stocks/I            : {stocks_i_ruin:>7.1%}   (papier : 8.2%)")


if __name__ == "__main__":
  main()
