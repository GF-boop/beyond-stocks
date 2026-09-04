"""Complete le panel de replication dans le numeraire de chaque resident.

Toutes les poches d'une ligne pays-annee mesurent la variation du pouvoir
d'achat d'un menage qui reside dans ce pays. L'ancienne version attachait a
chaque pays des rendements mondiaux deflates par le CPI americain ou par le CPI
propre a chaque emetteur et melangeait donc des numeraires.

Les actions mondiales et l'or restent non couverts : leur rendement nominal est
converti dans la monnaie du resident, puis deflate par son inflation. Le cas
principal couvre en revanche les obligations mondiales et le managed futures.
Sous parite couverte des taux, il conserve l'exces de rendement de l'actif sur
son cash effectivement embarque dans la serie source et lui substitue le bill
reel du resident. Pour les obligations, ce cash est le bill de l'emetteur ;
pour le managed futures, c'est le collateral U.S. observe dans la serie source.
Le carry est donc explicite et le change spot ex post n'entre pas dans le cas
principal. Les versions non couvertes sont conservees dans des colonnes
separees pour sensibilite.

Le panier obligataire exige huit emetteurs au minimum. Sur la fenetre
1927--2025 ce plancher ne retire aucune observation : le panier effectivement
produit contient 12 a 16 souverains, dont 16 dans la grande majorite du panel.
"""

from __future__ import annotations

import csv
import math
import os
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
# Tous les souverains du panel entrent dans le panier, y compris celui du
# resident : un indice obligataire mondial reel contient bien la dette du pays
# de l'investisseur, et le panier reste alors identique pour tous les
# residents, ce que la parite couverte des taux impose. Un panier restreint aux
# quatre grands emetteurs porterait mal son nom et concentrerait la
# diversification sur une poignee d'histoires souveraines.
BOND_ISSUERS = (
  "Australia", "Belgium", "Denmark", "Finland", "France", "Germany",
  "Italy", "Japan", "Netherlands", "Norway", "Portugal", "Spain",
  "Sweden", "Switzerland", "UK", "USA",
)
# Huit emetteurs au minimum pour qu'une annee compte comme mondiale. Sur la
# fenetre 1927-2025 ce plancher ne coute aucune observation : les seules
# annees ecartees sont anterieures a 1882.
MIN_BOND_ISSUERS = 8
BOND_FEE = 0.001
EQUITY_FEE_BEFORE_1970 = 0.002
WORLD_FROM = 1970


def read_rows(path: str) -> list[dict[str, str]]:
  with open(path, newline="", encoding="utf-8") as handle:
    return list(csv.DictReader(handle))


def convert_local_real_return(
    local_real: float,
    issuer_inflation: float,
    issuer_fx: float,
    issuer_previous_fx: float,
    resident_inflation: float,
    resident_fx: float,
    resident_previous_fx: float,
    ) -> float:
  """Convertit un rendement reel local en rendement reel du resident."""
  nominal_local = (1.0 + local_real) * (1.0 + issuer_inflation) - 1.0
  currency = ((resident_fx / issuer_fx)
              / (resident_previous_fx / issuer_previous_fx))
  return (1.0 + nominal_local) * currency / (1.0 + resident_inflation) - 1.0


def convert_us_real_return(
    us_real: float,
    us_inflation: float,
    resident_inflation: float,
    resident_fx: float,
    resident_previous_fx: float,
    ) -> float:
  """Convertit un rendement reel USD en rendement reel du resident."""
  nominal_us = (1.0 + us_real) * (1.0 + us_inflation) - 1.0
  usd_currency_return = resident_fx / resident_previous_fx
  return ((1.0 + nominal_us) * usd_currency_return
          / (1.0 + resident_inflation) - 1.0)


def covered_real_return(asset_real: float, foreign_bill_real: float,
                        resident_bill_real: float) -> float:
  """Rendement reel couvert, carry inclus, sous parite couverte des taux."""
  if foreign_bill_real <= -1.0:
    raise ValueError("Le rendement du bill etranger doit etre superieur a -100 %")
  return ((1.0 + resident_bill_real)
          * (1.0 + asset_real) / (1.0 + foreign_bill_real) - 1.0)


def fixed_notional_hedged_real_return(
    asset_real: float, foreign_bill_real: float, resident_bill_real: float,
    foreign_inflation: float, resident_inflation: float,
    foreign_fx: float, foreign_previous_fx: float,
    resident_fx: float, resident_previous_fx: float,
    ) -> float:
  """Rendement reel d'un actif etranger avec forward sur le notionnel initial.

  La convention ``covered_real_return`` suppose implicitement que la valeur
  terminale de l'actif entier est couverte. Un fonds couvre plus usuellement le
  notionnel connu au debut de la periode, puis renouvelle le forward. Cette
  fonction ajoute donc le payoff du forward sur une unite de devise etrangere
  au rendement local realise. Le forward est valorise sous CIP a partir des
  bills nominaux observes; le reste de la valeur terminale garde un risque FX.
  """
  foreign_bill_nominal = ((1.0 + foreign_bill_real)
                          * (1.0 + foreign_inflation))
  resident_bill_nominal = ((1.0 + resident_bill_real)
                           * (1.0 + resident_inflation))
  asset_nominal = (1.0 + asset_real) * (1.0 + foreign_inflation)
  currency = ((resident_fx / foreign_fx)
              / (resident_previous_fx / foreign_previous_fx))
  gross_resident_nominal = (
      resident_bill_nominal / foreign_bill_nominal
      + (asset_nominal - 1.0) * currency)
  return gross_resident_nominal / (1.0 + resident_inflation) - 1.0


def build(
    panel: list[dict[str, str]],
    world: dict[int, dict[str, str]],
    trend_us_real: dict[int, float],
    trend_us_cash_real: dict[int, float],
    gold_us_real: dict[int, float],
    excluded_bond_issuers: frozenset[str] = frozenset(),
    excluded_bond_issuer_years: frozenset[tuple[str, int]] = frozenset(),
    ) -> list[dict[str, str | float]]:
  by_country_year = {
    (row["country"], int(row["year"])): row for row in panel
  }
  us_inflation = {
    year: float(row["inflation"])
    for (country, year), row in by_country_year.items()
    if country == "USA"
  }
  result: list[dict[str, str | float]] = []
  for row in panel:
    country = row["country"]
    year = int(row["year"])
    previous = by_country_year.get((country, year - 1))
    if (previous is None or year not in trend_us_real
        or year not in trend_us_cash_real
        or year not in gold_us_real or year not in us_inflation):
      continue

    resident_inflation = float(row["inflation"])
    resident_fx = float(row["xrusd"])
    resident_previous_fx = float(previous["xrusd"])
    if (resident_inflation <= -1.0 or resident_fx <= 0.0
        or resident_previous_fx <= 0.0):
      continue

    resident_bill = float(row["bill_real"])
    covered_bonds: list[float] = []
    fixed_notional_bonds: list[float] = []
    unhedged_bonds: list[float] = []
    unhedged_bills: list[float] = []
    for issuer in BOND_ISSUERS:
      if (issuer in excluded_bond_issuers
          or (issuer, year) in excluded_bond_issuer_years):
        continue
      issuer_row = by_country_year.get((issuer, year))
      issuer_previous = by_country_year.get((issuer, year - 1))
      if issuer_row is None or issuer_previous is None:
        continue
      issuer_fx = float(issuer_row["xrusd"])
      issuer_previous_fx = float(issuer_previous["xrusd"])
      if issuer_fx <= 0.0 or issuer_previous_fx <= 0.0:
        continue
      arguments = (
        float(issuer_row["inflation"]), issuer_fx, issuer_previous_fx,
        resident_inflation, resident_fx, resident_previous_fx,
      )
      issuer_bond = float(issuer_row["bond_real"])
      issuer_bill = float(issuer_row["bill_real"])
      covered_bonds.append(covered_real_return(
        issuer_bond, issuer_bill, resident_bill))
      fixed_notional_bonds.append(fixed_notional_hedged_real_return(
        issuer_bond, issuer_bill, resident_bill,
        float(issuer_row["inflation"]), resident_inflation,
        issuer_fx, issuer_previous_fx, resident_fx, resident_previous_fx))
      unhedged_bonds.append(convert_local_real_return(
        issuer_bond, *arguments))
      unhedged_bills.append(convert_local_real_return(
        issuer_bill, *arguments))

    if len(covered_bonds) < MIN_BOND_ISSUERS:
      continue
    world_bond = sum(covered_bonds) / len(covered_bonds)
    world_bond = (1.0 + world_bond) * (1.0 - BOND_FEE) - 1.0
    world_bond_fixed_notional = sum(fixed_notional_bonds) / len(fixed_notional_bonds)
    world_bond_fixed_notional = ((1.0 + world_bond_fixed_notional)
                                 * (1.0 - BOND_FEE) - 1.0)
    world_bill = resident_bill
    world_bond_unhedged = sum(unhedged_bonds) / len(unhedged_bonds)
    world_bond_unhedged = ((1.0 + world_bond_unhedged)
                           * (1.0 - BOND_FEE) - 1.0)
    world_bill_unhedged = sum(unhedged_bills) / len(unhedged_bills)

    if year >= WORLD_FROM and year in world:
      world_equity = convert_us_real_return(
        float(world[year]["equity_real"]), us_inflation[year],
        resident_inflation, resident_fx, resident_previous_fx)
      world_equity_source = "MSCI World, resident currency"
    else:
      world_equity = float(
        row["world_equity_real_resident_reconstructed"])
      world_equity = ((1.0 + world_equity)
                      * (1.0 - EQUITY_FEE_BEFORE_1970) - 1.0)
      world_equity_source = "reconstructed, resident currency"

    trend_hedged = covered_real_return(
      trend_us_real[year], trend_us_cash_real[year], resident_bill)
    trend_fixed_notional = fixed_notional_hedged_real_return(
      trend_us_real[year], trend_us_cash_real[year], resident_bill,
      us_inflation[year], resident_inflation,
      1.0, 1.0, resident_fx, resident_previous_fx)
    trend_unhedged = convert_us_real_return(
      trend_us_real[year], us_inflation[year], resident_inflation,
      resident_fx, resident_previous_fx)
    converted_gold = convert_us_real_return(
      gold_us_real[year], us_inflation[year], resident_inflation,
      resident_fx, resident_previous_fx)

    output = dict(row)
    output.update({
      "world_equity_real": world_equity,
      "world_equity_source": world_equity_source,
      "world_bond_real": world_bond,
      "world_bond_real_fixed_notional": world_bond_fixed_notional,
      "world_bill_real": world_bill,
      "world_bond_real_unhedged": world_bond_unhedged,
      "world_bill_real_unhedged": world_bill_unhedged,
      "world_bond_issuers": len(covered_bonds),
      "trend_real": trend_hedged,
      "trend_real_fixed_notional": trend_fixed_notional,
      "trend_cash_us_real": trend_us_cash_real[year],
      "trend_real_unhedged": trend_unhedged,
      "gold_real": converted_gold,
    })
    if not all(math.isfinite(float(output[column])) for column in (
        "world_equity_real", "world_bond_real", "world_bond_real_fixed_notional", "world_bill_real",
        "world_bond_real_unhedged", "world_bill_real_unhedged",
        "trend_real", "trend_real_fixed_notional", "trend_cash_us_real", "trend_real_unhedged",
        "gold_real")):
      continue
    result.append(output)
  return result


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--panel", help="input replication panel")
  parser.add_argument("--out", help="output extended panel")
  parser.add_argument("--trend", help="annual managed-futures input")
  parser.add_argument("--world", help="world-equity input")
  parser.add_argument("--gold", help="gold input")
  parser.add_argument("--exclude-bond-issuer", action="append", default=[],
                      help="remove an issuer from every global bond basket (repeatable)")
  parser.add_argument("--exclude-bond-issuer-year", action="append", default=[],
                      metavar="COUNTRY:YEAR",
                      help="diagnostic only: remove a source country-year from global bond baskets")
  args = parser.parse_args()
  data = os.path.join(HERE, "..", "data")
  trend_path = args.trend or os.path.join(data, "managed-futures-annual-real.csv")
  panel_path = args.panel or os.path.join(data, "replication-panel.csv")
  out = args.out or os.path.join(data, "replication-panel-trend.csv")
  world_path = args.world or os.path.join(data, "jst-ntsg-panel-2025.csv")
  gold_path = args.gold or os.path.join(data, "gold-annual.csv")

  trend_rows = read_rows(trend_path)
  trend = {int(row["year"]): float(row["trend_real"])
           for row in trend_rows}
  trend_cash = {int(row["year"]): float(row["cash_real"])
                for row in trend_rows}
  world = {int(row["year"]): row for row in read_rows(world_path)}
  gold = {int(row["year"]): float(row["gold_real"])
          for row in read_rows(gold_path)}
  unknown = sorted(set(args.exclude_bond_issuer) - set(BOND_ISSUERS))
  if unknown:
    raise ValueError(f"unknown bond issuer(s): {', '.join(unknown)}")
  excluded_bond_issuer_years = set()
  for value in args.exclude_bond_issuer_year:
    try:
      country, year = value.rsplit(":", 1)
      if country not in BOND_ISSUERS:
        raise ValueError(f"unknown bond issuer: {country}")
      excluded_bond_issuer_years.add((country, int(year)))
    except ValueError:
      raise
  rows = build(read_rows(panel_path), world, trend, trend_cash, gold,
               frozenset(args.exclude_bond_issuer),
               frozenset(excluded_bond_issuer_years))

  fieldnames = [
    "country", "year", "domestic_equity_real", "international_equity_real",
    "international_equity_real_constant_real_fx",
    "world_equity_real_resident_reconstructed", "xrusd",
    "world_equity_real", "world_equity_source", "bond_real", "bill_real",
    "world_bond_real", "world_bond_real_fixed_notional", "world_bill_real", "world_bond_real_unhedged",
    "world_bill_real_unhedged", "world_bond_issuers", "inflation",
    "trend_real", "trend_real_fixed_notional", "trend_cash_us_real", "trend_real_unhedged", "gold_real",
  ]
  with open(out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

  years = [int(row["year"]) for row in rows]
  issuers = sorted({int(row["world_bond_issuers"]) for row in rows})
  print(f"{len(rows)} pays-annees ({min(years)}-{max(years)}), "
        f"emetteurs obligataires {issuers} "
        f"-> {os.path.normpath(out)}")


if __name__ == "__main__":
  main()
