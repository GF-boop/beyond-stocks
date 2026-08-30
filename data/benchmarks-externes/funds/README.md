# Daily series of listed managed-futures funds (ETFs/mutual funds)

Downloaded by `build/fetch_mf_fund_data.py` from the Yahoo Finance chart/v8
endpoint (https://query1.finance.yahoo.com). Last download: 2026-08-30.

One file per ticker: `date, close, adj_close` (USD). `adj_close`
incorporates distributions and splits; it is the input used for the total
return net of fees in `build/mf_fund_correlations.py`. The provider's terms
of use do not permit redistribution: gitignored folder, same terms as the
SG/Barclay indexes and the testfol series.

| Ticker | Fund | Yahoo type | Start | End | Days |
|---|---|---|---|---|---|
| WTMF | WisdomTree Managed Futures Strategy Fund | ETF | 2011-01-05 | 2026-08-28 | 3935 |
| QMHIX | AQR Managed Futures Strategy HV Fund, class I | MUTUALFUND | 2013-07-16 | 2026-08-28 | 3301 |
| AHLIX | American Beacon AHL Managed Futures Fund, class R5 | MUTUALFUND | 2014-08-20 | 2026-08-28 | 3024 |
| AHLT | American Beacon AHL Trend ETF | ETF | 2023-08-31 | 2026-08-28 | 751 |
| IMF | Invesco Managed Futures Strategy ETF | ETF | 2025-03-19 | 2026-08-28 | 364 |
| ISMF | iShares Managed Futures Active ETF | ETF | 2025-03-13 | 2026-08-28 | 368 |
| 0P0001BD8S | AQR Apex UCITS Fund, class RA USD (ISIN LU1662495974) | MUTUALFUND | 2022-03-07 | 2026-08-28 | 1004 |

Notes. `AHLIX` is the American Beacon AHL Managed Futures (R5) mutual fund;
the AHL Trend ETF trades under ticker `AHLT`. `0P0001BD8S` is the Yahoo
symbol of the RA USD class of the AQR Apex UCITS fund (ISIN LU1662495974), a
multi-strategy fund of which trend following is one component. IMF and ISMF
were launched only in March 2025; AHLT in August 2023.
