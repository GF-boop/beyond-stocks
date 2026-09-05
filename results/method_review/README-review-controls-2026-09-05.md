# Review controls — 5 September 2026

These experiments prepare the additional evidence requested during the
manuscript review. They use the versioned annual panel
`data/replication-panel-trend.csv`, fixed-notional hedges, a 30 bp financing
spread and 10 bp hedge friction unless the experiment varies one of those
terms. All 10,000-path lifecycle comparisons use paired return, income and
mortality draws, seed `20260827`, stationary blocks of ten years and the ACO
33/67, unlevered, 10%-saving benchmark.

The results are sensitivity evidence, not forecasts or investment advice.
`trend-haircut` is an annual deduction from the reconstructed MF return; it is
not an estimate of an investable fund's alpha or fee.

## Outputs and interpretation

| Question | Output | Main result |
|---|---|---|
| How much MF-return deterioration can the 175% rules absorb? | `mf_return_haircuts/` | The proportional rule remains below 10% equivalent saving through a 600 bp annual haircut (9.55%) but not at 700 bp (10.39%). The equal-weight rule is below 10% at 300 bp (9.39%) and above it at 400 bp (10.67%). |
| What happens at a common retirement-income target? | `common_consumption_target/aco_common_target_n10000.json` | Each path uses ACO's planned 4%-of-ACO-wealth financial draw. Conditional on reaching retirement with a positive target (9,832 paths), the proportional rule has a 2.21% shortfall probability, versus 7.10% for ACO; equal weight has 8.12%. |
| Do the 175% results survive financing and hedge-cost stress? | `costs_175/` | At a 250 bp financing spread, equivalent saving is 9.28% for proportional and 10.36% for equal weight. At 300 bp it is 10.34% and 11.58%; their ruin is still 5.32% and 6.92%, respectively, against ACO's 6.98% baseline ruin. |
| Do gold and bonds matter after the administered-gold era? | `post1970_ablation/ablation_1970_n10000.json` | On 1970–2025, all complete and ablated 175% rules have lower estimated ruin than ACO. Removing gold raises proportional-rule ruin from 0.04% to 0.64%, and equal-weight ruin from 0.03% to 0.08%; removing MF raises them to 0.68% and 0.81%. These are compositional reallocations at fixed gross exposure, not additive asset contributions. |
| Does the result survive uncertainty in the observed history? | `historical_panel_bootstrap/` | Across 100 outer resamples of complete calendar-year cross-sections and 1,000 paired inner paths per resample, the proportional 175% rule beats ACO on ruin in 98%, 99% and 100% of panels for outer mean blocks of 5, 10 and 20 years. Equal weight does so in 86%, 94% and 97%. |

## Exact result ranges

The common-target output corrects the previous inclusion of pre-retirement
deaths in funding ratios: a path with no retirement now contributes zero
retirement years, rather than an artificial year of required withdrawals.
All funding and shortfall ratios use the same eligible paths. For equal-weight
175%, the implied initial draw is a median 2.93% of its own capital,
a 90th percentile 6.83%, and exceeds 4% on 32.26% of eligible paths.
This distribution does not establish that lower volatility generally implies
a draw above 4%: the relevant quantity is the paired retirement-capital ratio.

### MF annual-return haircut, full panel

| Haircut | Proportional: saving / ruin | Equal weight: saving / ruin |
|---:|---:|---:|
| 100 bp | 6.35% / 2.32% | 7.35% / 3.11% |
| 200 bp | 6.89% / 2.57% | 8.30% / 3.88% |
| 300 bp | 7.47% / 3.01% | 9.39% / 4.76% |
| 400 bp | 8.10% / 3.39% | 10.67% / 5.92% |
| 600 bp | 9.55% / 4.65% | 13.95% / 9.12% |
| 700 bp | 10.39% / 5.36% | 16.07% / 11.24% |

### Outer historical-panel bootstrap: ruin difference versus ACO

The interval is the 5th–95th percentile across outer panels. It includes both
variation in the sampled calendar history and the remaining 1,000-path inner
Monte Carlo noise, so it must not be reported as a conventional confidence
interval.

| Outer mean block | Proportional median [p05, p95] | Equal weight median [p05, p95] |
|---:|---:|---:|
| 5 years | −5.50 pp [−17.51, −0.50] | −5.05 pp [−18.26, +0.82] |
| 10 years | −5.15 pp [−12.90, −1.19] | −4.70 pp [−13.11, +0.11] |
| 20 years | −5.05 pp [−11.01, −1.49] | −4.10 pp [−11.04, −0.60] |

## Reproduction commands

```bash
# One file per haircut: substitute 0.01, 0.02, ..., 0.07.
python3 build/compare_fixed_stacked_utility.py --runs 10000 --portfolio-set ladders \
  --trend-haircut 0.03 --output-json results/method_review/mf_return_haircuts/haircut_300bp_n10000.json

python3 build/common_consumption_target.py --runs 10000 \
  --output-json results/method_review/common_consumption_target/aco_common_target_n10000.json

python3 build/sleeve_ablation.py --runs 10000 --year-from 1970 \
  --output-json results/method_review/post1970_ablation/ablation_1970_n10000.json

python3 build/compare_fixed_stacked_utility.py --runs 10000 --portfolio-set ladders --spread 0.025 \
  --output-json results/method_review/costs_175/financing_250bp_n10000.json

python3 build/historical_panel_bootstrap.py --outer-replicates 100 --inner-runs 1000 \
  --outer-mean-block 10 \
  --output-json results/method_review/historical_panel_bootstrap/calendar_blocks_10y_outer100_inner1000.json
```

The outer bootstrap script resamples all rows from a chosen calendar year
together, then relabels the sampled years before the inner country-block
bootstrap. This retains the cross-country and cross-asset dependence within
each historical calendar year and prevents duplicate country-year keys in the
inner engine.
