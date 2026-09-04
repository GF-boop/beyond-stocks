#!/usr/bin/env python3
"""Run pre-declared source-event and source-country exclusion diagnostics.

These sensitivity exercises do not identify erroneous historical data.  A
source event is removed consistently from the resident bootstrap rows and from
the reconstructed international-equity and global-bond baskets.  The country
exercise removes Italy from every such basket and as a resident, while keeping
the remaining source history unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = {
    "source_event_italy_1942": {
        "event_exclusions": ("Italy:1942",), "country_exclusion": None,
    },
    "source_events_italy_1942_france_1946": {
        "event_exclusions": ("Italy:1942", "France:1946"),
        "country_exclusion": None,
    },
    "source_country_italy_all_years": {
        "event_exclusions": (), "country_exclusion": "Italy",
    },
}


def run(command: list[str], log: Path) -> None:
  completed = subprocess.run(command, cwd=ROOT, text=True,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=True)
  log.write_text(completed.stdout)


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--scenario", choices=tuple(SCENARIOS), action="append",
                      help="repeat to select scenarios; default runs all")
  parser.add_argument("--runs", type=int, default=10_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--output-dir",
                      default="results/method_review/source_exclusions")
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("runs must be positive")
  selected = args.scenario or list(SCENARIOS)
  target = ROOT / args.output_dir
  target.mkdir(parents=True, exist_ok=True)
  provenance = {
      "research_contract": {
          "question": "Do lifecycle rankings depend on the specified Italian and French source events or on Italy as a source country?",
          "baseline": "full 1927--2025 panel, fixed-notional hedge, ACO block continuation, fixed portfolio rules",
          "metrics": "annual volatility, retirement ruin, utility-equivalent saving, and paired Monte Carlo interval",
          "limitation": "exclusions are influence diagnostics, not evidence that source observations are errors or historically uninvestable",
      },
      "runs": args.runs, "seed": args.seed, "scenarios": {},
      "inputs": {},
  }
  for relative in ("data/replication-panel-trend.csv",
                   "build/source_exclusion_diagnostics.py",
                   "build/international_equity.py",
                   "build/build_replication_panel.py",
                   "build/panel_replication_tendance.py",
                   "build/compare_fixed_stacked_utility.py",
                   "build/replicate_extended.py"):
    path = ROOT / relative
    provenance["inputs"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()

  for name in selected:
    specification = SCENARIOS[name]
    folder = target / name
    folder.mkdir(parents=True, exist_ok=True)
    international = folder / "international-equity.csv"
    replication = folder / "replication-panel.csv"
    panel = folder / "replication-panel-trend.csv"
    result = folder / f"ladders_n{args.runs}.json"
    event_args = [item for event in specification["event_exclusions"]
                  for item in ("--exclude-market-year", event)]
    bond_event_args = [item for event in specification["event_exclusions"]
                       for item in ("--exclude-bond-issuer-year", event)]
    country = specification["country_exclusion"]
    if country:
      event_args.extend(("--exclude-market", country))
      bond_event_args.extend(("--exclude-bond-issuer", country))
    run([sys.executable, "build/international_equity.py", "--out", str(international),
         *event_args], folder / "01-international-equity.log")
    run([sys.executable, "build/build_replication_panel.py", "--international",
         str(international), "--out", str(replication)], folder / "02-replication-panel.log")
    run([sys.executable, "build/panel_replication_tendance.py", "--panel",
         str(replication), "--out", str(panel), *bond_event_args],
        folder / "03-trend-panel.log")
    simulation_args = [sys.executable, "build/compare_fixed_stacked_utility.py",
        "--panel", str(panel), "--portfolio-set", "ladders", "--runs", str(args.runs),
        "--seed", str(args.seed), "--hedge-mode", "fixed_notional",
        "--bootstrap-end-treatment", "aco", "--output-json", str(result)]
    if country:
      simulation_args.extend(("--exclude-country", country))
    else:
      for event in specification["event_exclusions"]:
        simulation_args.extend(("--exclude-country-year", event))
    run(simulation_args, folder / "04-simulation.log")
    payload = json.loads(result.read_text())
    provenance["scenarios"][name] = {
        "definition": specification,
        "observations": payload["observations"],
        "result": str(result),
        "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
    }
  (target / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
  print(target / "provenance.json")


if __name__ == "__main__":
  main()
