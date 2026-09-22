#!/usr/bin/env bash
# Complete paper rebuild, in order. Each step can be run separately.
# Total runtime: several hours.
#
# Only comparisons with CTA indexes and funds (step 7) require
# non-redistributable data. Without them, the versioned figures are retained.
set -euo pipefail
cd "$(dirname "$0")/.."

SEED=20260827
MF_ENGINE="build/managed_futures/run_managed_futures.py"
MF_OUTPUT="build/managed_futures/output"

echo "== 1. Panel and data =="
python3 "$MF_ENGINE" --output "$MF_OUTPUT"      # inputs: data/mf-inputs/
cp "$MF_OUTPUT/managed-futures-monthly.csv" data/managed-futures-monthly.csv
python3 build/international_equity.py          # -> data/international-equity.csv
python3 build/build_replication_panel.py       # -> data/replication-panel.csv
python3 build/panel_managed_futures.py         # -> data/managed-futures-annual-real.csv
python3 build/panel_replication_tendance.py    # -> data/replication-panel-trend.csv

echo "== 2. Source exclusions (for the ERC --full case) =="
python3 build/source_exclusion_diagnostics.py   # Italy 1942 panel

echo "== 3. ACO replication and main experiment (10,000 paths) =="
python3 build/compare_fixed_stacked_utility.py --runs 10000 --portfolio-set core \
  --include-suspect-data --output-json results/main_core_n10000.json
python3 build/compare_fixed_stacked_utility.py --runs 10000 --portfolio-set ladders \
  --include-suspect-data --output-json results/main_ladders_n10000.json
# erc_refocusing.py refuses to overwrite an existing directory; rebuild the final run.
rm -rf results/main/n10000_final
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python3 build/erc_refocusing.py --runs 10000 --full --tag final

echo "== 4. Composition value =="
python3 build/composition_value.py --runs 10000 --seed $SEED
python3 build/composition_value.py --runs 10000 --seed $SEED --year-from 1970 \
  --output-json results/composition_value_1970_n10000.json

echo "== 5. Sensitivities and restored appendices =="
python3 build/gamma_sensitivity.py --runs 10000
python3 build/gamma_sensitivity.py --runs 10000 --fixed-theta \
  --output-json results/gamma_fixed_theta_n10000.json
python3 build/policy_sensitivity.py
for block in 5 10 20; do
  python3 build/historical_panel_bootstrap.py --outer-replicates 100 --inner-runs 1000 \
    --outer-mean-block "$block" \
    --output-json "results/robustness/histories/calendar_blocks_${block}y_outer100_inner1000.json"
done
python3 build/margin_call_experiment.py
python3 build/bill_quintiles.py                 # Real-bill-rate quintile table
python3 build/historical_availability.py --prepare --runs 10000 \
  --allow-incomplete-mf-reallocation
python3 build/monthly_margin_diagnostic.py

echo "== 6. Appendix figures and data =="
( cd paper && python3 build_appendix_data.py --fixed-notional \
    --output-dir new_paper/figures && python3 build_mf_benchmark_data.py )
python3 build/mf_variants.py

echo "== 7. Optional external validation =="
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
  echo "Non-redistributable external data are absent; retaining the versioned MF matrices."
fi

echo "== 7b. September 22, 2026 revision checks (equal volatility, bond-free strategies) =="
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/revision_checks.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/revision_checks.py 0.03
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/eqvol_sensitivity.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/mf_variant_lifecycle.py
for b in 5 10 20; do
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/historical_panel_bootstrap_eqvol.py --outer-mean-block $b
done
# September 22, 2026 audit checks: consistent deflators, bond fees, and
# futures-consistent MF returns. Not included in the paper.
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/deflator_fee_check.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/mf_excess_return_check.py

echo "== 8. Render figures =="
python3 build/render_sleeve_properties.py >/dev/null
python3 build/render_erc_refocusing.py
python3 build/render_composition_value.py
python3 build/render_restored_appendices.py
python3 build/render_panel_margin_ablation.py

echo "== 9. Verify artifacts =="
python3 build/verify_repository.py

echo "== 10. PDF =="
( cd paper/new_paper && ./build.sh )

echo "Rebuild complete. Check the outputs under results/ and paper/figures/."
