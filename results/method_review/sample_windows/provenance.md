# Provenance — sample windows, fixed stacked utility

Runs completed sequentially on 2026-09-04 (UTC), from
`Cederburg_lifecycle/`, with the working tree left otherwise unchanged.

## Commands and timing

```text
/usr/bin/time -p python3 build/compare_fixed_stacked_utility.py --portfolio-set ladders --runs 10000 --seed 20260827 --hedge-mode fixed_notional --bootstrap-end-treatment aco --year-from 1950 --output-json results/method_review/sample_windows/post1950_ladders_n10000.json > results/method_review/sample_windows/post1950_ladders_n10000.log 2>&1
real 24.67
user 26.28
sys 0.40

/usr/bin/time -p python3 build/compare_fixed_stacked_utility.py --portfolio-set ladders --runs 10000 --seed 20260827 --hedge-mode fixed_notional --bootstrap-end-treatment aco --year-from 1970 --output-json results/method_review/sample_windows/post1970_ladders_n10000.json > results/method_review/sample_windows/post1970_ladders_n10000.log 2>&1
real 23.58
user 25.32
sys 0.42
```

## Inputs and code hashes (SHA-256)

```text
19dcb77aa650bee8131e3171ded33c9dc21f2e002380a3d9e53fe1570d980386  data/replication-panel-trend.csv
c5066b52c7b96f6eea92d65973ac5c06320bac8aba97c7ff9ec211db4e9179d1  data/fixed-stacked-design.json
c295222a4ac2b00e4959258afa31d74c616797ab9c8f5498aee3f7fab142b370  build/compare_fixed_stacked_utility.py
0d5a79b4f36d814d7daa12cccd6fffafe18195c9fdda7ff64a17989f5fc3bfc4  build/replicate_extended.py
3bda8a7ff9eb813217d8748bfc573940bedc58c20b6d7cb520afb96a8833fb79  build/compare_lifecycle_utility.py
8b9c3fbab832d44f15db56afa213129b82711d1f5f2d26a4f8203b8d5851442e  build/compare_gold_trend_equal_vol.py
0238d5b06aa2cf4950a23e55211531c74d248773a166bd7c51bf0907e218992a  build/income_process.py
1db129dbd8615f9b0ff38d050d4954d6ebb76d0e5b2e8d396cd1149470ce204f  build/mortality.py
018bea853599c64b543eacc85e2b0e125c95293800a4bf5b46cc0755237f63f4  build/data_quality.py
737e23d325dafcc1106a664f5ca39a22197621f53ef021ea82111e0d2ceb4c71  build/investability.py
bb83360230cdca0de8776dceed06b056e3934e08ebc172db1ebb0f0c6cdebf67  build/war_periods.py
```

The run used the script defaults for all unspecified options (`mean-block=10`,
full sample mode, no country/year exclusions, and the default cost and utility
parameters). No existing result was overwritten.
