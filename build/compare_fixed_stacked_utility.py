"""Panels de portefeuilles empiles fixes, sans calibrage retrospectif.

Les expositions sont definies avant lecture du panel et ne dependent d'aucune
volatilite estimee. Toutes les extensions conservent la meme poche actions que
le benchmark ACO : 33 % d'actions domestiques et 67 % d'actions
internationales du resident. Les autres briques sont les obligations
souveraines mondiales, l'or et le managed futures. L'exposition brute est
bornee a 200 % du capital. Les obligations et le managed futures sont couverts
dans la monnaie du resident avec carry ; une friction de couverture explicite
est retranchee. Le financement au-dela de 100 % coute le taux court du resident
plus le spread passe en argument.

Les quatre propositions principales sont :

* 2/3 d'un 90/60 et 1/3 de tendance : 60/40/33,33, brut 133,33 % ;
* 2/3 d'un 90/60 et 1/3 d'or : 60/40/33,33, brut 133,33 % ;
* 60 % d'un 90/60, 20 % tendance et 20 % or : 54/36/20/20, brut 130 % ;
* 90/60/25/25 : brut 200 %, soit le plafond de levier.

Deux echelles complementaires ajoutent des poids simples aux expositions
brutes 100 %, 125 %, 150 %, 175 % et 200 % : une famille proportionnelle a
60/40/25/25 et une famille equiponderee actions/obligations/or/tendance.
Elles sont fixes avant l'evaluation et ne ciblent aucune volatilite realisee.

Le script rapporte les moments historiques uniquement comme resultats. Ils ne
servent jamais a fixer les poids, le levier ou un multiplicateur de risque.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections.abc import Callable

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compare_gold_trend_equal_vol import (  # noqa: E402
  DEFAULT_TREND_COST,
  DEFAULT_TREND_FEE,
)
from compare_lifecycle_utility import (  # noqa: E402
  BASE_SAVINGS_RATE,
  GAMMA,
  WITHDRAWAL_RATE,
  build_scenario,
  draw_death_age,
  equivalent_savings_rate,
  evaluate_batch,
  expected_utility,
)
from income_process import draw_household_income  # noqa: E402
from mortality import table as mortality_table  # noqa: E402
from data_quality import exclusion_reason  # noqa: E402
from investability import exclusion_reason as investability_reason  # noqa: E402
from replicate_extended import (  # noqa: E402
  MAX_AGE,
  START_AGE,
  block_bootstrap,
  read_panel,
)
from war_periods import is_war_year  # noqa: E402


ReturnFunction = Callable[[dict[str, float]], float]
MAX_GROSS_EXPOSURE = 2.0
DEFAULT_SPREAD = 0.003
DEFAULT_FX_HEDGE_COST = 0.001
DESIGN_PATH = os.path.join(HERE, "..", "data", "fixed-stacked-design.json")
BENCHMARK_NAME = "ACO 33/67"
CORE_EXPOSURE_NAMES = {
  "60/40 ACO/couvert",
  "60/40 ACO + 33.33 MF",
  "60/40 ACO + 33.33 Or",
  "54/36/20/20 ACO",
  "90/60/25/25 ACO",
}


def load_fixed_exposures() -> dict[str, tuple[float, float, float, float]]:
  """Charge l'unique manifeste gele, sans option de recalibrage."""
  with open(DESIGN_PATH, encoding="utf-8") as handle:
    design = json.load(handle)
  if design.get("calibrated_from_returns") is not False:
    raise ValueError("Le manifeste doit interdire le calibrage sur rendements")
  if design.get("exposure_order") != [
      "aco_33_67_equity", "world_bond", "gold", "managed_futures"]:
    raise ValueError("Toutes les extensions doivent conserver les actions ACO 33/67")
  if not math.isclose(float(design["max_gross_exposure"]),
                      MAX_GROSS_EXPOSURE):
    raise ValueError("Le plafond du manifeste doit rester fixe a 2x")
  exposures = {}
  for portfolio in design["portfolios"]:
    values = tuple(float(value) for value in portfolio["exposures"])
    if len(values) != 4:
      raise ValueError("Chaque portefeuille doit avoir quatre expositions")
    exposures[str(portfolio["name"])] = values
  return exposures


# L'ordre du manifeste est celui des panels et constitue le design gele.
FIXED_EXPOSURES = load_fixed_exposures()


def validate_design() -> None:
  for name, exposures in FIXED_EXPOSURES.items():
    if any(exposure < 0.0 for exposure in exposures):
      raise ValueError(f"Exposition negative interdite : {name}")
    gross = sum(exposures)
    if gross > MAX_GROSS_EXPOSURE + 1e-12:
      raise ValueError(
        f"{name} depasse le plafond de {MAX_GROSS_EXPOSURE:.0f}x : {gross:.3f}x")


def empirical_quantile(values: list[float], probability: float) -> float:
  """Quantile lineaire, sans dependance externe."""
  ordered = sorted(values)
  position = probability * (len(ordered) - 1)
  lower = int(math.floor(position))
  upper = int(math.ceil(position))
  if lower == upper:
    return ordered[lower]
  weight = position - lower
  return ordered[lower] + weight * (ordered[upper] - ordered[lower])


def return_functions(rows: list[dict[str, float]], spread: float,
                     trend_fee: float, trend_cost: float,
                     trend_haircut: float, fx_hedge_cost: float,
                     gold_reallocation_from_year: int | None = None,
                    include_unhedged_control: bool = False,
                    include_constant_real_fx: bool = True,
                    hedge_mode: str = "fixed_notional",
                    ) -> dict[str, ReturnFunction]:
  """Construit les rendements sans estimer aucun poids ni levier."""
  if hedge_mode not in {"ideal", "fixed_notional"}:
    raise ValueError("hedge_mode must be ideal or fixed_notional")
  bond_key = "world_bond" if hedge_mode == "ideal" else "world_bond_fixed_notional"
  trend_key = "trend" if hedge_mode == "ideal" else "trend_fixed_notional"
  # Apply the fee and turnover cost to the selected gross return convention.
  selected_trend = [row[trend_key] for row in rows]
  net_trend = [
    (1.0 + value) * (1.0 - trend_fee) - 1.0 - trend_cost - trend_haircut
    for value in selected_trend
  ]
  trend_by_row = {id(row): value for row, value in zip(rows, net_trend)}
  functions: dict[str, ReturnFunction] = {
    "Actions domestiques": lambda row: row["domestic"],
    "ACO 33/67": lambda row: (
      0.33 * row["domestic"] + 0.67 * row["international"]),
    "Stocks/I": lambda row: 0.5 * (row["domestic"] + row["international"]),
    "Balanced domestique": lambda row: (
      0.6 * row["domestic"] + 0.4 * row["bond"]),
    "Balanced/I": lambda row: (
      0.3 * row["domestic"] + 0.3 * row["international"]
      + 0.4 * row["bond"]),
    # Comparateur fixe et non optimise : la branche actions reprend exactement
    # le 33/67 d'ACO ; obligations et financement restent ceux du resident.
    "90/60 local fixe": lambda row: (
      0.9 * (0.33 * row["domestic"] + 0.67 * row["international"])
      + 0.6 * row["bond"] - 0.5 * row["bill"] - 0.5 * spread),
    # Test d'identification : meme poche actions et memes poids que le
    # comparateur local ; seuls les obligations couvertes sont mondialisees.
    "90/60 oblig. mondiales": lambda row: (
      0.9 * (0.33 * row["domestic"] + 0.67 * row["international"])
      + 0.6 * row[bond_key] - 0.5 * row["world_bill"] - 0.5 * spread
      - 0.6 * fx_hedge_cost),
  }

  # Le contrefactuel de change reel constant n'est defini que lorsque chaque
  # ligne est deja dans le numeraire de son resident. Il n'a pas de sens apres
  # conversion des memes etats dans un dollar fixe.
  if include_constant_real_fx:
    functions["ACO 33/67, change reel cst"] = lambda row: (
      0.33 * row["domestic"]
      + 0.67 * row["international_constant_real_fx"])

  if include_unhedged_control:
    # Controle secondaire : meme test, mais au change spot ex post. Il ne
    # definit ni le cas principal ni les portefeuilles multi-actifs.
    functions["90/60 oblig. non couvert"] = lambda row: (
      0.9 * (0.33 * row["domestic"] + 0.67 * row["international"])
      + 0.6 * row["world_bond_unhedged"]
      - 0.5 * row["world_bill_unhedged"] - 0.5 * spread)

  for name, exposures in FIXED_EXPOSURES.items():
    equity, bond, gold, trend = exposures
    gross = sum(exposures)
    # Les rendements obligataires et tendance sont couverts avec carry. Le
    # poids cash negatif retire le taux court du resident sur le notionnel
    # empile avant d'ajouter le spread ; la friction de change est facturee sur
    # les seules poches couvertes. L'or et les actions restent non couverts.
    cash_weight = 1.0 - gross
    borrowing = max(0.0, gross - 1.0)

    def calculate(row: dict[str, float], *, e=equity, b=bond, g=gold,
                  t=trend, cash=cash_weight, debt=borrowing,
                  cutoff=gold_reallocation_from_year) -> float:
      # Avant 1968, le prix de l'or est administre. Dans la variante
      # d'indisponibilite, son notionnel est redistribue a parts egales entre
      # les sleeves non-or deja presents dans la recette. Le levier total et
      # le financement sont ainsi inchanges, sans introduire une nouvelle
      # classe d'actifs dans un portefeuille qui ne la detenait pas.
      if g > 0.0 and cutoff is not None and row["year"] < cutoff:
        active_non_gold = sum(weight > 0.0 for weight in (e, b, t))
        if active_non_gold == 0:
          raise ValueError("Une poche or doit avoir au moins un sleeve actif")
        reallocated = g / active_non_gold
        effective_equity = e + (reallocated if e > 0.0 else 0.0)
        effective_bond = b + (reallocated if b > 0.0 else 0.0)
        effective_gold = 0.0
        effective_trend = t + (reallocated if t > 0.0 else 0.0)
      else:
        effective_equity = e
        effective_bond = b
        effective_gold = g
        effective_trend = t
      aco_equity = 0.33 * row["domestic"] + 0.67 * row["international"]
      return (effective_equity * aco_equity
              + effective_bond * row[bond_key]
              + effective_gold * row["gold"]
              + effective_trend * trend_by_row[id(row)]
              + cash * row["world_bill"]
              - debt * spread
              - (b + t) * fx_hedge_cost)

    functions[name] = calculate
  return functions


def _fixed_numeraire_unhedged_return(
    return_source: float, inflation_source: float,
    source_xrusd_previous: float, source_xrusd_current: float,
    target_xrusd_previous: float, target_xrusd_current: float,
    inflation_target: float) -> float:
  """Convertit un rendement reel source en rendement reel du pays cible.

  ``xrusd`` est le nombre d'unites de devise par dollar. Le facteur de change
  d'une position en devise source, vu depuis la devise cible, est donc
  ``(x_cible,t / x_source,t) / (x_cible,t-1 / x_source,t-1)``. Cette fonction
  est employee pour les poches non couvertes seulement.
  """
  return ((1.0 + return_source) * (1.0 + inflation_source)
          * (target_xrusd_current / source_xrusd_current)
          / (target_xrusd_previous / source_xrusd_previous)
          / (1.0 + inflation_target) - 1.0)


def _fixed_numeraire_covered_return(return_source: float, source_bill: float,
                                    target_bill: float) -> float:
  """Remplace le bill source par celui du pays cible dans une poche couverte."""
  return ((1.0 + target_bill) * (1.0 + return_source)
          / (1.0 + source_bill) - 1.0)


def fixed_numeraire_rows(rows: list[dict[str, float]],
                         target_country: str) -> list[dict[str, float]]:
  """Conserve les etats pays-annee mais impose le numeraire d'un pays cible.

  Le pays source continue de definir les blocs et les actifs dits ``domestic``
  et ``international``. Le controle ne represente donc pas un portefeuille
  domestique litteral dans le pays cible : il isole le changement de numeraire
  dans le bootstrap ACO. Les poches couvertes conservent leur rendement en
  exces, mais sont recombinees avec le bill cible; les poches non couvertes sont
  converties au comptant puis deflatees par le CPI cible.
  """
  target_by_year = {
    row["year"]: row for row in rows if row["country"] == target_country
  }
  if not target_by_year:
    raise ValueError(f"Pays de numeraire absent du panel : {target_country}")
  by_country_year = {(row["country"], row["year"]): row for row in rows}
  converted = []
  for row in rows:
    previous = by_country_year.get((row["country"], row["year"] - 1))
    target = target_by_year.get(row["year"])
    target_previous = target_by_year.get(row["year"] - 1)
    if previous is None or target is None or target_previous is None:
      continue
    values = (row["xrusd"], previous["xrusd"], target["xrusd"],
              target_previous["xrusd"], row["inflation"],
              target["inflation"], row["bill"], target["bill"])
    if not all(math.isfinite(value) for value in values):
      continue
    if any(1.0 + value <= 0.0 for value in
           (row["inflation"], target["inflation"], row["bill"],
            target["bill"])):
      continue

    def unhedged(key: str) -> float:
      return _fixed_numeraire_unhedged_return(
        row[key], row["inflation"], previous["xrusd"], row["xrusd"],
        target_previous["xrusd"], target["xrusd"], target["inflation"])

    item = dict(row)
    item.update({
      "domestic": unhedged("domestic"),
      "international": unhedged("international"),
      "bond": unhedged("bond"),
      "bill": target["bill"],
      "inflation": target["inflation"],
      "world_equity": unhedged("world_equity"),
      "world_bond": _fixed_numeraire_covered_return(
        row["world_bond"], row["world_bill"], target["bill"]),
      "world_bill": target["bill"],
      "world_bond_unhedged": unhedged("world_bond_unhedged"),
      "world_bill_unhedged": unhedged("world_bill_unhedged"),
      "trend": _fixed_numeraire_covered_return(
        row["trend"], row["world_bill"], target["bill"]),
      "trend_unhedged": unhedged("trend_unhedged"),
      "gold": unhedged("gold"),
    })
    converted.append(item)
  return converted


def usd_numeraire_rows(rows: list[dict[str, float]]) -> list[dict[str, float]]:
  """Alias de compatibilite pour le controle a numeraire USD fixe."""
  return fixed_numeraire_rows(rows, "USA")


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", default=os.path.join(
    HERE, "..", "data", "replication-panel-trend.csv"))
  parser.add_argument("--runs", type=int, default=20_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--mean-block", type=float, default=10.0)
  parser.add_argument("--spread", type=float, default=DEFAULT_SPREAD)
  parser.add_argument("--fx-hedge-cost", type=float,
                      default=DEFAULT_FX_HEDGE_COST)
  parser.add_argument("--hedge-mode", choices=("ideal", "fixed_notional"),
                      default="fixed_notional",
                      help="fixed_notional hedges beginning-of-year FX notional; ideal is the legacy full-value CIP convention")
  parser.add_argument("--bootstrap-end-treatment", choices=("aco", "restart"),
                      default="aco",
                      help="aco completes a truncated block at a new country's first year; restart is the legacy implementation")
  parser.add_argument("--trend-fee", type=float, default=DEFAULT_TREND_FEE)
  parser.add_argument("--trend-cost", type=float, default=DEFAULT_TREND_COST)
  parser.add_argument("--trend-haircut", type=float, default=0.0)
  parser.add_argument("--withdrawal-rate", type=float,
                      default=WITHDRAWAL_RATE)
  parser.add_argument("--gamma", type=float, default=GAMMA)
  parser.add_argument("--year-from", type=int)
  parser.add_argument("--year-to", type=int)
  parser.add_argument("--exclude-country", action="append", default=[])
  parser.add_argument("--exclude-country-year", action="append", default=[],
                      metavar="COUNTRY:YEAR",
                      help="diagnostic only: remove a resident country-year from the bootstrap panel")
  parser.add_argument(
    "--portfolio-set", choices=("all", "core", "ladders"), default="all",
    help=("all (defaut) evalue toutes les recettes ; core produit les tableaux "
          "principaux ; ladders produit seulement les deux echelles de levier"))
  parser.add_argument(
    "--sample-mode", choices=("investable", "usa", "full"),
    default="full",
    help=("full (defaut) conserve le panel historique integral ; investable "
          "applique le filtre de negociabilite ; usa "
          "simule uniquement un resident americain ; full conserve tout le "
          "panel"))
  parser.add_argument("--usd-numeraire", action="store_true",
                      help=("conserve les blocs internationaux mais convertit "
                            "toutes les poches dans le dollar reel et finance "
                            "au bill americain"))
  parser.add_argument("--usd-common-sample", action="store_true",
                      help=("restreint le panel resident au sous-echantillon "
                            "convertible en dollars reels, pour une comparaison "
                            "appariee avec --usd-numeraire"))
  parser.add_argument("--exclude-war-years", action="store_true",
                      help="retire les conflits et ruptures monetaires "
                           "documentes, pays par pays")
  parser.add_argument("--include-suspect-data", action="store_true",
                      help="alias historique de --sample-mode full")
  parser.add_argument("--include-unhedged-control", action="store_true",
                      help="ajoute le controle obligations et cash etrangers "
                      "nus ; robustesse uniquement")
  parser.add_argument(
    "--reallocate-administered-gold-from", type=int,
    help=("a partir de cette annee, l'or redevient disponible ; avant cette "
          "date, sa poche est repartie egalement entre les sleeves non-or "
          "actifs (variante d'indisponibilite)"))
  parser.add_argument("--output-json",
                      help="sortie machine-readable optionnelle")
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs doit etre strictement positif")
  if args.spread < 0.0:
    raise ValueError("--spread ne peut pas etre negatif")
  if args.fx_hedge_cost < 0.0:
    raise ValueError("--fx-hedge-cost ne peut pas etre negatif")
  if (args.usd_numeraire or args.usd_common_sample) and args.sample_mode == "usa":
    raise ValueError("Le controle USD est redondant avec --sample-mode usa")
  validate_design()

  rows = read_panel(args.panel)
  sample_mode = "full" if args.include_suspect_data else args.sample_mode
  quality_flags = [
    {"country": row["country"], "year": row["year"],
     "reason": exclusion_reason(row["country"], row["year"])}
    for row in rows
    if exclusion_reason(row["country"], row["year"]) is not None
  ]
  investability_exclusions = [
    {"country": row["country"], "year": row["year"],
     "inflation": row["inflation"],
     "reason": investability_reason(
       row["country"], row["year"], row["inflation"])}
    for row in rows
    if investability_reason(row["country"], row["year"], row["inflation"])
    is not None
  ]
  if sample_mode == "investable":
    rows = [
      row for row in rows
      if investability_reason(row["country"], row["year"], row["inflation"])
      is None
    ]
  elif sample_mode == "usa":
    rows = [row for row in rows if row["country"] == "USA"]
  if args.year_from is not None:
    rows = [row for row in rows if row["year"] >= args.year_from]
  if args.year_to is not None:
    rows = [row for row in rows if row["year"] <= args.year_to]
  excluded = set(args.exclude_country)
  excluded_country_years = set()
  for value in args.exclude_country_year:
    try:
      country, year = value.rsplit(":", 1)
      excluded_country_years.add((country, int(year)))
    except ValueError as error:
      raise ValueError("--exclude-country-year must be COUNTRY:YEAR") from error
  if excluded:
    rows = [row for row in rows if row["country"] not in excluded]
  if excluded_country_years:
    rows = [row for row in rows
            if (row["country"], row["year"]) not in excluded_country_years]
  if args.exclude_war_years:
    rows = [row for row in rows
            if not is_war_year(row["country"], row["year"])]
  source_observations = len(rows)
  if args.usd_numeraire or args.usd_common_sample:
    converted_rows = usd_numeraire_rows(rows)
    if args.usd_numeraire:
      rows = converted_rows
    else:
      converted_keys = {(row["country"], row["year"]) for row in converted_rows}
      rows = [row for row in rows
              if (row["country"], row["year"]) in converted_keys]
  if len(rows) < 2:
    raise ValueError("La fenetre demandee ne contient pas assez de donnees")
  included_keys = {(row["country"], row["year"]) for row in rows}
  quality_flags = [
    flag for flag in quality_flags
    if (flag["country"], flag["year"]) in included_keys
  ]
  functions = return_functions(
    rows, args.spread, args.trend_fee, args.trend_cost, args.trend_haircut,
    args.fx_hedge_cost, args.reallocate_administered_gold_from,
    args.include_unhedged_control, not args.usd_numeraire, args.hedge_mode)
  if args.portfolio_set != "all":
    baseline_names = {
      "Actions domestiques", "ACO 33/67", "Stocks/I",
      "Balanced domestique", "Balanced/I", "90/60 local fixe",
      "90/60 oblig. mondiales", "ACO 33/67, change reel cst",
      "90/60 oblig. non couvert",
    }
    if args.portfolio_set == "core":
      allowed = baseline_names | CORE_EXPOSURE_NAMES
    else:
      allowed = {BENCHMARK_NAME} | (set(FIXED_EXPOSURES) - CORE_EXPOSURE_NAMES)
    functions = {name: function for name, function in functions.items()
                 if name in allowed}

  print("PANEL A -- DESIGN FIXE EX ANTE (aucun ciblage de volatilite)")
  if sample_mode == "investable":
    print("Echantillon central investissable : "
          f"{len(investability_exclusions)} pays-annees exclus selon des "
          "criteres documentes.")
  elif sample_mode == "usa":
    print("Controle coherent : resident USA, rendements et flux en dollars reels.")
  else:
    print("Stress historique integral : aucune exclusion d'investissabilite.")
  if args.usd_numeraire:
    print("Controle de numeraire : memes blocs pays-annee, toutes les poches "
          "en dollars reels; bill americain. "
          f"{len(rows)}/{source_observations} observations convertibles.")
  elif args.usd_common_sample:
    print("Echantillon apparie au controle de numeraire USD : "
          f"{len(rows)}/{source_observations} observations convertibles.")
  print(f"{'strategie':<24}{'actions':>10}{'oblig.':>10}{'or':>9}"
        f"{'MF':>9}{'brut':>9}{'emprunt':>10}")
  print("-" * 81)
  print(f"{'ACO 33/67':<24}{'100%*':>10}{'0.0%':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  print(f"{'Stocks/I 50/50':<24}{'100%*':>10}{'0.0%':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  print(f"{'Actions domestiques':<24}{'100%**':>10}{'0.0%':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  if not args.usd_numeraire:
    print(f"{'ACO 33/67, change cst':<24}{'100%****':>10}{'0.0%':>10}{'0.0%':>9}"
          f"{'0.0%':>9}{'100.0%':>9}{'0.0%':>10}")
  print(f"{'90/60 local fixe':<24}{'90%*':>10}{'60%**':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'150.0%':>9}{'50.0%':>10}")
  print(f"{'90/60 oblig. mondiales':<24}{'90%*':>10}{'60%***':>10}{'0.0%':>9}"
        f"{'0.0%':>9}{'150.0%':>9}{'50.0%':>10}")
  if args.include_unhedged_control:
    print(f"{'90/60 oblig. non cvt':<24}{'90%*':>10}{'60%*****':>10}{'0.0%':>9}"
          f"{'0.0%':>9}{'150.0%':>9}{'50.0%':>10}")
  for name, (equity, bond, gold, trend) in FIXED_EXPOSURES.items():
    gross = equity + bond + gold + trend
    print(f"{name:<24}{equity:>10.1%}{bond:>10.1%}{gold:>9.1%}"
          f"{trend:>9.1%}{gross:>9.1%}{max(0.0, gross - 1.0):>10.1%}")
  print("* ACO 33/67 est le portefeuille fixe optimal de la revision 2025 ;")
  print("  toutes les extensions conservent cette meme poche actions.")
  print("  Stocks/I conserve la convention historique 50/50 comme controle.")
  print("** Exposition domestique au pays de residence de la trajectoire.")
  print("*** Obligations mondiales couvertes ; bill du resident ; actions inchangees.")
  if not args.usd_numeraire:
    print("**** 33/67 domestique/international, change reel neutralise ; contrefactuel.")
  if args.include_unhedged_control:
    print("***** Controle secondaire au change spot, non couvert.")
  print()

  pooled = {name: [function(row) for row in rows]
            for name, function in functions.items()}
  moment_by_name = {}
  for name, values in pooled.items():
    worst_index = min(range(len(rows)), key=lambda index: values[index])
    worst_row = rows[worst_index]
    moment_by_name[name] = {
      "mean_return": statistics.fmean(values),
      "volatility": statistics.stdev(values),
      "first_percentile_return": empirical_quantile(values, 0.01),
      "worst_year": values[worst_index],
      "worst_country": worst_row["country"],
      "worst_calendar_year": worst_row["year"],
    }
  print("PANEL B -- MOMENTS REALISES (evaluation, jamais calibrage)")
  print(f"{'strategie':<24}{'rendement':>12}{'volatilite':>13}"
        f"{'pct. 1 %':>12}{'minimum (pays-annee)':>27}")
  print("-" * 88)
  for name, values in pooled.items():
    moment = moment_by_name[name]
    event = (f"{moment['worst_year']:.2%} "
             f"({moment['worst_country']} {moment['worst_calendar_year']})")
    print(f"{name:<24}{statistics.fmean(values):>12.2%}"
          f"{statistics.stdev(values):>13.2%}"
          f"{moment['first_percentile_return']:>12.2%}{event:>27}")
  print()

  female_survival = mortality_table("female", "ssa")
  male_survival = mortality_table("male", "ssa")
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(args.seed)
  scenarios = []
  income_at_25: list[float] = []
  income_at_47: list[float] = []
  for _ in range(args.runs):
    path = block_bootstrap(rows, horizon, rng, args.mean_block,
                           args.bootstrap_end_treatment)
    female_death = draw_death_age(female_survival, rng)
    male_death = draw_death_age(male_survival, rng)
    female_income, male_income, household_income = draw_household_income(rng)
    income_at_25.append(household_income[0])
    income_at_47.append(household_income[47 - START_AGE])
    scenarios.append(build_scenario(
      path, functions, female_death, male_death,
      female_income, male_income))

  target_utility = expected_utility(
    scenarios, BENCHMARK_NAME, BASE_SAVINGS_RATE, args.gamma,
    args.withdrawal_rate)
  print("PANEL C -- CYCLE DE VIE, CRRA ET EPARGNE EQUIVALENTE")
  print(f"{args.runs} trajectoires appariees ; blocs {args.mean_block:g} ans ; "
        f"spread {args.spread:.2%} ; gamma {args.gamma:g}")
  print(f"MF nets de frais {args.trend_fee:.2%}, couts {args.trend_cost:.2%} "
        f"et haircut {args.trend_haircut:.2%}")
  print(f"Obligations et MF couverts ; friction de change "
        f"{args.fx_hedge_cost:.2%}")
  if args.reallocate_administered_gold_from is not None:
    print("Or indisponible avant "
          f"{args.reallocate_administered_gold_from} : notionnel reparti "
          "egalement entre sleeves non-or actifs.")
  print(f"Controle revenu median : age 25 "
        f"{statistics.median(income_at_25):,.0f}, age 47 "
        f"{statistics.median(income_at_47):,.0f}".replace(",", " "))
  print()
  print(f"Reference d'utilite : {BENCHMARK_NAME} avec 10 % d'epargne.")
  print(f"{'strategie':<27}{'epargne eq.':>12}{'richesse med.':>16}"
        f"{'conso moy.':>13}{'ruine':>9}  {'delta [IC95]':>22}"
        f"{'legs med.':>14}")
  print("-" * 113)
  outcomes_by_name = {
    name: evaluate_batch(scenarios, name, BASE_SAVINGS_RATE,
                         args.withdrawal_rate, args.gamma)
    for name in functions
  }
  benchmark_ruin = outcomes_by_name[BENCHMARK_NAME].ruined.astype(float)
  machine_results = []
  for name in functions:
    outcomes = outcomes_by_name[name]
    equivalent = equivalent_savings_rate(
      scenarios, name, target_utility, args.gamma, args.withdrawal_rate)
    equivalent_text = (
      "hors borne" if math.isnan(equivalent) else f"{equivalent:.2%}")
    retirement = float(np.median(outcomes.retirement_wealth))
    consumption = float(np.mean(outcomes.retirement_consumption))
    ruin = float(np.mean(outcomes.ruined))
    differences = [
      float(outcome) - reference
      for outcome, reference in zip(outcomes.ruined, benchmark_ruin)
    ]
    delta = statistics.fmean(differences)
    standard_error = (statistics.stdev(differences) / math.sqrt(len(differences))
                      if len(differences) > 1 else 0.0)
    low = delta - 1.96 * standard_error
    high = delta + 1.96 * standard_error
    interval = f"{delta:+.2%} [{low:+.2%};{high:+.2%}]"
    bequest = float(np.median(outcomes.bequest))
    line = (f"{name:<27}{equivalent_text:>12}{retirement:>16,.0f}"
            f"{consumption:>13,.0f}{ruin:>9.2%}  {interval:>22}"
            f"{bequest:>14,.0f}")
    print(line.replace(",", " "))
    machine_results.append({
      "strategy": name,
      **moment_by_name[name],
      "equivalent_savings_rate": None if math.isnan(equivalent) else equivalent,
      "median_retirement_wealth": retirement,
      "mean_retirement_consumption": consumption,
      "ruin_probability": ruin,
      "ruin_difference_vs_benchmark": delta,
      "ruin_difference_ci95": [low, high],
      "median_bequest": bequest,
    })

  if args.output_json:
    payload = {
      "seed": args.seed,
      "runs": args.runs,
      "mean_block": args.mean_block,
      "bootstrap_end_treatment": args.bootstrap_end_treatment,
      "spread": args.spread,
      "fx_hedge_cost": args.fx_hedge_cost,
      "hedge_mode": args.hedge_mode,
      "trend_fee": args.trend_fee,
      "trend_cost": args.trend_cost,
      "trend_haircut": args.trend_haircut,
      "gold_reallocation_from_year": args.reallocate_administered_gold_from,
      "withdrawal_rate": args.withdrawal_rate,
      "gamma": args.gamma,
      "year_from": args.year_from,
      "year_to": args.year_to,
      "excluded_countries": sorted(excluded),
      "excluded_country_years": [
        {"country": country, "year": year}
        for country, year in sorted(excluded_country_years)
      ],
      "excluded_war_years": args.exclude_war_years,
      "included_suspect_data": bool(quality_flags),
      "sample_mode": sample_mode,
      "portfolio_set": args.portfolio_set,
      "usd_numeraire": args.usd_numeraire,
      "usd_common_sample": args.usd_common_sample,
      "source_observations": source_observations,
      "included_unhedged_control": args.include_unhedged_control,
      "data_quality_flags": quality_flags,
      "investability_exclusions": investability_exclusions,
      "observations": len(rows),
      "benchmark": BENCHMARK_NAME,
      "results": machine_results,
    }
    with open(args.output_json, "w", encoding="utf-8") as handle:
      json.dump(payload, handle, ensure_ascii=False, indent=2)
      handle.write("\n")


if __name__ == "__main__":
  main()
