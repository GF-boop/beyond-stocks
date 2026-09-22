# Canonical monthly snapshot for managed futures

> Adapted from the README of the sibling `CTO_vs_PEA` project. This repository
> contains only the files read by the simulation engine under `data/mf-inputs/`:
> `all-assets-monthly.csv`, `cash-returns-monthly.csv`,
> `fx-spot-returns-monthly.csv`, `series-metadata.csv`,
> `source-segments.csv`, and `snapshot-manifest.csv`. Other files mentioned
> below remain in `CTO_vs_PEA`.

The local data directory contains monthly series ready for the simulations.
No download or reconstruction pipeline is needed to use them; the main input
is `data/mf-inputs/all-assets-monthly.csv`. `build_canonical_assets.py` is retained
only to audit the construction and produce a future version. It runs offline.

## Frozen scope

- Monthly nominal returns in decimal form (`0.01` means 1%), January 1921 to
  December 2025.
- No inflation adjustment, fees, or interpolation.
- The first return of each new source segment is missing, so a signal cannot
  silently cross a source seam.

## Files

| File | Contents |
|---|---|
| `all-assets-monthly.csv` | Long format: asset class, market, return type, source segment, and default-universe membership |
| `equity-returns-monthly.csv` | 18 national price indexes, excluding dividends |
| `bond-returns-monthly.csv` | 18 sovereign ten-year excess-return proxies with carry and price changes |
| `commodity-returns-monthly.csv` | 19 spot/cash commodity series |
| `precious-metals-returns-monthly.csv` | Gold from 1921 and silver from 1960 |
| `currency-returns-monthly.csv` | Six synthetic forwards from month-end H.10 spot rates and short-rate differentials |
| `cash-returns-monthly.csv` | Monthly cash returns by country/currency, already lagged one month |
| `cash-return-sources-monthly.csv` | Source of each cash observation (monthly OECD or annual JST/GMD fallback) |
| `fx-spot-returns-monthly.csv` | USD spot changes for six H.10 currencies, used only to convert local P&L |
| `equity-benchmarks-monthly.csv` | SPYSIM, VTISIM, VXUSSIM, URTHSIM, and VTSIM; excluded from the default universe because they overlap |
| `bond-benchmarks-monthly.csv` | SHYSIM, IEISIM, IEFSIM, and TLTSIM; excluded from the default universe |
| `series-metadata.csv` | Series dictionary and principal limitations |
| `source-segments.csv` | Provenance and transformation of each segment |
| `flagged-outliers.csv` | Extreme moves retained but flagged for sensitivity checks |
| `snapshot-manifest.csv` | File sizes, periods, and SHA-256 hashes |
| `VALIDATION.txt` | Summary of checks and comparisons |

The public OECD and NBER data must be cited. The committed snapshot is a
frozen research input: its original market labels and descriptive notes are
preserved byte for byte to retain the recorded SHA-256 hashes. The builder
uses English labels for any future snapshot.

## Construction choices

### Equities

The default universe contains only the 18 JST-panel countries. NBER indexes
extend the US, UK, German, and French histories before OECD coverage. All are
price indexes: adding SPYSIM as a nineteenth market would both introduce
dividends and count the US twice. Testfol total-return benchmarks remain
available for checks with `default_universe=no`.

Coverage is thin before 1960. At the end of 1921, the snapshot has three
equity markets, three bond markets, four commodities, and gold. The volatility
of a three-market historical sector should not be compared mechanically with
that of a modern eighteen-market sector without an explicit scaling rule.

### Bonds

A yield is never used directly as a return. Sovereign yields are converted
into the return of a par bond initially maturing in ten years. Its coupon is
the preceding month's yield; one month later, the remaining twenty
semiannual cash flows are discounted at the new yield. The formula admits
the negative yields observed in Europe.

Before OECD coverage, the US uses NBER long rates from 1919 with a ten-year
proxy maturity; the UK uses Consol through 1934, followed by the Bank of
England ten-year series; and France uses the observed price of the perpetual
3% rente through 1940. These segments add history but are neither uniform
observed bond indexes nor observed futures histories.

The currency's three-month cash return is then subtracted to represent a
bond future. Monthly OECD/FRED fixings take priority. Before they exist,
the annual JST/GMD nominal short rate is applied in the following year, so
future annual releases cannot enter current-month returns.
`cash-return-sources-monthly.csv` records this choice for each observation.

### Currency convention

National equity and bond returns remain in local currency in
`all-assets-monthly.csv`. The separate `fx-spot-returns-monthly.csv` holds
USD spot changes for H.10 currencies, distinct from the forward returns of
the currency sector. The managed-futures engine uses these rates to convert
available local P&L into USD. It drops a foreign market when its USD spot
rate is unavailable rather than implicitly treating its P&L as USD.

### Commodities and metals

The long NBER/BLS series join the World Bank Pink Sheet without a return
across the source seam. Obvious duplicates (corn/maize, wheat, sugar, copper)
count as one market each. Gold uses the monthly repeated official US price
through 1959 and the World Bank monthly price thereafter, retaining the
1968 free-market rise. No custody fee is included.

These are spot/cash prices. They can support a trend proxy but cannot
recover the carry, basis, or rolls of futures contracts that did not exist
or whose prices were not archived.

### Currencies and collateral

The six AUD, CAD, EUR, JPY, CHF, and GBP markets use Federal Reserve H.10
daily fixings, taking the last available fixing in each month and converting
it to USD per foreign-currency unit. Their signals can therefore use
`t-1` without the overlap present in monthly-average prices. Synthetic
long-forward P&L combines the spot return, foreign cash return, and negative
USD cash return, all based on information known in the previous month.
EUR uses the euro-area fixing; predecessor currencies are not reconstructed.

The engine can add the USD cash return from `cash-returns-monthly.csv`
once to portfolio NAV as collateral income. It does not add it again to
contracts already expressed as excess returns.

## Choices left to the managed-futures signal

The snapshot deliberately contains no strategy rule. A future implementation
must set the lookback, signal lag, volatility estimator, leverage cap, sector
weights, treatment of short histories, and costs. Overlapping benchmarks
must stay out of automatic market counts.
