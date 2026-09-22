#!/usr/bin/env python3
"""Build panels that exclude pre-declared source events.

These sensitivity exercises do not identify erroneous historical data.  A
source event is removed consistently from the reconstructed international-
equity and global-bond baskets; the lifecycle scripts then drop the matching
resident rows (``erc_refocusing.source_exclusion_rows``).  The paper uses the
Italy 1942 exclusion; the other scenarios remain available on request.

Only the final panel ``<scenario>/replication-panel-trend.csv`` is kept;
intermediate panels are built in a temporary directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


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
DEFAULT = ("source_event_italy_1942",)


def run(command: list[str]) -> None:
  subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.DEVNULL, check=True)


def sha256(path: Path) -> str:
  return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--scenario", choices=tuple(SCENARIOS), action="append",
                      help="repeat to select scenarios; default: Italy 1942 only")
  parser.add_argument("--output-dir",
                      default="results/method_review/source_exclusions")
  args = parser.parse_args()
  selected = args.scenario or list(DEFAULT)

  target = ROOT / args.output_dir
  target.mkdir(parents=True, exist_ok=True)
  provenance = {"inputs": {}, "scenarios": {}}
  for relative in ("data/replication-panel-trend.csv",
                   "build/source_exclusion_diagnostics.py",
                   "build/international_equity.py",
                   "build/build_replication_panel.py",
                   "build/panel_replication_tendance.py"):
    provenance["inputs"][relative] = sha256(ROOT / relative)

  for name in selected:
    specification = SCENARIOS[name]
    folder = target / name
    folder.mkdir(parents=True, exist_ok=True)
    panel = folder / "replication-panel-trend.csv"
    event_args = [item for event in specification["event_exclusions"]
                  for item in ("--exclude-market-year", event)]
    bond_event_args = [item for event in specification["event_exclusions"]
                       for item in ("--exclude-bond-issuer-year", event)]
    country = specification["country_exclusion"]
    if country:
      event_args.extend(("--exclude-market", country))
      bond_event_args.extend(("--exclude-bond-issuer", country))
    with tempfile.TemporaryDirectory() as tmp:
      international = Path(tmp) / "international-equity.csv"
      replication = Path(tmp) / "replication-panel.csv"
      run([sys.executable, "build/international_equity.py", "--out", str(international),
           *event_args])
      run([sys.executable, "build/build_replication_panel.py", "--international",
           str(international), "--out", str(replication)])
      run([sys.executable, "build/panel_replication_tendance.py", "--panel",
           str(replication), "--out", str(panel), *bond_event_args])
    provenance["scenarios"][name] = {"definition": specification,
                                     "panel_sha256": sha256(panel)}
  (target / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
  print(target / "provenance.json")


if __name__ == "__main__":
  main()
