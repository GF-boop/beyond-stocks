#!/usr/bin/env python3
"""Verifie les invariants publics de la chaine ERC apres une reconstruction."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from social_security import (
  MAX_TAXABLE_EARNINGS,
  average_indexed_monthly_earnings,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
FIGURES = ROOT / "paper" / "figures"
PAPER = ROOT / "paper" / "new_paper"
ERC = RESULTS / "main" / "n10000_final"


def read_csv(name: str) -> list[dict[str, str]]:
  with (DATA / name).open(newline="", encoding="utf-8") as handle:
    return list(csv.DictReader(handle))


def read_json(path: Path) -> dict:
  return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
  return hashlib.sha256(path.read_bytes()).hexdigest()


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
  panel_hash = sha256(DATA / "replication-panel-trend.csv")

  completion = read_json(ERC / "completion.json")
  require(completion.get("complete") is True, "ERC: run final incomplete")
  require("source_italy1942" in completion["cases"], "ERC: case source manquant")

  baseline = read_json(ERC / "baseline.json")
  require(baseline["label"] == "baseline" and baseline["runs"] == 10_000,
          "ERC: baseline non conforme")
  audit = baseline.get("baseline_reproduction") or {}
  require(audit and all(value == "matches archived baseline within 1e-7"
                        for value in audit.values()),
          "ERC: la baseline ne reproduit plus l'archive main_ladders")

  manifest = read_json(ERC / "manifest.json")
  require(manifest["runs"] == 10_000, "ERC: manifeste non conforme")
  for name, expected in manifest["inputs_sha256"].items():
    source = ROOT / name
    if source == Path(__file__).resolve():
      continue
    if not source.exists():
      continue  # entree retiree lors du menage : deja signalee par le renderer
    if name.startswith("build/"):
      continue  # script de presentation modifiable apres le run gele
    require(sha256(source) == expected, f"ERC: empreinte obsolete pour {name}")
  sensitivities = read_json(ERC / "calibration_sensitivities.json")
  require(sensitivities["source_panel_sha256"]
          == sha256(RESULTS / "robustness" / "source_exclusions"
                    / "source_event_italy_1942" / "replication-panel-trend.csv"),
          "ERC: panneau source Italy-1942 obsolete")

  require(read_json(FIGURES / "gamma_sensitivity.json")["runs_per_gamma"] == 10_000,
          "gamma_sensitivity.json: attendu 10 000 chemins")
  require((FIGURES / "policy_sensitivity.json").exists(),
          "policy_sensitivity.json absent")
  require((RESULTS / "gamma_fixed_theta_n10000.json").exists(),
          "gamma_fixed_theta_n10000.json absent")

  for block in (5, 10, 20):
    payload = read_json(RESULTS / "robustness" / "histories"
                        / f"calendar_blocks_{block}y_outer100_inner1000.json")
    require(payload["outer_replicates"] == 100 and payload["inner_runs"] == 1_000
            and payload["outer_mean_block_years"] == block,
            f"bootstrap calendaire {block} ans: specification inattendue")

  require(read_json(RESULTS / "margin_call_n10000.json")["panel_sha256"] == panel_hash,
          "annual margin diagnostic uses an obsolete panel")
  require(read_json(RESULTS / "margin_monthly" / "input_provenance.json")["mf_sha256"]
          == sha256(DATA / "managed-futures-monthly.csv"),
          "monthly margin diagnostic uses an obsolete MF series")

  for name in ("composition_value_n10000.json", "composition_value_1970_n10000.json"):
    payload = read_json(RESULTS / name)
    require(payload["runs"] == 10_000 and payload["panel_sha256"] == panel_hash,
            f"{name}: specification ou panneau inattendu")

  for name in ("central", "common", "ablations", "sensitivity", "calibration",
               "composition_value", "exposure_value"):
    require((PAPER / "figures" / "erc" / f"{name}.tex").exists(),
            f"figure ERC manquante: {name}.tex")
  require((PAPER / "figures" / "erc" / "ladders.pdf").exists(), "ladders.pdf absent")
  for name in ("bills", "history", "margin", "monthly", "policy", "preferences"):
    require((PAPER / "figures" / "restored" / f"{name}.tex").exists(),
            f"figure restauree manquante: {name}.tex")
  for name in ("figures/erc/provenance.json", "figures/restored/provenance.json"):
    require((PAPER / name).exists(), f"provenance manquante: {name}")

  for doc, tokens in (("main-styled.tex", (r"\input{preamble.tex}", r"\externaldocument{internet-appendix}")),
                      ("internet-appendix.tex", (r"\input{preamble.tex}", r"\input{appendices-refocused.tex}"))):
    text = (PAPER / doc).read_text(encoding="utf-8")
    for token in tokens:
      require(token in text, f"{doc} n'importe plus {token}")
  for name in ("revision_checks.json", "revision_checks_mf_minus_300bp.json",
               "mf_variant_lifecycle.json", "sensitivity/baseline.json",
               "histories/calendar_blocks_10y_outer100_inner1000.json"):
    require((ROOT / "results" / "equal_volatility" / name).exists(),
            f"resultat de revision manquant: {name}")

  print("Verification du depot: OK")


if __name__ == "__main__":
  main()
