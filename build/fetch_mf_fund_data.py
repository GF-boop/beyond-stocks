"""Download the daily series of listed managed-futures funds (ETFs, mutual funds).

Source: Yahoo Finance, ``chart/v8`` endpoint —
<https://query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>>. One CSV file per
ticker in ``data/benchmarks-externes/funds/``: ``date, close, adj_close``. The
``adj_close`` column includes distributions and splits; the downstream monthly
compounding (``build/mf_fund_correlations.py``) therefore gives the fund's
total return net of fees.

Basket:

* ``WTMF``  WisdomTree Managed Futures Strategy Fund (ETF, 2011)
* ``QMHIX`` AQR Managed Futures Strategy HV Fund, class I (mutual fund, 2013)
* ``AHLIX`` American Beacon AHL Managed Futures Fund, class R5 (mutual fund, 2014)
* ``AHLT``  American Beacon AHL Trend ETF (2023) — the "AHL Trend"; the ticker
  AHLIX often cited for this fund is the AHL Managed Futures mutual fund
* ``IMF``   Invesco Managed Futures Strategy ETF (2025)
* ``ISMF``  iShares Managed Futures Active ETF (2025)
* ``0P0001BD8S`` AQR Apex UCITS Fund, class RA USD (ISIN LU1662495974) —
  AQR multi-strategy fund of which trend following is one component; under
  this symbol Yahoo returns history only from March 2022.

These data come from a third-party provider whose terms do not permit
redistribution: the folder is under ``data/benchmarks-externes/`` (gitignored,
same terms as the SG/Barclay indexes and the testfol series). The script also
writes a ``README.md`` recording provenance and coverage.
"""

from __future__ import annotations

import datetime
import json
import os
import time
import urllib.error
import urllib.request
import csv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "data", "benchmarks-externes", "funds")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) research-data-fetch"
PERIOD1_EPOCH_2000 = 946684800
REQUEST_TIMEOUT_S = 30.0
RETRIES = 4
BACKOFF_S = 4.0
INTER_REQUEST_SLEEP_S = 2.0

FUNDS = [
    ("WTMF", "WisdomTree Managed Futures Strategy Fund"),
    ("QMHIX", "AQR Managed Futures Strategy HV Fund, class I"),
    ("AHLIX", "American Beacon AHL Managed Futures Fund, class R5"),
    ("AHLT", "American Beacon AHL Trend ETF"),
    ("IMF", "Invesco Managed Futures Strategy ETF"),
    ("ISMF", "iShares Managed Futures Active ETF"),
    ("0P0001BD8S", "AQR Apex UCITS Fund, class RA USD (ISIN LU1662495974)"),
]


def http_get_json(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(BACKOFF_S * (attempt + 1))
    raise RuntimeError(f"failed after {RETRIES} attempts: {url}") from last_error


def fetch_daily(symbol: str) -> tuple[list[tuple[str, float, float]], dict]:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={PERIOD1_EPOCH_2000}&period2={int(time.time())}"
        f"&interval=1d&includeAdjustedClose=true"
    )
    payload = http_get_json(url)
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    timestamps = result.get("timestamp") or []
    quotes = result["indicators"]["quote"][0]
    adj_close = result["indicators"].get("adjclose", [{}])[0].get("adjclose") or quotes["close"]
    rows: list[tuple[str, float, float]] = []
    for ts, close, adj in zip(timestamps, quotes["close"], adj_close):
        if close is None or adj is None:
            continue
        day = datetime.datetime.fromtimestamp(ts, datetime.UTC).date().isoformat()
        rows.append((day, float(close), float(adj)))
    info = {
        "yahoo_name": meta.get("longName") or meta.get("shortName"),
        "instrument_type": meta.get("instrumentType"),
        "currency": meta.get("currency"),
        "first": rows[0][0] if rows else None,
        "last": rows[-1][0] if rows else None,
        "n_days": len(rows),
    }
    return rows, info


def write_csv(symbol: str, rows: list[tuple[str, float, float]]) -> None:
    path = os.path.join(OUT_DIR, f"{symbol}.csv")
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "close", "adj_close"])
        for day, close, adj in rows:
            writer.writerow([day, repr(close), repr(adj)])


def write_readme(records: list[dict]) -> None:
    lines = [
        "# Daily series of listed managed-futures funds (ETFs/mutual funds)",
        "",
        "Downloaded by `build/fetch_mf_fund_data.py` from the Yahoo Finance chart/v8",
        "endpoint (https://query1.finance.yahoo.com).",
        f"Last download: {datetime.date.today().isoformat()}.",
        "",
        "One file per ticker: `date, close, adj_close` (USD). `adj_close`",
        "incorporates distributions and splits; it is the input used for the total",
        "return net of fees in `build/mf_fund_correlations.py`. The provider's terms",
        "of use do not permit redistribution: gitignored folder, same terms as the",
        "SG/Barclay indexes and the testfol series.",
        "",
        "| Ticker | Fund | Yahoo type | Start | End | Days |",
        "|---|---|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            f"| {record['symbol']} | {record['fund']} ({record['yahoo_name']}) "
            f"| {record['instrument_type']} | {record['first']} | {record['last']} "
            f"| {record['n_days']} |"
        )
    lines += [
        "",
        "Notes. `AHLIX` is the American Beacon AHL Managed Futures (R5) mutual fund;",
        "the AHL Trend ETF trades under ticker `AHLT`. `0P0001BD8S` is the Yahoo",
        "symbol of the RA USD class of the AQR Apex UCITS fund (ISIN LU1662495974), a",
        "multi-strategy fund of which trend following is one component. IMF and ISMF",
        "were launched only in March 2025; AHLT in August 2023.",
        "",
    ]
    with open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    records = []
    for symbol, fund in FUNDS:
        rows, info = fetch_daily(symbol)
        write_csv(symbol, rows)
        records.append({"symbol": symbol, "fund": fund, **info})
        print(f"{symbol:<12} {info['n_days']:>5} days  {info['first']} -> {info['last']}"
              f"  [{info['yahoo_name']}]")
        time.sleep(INTER_REQUEST_SLEEP_S)
    write_readme(records)
    print(f"OK: {len(records)} series in {os.path.relpath(OUT_DIR)}")


if __name__ == "__main__":
    main()
