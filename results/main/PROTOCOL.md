# Retrospective ERC comparator — frozen design, 6 September 2026

Question: does broader diversification improve ACO-style retirement outcomes
under both fixed proportional weights and covariance-calibrated risk budgeting?
The user authorized numerical simulation and refocusing the existing manuscript.
Equal-capital weights are removed from the revised paper before seeing ERC
outcomes; their previous sources/results are preserved in the snapshot/archive.

Baseline: public 1927–2025 panel, all 1,561 country-years, 10,000 paired
households, seed 20260827, annual ACO continuation bootstrap, mean block 10 years.
Use the existing income, mortality, utility, own-capital 4% withdrawal and
10% contribution conventions, with utility-equivalent saving relative to
unlevered ACO. No personal tax or forced-liquidation model is added.

ERC calibration: sample covariance (ddof=1, equal country-year row weights) of
the four resident-real, net-of-existing-cost sleeve returns: ACO 33/67 equities,
fixed-notional hedged global bonds, gold, and fixed-notional hedged MF.
No mean-return forecast, shrinkage, return screen or outcome-based tuning.
Solve for strictly positive normalized weights with equal variance contributions.
Use the convex positive-variable objective 0.5*x'Cov*x - sum(log(x))/4;
normalize x to sum one. Audit positive definiteness and relative contributions
to tolerance 1e-7. Equality applies before portfolio financing, not to total
leveraged NAV including the random bill leg. This is explicitly in-sample.

Comparators: ACO, proportional (0.4,4/15,1/6,1/6), ERC; exposures
100,125,150,175,200%. Weights constant within a run. Financing spread 30bp,
hedging 10bp, existing MF fee/turnover and gold series costs unchanged.

Baseline includes common ACO-anchored planned income for every ladder point,
and pro-rata removal of each non-equity sleeve at 175% for both diversified
families (no reoptimization of surviving ERC weights).
Targeted sensitivities at 175%: funding spreads 100/200/300bp; MF annual return
deductions 300/600bp; 1970–2025 with baseline weights held fixed; source-event
Italy 1942 removal using the previously reconstructed source-exclusion panel,
baseline weights held fixed. Also report recalibrated covariance weights on
post-1970 and source-excluded panels as calibration diagnostics, not selected
replacement baseline weights. Historical-sample ranges are not confidence
intervals. No combined worst-case or universal robustness claim.

Primary evidence: saving and ruin jointly, plus common-income failure; paired
normal 95% intervals on failure differences conditional on the panel and weights.
Report all results, including reversals. These portfolios do not span an
efficient frontier or minimize household ruin. Existing ES/local-derivative
research remains outside this manuscript.

First run: 100 households and deterministic ERC/accounting tests. Production
must reproduce archived ACO/proportional baseline results. Record hashes of
code, protocol, input panels, and a pre-edit manuscript snapshot. Generated
outputs live here, never overwrite older research artifacts.
