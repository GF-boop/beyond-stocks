"""Extension de la replication : les strategies du papier confrontees a des
portefeuilles a levier et a tendance.

Le papier compare des allocations qui ne portent pas le meme risque, puis
conclut que la plus risquee "domine". La conclusion est en partie circulaire :
sur un horizon de quarante ans d'epargne, l'allocation la plus exposee aux
actions finit presque toujours devant, et le fonds a horizon perd surtout parce
qu'il porte moins de risque -- pas parce qu'il serait mal construit.

Ce module ajoute donc des strategies qui cherchent le rendement autrement que
par une exposition actions plus forte : un fonds a levier de type 90/60, et des
combinaisons avec une poche de tendance. Il rapporte aussi la volatilite du
portefeuille reellement traverse et un rendement par unite de risque, pour que
la comparaison ne se fasse pas seulement en niveau.

Fonde sur la replication fidele d'Anarkulova, Cederburg et O'Doherty (2023),
"Beyond the Status Quo: A Critical Assessment of Lifecycle Investment Advice".

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
  par ACO (voir mortality.py), et non la table mensuelle proprietaire ;
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
from trend_costs import (  # noqa: E402
  DEFAULT_TREND_COST, DEFAULT_TREND_FEE,
)
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
WITHDRAWAL_RATE = 0.04  # remplace par --withdrawal-rate si fourni
MEAN_BLOCK_MONTHS_EQUIVALENT = 10.0  # 120 mois -> 10 annees, le panel est annuel

# Cout de financement de l'exposition qui depasse cent pour cent, et frais de
# la poche de tendance. Un fonds cote donnant la performance d'une strategie de
# tendance doit financer son exposition comme n'importe quel fonds a levier.
#
# Les frais valent 0,85 % par an, mediane des ETF managed futures accessibles
# en 2026 (iMGP DBi UCITS 0,75 %, DBMF 0,85 %, KMLM 0,90 %), qui sont a frais
# fixes sans commission de performance. Le drag de transaction est derive du
# turnover REELLEMENT mesure sur le proxy managed futures (environ 19x par an)
# et d'un spread aller-retour de 3 points de base, soit environ 0,57 %.
#
# Ces deux valeurs viennent de trend_costs.py, ou le cout est recalcule depuis
# le turnover mesure sur data/managed-futures-monthly.csv et non recopie en dur
# : la version precedente codait 0,17 %, valeur heritee de l'ancien indice de
# tendance, qui s'est perimee en silence au changement de serie.
# Le cas principal du projet retient 0,30 % au-dessus des taux courts, cout du
# levier indique par l'utilisateur. Le 0,37 % de Cederburg reste une sensibilite
# de replication et 1,40 % un scenario de marge plus cher.
FINANCING_SPREAD = 0.003
TREND_FEE = DEFAULT_TREND_FEE
TREND_DRAG = DEFAULT_TREND_COST

# Panel A -- strategies "safe harbor" (glidepath ou allocation fixe).
# Panel B -- preservation du capital pure.
# Panel C -- strategies tout-actions, non-QDIA.
# Chaque strategie donne (domestique, international, obligations, bills) a
# 25 ans et a 65 ans ; les glidepaths interpolent lineairement entre les deux,
# les allocations fixes repetent la meme paire.
# Les poids sont (domestique, international, obligations, bills, tendance).
# Les cinq premieres strategies reprennent le papier, les suivantes l'etendent.
STRATEGIES: dict[str, dict] = {
  "TDF": {"young": (0.54, 0.36, 0.10, 0.00), "old": (0.18, 0.12, 0.55, 0.15)},
  "Balanced": {"young": (0.60, 0.00, 0.40, 0.00), "old": (0.60, 0.00, 0.40, 0.00)},
  "Balanced/I": {"young": (0.30, 0.30, 0.40, 0.00), "old": (0.30, 0.30, 0.40, 0.00)},
  "Age": {"glide_120": True, "international_share": 0.0},
  "Age/I": {"glide_120": True, "international_share": 0.5},
  "Bills": {"young": (0.00, 0.00, 0.00, 1.00), "old": (0.00, 0.00, 0.00, 1.00)},
  "Stocks": {"young": (1.00, 0.00, 0.00, 0.00), "old": (1.00, 0.00, 0.00, 0.00)},
  "Stocks/I": {"young": (0.50, 0.50, 0.00, 0.00), "old": (0.50, 0.50, 0.00, 0.00)},
  # 90 % actions et 60 % obligations pour cent euros investis : le fonds
  # cherche le rendement par le levier plutot que par plus d'actions. La poche
  # actions est diversifiee comme Stocks/I, pour que la comparaison ne melange
  # pas l'effet du levier et celui de la diversification geographique.
  "90/60/I": {"young": (0.45, 0.45, 0.60, 0.00), "old": (0.45, 0.45, 0.60, 0.00)},
  # La tendance remplace la poche obligataire.
  "90/60 MF": {"young": (0.45, 0.45, 0.00, 0.00, 0.60),
               "old": (0.45, 0.45, 0.00, 0.00, 0.60)},
  # Les trois poches ensemble, soit 210 % d'exposition.
  "90/60/60": {"young": (0.45, 0.45, 0.60, 0.00, 0.60),
               "old": (0.45, 0.45, 0.60, 0.00, 0.60)},
  # Montage realisable avec deux lignes cotees : 60 % du capital dans un fonds
  # 90/60, 40 % dans un fonds de tendance.
  "60 NTSG/40 MF": {"young": (0.27, 0.27, 0.36, 0.00, 0.40),
                    "old": (0.27, 0.27, 0.36, 0.00, 0.40)},
  # Portefeuilles avec or. Le sixieme poids est la poche d'or.
  # Un 60/40 classique dont une part est remplacee par de l'or.
  "50/30/20 Or": {"young": (0.25, 0.25, 0.30, 0.00, 0.00, 0.20),
                  "old": (0.25, 0.25, 0.30, 0.00, 0.00, 0.20)},
  # Le Dragon d'Artemis, sans sa poche de volatilite longue : ses cinq
  # briques sont actions, obligations, or, tendance et volatilite longue a
  # 20 % chacune. Cette derniere demande des donnees d'options historiques
  # qui ne sont pas publiques, donc les quatre autres sont reponderees a
  # 25 %.
  "Dragon (sans vol)": {"young": (0.125, 0.125, 0.25, 0.00, 0.25, 0.25),
                        "old": (0.125, 0.125, 0.25, 0.00, 0.25, 0.25)},
  # Le montage a deux lignes, complete d'une poche d'or.
  "NTSG/MF/Or": {"young": (0.225, 0.225, 0.30, 0.00, 0.30, 0.20),
                 "old": (0.225, 0.225, 0.30, 0.00, 0.30, 0.20)},
  # Le Dragon a la volatilite la plus basse du tableau hors bills, ce qui en
  # fait le candidat naturel au levier : le porter a 150 % ou 200 % le ramene
  # au niveau de risque des strategies tout-actions, et permet de les comparer
  # a risque comparable plutot qu'a exposition comparable.
  "Dragon x1.5": {"young": (0.1875, 0.1875, 0.375, 0.00, 0.375, 0.375),
                  "old": (0.1875, 0.1875, 0.375, 0.00, 0.375, 0.375)},
  "Dragon x2": {"young": (0.25, 0.25, 0.50, 0.00, 0.50, 0.50),
                "old": (0.25, 0.25, 0.50, 0.00, 0.50, 0.50)},
}

PANEL_A = ("TDF", "Balanced", "Balanced/I", "Age", "Age/I")
PANEL_B = ("Bills",)
PANEL_C = ("Stocks", "Stocks/I")
PANEL_D = ("90/60/I", "90/60 MF", "90/60/60", "60 NTSG/40 MF")
PANEL_E = ("50/30/20 Or", "Dragon (sans vol)", "NTSG/MF/Or",
           "Dragon x1.5", "Dragon x2")


def read_panel(path: str) -> list[dict[str, float]]:
  rows = []
  with open(path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      rows.append({
        "country": row["country"],
        "year": int(row["year"]),
        # Nombre d'unites de devise du resident par dollar. Il permet au
        # controle a numeraire USD fixe de reexprimer les memes etats
        # pays-annee sans changer le bootstrap.
        "xrusd": float(row.get("xrusd", "nan")),
        "domestic": float(row["domestic_equity_real"]),
        "international": float(row["international_equity_real"]),
        "international_constant_real_fx": float(row.get(
          "international_equity_real_constant_real_fx",
          row["international_equity_real"])),
        "bond": float(row["bond_real"]),
        "bill": float(row["bill_real"]),
        "inflation": float(row["inflation"]),
        # Poche obligataire mondiale : tous les souverains disponibles du panel
        # (jusqu'a 16), agreges a poids egaux puis convertis dans la monnaie et
        # le pouvoir d'achat du resident porte par cette ligne.
        "world_bond": float(row.get("world_bond_real", row["bond_real"])),
        "world_bill": float(row.get("world_bill_real", row["bill_real"])),
        "world_bond_unhedged": float(row.get(
          "world_bond_real_unhedged", row.get("world_bond_real",
                                                row["bond_real"]))),
        "world_bill_unhedged": float(row.get(
          "world_bill_real_unhedged", row.get("world_bill_real",
                                                row["bill_real"]))),
        # Poche actions mondiale : MSCI World a partir de 1970, reconstruction
        # ponderee avant cette date, dans les deux cas convertie dans le
        # numeraire du resident de la ligne.
        "world_equity": float(row.get("world_equity_real",
                                      row["domestic_equity_real"])),
        "trend": float(row.get("trend_real", 0.0)),
        "trend_unhedged": float(row.get(
          "trend_real_unhedged", row.get("trend_real", 0.0))),
        # L'or ne verse aucun revenu : son rendement est la seule variation de
        # prix, nette des frais de garde d'un detenteur physique.
        "gold": float(row.get("gold_real", 0.0)),
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


def weights_at(name: str, age: int) -> tuple[float, ...]:
  """Poids (domestique, international, obligations, bills, tendance).

  Les strategies du papier n'ont pas de poche de tendance ; leurs tuples a
  quatre elements sont completes par un zero.
  """
  spec = STRATEGIES[name]
  progress = min(1.0, max(0.0, (age - START_AGE) / (RETIRE_AGE - START_AGE)))

  if spec.get("glide_120"):
    # La regle "120 moins l'age" : la part actions decroit lineairement avec
    # l'age et n'est plus une simple interpolation entre deux bornes fixees.
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
  """Rendement reel annuel du portefeuille.

  Ce qui depasse cent pour cent d'exposition est finance au taux court majore
  du spread, quelle que soit la poche qui porte cet exces. La tendance supporte
  en outre ses frais de gestion et son cout de replication.

  `world_bonds` distingue les deux familles de strategies. Celles du papier
  tiennent la dette et les actions du pays de residence, comme leurs auteurs
  les modelisent : la poche actions y est un panier 50/50 domestique et
  international. Les fonds a levier tiennent un indice mondial et un panier
  souverain a quatre emetteurs, parce que c'est ce que font les instruments
  reels. Le financement du levier suit la meme poche que les obligations.
  """
  domestic, international, bond, bill, trend, gold = weights
  leverage = max(0.0,
                 domestic + international + bond + bill + trend + gold - 1.0)
  net_trend = (1.0 + observation["trend"]) * (1.0 - TREND_FEE) - 1.0 - TREND_DRAG

  if world_bonds:
    # Les poids actions domestique et international sont additionnes : le fonds
    # ne distingue pas les deux, il suit un indice mondial unique.
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
  # Les strategies hors papier utilisent la poche obligataire mondiale.
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
                      help="desactive les pensions, pour comparer")
  parser.add_argument("--mean-block", type=float,
                      default=MEAN_BLOCK_MONTHS_EQUIVALENT,
                      help="longueur moyenne des blocs en annees ; 1 pour IID")
  parser.add_argument("--withdrawal-rate", type=float,
                      default=WITHDRAWAL_RATE,
                      help="taux de rente en %% du capital constate par "
                           "chaque strategie a son propre depart en retraite "
                           "(defaut : 0.04, la regle du papier)")
  parser.add_argument("--financing-spread", type=float,
                      default=FINANCING_SPREAD,
                      help="spread annuel au-dessus des bills pour financer "
                           "le levier (defaut : 0.003)")
  args = parser.parse_args()
  WITHDRAWAL_RATE = args.withdrawal_rate
  FINANCING_SPREAD = args.financing_spread

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

  order = (list(PANEL_A) + list(PANEL_B) + list(PANEL_C) + list(PANEL_D)
           + list(PANEL_E))
  def money(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")

  def group_of(name: str) -> str:
    if name in PANEL_E:
      return "or"
    if name in PANEL_D:
      return "ajout"
    return "papier"

  print("=" * 96)
  print("TABLEAU 1 -- PERFORMANCE (euros reels)")
  print("=" * 96)
  header = (f"{'strategie':<17}{'':>8}{'richesse med.':>15}{'richesse moy.':>15}"
           f"{'conso/an':>12}{'heritage med.':>16}")
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
    tag = "or" if name in PANEL_E else ("ajout" if name in PANEL_D else "")
    print(f"{name:<17}{tag:>8}{money(median_wealth):>15}"
          f"{money(mean_wealth):>15}{money(consumption):>12}"
          f"{money(bequest):>16}")
  print()
  print("Lecture : la richesse MEDIANE est la statistique a retenir. Le papier")
  print("  compare des moyennes, mais sur un panel annuel les queues sont trop")
  print("  epaisses pour qu'une moyenne ait un sens : la croissance sur")
  print("  quarante ans de Stocks/I a une mediane de x10 et une moyenne de")
  print("  x140. 'conso/an' inclut la pension de Social Security.")
  print()

  print("=" * 96)
  print("TABLEAU 2 -- RISQUE")
  print("=" * 96)
  header = (f"{'strategie':<17}{'':>8}{'vol':>9}{'rendt/vol':>12}"
           f"{'ruine':>9}{'DD retraite':>14}")
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
    tag = "or" if name in PANEL_E else ("ajout" if name in PANEL_D else "")
    print(f"{name:<17}{tag:>8}{vol:>9.1%}{ratio:>12.2f}{ruin:>9.1%}"
          f"{dd:>14.1%}")
  print()
  print("Lecture : 'vol' est l'ecart-type des rendements annuels REELLEMENT")
  print("  traverses par le menage, pas celui de l'allocation cible -- un")
  print("  glidepath expose des actions jeune et des obligations agee.")
  print("  'rendt/vol' rapporte le rendement a ce risque : c'est la colonne qui")
  print("  repond a l'objection selon laquelle les strategies du papier ne")
  print("  portent pas le meme risque. 'ruine' est la probabilite d'epuiser le")
  print("  capital avant le deces du dernier survivant.")
  print()
  print("Les lignes marquees 'ajout' ne figurent pas dans le papier. Leur poche")
  print("actions suit un indice mondial et leur poche obligataire un panier de")
  print("quatre emetteurs souverains, comme les instruments cotes ; celles du")
  print("papier detiennent les actifs du pays de residence.")
  print()

  # Table X du papier, Panel A, block bootstrap sur l'echantillon developpe.
  PUBLISHED_RUIN = {
    "TDF": 0.169, "Balanced": 0.157, "Balanced/I": 0.109, "Age": 0.168,
    "Age/I": 0.133, "Bills": 0.357, "Stocks": 0.174, "Stocks/I": 0.082,
  }
  print("Probabilite de ruine, les huit strategies du papier (Table X) :")
  print(f"{'strategie':<12}{'notre JST':>12}{'papier':>10}{'ecart':>10}")
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
  print("Ecart de richesse mediane face au fonds a horizon (TDF) :")
  for name in order:
    if name == "TDF":
      continue
    median = statistics.median(r["retirement_wealth"] for r in results[name])
    reference = "   (papier : +30%)" if name == "Stocks" else (
      "   (papier : +32%)" if name == "Stocks/I" else "")
    print(f"  {name:<17}{median / tdf_median - 1:>+8.1%}{reference}")


if __name__ == "__main__":
  main()
