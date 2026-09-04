#!/usr/bin/env bash
# Reconstruction canonique du papier — documentation executable.
# Chaque etape est independante ; en cas de doute, relancer uniquement
# l'etape dont on audite la sortie. Duree totale : plusieurs heures.
#
# Depot autonome pour toutes les simulations. Les validations externes de
# l'etape 7 ont besoin d'indices et de fonds non redistribuables ; sans eux,
# leurs artefacts versionnes sont conserves et le reste du rebuild continue.
set -euo pipefail
cd "$(dirname "$0")/.."

SEED=20260827

# build/data_quality.py signale Japon 1945-1949 sans le retirer du panel central.
# build/investability.py porte le filtre ex ante de la sensibilite investissable.

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
python3 build/grid_search_equity.py
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --year-from 1970 --portfolio-set all \
  --output-json results/window_1970_2025_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --portfolio-set core --reallocate-administered-gold-from 1968 \
  --output-json results/sensitivity_gold_unavailable_n10000.json

echo "== 3. Controles numeraire et USA =="
python3 build/compare_fixed_stacked_utility.py --runs 20000 --seed $SEED \
  --sample-mode usa --output-json results/control_usa_n20000.json
python3 build/compare_fixed_stacked_utility.py --runs 20000 --seed $SEED \
  --sample-mode usa --portfolio-set ladders \
  --output-json results/control_usa_ladders_n20000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --usd-numeraire --output-json results/control_usd_numeraire_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --usd-common-sample --output-json results/control_usd_common_n10000.json
python3 build/experiment_fixed_numeraire.py --runs 20000 \
  --output-json results/control_numeraires_n20000.json

echo "== 4. Sweeps de levier (sortie console archivee) =="
python3 build/experiment_voltarget.py --mode frontier --runs 5000 \
  | tee results/frontier_n5000.txt                                  # Table 7
{
  for phi in 0 0.0015 0.003 0.006 0.010; do                         # Table 9 (levier 1.5)
    python3 build/experiment_voltarget.py --mode frontier --runs 10000 --spread $phi
  done
} | tee results/spread_frontier_n10000.txt

echo "== 5. Sensibilites et annexes =="
python3 build/central_cost_sensitivity.py
python3 build/gamma_sensitivity.py --runs 10000
python3 build/gamma_sensitivity.py --runs 10000 --fixed-theta \
  --output-json results/gamma_fixed_theta_n10000.json \
  --output-tex paper/figures/gamma_fixed_theta.tex
python3 build/policy_sensitivity.py
python3 build/source_country_sensitivity.py --runs 5000
python3 build/source_exclusion_diagnostics.py --runs 10000 --seed $SEED
python3 build/variance_concentration.py
python3 build/margin_call_experiment.py
python3 build/sleeve_ablation.py --runs 10000 --seed $SEED
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --year-from 1950 --portfolio-set ladders \
  --output-json results/method_review/sample_windows/post1950_ladders_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --seed $SEED \
  --year-from 1970 --portfolio-set ladders \
  --output-json results/method_review/sample_windows/post1970_ladders_n10000.json

echo "== 6. Figures et diagnostics publics =="
( cd paper && python3 build_appendix_data.py --fixed-notional \
  --output-dir new_paper/figures && python3 build_mf_benchmark_data.py )
python3 build/plot_ladders_main.py \
  results/main_ladders_n10000.json paper/figures/ladders_main.tex    # Figure 1
python3 build/plot_ladders_main.py \
  results/control_usa_ladders_n20000.json paper/figures/ladders_usa.tex 8 19 # Figure 2

echo "== 7. Validation externe conditionnelle =="
external_ready=true
for path in \
  data/benchmarks-externes/official-index-returns-monthly.csv \
  data/benchmarks-externes/testfol/KMLMSIM.csv \
  data/benchmarks-externes/testfol/DBMF.csv \
  data/benchmarks-externes/testfol/KMLM.csv \
  data/benchmarks-externes/funds/WTMF.csv \
  data/benchmarks-externes/funds/QMHIX.csv \
  data/benchmarks-externes/funds/AHLIX.csv \
  data/benchmarks-externes/funds/AHLT.csv \
  data/benchmarks-externes/funds/IMF.csv \
  data/benchmarks-externes/funds/ISMF.csv \
  data/benchmarks-externes/funds/0P0001BD8S.csv; do
  [[ -f "$path" ]] || external_ready=false
done
if $external_ready; then
  python3 build/mf_fund_correlations.py
  ( cd paper && python3 build_mf_pack_matrix.py )
else
  echo "Donnees externes non redistribuables absentes : matrices MF conservees."
fi

python3 build/replicate_aco_leverage.py --methods-only
python3 build/render_aco_comparisons.py

echo "== 8. Verification des artefacts =="
python3 build/verify_repository.py

echo "== 9. PDF =="
( cd paper/new_paper && pdflatex -interaction=nonstopmode main-styled.tex && \
  biber main-styled && pdflatex -interaction=nonstopmode main-styled.tex && \
  pdflatex -interaction=nonstopmode main-styled.tex )

echo "Reconstruction terminee. Verifier les sorties results/ et paper/figures/."
