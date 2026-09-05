# Revised manuscript with technical appendices

The September 5 review revision integrates the MF return deductions, 175%
financing/hedge-cost grid, post-1970 ablations, outer calendar-panel bootstrap,
and common planned ACO withdrawal. Regenerate the five added exhibits with
`python3 ../../build/render_review_controls.py` before the LaTeX build below.
Their input hashes are recorded in
`../../results/method_review/review_exhibits_provenance.json`.

The common-withdrawal exhibit reports unconditional failure frequencies
alongside rates conditional on reaching retirement with a positive target.
ACO has the same 698 failures in both presentations (6.98% of 10,000
lifetimes; 7.10% of 9,832 eligible paths). The output JSON includes an
own-capital-target audit: all four portfolios reproduce the main engine's
failure indicators exactly and match their archived main ruin estimates.
Only the earlier common-target funding ratios required correction for paths
with no retirement years; the main unconditional ruin definition is unchanged.
The historical-bootstrap ranges retain inner simulation noise and are
described as sensitivity ranges rather than calibrated confidence intervals.

`main-styled.tex` and `main-styled.pdf` are the revised manuscript. They
use the 1,561-country-year raw panel, the ACO bootstrap continuation rule, and
the fixed-notional currency-hedge convention. The equal-weight four-sleeve
portfolio at 175% gross exposure has nearly the same full-panel volatility
as ACO 33/67, but this descriptive match is sensitive to extreme conversions.
The main sample remains 1927--2025, with later-window and source-exclusion
diagnostics. `appendices-revised.tex` restores the original appendix topics;
archived diagnostics not recalculated under the revised conventions are
explicitly distinguished from current results.

The event and country-source influence diagnostics are reproducible with:

```bash
python3 ../../build/source_exclusion_diagnostics.py --runs 10000
```

They write separate reconstructed panels, logs, results and a provenance file
under `../../results/method_review/source_exclusions/`. They are diagnostics of
historical influence, not a data-cleaning rule.

Build the complete revised manuscript from this directory with:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main-styled.tex
biber main-styled
pdflatex -interaction=nonstopmode -halt-on-error main-styled.tex
pdflatex -interaction=nonstopmode -halt-on-error main-styled.tex
```

# Archived full-manuscript workflow

The manuscript is built from fixed, non-estimated portfolio definitions and
paired lifecycle simulations in the parent project. Every extension retains
the ACO 33/67 resident-equity sleeve. All other foreign returns are converted
or covered into the currency and purchasing power of the simulated resident
before portfolio aggregation.

```bash
python3 build_appendix_data.py        # cumulative_wealth.tex + mf_diagnostics.tex + mf_convexity.tex
python3 build_mf_benchmark_data.py    # mf_vs_benchmarks.tex + mf_benchmark_corr.tex
python3 ../build/mf_variants.py             # mf_variants.tex + JSON audit
python3 ../build/mf_variant_lifecycle.py    # mf_variant_lifecycle.tex + JSON audit
python3 ../build/historical_uncertainty.py  # historical_uncertainty*.tex + JSON audit
python3 ../build/central_cost_sensitivity.py # central cost/hedging table
python3 ../build/gamma_sensitivity.py       # gamma_sensitivity.tex + JSON audit
python3 ../build/policy_sensitivity.py      # policy_sensitivity.tex + JSON audit
python3 ../build/plot_ladders_main.py ../results/main_ladders_n10000.json figures/ladders_main.tex
pdflatex -interaction=nonstopmode main.tex
biber main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

`build_appendix_data.py` regenerates the cumulative-wealth figure and the
managed-futures annual diagnostics from `../data/replication-panel-trend.csv`.
`build_mf_benchmark_data.py` regenerates the external-validation figure and
correlation table for the managed-futures appendix (Appendix B). The SG and
BarclayHedge
indexes are proprietary and are not redistributed with this repository: the
script reads them, if present, from `../data/benchmarks-externes/`
(`official-index-returns-monthly.csv` and a `testfol/` folder), under the terms
held for this research. Without them it exits cleanly and the figure and table
remain the ones in the distributed PDF.

`mf_variants.py` rebuilds the annual real managed-futures series for four
alternative construction choices (1/3/12 blend, 12-month signal only, 1-month
signal only, and the 1/6/12 blend with a doubled management fee) from the same
monthly file, using the identical volatility target, sector weighting, and
month-by-month CPI deflation as `build/panel_managed_futures.py`, with each
variant carrying its own realized turnover cost. It reports each variant's
moments and its annual correlation with the 1/6/12 series used in the paper.

`mf_variant_lifecycle.py` goes one step further and reruns the full lifecycle
model with each variant in the managed-futures sleeve. For every variant it
rebuilds the country-year panel by injecting the variant's U.S. gross annual
real series and covering it into each resident's currency with the same rule as
`build/panel_replication_tendance.py`, then evaluates the two 200% families
and the ACO 33/67 benchmark on 10,000 paired paths at seed 20260827. The
baseline row reproduces the 200% rows of the main ladder table exactly. It
shows the ruin and equivalent-saving ranking, not just the correlation,
survives every construction choice.

The central fixed tables use 10,000 paths on the complete 1,557-country-year
raw panel; the main leverage frontier uses 5,000 paths, the spread sweep uses
10,000 paths per spread, and the multi-numeraire diagnostic uses 20,000. All
use stationary-bootstrap blocks with a mean length of
ten years, a 0.30% financing spread, and the exact fixed weights in
`../data/fixed-stacked-design.json`. No observed return moment enters those
weights. This removes direct volatility calibration; it is not a claim that
the strategy family was pre-registered independently of the sample.

`historical_uncertainty.py` runs 5,000 paired paths for each of 22 fixed
historical-sample perturbations: mean stationary blocks of 5, 10, and 20 years,
post-1950 and post-1970 windows, the ex ante investability screen, and all 16
leave-one-country-out samples. Every row draws the same paths at the common
seed 20260827, so only the panel changes. Its ranges are sensitivity
diagnostics rather than confidence intervals.

`central_cost_sensitivity.py` uses 10,000 common paired paths per cost point to
stress the two 200% central portfolios at financing spreads of 30--300 bp and
hedge frictions of 10--100 bp.

`gamma_sensitivity.py` uses 10,000 paired paths for each of six risk-aversion
coefficients (2 to 10) to stress the same two 200% portfolios, applying the
critique of Section 2.1 to the paper's own ranking. The bequest intensity is
rescaled to each gamma as theta(gamma) = theta_3.84 * 12^(3.84 - gamma), which
reproduces ACO's monthly-to-annual bequest calibration at every gamma. The
weights and gross exposure are never re-optimised, so this is a sensitivity of
the fixed rule.

`policy_sensitivity.py` does the same for the two household policy parameters
inherited from ACO: the contribution rate (5, 10, 15%) and the real withdrawal
rate (3, 4, 5%), 10,000 paired paths per row. On the contribution axis the ACO
33/67 benchmark also contributes r_c, so its reference saving rate is r_c
itself and the family figure is the rate that matches ACO's lifecycle utility
at that r_c, not a rescaling of the 10% figure.

All four sensitivity tables (gamma, policy, historical-sample, and the
managed-futures variant sweep) report levels: retirement ruin and the
utility-equivalent saving rate for each family, with the ACO 33/67 figures as
an explicit reference row or column. Lower is better in every column. The JSON
audits still carry the signed differences from ACO for internal checks.
