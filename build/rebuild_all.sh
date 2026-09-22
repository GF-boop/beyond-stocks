#!/usr/bin/env bash
# Reconstruction complete du papier, dans l'ordre. Chaque etape peut etre
# relancee seule. Duree totale : plusieurs heures.
#
# Seules les comparaisons aux indices CTA et aux fonds (etape 7) dependent de
# donnees non redistribuables ; sans elles, ces figures restent versionnees.
set -euo pipefail
cd "$(dirname "$0")/.."

SEED=20260827
MF_ENGINE="build/managed_futures/run_managed_futures.py"
MF_OUTPUT="build/managed_futures/output"

echo "== 1. Panel et donnees =="
python3 "$MF_ENGINE" --output "$MF_OUTPUT"      # entrees : data/mf-inputs/
cp "$MF_OUTPUT/managed-futures-monthly.csv" data/managed-futures-monthly.csv
python3 build/international_equity.py          # -> data/international-equity.csv
python3 build/build_replication_panel.py       # -> data/replication-panel.csv
python3 build/panel_managed_futures.py         # -> data/managed-futures-annual-real.csv
python3 build/panel_replication_tendance.py    # -> data/replication-panel-trend.csv

echo "== 2. Exclusions de source (alimente le cas ERC --full) =="
python3 build/source_exclusion_diagnostics.py   # panneau Italie 1942

echo "== 3. Replication d'ACO et experience principale (10 000 traj.) =="
python3 build/compare_fixed_stacked_utility.py --runs 10000 --portfolio-set core \
  --include-suspect-data --output-json results/main_core_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --portfolio-set ladders \
  --include-suspect-data --output-json results/main_ladders_n10000.json
# erc_refocusing.py refuse d'ecraser un dossier existant : on repart du final.
rm -rf results/erc_refocusing/n10000_final
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 build/erc_refocusing.py --runs 10000 --full --tag final

echo "== 4. Valeur de composition =="
python3 build/composition_value.py --runs 10000 --seed $SEED
python3 build/composition_value.py --runs 10000 --seed $SEED --year-from 1970 \
  --output-json results/composition_value_1970_n10000.json

echo "== 5. Sensibilites et annexes restaurees =="
python3 build/gamma_sensitivity.py --runs 10000
python3 build/gamma_sensitivity.py --runs 10000 --fixed-theta \
  --output-json results/gamma_fixed_theta_n10000.json
python3 build/policy_sensitivity.py
for block in 5 10 20; do
  python3 build/historical_panel_bootstrap.py --outer-replicates 100 --inner-runs 1000 \
    --outer-mean-block "$block" \
    --output-json "results/method_review/historical_panel_bootstrap/calendar_blocks_${block}y_outer100_inner1000.json"
done
python3 build/margin_call_experiment.py
python3 build/bill_quintiles.py                 # Table des quintiles de taux reels
python3 build/historical_availability.py --prepare --runs 10000 \
  --allow-incomplete-mf-reallocation
python3 build/monthly_margin_diagnostic.py

echo "== 6. Figures et donnees d'annexes =="
( cd paper && python3 build_appendix_data.py --fixed-notional \
    --output-dir new_paper/figures && python3 build_mf_benchmark_data.py )
python3 build/mf_variants.py

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

echo "== 7b. Controles de la revision du 22 septembre 2026 (volatilite egale, strategies sans obligations) =="
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/revision_checks.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/revision_checks.py 0.03
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/eqvol_sensitivity.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/mf_variant_lifecycle.py
for b in 5 10 20; do
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/historical_panel_bootstrap_eqvol.py --outer-mean-block $b
done
# Controles d'audit (22 septembre 2026) : coherence des deflateurs, frais
# obligataires et rendements MF coherents avec des futures. Hors papier.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/deflator_fee_check.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/mf_excess_return_check.py

echo "== 8. Rendu des figures =="
python3 build/render_sleeve_properties.py >/dev/null
python3 build/render_erc_refocusing.py
python3 build/render_composition_value.py
python3 build/render_restored_appendices.py
python3 build/render_panel_margin_ablation.py

echo "== 9. Verification des artefacts =="
python3 build/verify_repository.py

echo "== 10. PDF =="
( cd paper/new_paper && ./build.sh )

echo "Reconstruction terminee. Verifier les sorties results/ et paper/figures/."
