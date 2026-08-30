"""Assemble le panel a quatre classes d'actifs pour la replication fidele.

Anarkulova, Cederburg et O'Doherty comparent des strategies qui melangent
jusqu'a quatre classes d'actifs : actions domestiques, actions internationales,
obligations, bills. JST ne fournit nativement que les trois premieres (sous les
noms eq_tr, bond_tr, bill_rate) plus le CPI ; la serie d'actions internationales
est reconstruite dans international_equity.py, selon leur propre definition
(moyenne ponderee par PIB -- proxy de capitalisation -- des marches etrangers,
ajustee du change, deflatee par l'inflation locale).

Le panel conserve egalement le contrefactuel a change reel constant produit
par ``international_equity.py``. Il permet de comparer le benefice geographique
du panier etranger avant d'ajouter le canal change-inflation.

Ce module les assemble en un seul CSV par pays-annee, pret pour le bootstrap.
"""

from __future__ import annotations

import argparse
import csv
import os


def build(dta_path: str, international_path: str,
          extended_path: str | None = None) -> list[dict[str, float]]:
  import pandas as pd

  frame = pd.read_stata(dta_path)[
    ["year", "country", "eq_tr", "bond_tr", "bill_rate", "cpi"]].dropna()
  frame = frame.sort_values(["country", "year"])
  frame["inflation"] = frame.groupby("country", observed=True)["cpi"].pct_change()
  frame = frame.dropna(subset=["inflation"])
  frame = frame[frame["inflation"] > -1.0]

  domestic: dict[tuple[str, int], dict[str, float]] = {}
  for record in frame.itertuples(index=False):
    scale = 1.0 + record.inflation
    domestic[(record.country, int(record.year))] = {
      "domestic_equity_real": (1.0 + record.eq_tr) / scale - 1.0,
      "bond_real": (1.0 + record.bond_tr) / scale - 1.0,
      "bill_real": (1.0 + record.bill_rate) / scale - 1.0,
      "inflation": record.inflation,
    }

  international: dict[tuple[str, int], dict[str, float]] = {}
  with open(international_path, newline="", encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      international[(row["country"], int(row["year"]))] = {
        "observed": float(row["international_equity_real"]),
        "constant_real_fx": float(
          row["international_equity_real_constant_real_fx"]),
        "world_resident": float(row["world_equity_real_resident"]),
        "xrusd": float(row["resident_xrusd"]),
      }

  # Les annees posterieures a JST viennent du panel prolonge, qui porte deja
  # les rendements reels d'actions, d'obligations et de taux court pour
  # 2021-2025. Les bills y sont le taux court.
  if extended_path and os.path.exists(extended_path):
    with open(extended_path, newline="", encoding="utf-8") as handle:
      for row in csv.DictReader(handle):
        key = (row["country"], int(row["year"]))
        if key in domestic:
          continue
        domestic[key] = {
          "domestic_equity_real": float(row["equity_real"]),
          "bond_real": float(row["bond_real"]),
          "bill_real": float(row["short_real"]),
          "inflation": float(row["inflation"]),
        }

  rows: list[dict[str, float]] = []
  for (country, year), values in domestic.items():
    if (country, year) not in international:
      continue
    rows.append({
      "country": country, "year": year,
      "domestic_equity_real": values["domestic_equity_real"],
      "international_equity_real": international[(country, year)]["observed"],
      "international_equity_real_constant_real_fx":
        international[(country, year)]["constant_real_fx"],
      "world_equity_real_resident_reconstructed":
        international[(country, year)]["world_resident"],
      "xrusd": international[(country, year)]["xrusd"],
      "bond_real": values["bond_real"],
      "bill_real": values["bill_real"],
      "inflation": values["inflation"],
    })

  rows.sort(key=lambda r: (r["country"], r["year"]))
  return rows


def main() -> None:
  here = os.path.dirname(os.path.abspath(__file__))
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--dta", default=os.path.join(
    here, "..", "data", "JSTdatasetR6.dta"))
  parser.add_argument("--extended", default=os.path.join(
    here, "..", "data", "jst-real-returns-2025.csv"),
    help="panel prolonge 2021-2025, pour les classes autres qu'actions "
         "internationales")
  parser.add_argument("--international", default=os.path.join(
    here, "..", "data", "international-equity.csv"))
  parser.add_argument("--out", default=os.path.join(
    here, "..", "data", "replication-panel.csv"))
  args = parser.parse_args()

  rows = build(args.dta, args.international, args.extended)
  countries = {r["country"] for r in rows}
  years = {r["year"] for r in rows}
  print(f"{len(rows)} pays-annees, {len(countries)} pays, "
       f"{min(years)}-{max(years)}")

  with open(args.out, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=[
      "country", "year", "domestic_equity_real", "international_equity_real",
      "international_equity_real_constant_real_fx",
      "world_equity_real_resident_reconstructed", "xrusd", "bond_real",
      "bill_real", "inflation"])
    writer.writeheader()
    writer.writerows(rows)
  print(f"Ecrit dans {os.path.normpath(args.out)}")


if __name__ == "__main__":
  main()
