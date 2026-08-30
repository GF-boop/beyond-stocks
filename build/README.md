# Role of the scripts in `build/`

Real dependency graph: almost every file is imported by table producers.
**Do not move or delete anything without checking the "Libraries" section
below.** Simulation inputs stay within `Cederburg_lifecycle/`; external
validation consumes optional, non-redistributed files under
`data/benchmarks-externes/`.

## Libraries (imported by producers — do not move)

| File | Imported by |
|---|---|
| `replicate_extended.py` | shared engine: central_cost, compare_fixed_stacked, experiment_fixed_numeraire, experiment_voltarget, gamma, historical_uncertainty, mf_variant_lifecycle, policy, compare_* |
| `compare_fixed_stacked_utility.py` | central_cost, experiment_fixed_numeraire, gamma, historical_uncertainty, mf_variant_lifecycle, policy |
| `compare_lifecycle_utility.py` | audit_mf_hedge, central_cost, compare_fixed_stacked, experiment_*, gamma, historical_uncertainty, mf_variant_lifecycle, policy |
| `compare_equal_vol.py` | compare_gold_trend_equal_vol, compare_lifecycle_utility |
| `compare_gold_trend_equal_vol.py` | central_cost, compare_fixed_stacked, gamma, historical_uncertainty, mf_variant_lifecycle, policy |
| `historical_uncertainty.py` | central_cost, gamma, mf_variant_lifecycle, policy |
| `replicate_cederburg.py` | analyze_international_diversification |
| `panel_replication_tendance.py` | mf_variant_lifecycle (functions `read_rows`, `build`); also produces `data/replication-panel-trend.csv` in `__main__` |
| `trend_costs.py` | replicate_extended, compare_gold_trend_equal_vol (MF proxy fees and transaction cost, recomputed from `data/managed-futures-monthly.csv`) |
| `war_periods.py` | compare_fixed_stacked_utility (option `--exclude-war-years`) |
| `income_process.py`, `mortality.py`, `social_security.py`, `investability.py`, `data_quality.py` | cross-cutting base modules |

## Producers (one published output each)

`central_cost_sensitivity.py`, `gamma_sensitivity.py`,
`policy_sensitivity.py`, `mf_variants.py`, `mf_variant_lifecycle.py`,
`historical_uncertainty.py` (appendix E), `experiment_fixed_numeraire.py`
(multi-numeraire), `experiment_voltarget.py` (Tables 7 and 9, stdout output),
`plot_ladders_main.py` (Figures 1 and 2), `international_equity.py`,
`build_replication_panel.py`, `panel_managed_futures.py` and
`panel_replication_tendance.py` (data, step 1). `data_quality.py` is a flagging
module imported by the main engine, not a standalone producer.

Full mapping script → command → output → table:
[`../REPRODUCIBILITY.md`](../REPRODUCIBILITY.md). Ordered rebuild:
[`rebuild_all.sh`](rebuild_all.sh).
Post-rebuild invariants: [`verify_repository.py`](verify_repository.py).

## One-off analyses (entry points with no dependents)

`analyze_international_diversification.py`, `audit_mf_hedge.py`,
`replicate_cederburg.py` (original ACO replication, also a library for the
point above). Kept for development traceability.
