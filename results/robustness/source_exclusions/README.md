# Source-event exclusion panel

`source_event_italy_1942/replication-panel-trend.csv` is the 1927--2025 panel
with Italy 1942 removed from the international-equity and global-bond baskets.
The lifecycle scripts also drop the Italy 1942 resident row
(`erc_refocusing.source_exclusion_rows`). This is an influence diagnostic: it
does not classify the observation as erroneous or uninvestable.

`provenance.json` records the scenario definition and the SHA-256 hashes of the
inputs and of the panel. Rebuild with
`python3 build/source_exclusion_diagnostics.py` from the repository root; other
pre-declared scenarios (Italy 1942 and France 1946, Italy in all years) can be
built with `--scenario`.
