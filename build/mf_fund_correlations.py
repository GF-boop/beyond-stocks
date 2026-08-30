"""Corrélations des fonds managed futures cotés entre eux et avec le proxy.

Entrées :

* ``data/managed-futures-monthly.csv`` — proxy maison, colonne
  ``mf_1_6_12_net_return`` (1926-03 → 2025-12) ;
* ``data/benchmarks-externes/funds/<TICKER>.csv`` — séries quotidiennes
  ``date, close, adj_close`` produites par ``build/fetch_mf_fund_data.py``
  (Yahoo Finance). ``adj_close`` donne le rendement total net de frais ;
  composition mensuelle par produit, premier mois civil retiré (mois
  incomplet, même convention que pour les séries testfol du dépôt).

Sortie : ``results/mf_fund_correlations.json`` et résumé console. Trois
fenêtres communes pour le test « peloton » :

* ``2015-2025`` : WTMF, QMHIX, AHLIX (les trois fonds avec plus de dix ans
  d'historique), plus le proxy ;
* ``2024-2025`` : ajoute AQR Apex UCITS (2022) et AHL Trend ETF (2023) ;
* ``2025``     : les sept fonds, avril → décembre 2025 seulement (IMF et ISMF
  lancés en mars 2025) — échantillon court, à lire avec prudence.

Pour chaque fenêtre : corrélations proxy/fonds, moyenne des corrélations
paire-à-paire des fonds, et corrélation de chaque acteur avec le « centroïde »
du peloton (moyenne équipondérée des fonds, hors soi-même pour les membres).
Si le proxy se comporte comme un membre du peloton, sa corrélation au
centroïde doit se situer dans la fourchette de celles des fonds eux-mêmes.
"""

from __future__ import annotations

import calendar
import csv
import datetime
import json
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "data")
FUNDS_DIR = os.path.join(DATA, "benchmarks-externes", "funds")
PROXY_CSV = os.path.join(DATA, "managed-futures-monthly.csv")
PROXY_COL = "mf_1_6_12_net_return"
OUT_JSON = os.path.join(ROOT, "results", "mf_fund_correlations.json")

FUNDS = [
    ("WTMF", "0. WisdomTree Managed Futures Strategy Fund (ETF, 2011)"),
    ("QMHIX", "AQR Managed Futures Strategy HV Fund, classe I (OPCVM, 2013)"),
    ("AHLIX", "American Beacon AHL Managed Futures Fund, classe R5 (OPCVM, 2014)"),
    ("AHLT", "American Beacon AHL Trend ETF (2023)"),
    ("IMF", "Invesco Managed Futures Strategy ETF (2025)"),
    ("ISMF", "iShares Managed Futures Active ETF (2025)"),
    ("APEX", "AQR Apex UCITS Fund RA USD Acc (multi-stratégies, 2022)"),
]
TICKER_FILE = {"APEX": "0P0001BD8S.csv"}

WINDOWS = {
    "2015-2025": ("2015-01", "2025-12", ["WTMF", "QMHIX", "AHLIX"]),
    "2024-2025": ("2024-01", "2025-12", ["WTMF", "QMHIX", "AHLIX", "APEX", "AHLT"]),
    "2025": ("2025-04", "2025-12", ["WTMF", "QMHIX", "AHLIX", "APEX", "AHLT", "IMF", "ISMF"]),
}


def load_proxy() -> dict[str, float]:
    out = {}
    with open(PROXY_CSV, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get(PROXY_COL)
            if value:
                out[row["month"]] = float(value)
    return out


def fund_monthly(symbol: str) -> dict[str, float]:
    path = os.path.join(FUNDS_DIR, TICKER_FILE.get(symbol, f"{symbol}.csv"))
    level: dict[str, float] = {}
    previous_adj: float | None = None
    last_date = ""
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            day, adj = row["date"], float(row["adj_close"])
            if previous_adj is not None:
                month = day[:7]
                level[month] = level.get(month, 1.0) * (1.0 + adj / previous_adj - 1.0)
            previous_adj = adj
            last_date = day
    monthly = {month: value - 1.0 for month, value in level.items()}
    if monthly:
        del monthly[min(monthly)]
    year, mon = (int(part) for part in last_date[:7].split("-"))
    if last_date[8:10] < f"{calendar.monthrange(year, mon)[1]:02d}":
        del monthly[max(monthly)]
    return monthly


def window(series: dict[str, float], lo: str = "0000-00", hi: str = "9999-99") -> dict[str, float]:
    return {m: v for m, v in series.items() if lo <= m <= hi}


def correlation(a: dict[str, float], b: dict[str, float]) -> tuple[float, int, str, str]:
    months = sorted(set(a) & set(b))
    xs = [a[m] for m in months]
    ys = [b[m] for m in months]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    if den == 0.0:
        return float("nan"), len(months), months[0], months[-1]
    return num / den, len(months), months[0], months[-1]


def regression(x: list[float], y: list[float]) -> dict:
    """OLS ``y = alpha + beta x`` avec erreurs-types classiques (homoscédastiques).

    Renvoie ``n, alpha, beta, r2, t_alpha, t_beta``. Utilisé pour la
    décomposition ``R_fund = alpha + beta R_proxy + eps`` de l'annexe B.
    """
    n = len(x)
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((v - mx) ** 2 for v in x)
    sxy = sum((u - mx) * (v - my) for u, v in zip(x, y))
    beta = sxy / sxx
    alpha = my - beta * mx
    sse = sum((v - (alpha + beta * u)) ** 2 for u, v in zip(x, y))
    sst = sum((v - my) ** 2 for v in y)
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    s2 = sse / (n - 2) if n > 2 else float("nan")
    se_beta = math.sqrt(s2 / sxx) if sxx > 0 else float("nan")
    se_alpha = (math.sqrt(s2 * (1.0 / n + mx * mx / sxx))
                if sxx > 0 else float("nan"))
    return {"n": n, "alpha": alpha, "beta": beta, "r2": r2,
            "t_alpha": alpha / se_alpha, "t_beta": beta / se_beta}


def annualised_vol(series: dict[str, float]) -> float:
    return math.sqrt(12.0) * statistics.pstdev(list(series.values()))


def centroid(returns: dict[str, dict[str, float]], months: list[str],
             exclude: str | None = None) -> dict[str, float]:
    out = {}
    for month in months:
        values = [returns[name][month] for name in returns
                  if name != exclude and month in returns[name]]
        out[month] = statistics.fmean(values)
    return out


def window_report(label: str, lo: str, hi: str, members: list[str],
                  proxy: dict[str, float], funds: dict[str, dict[str, float]]) -> dict:
    fund_w = {name: window(funds[name], lo, hi) for name in members}
    proxy_w = window(proxy, lo, hi)
    common = sorted(set.intersection(set(proxy_w), *(set(fund_w[n]) for n in members)))
    proxy_c = {m: proxy_w[m] for m in common}
    fund_c = {name: {m: fund_w[name][m] for m in common} for name in members}

    proxy_vs_funds = {}
    for name in members:
        c, n, first, last = correlation(proxy_c, fund_c[name])
        proxy_vs_funds[name] = {"corr": round(c, 3), "n": n, "first": first, "last": last}

    pairwise = []
    for i, a in enumerate(members):
        for b in members[i + 1:]:
            c, n, _f, _l = correlation(fund_c[a], fund_c[b])
            pairwise.append({"a": a, "b": b, "corr": round(c, 3)})
    mean_pairwise = statistics.fmean(p["corr"] for p in pairwise)

    cent = centroid(fund_c, common)
    proxy_vs_centroid, n, first, last = correlation(proxy_c, cent)
    members_vs_centroid = {}
    for name in members:
        c, _n, _f, _l = correlation(fund_c[name], centroid(fund_c, common, exclude=name))
        members_vs_centroid[name] = round(c, 3)

    vols = {name: round(annualised_vol(fund_c[name]), 3) for name in members}
    vols["proxy"] = round(annualised_vol(proxy_c), 3)

    all_series = {PROXY_LABEL: proxy_c, **fund_c}
    all_names = [PROXY_LABEL] + members
    matrix = correlation_matrix(all_names, all_series)
    clusters = average_linkage_clusters(all_names, matrix)

    return {
        "window": [lo, hi],
        "n_months": len(common),
        "proxy_vs_funds": proxy_vs_funds,
        "pairwise": pairwise,
        "mean_pairwise_corr": round(mean_pairwise, 3),
        "proxy_vs_centroid": {"corr": round(proxy_vs_centroid, 3), "n": n,
                              "first": first, "last": last},
        "funds_vs_centroid": members_vs_centroid,
        "annualised_vol": vols,
        "matrix": matrix,
        "clusters": clusters,
    }


PROXY_LABEL = "PROXY"
CLUSTER_MIN_CORR = 0.5


def correlation_matrix(names: list[str], series: dict[str, dict[str, float]]) -> dict:
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            c, n, first, last = correlation(series[a], series[b])
            pairs.append({"a": a, "b": b, "corr": round(c, 3),
                          "n_months": n, "first": first, "last": last})
    lookup = {tuple(sorted((p["a"], p["b"]))): p["corr"] for p in pairs}
    mean_vs_others = {}
    for name in names:
        values = [lookup[tuple(sorted((name, other)))] for other in names if other != name]
        mean_vs_others[name] = round(statistics.fmean(values), 3)
    return {"labels": names, "pairs": pairs, "mean_corr_vs_others": mean_vs_others}


def average_linkage_clusters(names: list[str], matrix: dict,
                             min_corr: float = CLUSTER_MIN_CORR) -> list[list[str]]:
    lookup = {tuple(sorted((p["a"], p["b"]))): p["corr"] for p in matrix["pairs"]}
    groups = [[name] for name in names]
    while len(groups) > 1:
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                pairs = [lookup[tuple(sorted((a, b)))] for a in groups[i] for b in groups[j]]
                mean = statistics.fmean(pairs)
                if best is None or mean > best[0]:
                    best = (mean, i, j)
        if best is None or best[0] < min_corr:
            break
        _mean, i, j = best
        groups[i] = groups[i] + groups[j]
        del groups[j]
    return groups


def format_matrix(matrix: dict, indent: str = "  ") -> str:
    labels = matrix["labels"]
    lookup = {tuple(sorted((p["a"], p["b"]))): p["corr"] for p in matrix["pairs"]}
    lines = [indent + "        " + "".join(f"{b:>7}" for b in labels)]
    for a in labels:
        cells = []
        for b in labels:
            if a == b:
                cells.append("     -")
            else:
                cells.append(f"{lookup[tuple(sorted((a, b)))]:>7.2f}")
        lines.append(indent + f"{a:<8}" + "".join(cells))
    return "\n".join(lines)


def main() -> None:
    missing = [symbol for symbol, _desc in FUNDS if not os.path.exists(
        os.path.join(FUNDS_DIR, TICKER_FILE.get(symbol, f"{symbol}.csv")))]
    if missing:
        print(f"mf_fund_correlations : séries de fonds absentes de {FUNDS_DIR} "
              f"({', '.join(missing)}) ; corrélations non régénérées. "
              "Lancer d'abord build/fetch_mf_fund_data.py. Voir "
              "data/benchmarks-externes/README.md.")
        return
    proxy = load_proxy()
    funds = {symbol: fund_monthly(symbol) for symbol, _desc in FUNDS}

    proxy_vs_funds = []
    for symbol, desc in FUNDS:
        c, n, first, last = correlation(proxy, funds[symbol])
        proxy_vs_funds.append({"fund": symbol, "description": desc, "corr": round(c, 3),
                               "n_months": n, "first": first, "last": last})

    pairwise_full = []
    for i, (a, _da) in enumerate(FUNDS):
        for b, _db in FUNDS[i + 1:]:
            c, n, first, last = correlation(funds[a], funds[b])
            pairwise_full.append({"a": a, "b": b, "corr": round(c, 3),
                                  "n_months": n, "first": first, "last": last})

    reports = {name: window_report(name, lo, hi, members, proxy, funds)
               for name, (lo, hi, members) in WINDOWS.items()}

    all_names = [PROXY_LABEL] + [symbol for symbol, _desc in FUNDS]
    all_series = {PROXY_LABEL: proxy, **funds}
    matrix_full = correlation_matrix(all_names, all_series)
    clusters_full = average_linkage_clusters(all_names, matrix_full)

    today = datetime.date.today().isoformat()
    payload = {
        "generated": today,
        "proxy": {"file": os.path.relpath(PROXY_CSV, ROOT), "column": PROXY_COL,
                  "first": min(proxy), "last": max(proxy)},
        "funds": {symbol: {"first": min(returns), "last": max(returns),
                           "vol_ann_full": round(annualised_vol(returns), 3)}
                  for symbol, returns in funds.items()},
        "proxy_vs_funds_full_overlap": proxy_vs_funds,
        "fund_vs_fund_full_overlap": pairwise_full,
        "matrix_full_overlap": matrix_full,
        "clusters_full_overlap": clusters_full,
        "windows": reports,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    print(f"Proxy {min(proxy)} -> {max(proxy)} ; {len(funds)} fonds ; "
          f"{today}")
    print("\n== Proxy (mf 1/6/12 net) vs fonds, recouvrement maximal ==")
    for row in proxy_vs_funds:
        print(f"  {row['fund']:<6} {row['corr']:>6.2f}   "
              f"{row['first']}..{row['last']} ({row['n_months']} mo.)   {row['description']}")
    print("\n== Fonds entre eux, recouvrement maximal par paire ==")
    print("       " + "".join(f"{b:>7}" for b, _d in FUNDS))
    for a, _da in FUNDS:
        cells = []
        for b, _db in FUNDS:
            if a == b:
                cells.append("     -")
            else:
                match = next(p for p in pairwise_full if {p["a"], p["b"]} == {a, b})
                cells.append(f"{match['corr']:>7.2f}")
        print(f"{a:<7}" + "".join(cells))
    print("\n== Matrice complète (PROXY inclus), recouvrement maximal par paire ==")
    print(format_matrix(matrix_full))
    ranking = sorted(matrix_full["mean_corr_vs_others"].items(), key=lambda kv: -kv[1])
    print("  corrélation moyenne avec les autres : "
          + ", ".join(f"{k} {v:.2f}" for k, v in ranking))
    print("  clusters (lien moyen, corr. min. 0,50) : "
          + " | ".join("+".join(g) for g in clusters_full))
    for name, report in reports.items():
        lo, hi = report["window"]
        print(f"\n== Fenêtre commune {name} ({lo}..{hi}, {report['n_months']} mo.) ==")
        print(format_matrix(report["matrix"]))
        ranking = sorted(report["matrix"]["mean_corr_vs_others"].items(), key=lambda kv: -kv[1])
        print("  corrélation moyenne avec les autres : "
              + ", ".join(f"{k} {v:.2f}" for k, v in ranking))
        print("  clusters (lien moyen, corr. min. 0,50) : "
              + " | ".join("+".join(g) for g in report["clusters"]))
        print("  proxy vs fonds : "
              + ", ".join(f"{k} {v['corr']:.2f}" for k, v in report["proxy_vs_funds"].items()))
        print(f"  moyenne paire-à-paire des fonds : {report['mean_pairwise_corr']:.2f}")
        print("  fonds vs centroïde (hors soi-même) : "
              + ", ".join(f"{k} {v:.2f}" for k, v in report["funds_vs_centroid"].items()))
        pc = report["proxy_vs_centroid"]["corr"]
        vals = list(report["funds_vs_centroid"].values())
        print(f"  proxy vs centroïde : {pc:.2f}"
              f"   [fonds : {min(vals):.2f}..{max(vals):.2f}]")
        print("  vol. annualisée : "
              + ", ".join(f"{k} {v:.0%}" if False else f"{k} {v:.2f}"
                          for k, v in report["annualised_vol"].items()))
    print(f"\nOK : {os.path.relpath(OUT_JSON, ROOT)}")


if __name__ == "__main__":
    main()
