# Monthly managed-futures proxy: MOP, AQR, and 1/6/12 variants

This strategy reads the frozen snapshot in `data/mf-inputs/` directly.
It downloads no data and reconstructs no market series. The engine came
from the sibling `CTO_vs_PEA` project and regenerates
`data/managed-futures-monthly.csv` byte for byte.

```bash
python3 build/managed_futures/run_managed_futures.py
```

Outputs go to the unversioned `build/managed_futures/output/` directory.
`rebuild_all.sh` copies the monthly series into `data/`. Outputs include
monthly returns, compounded annual returns, sector contributions, market
positions, period statistics, and SHA-256 hashes. The annual file includes
only calendar years with twelve monthly returns, so it can join an annual
panel without inventing a partial year.

## Signal

For each market and month `t`:

1. Compute compounded returns over 1, 3, 6, and 12 months. Monthly-average
   prices stop at `t-2`; month-end H.10 currency prices stop at `t-1`.
2. Map each momentum return to `-1`, `0`, or `+1`.
3. Publish two fixed blends: 1/3/12, used by AQR in its historical
   reconstruction, and 1/6/12, the project's original variant. Each
   blend averages its signal signs equally.
4. Estimate volatility from the preceding 36 months, requiring at least
   24 observations.
5. Scale inversely with volatility, targeting 15% per market with a
   maximum leverage multiplier of 4.

The default `all_four_sectors` profile retains national equities, bonds,
commodities, and currencies whenever each market is available and can be
converted properly into USD. Sectors receive inverse-volatility weights
using lagged estimates rather than equal weights. Historical equities
therefore remain in the universe even though they are cash price indexes,
not observed futures. Gold and silver belong to commodities; they do not
form an artificial fifth sector with a 20% weight.

`--universe-profile legacy_three_sector` reproduces the earlier
equity-bond-commodity universe. `all_four_sectors` adds currencies for
an SG Trend Indicator-style sensitivity. `historical_equity_transition`
is another sensitivity, dropping equities after December 1970 when H.10
currencies become available. The default `--sector-weighting inverse_vol`
uses sector volatilities over the previous 36 months and falls back to
equal weights when too little history is available.

The gross portfolio targets 10% volatility based on its lagged 36-month
estimate, with a leverage multiplier capped at 3.

Month `t-1` is deliberately skipped for monthly-average prices. Using
the average of `t-1` to predict the average of `t` creates temporal
overlap and greatly inflates the short signal. The diagnostic option
`--signal-skip-months 0` reproduces that naive convention; the comparison
is in `signal-lag-diagnostic.csv`.

## Gross and net returns

`managed-futures-monthly.csv` reports separate 1-, 3-, 6-, and 12-month
strategies and the 1/3/12 and 1/6/12 blends. Each has:

- `gross_return`: return before fees;
- `net_return`: gross return less a 0.85% annual fee and 3 basis points
  per unit of turnover;
- `cash_collateral_return`, `gross_exposure`, `turnover`, and the
  volatility-targeting multiplier.

Bond and currency contract P&L is expressed in excess of cash. The engine
adds USD cash income once to NAV as collateral; `--no-add-usd-collateral`
removes it for a sensitivity check. The local, versioned collateral series
is `data/mf-inputs/cash-returns-monthly.csv`.

By default, local-currency equity returns are converted to USD using
month-end spot rates. Bonds are synthetic cash-excess P&L: only their P&L
is converted at spot, without exposing principal to exchange rates. This
matches a USD-collateralized future: zero local P&L remains zero when the
currency moves. Spot rates come from
`data/mf-inputs/fx-spot-returns-monthly.csv`, separately from the
currency-sector forward returns. A foreign market is excluded in any month
without an available USD spot rate. `--no-futures-pnl-fx` restores the
earlier convention that exposed synthetic principal; it is retained only
as a sensitivity check.

Costs can be changed with `--annual-fee` and `--transaction-bps`.

## Important limitations

- Six currencies are synthetic forwards from month-end H.10 spot and
  short-rate differentials.
- USD conversion limits foreign equities and bonds to periods with
  available H.10 spot rates, reducing early coverage.
- National equities are price returns without dividends.
- Commodities and metals are spot returns without observed roll or basis;
  their assumed futures roll is zero, so their return level is not an
  observed futures index.
- Bonds are synthetic ten-year excess cash P&L.
- The universe expands with data availability; monthly active-market
  counts are published.
- Risk scaling is revised monthly using a 36-month window, not the daily
  deleveraging of a CTA.
- The published Sharpe ratio uses zero as its reference rate, so it is
  not an excess-return Sharpe even though USD collateral is included.

These limitations make the series useful for testing trend mechanics and
diversification, while limiting claims about the historical performance
of an investable futures product.

## External validation

`paper/build_mf_benchmark_data.py` and
`paper/build_mf_pack_matrix.py` produce comparisons with SG CTA,
SG Trend, BTOP50, and listed funds for the paper's internet appendix.
For 2000–2025, the monthly correlation of the 1/6/12 blend is about
0.51 with SG CTA, 0.49 with SG Trend, and 0.53 with BTOP50.

`build/mf_excess_return_check.py` rebuilds the series using
futures-consistent returns (equities with dividends and less local cash,
commodities less USD cash). The average annual difference is -0.05
percentage points; the paper's results change by at most a few tenths
of a point (`results/audit/mf_excess_return_check.json`).
