# Role of the scripts in `build/`

`erc_refocusing.py` runs the main experiment (the risk parity portfolio is
called ERC, equal risk contribution, in the code), `composition_value.py` values the composition across the panel, the
`sensitivity` producers fill the appendices, and the `render_*` scripts turn
frozen JSON into the LaTeX tables included by `paper/new_paper/`. The shared
lifecycle engine is imported by nearly every producer, so **do not move or
delete anything without checking the "Libraries" section below.** Simulation
inputs stay within `Cederburg_lifecycle/`; external validation consumes
optional, non-redistributed files under `data/benchmarks-externes/`.

## Libraries (imported by producers — do not move)

| File | Role | Imported by |
|---|---|---|
| `replicate_extended.py` | shared lifecycle engine and simulation primitives | nearly every producer and test below |
| `compare_fixed_stacked_utility.py` | stacked-utility comparison and baseline archive | common_consumption_target, composition_value, erc_refocusing, gamma, historical_panel_bootstrap, historical_uncertainty, margin_call, policy, sleeve_ablation, tests |
| `compare_gold_trend_equal_vol.py` | gold / trend equal-volatility family | common_consumption_target, compare_fixed_stacked_utility, composition_value, erc_refocusing, gamma, historical_panel_bootstrap, historical_uncertainty, policy, sleeve_ablation, tests |
| `compare_lifecycle_utility.py` | lifecycle-utility family | common_consumption_target, compare_fixed_stacked_utility, composition_value, erc_refocusing, gamma, historical_panel_bootstrap, historical_uncertainty, policy, sleeve_ablation, tests |
| `compare_equal_vol.py` | equal-volatility building block | compare_gold_trend_equal_vol, compare_lifecycle_utility |
| `historical_uncertainty.py` | historical scenario library (also `scenarios_for`) | common_consumption_target, erc_refocusing, gamma, historical_panel_bootstrap, policy |
| `common_consumption_target.py` | common-income objective | erc_refocusing, test_common_consumption_target |
| `sleeve_ablation.py` | sleeve reallocation primitives | composition_value, erc_refocusing, tests |
| `panel_replication_tendance.py` | resident conversion of bonds, bills, gold and MF; also produces `data/replication-panel-trend.csv` in `__main__` | — |
| `trend_costs.py` | MF proxy fees and transaction cost, recomputed from `data/managed-futures-monthly.csv` | compare_gold_trend_equal_vol, replicate_extended |
| `war_periods.py` | war-year exclusion option | compare_fixed_stacked_utility |
| `income_process.py`, `mortality.py`, `social_security.py`, `investability.py`, `data_quality.py` | cross-cutting base modules | see import graph above |

## Producers (one published output each)

- `erc_refocusing.py` — main ERC experiment, ablations and sensitivity cases
  (writes `results/erc_refocusing/<tag>/`).
- `composition_value.py` — value of composition across the historical panel.
- `source_exclusion_diagnostics.py` — source-event exclusion panels.
- `gamma_sensitivity.py` — joint preference calibration and fixed-bequest
  comparison.
- `policy_sensitivity.py` — household-policy grid.
- `historical_panel_bootstrap.py` — nested calendar-history bootstrap.
- `margin_call_experiment.py` — annual maintenance-margin diagnostic.
- `monthly_margin_diagnostic.py` — monthly monitoring diagnostic.
- `mf_variants.py` — managed-futures construction variants.
- `mf_fund_correlations.py` — external fund correlations (non-redistributed
  inputs).
- `managed_futures/run_managed_futures.py` — monthly managed-futures proxy
  from `data/mf-inputs/` (see `managed_futures/README.md`).
- `international_equity.py`, `build_replication_panel.py`,
  `panel_managed_futures.py`, `panel_replication_tendance.py` — data, step 1.
- `compare_fixed_stacked_utility.py --portfolio-set core` — replication of ACO
  (`results/main_core_n10000.json`); `--portfolio-set ladders` — exposure
  ladders used as a reproduction check (`results/main_ladders_n10000.json`).
- `bill_quintiles.py` — returns of leverage by real-bill quintile
  (`results/method_review/bill_volatility/`, `figures/bill_quintiles.tex`).
- `historical_availability.py` — gold and managed-futures markets added as they
  opened (`results/historical_availability/`).
- `fetch_mf_fund_data.py` — optional fetch of external fund price files.
- `revision_checks.py` — September 22, 2026 revision: bond-free strategies,
  equal-volatility scaling, excess-return Sharpe ratios, common-income dollars
  and proxy-versus-index subperiod statistics. Same seed as the frozen run; it
  asserts that the published baseline is reproduced. Optional argument: an
  annual managed-futures haircut (e.g. `0.03`).
- `eqvol_sensitivity.py`, `historical_panel_bootstrap_eqvol.py`,
  `mf_variant_lifecycle.py` — the same revision: Table VII (sensitivity),
  Table VI (resampled histories) and Table VII Panel E (managed-futures
  signal variants) at the equal-volatility exposures, with the path-matched
  income failure.
- `deflator_fee_check.py`, `mf_excess_return_check.py` — audit checks of the
  same revision: consistent deflators for gold and managed futures, the bond
  fund fee, and futures-consistent managed-futures returns. Not in the paper.

## Renderers (frozen JSON → LaTeX, no simulation)

| File | Output |
|---|---|
| `render_sleeve_properties.py` | `paper/new_paper/figures/erc/sleeves.tex` (Table I, including excess-return Sharpe ratios) |
| `render_erc_refocusing.py` | `paper/new_paper/figures/erc/{central,common,ablations,sensitivity,calibration}.tex`, `ladders.{pdf,png}`, `provenance.json`; Panels D–E of Tables II and VI read `results/revision_2026-09-22/` |
| `render_composition_value.py` | `paper/new_paper/figures/erc/{composition_value,exposure_value}.tex` |
| `render_restored_appendices.py` | `paper/new_paper/figures/restored/{bills,history,margin,monthly,policy,preferences}.tex` |
| `render_panel_margin_ablation.py` | `paper/new_paper/figures/margin_monthly.tex` |

`render_erc_refocusing.py` verifies every frozen input against the manifest of
the main run: data files are asserted exactly, while retired or locally
modified `build/*.py` entries are reported and skipped so the run stays
reproducible from a cleaned checkout.

## Tests and verification

- `test_erc_refocusing.py`, `test_composition_value.py`,
  `test_common_consumption_target.py`, `test_panel_margin_ablation.py`,
  `test_historical_availability.py` —
  focused unit tests.
- `verify_repository.py` — post-rebuild invariants of the ERC chain (data row
  counts, frozen-run fingerprints, preference/bootstrap/margin provenance,
  rendered figures, manuscript inputs).

Ordered rebuild: [`rebuild_all.sh`](rebuild_all.sh). The manuscript-side data producers
`paper/build_appendix_data.py`, `paper/build_mf_benchmark_data.py` and
`paper/build_mf_pack_matrix.py` live under `paper/`.
