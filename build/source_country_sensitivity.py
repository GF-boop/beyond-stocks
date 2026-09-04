#!/usr/bin/env python3
"""Retire chaque pays de residence et de chaque panier investissable.

Contrairement au precedent leave-one-country-out, cette experience reconstruit
les actions internationales et les obligations mondiales sans le pays omis,
puis retire aussi ses lignes de resident avant le bootstrap. Elle repond donc
a la question de sensibilite a un pays-source, pas seulement a celle de la
composition des residents tires.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COUNTRIES = (
    "Australia", "Belgium", "Denmark", "Finland", "France", "Germany",
    "Italy", "Japan", "Netherlands", "Norway", "Portugal", "Spain",
    "Sweden", "Switzerland", "UK", "USA",
)
PORTFOLIOS = ("ACO 33/67", "80/53.33/33.33/33.33 ACO", "50/50/50/50 ACO")


def command(*args: str) -> None:
  subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--runs", type=int, default=5_000)
  parser.add_argument("--seed", type=int, default=20260827)
  parser.add_argument("--output-dir", default="results/method_review/source_loo")
  parser.add_argument("--summary-json", default="paper/figures/source_country_sensitivity.json")
  parser.add_argument("--summarize-existing", action="store_true",
                      help="write the summary from already generated country files")
  args = parser.parse_args()
  if args.runs <= 0:
    raise ValueError("--runs must be positive")
  out = ROOT / args.output_dir
  out.mkdir(parents=True, exist_ok=True)
  results = []
  for country in COUNTRIES:
    international = out / f"international-{country}.csv"
    replication = out / f"replication-{country}.csv"
    panel = out / f"panel-{country}.csv"
    result = out / f"{country}.json"
    if not args.summarize_existing:
      command("build/international_equity.py", "--exclude-market", country,
              "--out", str(international))
      command("build/build_replication_panel.py", "--international",
              str(international), "--out", str(replication))
      command("build/panel_replication_tendance.py", "--panel", str(replication),
              "--exclude-bond-issuer", country, "--out", str(panel))
      command("build/compare_fixed_stacked_utility.py", "--panel", str(panel),
              "--exclude-country", country, "--runs", str(args.runs), "--seed",
              str(args.seed), "--portfolio-set", "ladders", "--output-json",
              str(result))
    payload = json.loads(result.read_text())
    rows = {row["strategy"]: row for row in payload["results"]}
    results.append({"omitted_country": country,
                    "observations": payload["observations"],
                    "portfolios": {name: rows[name] for name in PORTFOLIOS}})
  summary = {"runs_per_omission": args.runs, "seed": args.seed,
             "definition": "country removed from resident rows, international equity and world-bond baskets",
             "results": results}
  target = ROOT / args.summary_json
  target.parent.mkdir(parents=True, exist_ok=True)
  target.write_text(json.dumps(summary, indent=2) + "\n")
  print(f"Wrote {target}")


if __name__ == "__main__":
  main()
