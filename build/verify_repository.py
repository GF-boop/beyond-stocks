#!/usr/bin/env python3
"""Verifie les invariants publics du depot apres une reconstruction complete."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from trend_costs import DEFAULT_TREND_COST, DEFAULT_TREND_FEE

from social_security import (
  MAX_TAXABLE_EARNINGS,
  average_indexed_monthly_earnings,
)


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
  capped_aime = average_indexed_monthly_earnings([200_000.0] * 35)
  require(capped_aime == MAX_TAXABLE_EARNINGS / 12.0,
          "le plafond des revenus taxables n'est pas applique a l'AIME")

  expected_rows = {
    "jst-real-returns-2025.csv": 2247,
    "international-equity.csv": 2324,
    "replication-panel.csv": 2237,
    "managed-futures-annual-real.csv": 99,
    "replication-panel-trend.csv": 1561,
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
  require(issuers == {13, 14, 15, 16},
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
  require(grid["argmax"]["domestic_pct"] == 25.0,
          "l'optimum du grid search n'est plus 25/75")

  audited_results = (
    "main_core_n10000.json", "main_ladders_n10000.json",
    "sensitivity_gold_unavailable_n10000.json",
    "window_1970_2025_n10000.json", "control_usa_n20000.json",
    "control_usa_ladders_n20000.json", "control_usd_common_n10000.json",
    "control_usd_numeraire_n10000.json",
  )
  for name in audited_results:
    payload = read_json(RESULTS / name)
    require(payload['trend_cost'] == DEFAULT_TREND_COST
            and payload['trend_fee'] == DEFAULT_TREND_FEE,
            f'{name}: obsolete MF costs')
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

  panel_hash = hashlib.sha256((DATA / 'replication-panel-trend.csv').read_bytes()).hexdigest()
  require(read_json(RESULTS / 'margin_call_n10000.json')['panel_sha256'] == panel_hash,
          'annual margin diagnostic uses an obsolete panel')
  require(read_json(RESULTS / 'panel_concentration/provenance.json')['raw_sha256'] == panel_hash,
          'concentration comparison uses an obsolete panel')
  monthly_hash = hashlib.sha256((DATA / 'managed-futures-monthly.csv').read_bytes()).hexdigest()
  require(read_json(RESULTS / 'margin_monthly/input_provenance.json')['mf_sha256'] == monthly_hash,
          'monthly margin diagnostic uses an obsolete MF series')
  baseline = {r['strategy']: r for r in read_json(RESULTS / 'main_ladders_n10000.json')['results']}
  full = {r['strategy']: r for r in read_json(RESULTS / 'panel_concentration/raw_n10000.json')['results']}
  for name, row in baseline.items():
    require(row == full[name], f'{name}: baseline and full-comparison outputs differ')
  current = {(r['country'], r['year']): r for r in panel}
  with (RESULTS / 'method_review/panel-filtered.csv').open() as handle:
    for row in csv.DictReader(handle):
      require(row == current[(row['country'], row['year'])],
              'frozen legacy membership contains obsolete returns')
  print("Verification du depot: OK")


if __name__ == "__main__":
  main()
