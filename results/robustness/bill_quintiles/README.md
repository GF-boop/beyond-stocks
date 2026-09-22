# Financing-rate (bill) volatility diagnostic

This is an ex-post attribution diagnostic, not a simulated policy or a
replacement of the main panel. It decomposes the arithmetic return increment of
the 175% over the 100% allocation, by equal-weighted resident country-years and
by ex-post pooled bill-return quintile.

Producer: `build/bill_quintiles.py`, which also writes
`paper/new_paper/figures/bill_quintiles.tex`. It reproduces `audit.json` exactly.

## Definition

From `audit.json`: "175% minus 100%, fixed composition; equal-weighted resident
country-years; ex-post pooled bill quintiles. Additive arithmetic-return
attribution, not utility or causal attribution."

Inputs fingerprinted in `audit.json` (`inputs_sha256`):
`data/replication-panel-trend.csv`, `results/main_ladders_n10000.json`,
`data/managed-futures-monthly.csv`, `data/cpi-monthly.csv`, and the producer script.

## Contents

- `audit.json`: per-quintile and per-period attribution for the ACO,
  Proportional and Equal-weight families (`quintiles`, `periods`,
  `mf_volatility`).
