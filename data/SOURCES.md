# Data provenance

All series in `data/` come from sources freely accessible for non-commercial
research. No data under a commercial licence is redistributed in this
repository.

One single exception, outside the repository: the external validation of the
managed-futures proxy (`paper/build_mf_benchmark_data.py`, matrix and
regressions of `paper/build_mf_pack_matrix.py`) compares the series with
proprietary SG and Barclay BTOP50 indexes and with the testfol series
(`testfol/`: KMLMSIM, DBMF, KMLM). They are not included; without them the
scripts stop cleanly and the corresponding figures and tables remain those of
the distributed PDF. See the main README. The listed-fund series of
`data/benchmarks-externes/funds/` (`build/fetch_mf_fund_data.py`, source
Yahoo Finance) fall under the same terms and are not redistributed; they feed
the investable-fund comparison of appendix B (via
`build/mf_fund_correlations.py`).

Each file below carries, wherever possible, the check URL of the source, its
terms of use, and the script that consumes it.

---

## 1. Long-run returns by country — `JSTdatasetR6.dta`

**Source.** Jordà-Schularick-Taylor Macrohistory Database, release 6.
<https://www.macrohistory.net/database/>

**Reference.** Òscar Jordà, Moritz Schularick, Alan M. Taylor, "Macrofinancial
History and the New Business Cycle Facts", *NBER Macroeconomics Annual* 2016,
volume 31, MIT Press.

**Licence.** CC BY-NC-SA 4.0 — non-commercial use, mandatory citation,
share-alike.

**Use.** Raw Stata file, unmodified. Columns read: `eq_tr`, `bond_tr`,
`bill_rate`, `cpi`, `xrusd`, `rgdpmad`, `pop`, by
`build/build_replication_panel.py` and `build/international_equity.py`.
Coverage 1871–2020, 16 countries retained (18 in JST, 2 dropped for lack of a
complete bond series).

## 2. 2021–2025 extension — `jst-real-returns-2025.csv`

**Content.** JST extended by five years: `equity_real`, `bond_real`,
`short_real`, `inflation` by country-year, a `source` column distinguishing
JST years from added years. 2,245 observations, 1871–2025.

**Sources of the extension.**

- Equity: official total-return indexes (DAX, S&P 500 TR, Nordic OMX GI via
  FRED) or locally listed trackers, adjusted for dividends. Japan and
  Portugal approximated, flagged.
- Bonds: locally listed sovereign bond funds, or the euro-area aggregate, or
  a duration approximation for four markets without a local fund.
- Inflation and short rates: Global Macro Database (see §3).

Detailed reconstruction and validation in the repository that produces this
file. Over the overlap 2006–2020, equity correlation ≥ 0.87 for ten of the
fourteen countries; bond root-mean-square error 5.15% for the measured
series against 7.67% for the duration approximation.

## 3. Recent CPI, exchange rates and GDP — `gmd-cpi-fx.csv`

**Source.** Global Macro Database. <https://www.globalmacrodata.com/>

**Reference.** Karsten Müller, Chenzi Xu, Mohamed Lehbib, Ziliang Chen, "The
Global Macro Database: A New International Macroeconomic Dataset", NBER
Working Paper 33714, 2025.

**Licence.** Free for academic and non-profit research.

**Use.** Extract of only the columns `countryname`, `year`, `CPI`, `USDfx`,
`rGDP_USD` from the full database (the original file contains dozens of
indicators not used here). `build/international_equity.py` derives CPI and
exchange-rate changes from it to extend the panel after the last JST
observation, and real GDP in dollars to extend the market-size weights.

## 4. Market capitalisation to GDP — `bb-mcap-gdp.csv`

**Source.** Big Bang Database (Dmitry Kuvshinov, Kaspar Zimmermann).
<https://dkuvshinov.com/> — file `BBdatasetR1.xlsx`, converted to CSV, single
column `mcap_gdp`.

**Reference.** Dmitry Kuvshinov, Kaspar Zimmermann, "The Big Bang: Stock
Market Capitalization in the Long Run", *Journal of Financial Economics*,
2022.

**Licence.** CC BY-NC-SA 4.0.

**Use.** `build/international_equity.py` weights the international equity
basket by capitalisation (GDP × the `mcap_gdp` ratio) where coverage is
sufficient, and by GDP otherwise.

## 5. World equity index — `jst-ntsg-panel-2025.csv`

**Content.** World equity series, equal-weight sovereign bond series (United
States, Germany, United Kingdom, Japan) and the associated short rate,
expressed in real dollars; `equity_source` indicates the origin by period.

**Sources.** MSCI World from 1970 (Testfol proxy `URTHSIM`, total return,
deflated by the FRED U.S. CPI series `CPIAUCSL`). Before 1970, the average of
the JST markets weighted by capitalisation (World Bank, `CM.MKT.LCAP.CD`),
then by GDP.

**Use.** `build/panel_replication_tendance.py` derives from it the world
equity and world bond sleeves converted into each resident's numeraire. Over
1970–2025, the reconstruction and the index agree at 0.92 correlation, mean
gap 0.34 point.

## 6. Gold — `gold-annual.csv`

**Content.** Nominal and real gold price, annual, dollars per ounce.
`year, gold_nominal, gold_real`.

**Sources.** MeasuringWorth up to 1967
(<https://www.measuringworth.com/datasets/gold/>), then LBMA prices from 1968
(<https://www.lbma.org.uk/prices-and-data>). The two segments are not
recalibrated at the junction: the 1968 return keeps the observed move from
$35 to $41.90 per ounce.

**Terms.** MeasuringWorth asks for explicit citation. LBMA prices may require
a redistribution licence — the series here is aggregated annually and is not
the daily fixing. Before 1968, the gold price is administered:
`build/compare_fixed_stacked_utility.py` offers a
`--reallocate-administered-gold-from` variant that neutralises that period.

## 7. Monthly managed-futures proxy — `managed-futures-monthly.csv`

**Nature.** A **constructed** series, not a primary dataset. 1/6/12-month
momentum signal, volatility target, inverse-volatility sector weighting,
across four sectors (domestic equity in price indexes, bonds, commodities,
currencies). Consumed column: `mf_1_6_12_gross_return`;
`mf_1_6_12_turnover` calibrates the transaction cost in
`build/trend_costs.py`.

**Underlying signal sources.**

- Commodities: NBER Macrohistory via FRED (1841–1956) and the World Bank
  monthly Pink Sheet (1960–2025).
- Equity and rates: the 16 JST equity indexes and 16 rate markets.
- Currencies: MeasuringWorth
  (<https://www.measuringworth.com/datasets/exchangeglobal/>), and Federal
  Reserve H.10 fixings via FRED from 1971.

**Use.** `build/mf_variants.py` and `build/mf_variant_lifecycle.py` rebuild
the annual real series from this file; `build/panel_managed_futures.py`
produces `data/managed-futures-annual-real.csv`, which enters
`build/panel_replication_tendance.py`.

**Limitations.** Annual signal before 1971 in part, equity prices as price
indexes (no dividends, no futures contracts), gross-of-fee returns in the
source series — fees and costs are applied downstream. Monthly correlation
2000–2025 of about 0.51–0.53 with SG CTA, SG Trend and BTOP50: the goal is an
aligned proxy, not a replication of rolled futures.

## 8. Monthly U.S. CPI — `cpi-monthly.csv`

**Source.** Bureau of Labor Statistics, series CPIAUCSL, via FRED.
<https://fred.stlouisfed.org/series/CPIAUCSL>

**Use.** Monthly deflator of the managed-futures proxy in
`build/panel_managed_futures.py` (deflation month by month before
composition).

---

## Reconstructed panels

`international-equity.csv`, `replication-panel.csv`,
`managed-futures-annual-real.csv` and `replication-panel-trend.csv` are
produced by step 1 of `build/rebuild_all.sh` from the files above. They are
versioned so the experiment can be run without `pandas` or reconstruction,
and they regenerate identically.

## Citation

Please cite the primary sources listed above (JST, Global Macro Database,
Big Bang Database, MeasuringWorth) per their respective terms, in addition to
the manuscript.
