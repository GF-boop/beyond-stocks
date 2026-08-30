#!/usr/bin/env bash
# Reconstruction canonique du papier — documentation executable.
# Chaque etape est independante ; en cas de doute, relancer uniquement
# l'etape dont on audite la sortie. Duree totale : plusieurs heures.
#
# Depot autonome : aucune dependance hors de ce dossier. Seul
# build_mf_benchmark_data.py (etape 6) a besoin d'indices proprietaires absents
# du depot ; sans eux il s'arrete proprement et la figure/table de validation
# externe restent celles du PDF distribue.
set -euo pipefail
cd "$(dirname "$0")/.."

SEED=20260827

# build/data_quality.py et build/investability.py sont des modules importes par
# compare_fixed_stacked_utility.py (exclusions Japon 1945-1949 et filtre ex ante).

echo "== 1. Panel et donnees =="
python3 build/international_equity.py          # -> data/international-equity.csv
python3 build/build_replication_panel.py       # -> data/replication-panel.csv
python3 build/panel_managed_futures.py         # -> data/managed-futures-annual-real.csv
python3 build/panel_replication_tendance.py    # -> data/replication-panel-trend.csv

echo "== 2. Experience principale (10 000 traj.) =="
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --portfolio-set core    --output-json results/main_core_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --portfolio-set ladders --output-json results/main_ladders_n10000.json

echo "== 3. Controles numeraire et USA =="
python3 build/compare_fixed_stacked_utility.py --runs 20000 --seed $SEED \
  --sample-mode usa --output-json results/control_usa_n20000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --usd-numeraire --output-json results/control_usd_numeraire_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --usd-common-sample --output-json results/control_usd_common_n10000.json
python3 build/experiment_fixed_numeraire.py --runs 20000 \
  --output-json results/control_numeraires_n20000.json

echo "== 4. Sweeps de levier (sortie stdout) =="
python3 build/experiment_voltarget.py --mode frontier --runs 5000   # Table 7
for phi in 0 0.0015 0.003 0.006 0.010; do                           # Table 12 (levier 1.5)
  python3 build/experiment_voltarget.py --mode frontier --runs 10000 --spread $phi
done

echo "== 5. Sensibilites et annexes =="
python3 build/central_cost_sensitivity.py
python3 build/gamma_sensitivity.py
python3 build/policy_sensitivity.py
python3 build/mf_variants.py
python3 build/mf_variant_lifecycle.py
python3 build/historical_uncertainty.py

echo "== 6. Figures et diagnostics d'annexe =="
( cd paper && python3 build_appendix_data.py && python3 build_mf_benchmark_data.py )
python3 build/plot_ladders_main.py                # Figure 1

echo "== 7. PDF =="
( cd paper && pdflatex main.tex && biber main && pdflatex main.tex && pdflatex main.tex )

echo "Reconstruction terminee. Verifier les sorties results/ et paper/figures/."
