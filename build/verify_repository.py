#!/usr/bin/env python3
"""Verifie les invariants publics du depot apres une reconstruction complete."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
FIGURES = ROOT / "paper" / "figures"


def read_csv(name: str) -> list[dict[str, str]]:
  with (DATA / name).open(newline="", encoding="utf-8") as handle:
    return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
  return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
  if not condition:
    raise AssertionError(message)


def main() -> None:
  expected_rows = {
    "jst-real-returns-2025.csv": 2247,
    "international-equity.csv": 2319,
    "replication-panel.csv": 2233,
    "managed-futures-annual-real.csv": 99,
    "replication-panel-trend.csv": 1557,
  }
  for name, expected in expected_rows.items():
    rows = read_csv(name)
    require(len(rows) == expected, f"{name}: {len(rows)} lignes, attendu {expected}")
    require(all(all(value != "" for value in row.values()) for row in rows),
            f"{name}: cellule vide")

  panel = read_csv("replication-panel-trend.csv")
  require({int(row["year"]) for row in panel} == set(range(1927, 2026)),
          "le panel ne couvre pas chaque annee de 1927 a 2025")
  require(len({row["country"] for row in panel}) == 16,
          "le panel ne contient pas 16 pays")
  issuers = {int(row["world_bond_issuers"]) for row in panel}
  require(issuers == {12, 13, 14, 15, 16},
          f"nombre d'emetteurs obligataires inattendu: {sorted(issuers)}")

  main_core = read_json(RESULTS / "main_core_n10000.json")
  benchmark = next(row for row in main_core["results"]
                   if row["strategy"] == "ACO 33/67")
  grid = read_json(RESULTS / "grid_equity_n10000.json")
  grid_benchmark = next(row for row in grid["grid"]
                        if row["domestic_pct"] == 33.0)
  require(abs(100.0 * benchmark["ruin_probability"]
              - grid_benchmark["ruin_pct"]) <= 0.005,
          "grid search et experience principale divergent sur la ruine ACO")
  require(grid["argmax"]["domestic_pct"] == 30.0,
          "l'optimum du grid search n'est plus 30/70")

  audited_results = (
    "main_core_n10000.json", "main_ladders_n10000.json",
    "sensitivity_gold_unavailable_n10000.json",
    "window_1970_2025_n10000.json", "control_usa_n20000.json",
    "control_usa_ladders_n20000.json", "control_usd_common_n10000.json",
    "control_usd_numeraire_n10000.json",
  )
  for name in audited_results:
    payload = read_json(RESULTS / name)
    flags = payload.get("data_quality_flags", [])
    require("data_quality_exclusions" not in payload,
            f"{name}: ancien nom trompeur data_quality_exclusions")
    require(payload["included_suspect_data"] == bool(flags),
            f"{name}: included_suspect_data incoherent")

  canonical_metadata = {
    "main_core_n10000.json": (10_000, "full", "core"),
    "main_ladders_n10000.json": (10_000, "full", "ladders"),
    "control_usa_n20000.json": (20_000, "usa", "all"),
    "control_usa_ladders_n20000.json": (20_000, "usa", "ladders"),
    "control_usd_common_n10000.json": (10_000, "full", "all"),
    "control_usd_numeraire_n10000.json": (10_000, "full", "all"),
    "window_1970_2025_n10000.json": (10_000, "full", "all"),
    "sensitivity_gold_unavailable_n10000.json": (10_000, "full", "core"),
  }
  for name, expected in canonical_metadata.items():
    payload = read_json(RESULTS / name)
    actual = (payload["runs"], payload["sample_mode"], payload["portfolio_set"])
    require(actual == expected, f"{name}: metadonnees {actual}, attendu {expected}")
  require(read_json(FIGURES / "gamma_sensitivity.json")["runs_per_gamma"]
          == 10_000, "gamma_sensitivity.json: attendu 10 000 chemins")
  require(read_json(FIGURES / "historical_uncertainty.json")
          ["runs_per_specification"] == 5_000,
          "historical_uncertainty.json: attendu 5 000 chemins")

  expected_sources = {
    "ladders_main.tex": "results/main_ladders_n10000.json",
    "ladders_usa.tex": "results/control_usa_ladders_n20000.json",
  }
  for name, source in expected_sources.items():
    first_lines = "\n".join(
      (FIGURES / name).read_text(encoding="utf-8").splitlines()[:3])
    require(f"Source : {source}" in first_lines,
            f"{name}: provenance incorrecte")

  for name in ("frontier_n5000.txt", "spread_frontier_n10000.txt"):
    require((RESULTS / name).stat().st_size > 0, f"{name}: sortie absente ou vide")

  print("Verification du depot: OK")


if __name__ == "__main__":
  main()
