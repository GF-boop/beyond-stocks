# Progressive historical availability

This is a separate robustness experiment, not a replacement of the main
1927–2025 panel or published baseline simulations. Personal taxes remain
unmodeled. All costs use the existing contemporary-cost convention.

> **Retired producer.** The script that generated this experiment
> (`build/historical_availability.py`) was removed during the repository
> cleanup, so the run can no longer be reproduced from source. The frozen
> output `results_n10000.json` is retained because the current manuscript links
> it. The design and results below are kept as the experiment's record.

## Preregistered choices for this run

- Five gross exposures (100/125/150/175/200%) for ACO and for each of two
  diversified families under four availability modes: 45 strategy paths.
- Gold gate: January 1975, both outer gold sleeve and METAL_GOLD within MF.
- Sector gates: commodities throughout, currencies June 1972, bonds September
  1977, equities May 1982. These are sector milestones, not constituent-level
  launch dates. Signal formation still requires the baseline lagged data.
  In the snapshot, the first eligible currency positions occur in February
  1973 because the lagged estimation requirements are not met in June 1972.
- Separate gold-only, MF-sector-only, and joint variants. MF-sector-only
  deliberately retains baseline gold eligibility to isolate the two masks.
- Each variant recalculates monthly sector allocations, aggregate volatility
  scaling, and turnover. One active commodity sector is allowed. Asset-level
  signal and volatility histories may use pre-entry source prices; sector
  and aggregate histories only contain positions eligible at that date.
- Full 1,561 country-years retained. Gates follow sampled historical dates,
  not household age. This is not a chronological history of product adoption.
- Gold's unavailable outer weight is redistributed proportionally, preserving
  gross exposure. Hedge friction follows the covered weight after reallocation.
- The restricted MF has insufficient coverage for complete calendar returns
  in 1960–1963. The user explicitly approved zero MF weight and proportional
  redistribution in these years, with no observation removed. This is an
  annual data-completeness rule, not an ex-ante trading signal. Partial annual
  MF returns are never manufactured or filled with zeros. In annual.csv they
  remain empty and are accompanied by available=0 and available_months.
- 10,000 paired lifecycle paths, seed 20260827; identical bootstrap, income,
  mortality, financing spread (30 bp), hedge friction (10 bp), and utility
  reference to the canonical ablation experiment. No allocation optimization.

## Reproduction

The producer script and its renderer were removed in the repository cleanup;
this section documents how the frozen run was originally obtained and is not
re-executable. It used Python with NumPy, pandas and matplotlib, from the
Cederburg_lifecycle root:

```sh
python3 build/historical_availability.py --prepare
python3 build/historical_availability.py --runs 10000 --allow-incomplete-mf-reallocation
python3 build/render_historical_availability.py
```

Preparation reads the existing engine and canonical public-data snapshots in
the neighboring CTO_vs_PEA project. It does not edit them or download data.
Their exact input hashes, local paths, coverage gaps, entry dates, and measured
costs are recorded in manifest.json. The Python environment used was
`/mnt/Data/caillasse/caillasse/.venv/bin/python3`.
Repository HEAD before the experiment: d27372fb9e7da3a9653f4c9822f6b51ead53914d;
the experiment is a working-tree addition, with its script hash in the manifest.

The annual turnover deduction follows the baseline convention: mean monthly
turnover over available strategy months, multiplied by 12 and 3 bp, charged
once downstream of gross MF returns. It is not a historical transaction-cost
estimate. No fee is charged to a zero-weight annual MF sleeve.

## Checks

- Unit tests cover sector entry boundaries, the nested gold gate, no-mask
  eligibility, and preservation of total exposure and surviving-weight ratios.
- The no-mask reconstruction matches the frozen canonical monthly returns
  within 5e-13 and turnover/scalars within 5e-12. Annual fixed-notional
  resident conversions also reproduce the panel before simulation.
- Every month has nonnegative sector weights summing to one; unavailable
  sectors and gold have no positions before their specified dates.
- After both rolling estimation windows have washed out entry effects,
  all variant gross monthly returns equal baseline exactly from 1989 onward.
  Constant measured turnover deductions can still differ across variants.
- The 10,000-path run checked all baseline diversified and ACO ladder outcomes
  against the then-current ladder archive before writing results.
- JSON outputs include paired ruin differences both against unlevered ACO and
  against the same family's unrestricted allocation at the same exposure.
  Intervals are Monte Carlo uncertainty conditional on this fixed history.

## Completed result

Preparation took 21 seconds, the 100-path pilot 3.4 seconds, and the final
10,000-path experiment 65.1 seconds. All archived-baseline checks passed.
At 175% exposure under joint restrictions:

| Family | Annual volatility | Equivalent saving | Ruin |
| --- | ---: | ---: | ---: |
| Proportional | 24.18% | 5.77% | 2.26% |
| Equal-weight | 21.75% | 6.15% | 2.18% |

Unlevered ACO remains at 25.28% annual volatility, 10% reference saving and
6.98% ruin. Relative to each unrestricted 175% allocation, paired ruin
changes are +0.13 percentage point (95% MC interval −0.06 to +0.32) and
−0.30 point (−0.49 to −0.11). MF-only restrictions raise equal-weight ruin
from 2.48% to 2.80%; the masks do not uniformly improve every outcome.

The manuscript now includes the explicit modern-investor counterfactual and
ACO Panel L link in the introduction, a brief main-text result, and Appendix D
with Figure 5 and Table 17. The rebuilt PDF has 52 pages. Biber and final
LaTeX passes report no warnings or undefined references; the rendered figure
and appendix table were visually checked. The main baseline is unchanged.

Sources for dates and framing are cited in the manuscript: CME's first-trade
date table, the U.S. Mint's December 9, 1974 statement, and ACO's November 18,
2024 manuscript (Table VI, Panel L). This test does not fix synthetic futures
returns, omitted carry, country-specific access, or historical market capacity.
