"""Matrice de corrélations et régressions proxy / indices / fonds (annexe B).

Réunit dans une même analyse les séries de la validation externe
(``build_mf_benchmark_data.py``) et les fonds investissables
(``mf_fund_correlations.py``) :

* indices commerciaux : SG CTA, SG Trend, Barclay BTOP50
  (``data/benchmarks-externes/official-index-returns-monthly.csv``) ;
* séries testfol : KMLMSIM (simulation), DBMF et KMLM (ETF cotés,
  ``data/benchmarks-externes/testfol/``) ;
* sept fonds investissables téléchargés de Yahoo Finance
  (``build/fetch_mf_fund_data.py``) : WTMF, QMHIX, AHLIX, AHLT, IMF, ISMF,
  APEX.

Produit trois tableaux (toutes les séries sont cadrées sur 2000-01 → 2025-12,
fenêtre de la figure et de la table de validation externe ; chaque paire est
évaluée sur le recouvrement de ses deux historiques dans ce cadre) :

* ``figures/mf_pack_corr.tex`` : matrice de corrélation complète 14×14, proxy
  inclus. Les cellules sont ombrées selon la force de la corrélation pour
  faire ressortir la structure de blocs : indices et fonds purs de trend
  sombres, WTMF (timing actions multi-actifs) et APEX (multi-stratégies)
  clairs ;
* ``figures/mf_pack_long_corr.tex`` : matrice restreinte aux séries d'au
  moins dix ans d'historique (proxy, SG CTA, SG Trend, BTOP50, KMLMSIM,
  WTMF, QMHIX, AHLIX), toutes les paires évaluées sur la même fenêtre commune
  2014-09 → 2025-12 (136 mois), pour une comparaison à échantillon identique ;
* ``figures/mf_pack_regressions.tex`` : pour chaque série, régression
  ``R_serie = alpha + beta R_proxy + eps`` sur son recouvrement dans le cadre
  2000-2025 : alpha (% par mois, t de Student), beta (t), R², volatilité
  relative sigma_serie / sigma_proxy et tracking error annualisée (écart-type
  de ``R_serie − R_proxy``, ×√12, en %).

Le script imprime enfin les moyennes de corrélations non pondérées et
pondérées par le nombre de mois de recouvrement : les fonds lancés en 2025
(neuf mois de données) ne doivent pas peser autant que ceux de 2011-2014 dans
une moyenne de corrélations. Les corrélations proxy contre les six séries
externes doivent reproduire celles de la table ``tab:mf-benchmark-corr``.

Sources : ``data/managed-futures-monthly.csv`` et ``data/benchmarks-externes/``
(séries non redistribuées, cf. ``build/fetch_mf_fund_data.py`` et le README du
dossier). Sans les fichiers d'indices, le script s'arrête : cf.
``build_mf_benchmark_data.py`` pour la même convention.
"""

from __future__ import annotations

import csv
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "build"))

from mf_fund_correlations import (  # noqa: E402
    load_proxy, fund_monthly, window, correlation, regression)

DATA = os.path.join(ROOT, "data")
BENCHMARKS = os.path.join(DATA, "benchmarks-externes")
OFFICIAL = os.path.join(BENCHMARKS, "official-index-returns-monthly.csv")
TESTFOL = os.path.join(BENCHMARKS, "testfol")

OUT_DIR = os.path.join(HERE, "figures")
OUT_TEX = os.path.join(OUT_DIR, "mf_pack_corr.tex")
OUT_LONG = os.path.join(OUT_DIR, "mf_pack_long_corr.tex")
OUT_REG = os.path.join(OUT_DIR, "mf_pack_regressions.tex")

PROXY = "proxy"
BENCHMARK_NAMES = ["SGCTA", "SGTREND", "BTOP50", "KMLMSIM"]
TREND_FUNDS = ["DBMF", "KMLM", "QMHIX", "AHLIX", "AHLT", "IMF", "ISMF"]
OUTLIERS = ["WTMF", "APEX"]
NAMES = [PROXY] + BENCHMARK_NAMES + TREND_FUNDS + OUTLIERS
HEADERS = {PROXY: "Proxy", "SGCTA": "SG CTA", "SGTREND": "SG Trend",
           "BTOP50": "BTOP50", "KMLMSIM": "KMLMSIM", "DBMF": "DBMF",
           "KMLM": "KMLM", "WTMF": "WTMF", "QMHIX": "QMHIX", "AHLIX": "AHLIX",
           "AHLT": "AHLT", "IMF": "IMF", "ISMF": "ISMF", "APEX": "APEX"}
# Fenêtre longue : séries d'au moins dix ans d'historique. DBMF (79 mois) et
# KMLM (60 mois) n'y entrent pas ; la fenêtre commune reste pilotée par AHLIX.
LONG_NAMES = [PROXY] + BENCHMARK_NAMES + ["WTMF", "QMHIX", "AHLIX"]
LONG_START, LONG_END = "2014-09", "2025-12"
SAMPLE_START, SAMPLE_END = "2000-01", "2025-12"
SHADE_MAX = 55


def texminus(text: str) -> str:
    return text.replace("-", "$-$")


def shade(value: float) -> str:
    level = round(min(abs(value), 1.0) * SHADE_MAX)
    if level == 0:
        return ""
    color = "blue" if value >= 0 else "orange"
    return f"\\cellcolor{{{color}!{level}}}"


def read_month_map(path: str, column: str) -> dict[str, float]:
    out = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get(column)
            if value:
                out[row["month"]] = float(value)
    return out


def testfol_monthly(name: str, drop_first: bool = False) -> dict[str, float]:
    """Composition mensuelle des rendements quotidiens testfol.

    Même convention que ``build_mf_benchmark_data.py`` : ``drop_first`` retire
    le premier mois civil, incomplet pour les tickers cotés.
    """
    level: dict[str, float] = defaultdict(lambda: 1.0)
    with open(os.path.join(TESTFOL, name + ".csv"), encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            level[row["date"][:7]] *= 1.0 + float(row["daily_return"])
    monthly = {month: value - 1.0 for month, value in level.items()}
    if drop_first and monthly:
        del monthly[min(monthly)]
    return monthly


def load_series() -> dict[str, dict[str, float]]:
    if not (os.path.exists(OFFICIAL) and os.path.isdir(TESTFOL)):
        raise SystemExit(
            "indices propriétaires absents de data/benchmarks-externes/ ; "
            "cf. README et build_mf_benchmark_data.py (même convention)")
    series = {PROXY: load_proxy()}
    series["SGCTA"] = read_month_map(OFFICIAL, "sg_cta")
    series["SGTREND"] = read_month_map(OFFICIAL, "sg_trend")
    series["BTOP50"] = read_month_map(OFFICIAL, "btop50")
    series["KMLMSIM"] = testfol_monthly("KMLMSIM")
    series["DBMF"] = testfol_monthly("DBMF", drop_first=True)
    series["KMLM"] = testfol_monthly("KMLM", drop_first=True)
    for fund in TREND_FUNDS[2:] + OUTLIERS:
        series[fund] = fund_monthly(fund)
    return {k: window(v, SAMPLE_START, SAMPLE_END) for k, v in series.items()}


def write_matrix(path: str, names: list[str], corr: dict,
                 rule_after: str | None, compact: bool = False) -> None:
    lines = ["% Généré par build_mf_pack_matrix.py — ne pas éditer à la main."]
    if compact:
        # Matrice 14×14 : réduction de la taille et de l'espacement pour
        # tenir dans \textwidth.
        lines += ["\\scriptsize", "\\setlength{\\tabcolsep}{1.5pt}"]
    lines += ["\\begin{tabular}{l" + "r" * (len(names) - 1) + "}",
              "\\toprule"]
    lines.append(" & " + " & ".join(HEADERS[t] for t in names[1:]) + " \\\\")
    lines.append("\\midrule")
    for a in names:
        cells = [HEADERS[a]]
        for b in names[1:]:
            if a == b:
                cells.append("---")
                continue
            c = corr[(a, b)]
            value = texminus(f"{c:.2f}")
            if a == PROXY or b == PROXY:
                value = f"\\textbf{{{value}}}"
            cells.append(shade(c) + value)
        lines.append(" & ".join(cells) + " \\\\")
        if a == rule_after:
            lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}"]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def write_regressions(path: str, series: dict[str, dict[str, float]]) -> None:
    lines = ["% Généré par build_mf_pack_matrix.py — ne pas éditer à la main.",
             "\\begin{tabular}{lrrrrrr}",
             "\\toprule",
             "Series & $n$ & $\\alpha$ (\\%/mo.) & $\\beta$ & $R^2$ & "
             "$\\sigma_f/\\sigma_p$ & TE (\\%/yr.) \\\\",
             "\\midrule"]
    for name in NAMES[1:]:
        months = sorted(set(series[PROXY]) & set(series[name]))
        xs = [series[PROXY][m] for m in months]
        ys = [series[name][m] for m in months]
        fit = regression(xs, ys)
        active = [y - x for x, y in zip(xs, ys)]
        te_ann = statistics.stdev(active) * math.sqrt(12.0) * 100.0
        rel_vol = statistics.stdev(ys) / statistics.stdev(xs)
        alpha = f"{fit['alpha'] * 100.0:+.2f}\\,{{\\scriptsize({fit['t_alpha']:+.1f})}}"
        beta = f"{fit['beta']:.2f}\\,{{\\scriptsize({fit['t_beta']:+.1f})}}"
        cells = [HEADERS[name], str(len(months)), texminus(alpha), texminus(beta),
                 f"{fit['r2']:.2f}", f"{rel_vol:.2f}", f"{te_ann:.1f}"]
        lines.append(" & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def weighted_mean(pairs: list[tuple[float, int]]) -> float:
    return sum(c * n for c, n in pairs) / sum(n for _c, n in pairs)


def block_stats(label: str, members: list[str], corr: dict, spans: dict,
                against: list[str]) -> None:
    pairs = [(corr[(a, b)], spans[(a, b)][0]) for a in members for b in against
             if a != b]
    values = [c for c, _n in pairs]
    print(f"{label:<28} médiane {statistics.median(values):.2f}, "
          f"moyenne {statistics.fmean(values):.2f}, "
          f"pondérée {weighted_mean(pairs):.2f}, "
          f"étendue {min(values):.2f}--{max(values):.2f}")


def main() -> None:
    series = load_series()
    for name in NAMES:
        months = sorted(series[name])
        print(f"{HEADERS[name]:<8} {months[0]} -> {months[-1]}  ({len(months)} mois)")

    corr: dict = {}
    spans: dict = {}
    for i, a in enumerate(NAMES):
        for b in NAMES[i + 1:]:
            c, n, _first, _last = correlation(series[a], series[b])
            corr[(a, b)] = corr[(b, a)] = c
            spans[(a, b)] = spans[(b, a)] = (n, _first, _last)

    os.makedirs(OUT_DIR, exist_ok=True)
    write_matrix(OUT_TEX, NAMES, corr, rule_after="KMLMSIM", compact=True)

    # Fenêtre commune aux séries longues (>= 10 ans d'historique).
    long_series = {t: window(series[t], LONG_START, LONG_END) for t in LONG_NAMES}
    long_corr: dict = {}
    long_n = 0
    for i, a in enumerate(LONG_NAMES):
        for b in LONG_NAMES[i + 1:]:
            c, n = correlation(long_series[a], long_series[b])[:2]
            long_corr[(a, b)] = long_corr[(b, a)] = c
            long_n = n
    write_matrix(OUT_LONG, LONG_NAMES, long_corr, rule_after=None)

    write_regressions(OUT_REG, series)

    print("\n== Contrôle : doit reproduire tab:mf-benchmark-corr ==")
    for b in BENCHMARK_NAMES + ["DBMF", "KMLM"]:
        c = corr[(PROXY, b)]
        n, first, _ = spans[(PROXY, b)]
        print(f"proxy vs {HEADERS[b]:<8} {c:.2f}  ({n} mois, {first}--{SAMPLE_END})")

    print("\n== Recouvrement maximal, corrélations par bloc ==")
    block_stats("proxy vs indices", BENCHMARK_NAMES, corr, spans, [PROXY])
    block_stats("proxy vs fonds de trend", TREND_FUNDS, corr, spans, [PROXY])
    block_stats("proxy vs WTMF/APEX", OUTLIERS, corr, spans, [PROXY])
    block_stats("indices entre eux", BENCHMARK_NAMES, corr, spans, BENCHMARK_NAMES)
    block_stats("fonds de trend entre eux", TREND_FUNDS, corr, spans, TREND_FUNDS)
    block_stats("WTMF vs fonds de trend", ["WTMF"], corr, spans, TREND_FUNDS)
    block_stats("APEX vs fonds de trend", ["APEX"], corr, spans, TREND_FUNDS)

    print(f"\n== Fenêtre commune {LONG_START}..{LONG_END} ({long_n} mois) ==")
    for b in LONG_NAMES[1:]:
        print(f"proxy vs {HEADERS[b]:<8} {long_corr[(PROXY, b)]:.2f}")

    print("\n== Régressions R_serie = alpha + beta R_proxy (cadre 2000-2025) ==")
    for name in NAMES[1:]:
        months = sorted(set(series[PROXY]) & set(series[name]))
        xs = [series[PROXY][m] for m in months]
        ys = [series[name][m] for m in months]
        fit = regression(xs, ys)
        active = [y - x for x, y in zip(xs, ys)]
        te = statistics.stdev(active) * math.sqrt(12.0) * 100.0
        rel = statistics.stdev(ys) / statistics.stdev(xs)
        print(f"  {HEADERS[name]:<8} n={len(months):>3}  alpha={fit['alpha'] * 100.0:+.2f}"
              f" (t={fit['t_alpha']:+.1f})  beta={fit['beta']:.2f}"
              f" (t={fit['t_beta']:+.1f})  R2={fit['r2']:.2f}"
              f"  srel={rel:.2f}  TE={te:.1f}%")

    for path in (OUT_TEX, OUT_LONG, OUT_REG):
        print(f"OK : {os.path.relpath(path, ROOT)}")


if __name__ == "__main__":
    main()
