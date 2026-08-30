# External benchmarks — proprietary indexes and funds

This folder feeds the external validation of the managed-futures proxy
(appendix B):

- `paper/build_mf_benchmark_data.py` → the "proxy vs indexes" figure and the
  correlation table (`mf_vs_benchmarks.tex`, `mf_benchmark_corr.tex`);
- `build/mf_fund_correlations.py` + `paper/build_mf_pack_matrix.py` → the
  correlation and regression tables against investable managed-futures funds
  (`mf_pack_corr.tex`, `mf_pack_long_corr.tex`, `mf_pack_regressions.tex`).

**No data in this folder is versioned.** The providers (Société Générale,
BarclayHedge, testfol.io, Yahoo Finance) do not permit redistribution. Only
this file and `funds/README.md` are tracked by Git. In the absence of the
files, the scripts stop cleanly and the figures and tables remain those of
`paper/main.pdf` — not publicly rebuildable, as noted in the main README.

To regenerate these outputs, fetch the files below with authorised access to
the sources, under the exact expected names.

---

## `official-index-returns-monthly.csv`

Monthly returns of the CTA indexes. Columns:
`month, sg_trend_indicator, sg_cta, sg_trend, btop50` (`month` in `YYYY-MM`
format; decimal returns, e.g. `0.011`).

| Series | Source | Retrieval |
|---|---|---|
| SG Trend Indicator, SG CTA Index, SG Trend Index | Société Générale, daily levels, base 100 at 2000-01-01 | `https://wholesale.banking.societegenerale.com/fileadmin/indices_feeds/ti_screen/data/4.nav.csv` |
| Barclay BTOP50 | BarclayHedge, monthly returns and VAMI since 1987-01 | "Monthly Download" form at <https://portal.barclayhedge.com/cgi-bin/indices/displayHfIndex.cgi?indexCat=Barclay-Investable-Benchmarks&indexName=BTOP50-Index> |

Normalisation: SG monthly returns are computed between the last daily
observations of two consecutive months; the incomplete current month is
excluded. BTOP50 publishes monthly returns directly.

**Licence.** SG requires a licence to reference or redistribute its returns.
BarclayHedge data must not be presumed free of redistribution. Reference
snapshot: 26 August 2026.

## `testfol/{KMLMSIM,DBMF,KMLM}.csv`

Daily returns reconstructed by testfol.io. Columns:
`date, daily_return, wealth` (`date` in `YYYY-MM-DD` format).

| File | Content | Retrieval |
|---|---|---|
| `KMLMSIM.csv` | long-run simulation of the KMLM (KFA Mount Lucas) strategy | <https://testfol.io/simulated-tickers>, API <https://testfol.io/api/backtest> |
| `DBMF.csv` | iMGP DBi Managed Futures ETF, listed (splicing check) | API <https://testfol.io/api/backtest> |
| `KMLM.csv` | KFA Mount Lucas ETF, listed (splicing check) | API <https://testfol.io/api/backtest> |

`build_mf_benchmark_data.py` composes these daily returns into monthly
returns; `DBMF` and `KMLM` are trimmed of their first calendar month,
incomplete for a listed security.

**Licence.** testfol.io terms; kept for this local research only. Reference
snapshot: 26 August 2026.

## `funds/*.csv`

Daily series of listed managed-futures funds (ETFs and mutual funds),
downloaded by `build/fetch_mf_fund_data.py` from Yahoo Finance. Columns:
`date, close, adj_close` (USD; `adj_close` incorporates distributions and
splits). The ticker list, full names and ranges are in
[`funds/README.md`](funds/README.md), regenerated at each download.

**Licence.** Yahoo Finance forbids redistribution of its data. Reference
download: 30 August 2026.

---

## Regeneration

```bash
# 1. place the files above at the expected locations
#    (funds/ can be re-downloaded: python3 build/fetch_mf_fund_data.py)
# 2. appendix B:
python3 build/mf_fund_correlations.py
( cd paper && python3 build_mf_benchmark_data.py && python3 build_mf_pack_matrix.py )
```
