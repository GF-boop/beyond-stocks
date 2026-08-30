# Reproducibility and auditability

This document maps every published element of the paper to its full chain:
**input data → script → command → output → location in the paper**. All
simulations share the seed `20260827` and a stationary block bootstrap with
mean block length ten years.

Baseline cost framework: financing spread $\phi$ = 30 bp, hedging friction
$\kappa$ = 10 bp, MF fee 0.85%, realised turnover (~0.57%). Path counts:
10,000 (main tables, central costs, γ, policy, MF variants), 5,000 (leverage
sweeps and historical uncertainty), 20,000 (USA, multi-numeraire).

---

## 1. Input data (`data/`)

Provenance, licence and consuming script of every file:
[`data/SOURCES.md`](data/SOURCES.md).

### Primary sources (versioned)

| File | Role | Source |
|---|---|---|
| `JSTdatasetR6.dta` | equity, bonds, bills, CPI, exchange rates, 1871–2020 | Jordà-Schularick-Taylor Macrohistory Database, release 6 |
| `jst-real-returns-2025.csv` | 2021–2025 extension of non-international-equity classes | JST + appendices |
| `gmd-cpi-fx.csv` | recent CPI, USD exchange rate and real GDP (columns `CPI`, `USDfx`, `rGDP_USD`) | Global Macro Database, extract |
| `equity-tr-recent.csv` | nominal equity returns 2021–2025 | listed trackers |
| `bb-mcap-gdp.csv` | market-capitalisation / GDP ratios by country-year | World Bank |
| `jst-ntsg-panel-2025.csv` | NTSG world equity index, 1880–2025 | JST reconstruction |
| `gold-annual.csv` | real gold price, annual | public series |
| `managed-futures-monthly.csv` | raw monthly managed-futures proxy, by sector | in-house construction (appendix B.1) |
| `cpi-monthly.csv` | monthly U.S. CPI, MF proxy deflator | BLS |
| `ssa_life_table.html` | mortality (Gompertz–Makeham) | SSA source, calibrated by `build/mortality.py` |
| `fixed-stacked-design.json` | manifest of portfolio rules (frozen SHA-256) | frozen, read by `compare_fixed_stacked_utility.py` |

### Reconstructed panels (versioned, rebuildable — step 1 of `rebuild_all.sh`)

| File | Producer | Inputs |
|---|---|---|
| `international-equity.csv` | `build/international_equity.py` | `JSTdatasetR6.dta`, `equity-tr-recent.csv`, `gmd-cpi-fx.csv`, `bb-mcap-gdp.csv` |
| `replication-panel.csv` | `build/build_replication_panel.py` | `JSTdatasetR6.dta`, `international-equity.csv`, `jst-real-returns-2025.csv` |
| `managed-futures-annual-real.csv` | `build/panel_managed_futures.py` | `managed-futures-monthly.csv`, `cpi-monthly.csv` |
| `replication-panel-trend.csv` | `build/panel_replication_tendance.py` | `replication-panel.csv`, `jst-ntsg-panel-2025.csv`, `gold-annual.csv`, `managed-futures-annual-real.csv` |

`replication-panel-trend.csv` (1,557 country-years, 16 markets, 1927–2025) is
the direct input of all simulations.

Data quality: `build/data_quality.py` (module `SUSPECT_PERIODS` /
`exclusion_reason`, imported by `compare_fixed_stacked_utility.py`; Japan
1945–1949 excluded, justifying docstring). Investability filter:
`build/investability.py` (30 rows excluded, labelled sensitivity).

## 2. Paper → output → script mapping

Single table, in manuscript order. **The authoritative key is the `\label`**,
not the number: the table and figure numbers below are the order as of
2026-08-29 and shift with any insertion into `main.tex`. Appendices are
A `app:returns`, B `app:mf-proxy`, C `app:gold-availability`,
D `app:leverage-ladders`, E `app:historical-uncertainty`,
F `app:gamma-sensitivity`, G `app:policy-sensitivity`.

Common engine of the main experiment: `build/compare_fixed_stacked_utility.py`
(household, incomes of Guvenen et al. 2021, Social Security, block bootstrap
of country-decades). `--seed 20260827` is the default and is left implicit
below.

| Paper | `\label` | Content | Source file | Producing script — command |
|---|---|---|---|---|
| Table 1 | `tab:moments` | Realised portfolio properties | `results/main_core_n10000.json` | `compare_fixed_stacked_utility.py --runs 10000 --portfolio-set core --output-json …` |
| Table 2 | `tab:design` | Fixed portfolio rules | `data/fixed-stacked-design.json` | frozen manifest (`calibrated_from_returns: false`) |
| Table 3 | `tab:currency` | Public replication + equity attribution | `results/main_core_n10000.json` | same as Table 1 |
| Table 4 | `tab:lifecycle` | Lifecycle results of the fixed portfolios | `results/main_ladders_n10000.json` | `compare_fixed_stacked_utility.py --runs 10000 --portfolio-set ladders --output-json …` |
| Table 5 | `tab:main-ladders` | Two pre-specified leverage ladders | `results/main_ladders_n10000.json` | same as Table 4 |
| Figure 1 | `fig:ladders-main` | Ladders vs ACO benchmark | `paper/figures/ladders_main.tex` | `build/plot_ladders_main.py` (reads `main_ladders_n10000.json`) |
| Table 6 | `tab:main-similar-volatility` | Dominance at comparable volatility | `results/main_ladders_n10000.json` | same as Table 4 |
| Table 7 | `tab:frontier` | Ruin along a leverage sweep | *stdout, not persisted* | `build/experiment_voltarget.py --mode frontier --runs 5000` |
| Table 8 | `tab:usd-numeraire` | Same states, resident vs fixed-dollar numeraire | `results/control_usd_common_n10000.json` | `compare_fixed_stacked_utility.py --runs 10000 --usd-common-sample --output-json …` |
| §5.2 window | — | 90/60 covered comment over 1970–2025 | `results/window_1970_2025_n10000.json` | `compare_fixed_stacked_utility.py --runs 10000 --year-from 1970 --portfolio-set all --output-json …` |
| §2.1 search | — | ACO optimisation grid on the public panel (optimum ≈ 30/70) | `results/grid_equity_n10000.json` | `build/grid_search_equity.py` |
| Figure 2 + §5.5 | `fig:ladders-usa` | Ladders on U.S. country-years only (vol-matched) | `results/control_usa_ladders_n20000.json` | `compare_fixed_stacked_utility.py --runs 20000 --sample-mode usa --portfolio-set ladders --output-json …` (figure: `build/plot_ladders_main.py results/control_usa_ladders_n20000.json paper/figures/ladders_usa.tex 8`) |
| Table 9 | `tab:spread` | Leverage sweep across a range of spreads | *stdout, not persisted* | `build/experiment_voltarget.py --mode frontier --runs 10000 --spread {0, 0.0015, 0.003, 0.006, 0.010}` (5 runs, read off leverage 1.5) |
| Table 10 (§5.6) | `tab:central-cost-sensitivity` | Financing and hedging cost stress | `paper/figures/central_cost_sensitivity.{json,tex}` | `build/central_cost_sensitivity.py` |
| Figure 3 (app. A) | `fig:cumwealth` | Cumulative real return by asset class | `paper/figures/cumulative_wealth.tex` | `paper/build_appendix_data.py` |
| Table 11 (app. B) | `tab:mf-monthly-sources` | Monthly sources of the MF proxy | *inline in `main.tex`* | — (static table) |
| Figure 4 (app. B) | `fig:mf-vs-benchmarks` | $1 invested: net proxy vs commercial indexes | `paper/figures/mf_vs_benchmarks.tex` | `paper/build_mf_benchmark_data.py` |
| Table 12 (app. B) | `tab:mf-benchmark-corr` | Monthly proxy / trend-index correlation | `paper/figures/mf_benchmark_corr.tex` | `paper/build_mf_benchmark_data.py` |
| Table 13 (app. B) | `tab:mf-pack-corr` | 14×14 correlation matrix: proxy, SG/BTOP50 indexes, KMLMSIM/DBMF/KMLM and investable funds | `paper/figures/mf_pack_corr.tex` | `paper/build_mf_pack_matrix.py` (reads `data/benchmarks-externes/`: `official-index-returns-monthly.csv`, `testfol/`, `funds/`) |
| Table 14 (app. B) | `tab:mf-pack-long-corr` | Correlation matrix over a common window (series ≥ 10 years: proxy, indexes, WTMF/QMHIX/AHLIX; 2014-09 → 2025-12) | `paper/figures/mf_pack_long_corr.tex` | `paper/build_mf_pack_matrix.py` (same run) |
| Table 15 (app. B) | `tab:mf-pack-reg` | Regressions of the 13 series (indexes + funds) on the proxy (β, α, R², relative vol., tracking error) | `paper/figures/mf_pack_regressions.tex` | `paper/build_mf_pack_matrix.py` (same run) |
| Table 16 (app. B) | `tab:mf-diagnostics` | MF proxy against the other asset classes | `paper/figures/mf_diagnostics.tex` | `paper/build_appendix_data.py` |
| Figure 5 (app. B) | `fig:mf-convexity` | Annual proxy return vs equity (convexity) | `paper/figures/mf_convexity.tex` | `paper/build_appendix_data.py` |
| Table 17 (app. B) | `tab:mf-variants` | MF proxy under alternative construction choices | `paper/figures/mf_variants.{json,tex}` | `build/mf_variants.py` |
| Table 18 (app. B) | `tab:mf-variant-lifecycle` | Lifecycle with each MF variant in the sleeve | `paper/figures/mf_variant_lifecycle.{json,tex}` | `build/mf_variant_lifecycle.py` |
| Table 19 (app. C) | `tab:gold-availability` | Gold unavailable before 1968 | `results/sensitivity_gold_unavailable_n10000.json` | `compare_fixed_stacked_utility.py --runs 10000 --reallocate-administered-gold-from 1968 --output-json …` |
| Table 20 (app. D) | `tab:60402525-ladder` | Proportional 60/40/25/25 leverage ladder | `results/main_ladders_n10000.json` | same as Table 4 |
| Table 21 (app. D) | `tab:equal-ladder` | Equal-weight four-sleeve leverage ladder | `results/main_ladders_n10000.json` | same as Table 4 |
| Table 22 (app. E) | `tab:historical-uncertainty` | Sensitivity to the historical sample | `paper/figures/historical_uncertainty.{json,tex}` | `build/historical_uncertainty.py` (22 perturbations, 5,000 paths) |
| Table 23 (app. E) | `tab:historical-uncertainty-loo` | Leave-one-country-out | `paper/figures/historical_uncertainty_loo.tex` | `build/historical_uncertainty.py` (same run) |
| Table 24 (app. F) | `tab:gamma-sensitivity` | Sensitivity to risk aversion | `paper/figures/gamma_sensitivity.{json,tex}` | `build/gamma_sensitivity.py` |
| Table 25 (app. G) | `tab:policy-sensitivity` | Sensitivity to contribution and withdrawal rates | `paper/figures/policy_sensitivity.{json,tex}` | `build/policy_sensitivity.py` |
| Table 26 (app. I) | `tab:usa-control` | Results on U.S. country-years only | `results/control_usa_n20000.json` | `compare_fixed_stacked_utility.py --runs 20000 --sample-mode usa --output-json …` |
| Table 27 (app. I) | `tab:currency-numeraire` | ACO 33/67: exchange-rate and numeraire diagnostics | `results/control_usd_common_n10000.json`, `results/control_usd_numeraire_n10000.json` | `--usd-common-sample` (above) + `compare_fixed_stacked_utility.py --runs 10000 --usd-numeraire --output-json …` |
| Table 28 (app. I) | `tab:multiple-numeraires` | ACO 33/67 under alternative fixed numeraires | `results/control_numeraires_n20000.json` | `build/experiment_fixed_numeraire.py --runs 20000 --output-json …` |
| Appendix J | `app:margin-call` | Margin calls on the DIY route: account at the levered families' weights (200%×2 + covered 150%), rebalanced annually, 25% margin tested at year-end, nominal per asset | `results/margin_call_n10000.json` | `build/margin_call_experiment.py` |

Notes:

- **`results/main_ladders_n10000.json`** alone feeds Tables 4, 5, 6, 20, 21
  and Figure 1. **`results/main_core_n10000.json`** feeds Tables 1 and 3.
  This is intentional: files are named after the experiment, not after a
  table.
- **Tables 7 and 9**: `experiment_voltarget.py` has its own leverage
  implementation, distinct from the main engine (see the note to Table 9 for
  the numerical consequence). stdout output only; the audited cells are those
  printed at run time.
- **Imported modules, not executed directly**: `replicate_extended.py`
  (shared engine), `compare_lifecycle_utility.py`, `compare_gold_trend_equal_vol.py`,
  `compare_equal_vol.py`, `income_process.py`, `mortality.py`,
  `social_security.py`, `investability.py`, `data_quality.py`. One-off
  analyses kept for traceability, with no published table:
  `audit_mf_hedge.py`, `replicate_cederburg.py`,
  `analyze_international_diversification.py`. See `build/README.md` — do not
  move.

## 3. Rebuild order

`build/rebuild_all.sh` chains the commands in the canonical order (data →
main experiment → sweeps → sensitivities → figures → PDF). It is provided as
documentation: each step is independent and can be rerun in isolation.

## 4. Audit rules

1. Every table in the PDF must be traced back to a JSON in `results/` or a
   `.json/.tex` in `paper/figures/` via the table in section 2.
2. ACO benchmarks must coincide across tables with a common path count and
   sample; any difference is read in the table notes (path-count effect, or
   declared sweep machinery).
3. The manifest `data/fixed-stacked-design.json` fixes the recipes
   (`calibrated_from_returns: false`); `compare_fixed_stacked_utility.py`
   loads it with no option to re-estimate the weights.
4. No number in the paper is typed by hand: the tables come from the JSON
   outputs, and Figure 1 is rebuildable with
   `python3 build/plot_ladders_main.py`.
