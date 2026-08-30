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

Le panier obligataire exige deux emetteurs au minimum. Cette regle conserve
1946 et 1947, ou seuls les Etats-Unis et le Royaume-Uni sont simultanement
disponibles, au lieu de supprimer ces annees de toutes les strategies.
"""

from __future__ import annotations

import csv
import math
import os

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


def build(
    panel: list[dict[str, str]],
    world: dict[int, dict[str, str]],
    trend_us_real: dict[int, float],
    trend_us_cash_real: dict[int, float],
    gold_us_real: dict[int, float],
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
    unhedged_bonds: list[float] = []
    unhedged_bills: list[float] = []
    for issuer in BOND_ISSUERS:
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
      unhedged_bonds.append(convert_local_real_return(
        issuer_bond, *arguments))
      unhedged_bills.append(convert_local_real_return(
        issuer_bill, *arguments))

    if len(covered_bonds) < MIN_BOND_ISSUERS:
      continue
    world_bond = sum(covered_bonds) / len(covered_bonds)
    world_bond = (1.0 + world_bond) * (1.0 - BOND_FEE) - 1.0
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
      "world_bill_real": world_bill,
      "world_bond_real_unhedged": world_bond_unhedged,
      "world_bill_real_unhedged": world_bill_unhedged,
      "world_bond_issuers": len(covered_bonds),
      "trend_real": trend_hedged,
      "trend_cash_us_real": trend_us_cash_real[year],
      "trend_real_unhedged": trend_unhedged,
      "gold_real": converted_gold,
    })
    if not all(math.isfinite(float(output[column])) for column in (
        "world_equity_real", "world_bond_real", "world_bill_real",
        "world_bond_real_unhedged", "world_bill_real_unhedged",
        "trend_real", "trend_cash_us_real", "trend_real_unhedged",
        "gold_real")):
      continue
    result.append(output)
  return result


def main() -> None:
  data = os.path.join(HERE, "..", "data")
  trend_path = os.path.join(data, "managed-futures-annual-real.csv")
  panel_path = os.path.join(data, "replication-panel.csv")
  out = os.path.join(data, "replication-panel-trend.csv")
  world_path = os.path.join(data, "jst-ntsg-panel-2025.csv")
  gold_path = os.path.join(data, "gold-annual.csv")

  trend_rows = read_rows(trend_path)
  trend = {int(row["year"]): float(row["trend_real"])
           for row in trend_rows}
  trend_cash = {int(row["year"]): float(row["cash_real"])
                for row in trend_rows}
  world = {int(row["year"]): row for row in read_rows(world_path)}
  gold = {int(row["year"]): float(row["gold_real"])
          for row in read_rows(gold_path)}
  rows = build(read_rows(panel_path), world, trend, trend_cash, gold)

  fieldnames = [
    "country", "year", "domestic_equity_real", "international_equity_real",
    "international_equity_real_constant_real_fx",
    "world_equity_real_resident_reconstructed", "xrusd",
    "world_equity_real", "world_equity_source", "bond_real", "bill_real",
    "world_bond_real", "world_bill_real", "world_bond_real_unhedged",
    "world_bill_real_unhedged", "world_bond_issuers", "inflation",
    "trend_real", "trend_cash_us_real", "trend_real_unhedged", "gold_real",
  ]
  with open(out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, lineterminator="\n", fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

  years = [int(row["year"]) for row in rows]
  issuers = sorted({int(row["world_bond_issuers"]) for row in rows})
  print(f"{len(rows)} pays-annees ({min(years)}-{max(years)}), "
        f"emetteurs obligataires {issuers} "
        f"-> {os.path.normpath(out)}")


if __name__ == "__main__":
  main()
