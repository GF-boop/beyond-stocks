# Source-event and source-country diagnostics

These are influence diagnostics on the 1927--2025 full panel. They do not
classify any historical observation as erroneous or unavailable to investors.
Every run uses 10,000 paired lifecycle simulations, seed `20260827`, the ACO
bootstrap-continuation convention, the fixed-notional hedge and baseline costs.

`source_event_italy_1942/` removes Italy 1942 from the resident bootstrap row,
international-equity baskets and global-bond baskets. Its ACO/equal-weight-175
results are 18.17%/17.30% annual volatility, 7.19%/2.61% ruin and
10.00%/7.02% equivalent saving.

`source_events_italy_1942_france_1946/` applies the same treatment to both
specified country-years. Its ACO/equal-weight-175 results are
17.50%/15.61% annual volatility, 7.17%/2.74% ruin and 10.00%/7.03%
equivalent saving.

`source_country_italy_all_years/` removes Italy as a resident and from all
international-equity and global-bond baskets. Its ACO/equal-weight-175 results
are 18.08%/17.31% annual volatility, 7.54%/2.70% ruin and
10.00%/7.16% equivalent saving.

`provenance.json` records the research contract, scenario definitions,
input/code SHA-256 hashes and the checksums of every result JSON. Re-run all
three scenarios with `python3 build/source_exclusion_diagnostics.py --runs 10000`
from the repository root.
