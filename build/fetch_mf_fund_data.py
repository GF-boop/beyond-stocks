"""Télécharge les séries quotidiennes de fonds managed futures cotés (ETF/OPCVM).

Source : Yahoo Finance, endpoint ``chart/v8`` —
<https://query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>>. Un fichier CSV
par ticker dans ``data/benchmarks-externes/funds/`` : ``date, close, adj_close``.
La colonne ``adj_close`` intègre distributions et splits ; la composition
mensuelle aval (``build/mf_fund_correlations.py``) fournit donc le rendement
total net de frais du fonds.

Panier :

* ``WTMF``  WisdomTree Managed Futures Strategy Fund (ETF, 2011)
* ``QMHIX`` AQR Managed Futures Strategy HV Fund, classe I (OPCVM, 2013)
* ``AHLIX`` American Beacon AHL Managed Futures Fund, classe R5 (OPCVM, 2014)
* ``AHLT``  American Beacon AHL Trend ETF (2023) — l'« AHL Trend » ; le ticker
  AHLIX souvent cité à tort pour ce fonds désigne l'OPCVM AHL Managed Futures
* ``IMF``   Invesco Managed Futures Strategy ETF (2025)
* ``ISMF``  iShares Managed Futures Active ETF (2025)
* ``0P0001BD8S`` AQR Apex UCITS Fund, classe RA USD (ISIN LU1662495974) —
  fonds multi-stratégies d'AQR dont le trend following est une composante ;
  sous ce symbol Yahoo ne remonte que l'historique depuis mars 2022.

Ces données proviennent d'un fournisseur tiers dont les conditions d'usage ne
permettent pas la redistribution : le dossier est sous ``data/benchmarks-externes/``
(gitignore, mêmes termes que les indices SG/Barclay et les séries testfol).
Le script écrit aussi un ``README.md`` retraçant provenance et couverture.
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
    ("QMHIX", "AQR Managed Futures Strategy HV Fund, classe I"),
    ("AHLIX", "American Beacon AHL Managed Futures Fund, classe R5"),
    ("AHLT", "American Beacon AHL Trend ETF"),
    ("IMF", "Invesco Managed Futures Strategy ETF"),
    ("ISMF", "iShares Managed Futures Active ETF"),
    ("0P0001BD8S", "AQR Apex UCITS Fund, classe RA USD (ISIN LU1662495974)"),
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
    raise RuntimeError(f"echec apres {RETRIES} tentatives : {url}") from last_error


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
        "# Séries quotidiennes de fonds managed futures (ETF/OPCVM)",
        "",
        "Téléchargées par `build/fetch_mf_fund_data.py` depuis l'endpoint",
        "chart/v8 de Yahoo Finance (https://query1.finance.yahoo.com).",
        f"Dernier téléchargement : {datetime.date.today().isoformat()}.",
        "",
        "Un fichier par ticker : `date, close, adj_close` (USD). `adj_close`",
        "intègre distributions et splits ; c'est lui qui sert au rendement total",
        "net de frais dans `build/mf_fund_correlations.py`. Les conditions",
        "d'usage du fournisseur ne permettent pas la redistribution : dossier",
        "gitignore, mêmes termes que les indices SG/Barclay et les séries testfol.",
        "",
        "| Ticker | Fonds | Type Yahoo | Début | Fin | Jours |",
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
        "Notes. `AHLIX` est l'OPCVM American Beacon AHL Managed Futures (R5) ;",
        "l'ETF AHL Trend a pour ticker `AHLT`. `0P0001BD8S` est le symbol Yahoo",
        "de la classe RA USD du fonds AQR Apex UCITS (ISIN LU1662495974),",
        "multi-stratégies dont le trend following est une composante. IMF et",
        "ISMF n'ont été lancés qu'en mars 2025 ; AHLT en août 2023.",
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
        print(f"{symbol:<12} {info['n_days']:>5} jours  {info['first']} -> {info['last']}"
              f"  [{info['yahoo_name']}]")
        time.sleep(INTER_REQUEST_SLEEP_S)
    write_readme(records)
    print(f"OK : {len(records)} series dans {os.path.relpath(OUT_DIR)}")


if __name__ == "__main__":
    main()
