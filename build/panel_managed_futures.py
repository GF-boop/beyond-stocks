"""Convertit le proxy managed futures mensuel en serie annuelle reelle.

Le moteur `managed_futures/run_managed_futures.py` publie des rendements
**nominaux en USD** : son collateral est du cash USD et les P&L locaux sont
convertis au spot USD. Le panel des simulations, lui, raisonne entierement en
**reel**. Brancher l'un sur l'autre sans deflater injecterait un siecle
d'inflation americaine dans la poche de tendance.

Le deflateur retenu est donc le CPI **americain** mensuel, et non l'inflation
mondiale du panel NTSG : c'est la devise dans laquelle la poche est libellee
qui commande, pas la composition geographique de l'indice actions.

La deflation est faite **mois par mois avant composition**. Avec douze mois
complets et les memes bornes de CPI, elle est algebriquement equivalente a
la deflation du rendement nominal annuel compose par le ratio annuel de CPI.

La serie retenue est `mf_1_6_12_gross_return`, en **brut** : les frais et les
couts de transaction sont appliques en aval par les scripts de simulation (voir
`trend_costs.py`), ce qui evite un double comptage et garde `--trend-fee`
pilotable.

Entree : `data/managed-futures-monthly.csv` et `data/cpi-monthly.csv`.
Sortie : `data/managed-futures-annual-real.csv`.

Une annee n'est conservee que si ses douze mois sont presents. Aucune annee
partielle n'est fabriquee.
"""

from __future__ import annotations

import csv
import os
import statistics
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
TREND = DATA

VARIANT = "mf_1_6_12_gross_return"


def read_cpi(path: str) -> dict[str, float]:
  """Indice des prix mensuel americain, pour deflater les rendements USD."""
  with open(path, encoding="utf-8") as handle:
    return {row["month"]: float(row["cpi"])
            for row in csv.DictReader(handle) if row.get("cpi")}


def fill_isolated_gaps(cpi: dict[str, float]) -> tuple[dict[str, float], list[str]]:
  """Comble un mois de CPI isole par moyenne geometrique de ses voisins.

  Le BLS n'a pas publie octobre 2025 (interruption budgetaire) : sans ce seul
  mois, toute l'annee 2025 serait perdue alors que ses douze rendements MF
  existent. Seul un trou d'exactement un mois est comble, et jamais une borne
  de la serie : une lacune plus longue reste une lacune, et l'annee tombe.

  L'interpolation porte sur le deflateur, pas sur les donnees de marche : le
  snapshot canonique reste, lui, strictement sans interpolation.
  """
  filled = dict(cpi)
  patched: list[str] = []
  months = sorted(cpi)
  for index in range(1, len(months)):
    earlier, later = months[index - 1], months[index]
    if month_number(later) - month_number(earlier) != 2:
      continue
    missing = previous_month(later)
    filled[missing] = (cpi[earlier] * cpi[later]) ** 0.5
    patched.append(missing)
  return filled, patched


def month_number(month: str) -> int:
  year, part = month.split("-")
  return int(year) * 12 + int(part) - 1


def previous_month(month: str) -> str:
  number = month_number(month) - 1
  return f"{number // 12:04d}-{number % 12 + 1:02d}"


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--input", default=os.path.join(
      TREND, "managed-futures-monthly.csv"))
  parser.add_argument("--output", default=os.path.join(
      TREND, "managed-futures-annual-real.csv"))
  args = parser.parse_args()
  cpi, patched = fill_isolated_gaps(
      read_cpi(os.path.join(TREND, "cpi-monthly.csv")))

  monthly: dict[int, list[float]] = {}
  monthly_cash: dict[int, list[float]] = {}
  source = args.input
  with open(source, encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      nominal = row.get(VARIANT)
      if not nominal:
        continue
      month = row["month"]
      earlier = previous_month(month)
      if month not in cpi or earlier not in cpi:
        continue
      deflator = cpi[month] / cpi[earlier]
      real = (1.0 + float(nominal)) / deflator - 1.0
      monthly.setdefault(int(month[:4]), []).append(real)
      cash_nominal = row.get("mf_1_6_12_cash_collateral_return")
      if cash_nominal:
        cash_real = (1.0 + float(cash_nominal)) / deflator - 1.0
        monthly_cash.setdefault(int(month[:4]), []).append(cash_real)

  annual = {}
  annual_cash = {}
  for year, values in monthly.items():
    cash_values = monthly_cash.get(year, [])
    if len(values) != 12 or len(cash_values) != 12:
      continue
    compounded = 1.0
    for value in values:
      compounded *= 1.0 + value
    annual[year] = compounded - 1.0
    cash_compounded = 1.0
    for value in cash_values:
      cash_compounded *= 1.0 + value
    annual_cash[year] = cash_compounded - 1.0

  years = sorted(annual)
  out = args.output
  with open(out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["year", "trend_real", "cash_real"])
    for year in years:
      writer.writerow([year, annual[year], annual_cash[year]])

  values = [annual[year] for year in years]
  mean = statistics.fmean(values)
  volatility = statistics.stdev(values)
  print(f"{len(years)} annees ({years[0]}-{years[-1]}), "
        f"rendement reel {mean:.2%}, vol {volatility:.2%}, "
        f"Sharpe {mean / volatility:.2f}")
  if patched:
    print(f"CPI comble par interpolation ({len(patched)}) : "
          f"{', '.join(patched)}")
  print(f"Ecrit dans {os.path.normpath(out)}")


if __name__ == "__main__":
  main()
