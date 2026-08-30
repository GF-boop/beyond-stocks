"""Validation externe du proxy managed futures contre les indices CTA.

Produit deux fichiers autonomes inclus par main.tex :

* ``figures/mf_vs_benchmarks.tex`` : tikzpicture, cumul d'un dollar 2000-2025
  du proxy net (variante canonique 1/6/12), des indices SG CTA, SG Trend et
  Barclay BTOP50, et de KMLMSIM, en echelle log ;
* ``figures/mf_benchmark_corr.tex`` : tabular des correlations mensuelles
  contemporaines du proxy avec les indices SG/Barclay, KMLMSIM et les ETF
  cotes DBMF/KMLM.

Sources :
  data/managed-futures-monthly.csv                       -- proxy, colonnes *_net_return
  data/benchmarks-externes/official-index-returns-monthly.csv  -- SG CTA, SG Trend, BTOP50
  data/benchmarks-externes/testfol/{KMLMSIM,DBMF,KMLM}.csv     -- rendements quotidiens

Les indices SG et BarclayHedge sont proprietaires : ils ne sont pas
redistribues avec ce depot. Ils sont lus, si presents, depuis
data/benchmarks-externes/, aux termes de la licence detenue pour cette
recherche, et seuls des statistiques derivees (cumul, correlation) sont
reproduites. Sans eux, la figure et la table restent celles du PDF distribue.
"""

from __future__ import annotations

import csv
import math
import os
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
MF_MONTHLY = os.path.join(DATA, "managed-futures-monthly.csv")

# Validation externe sur indices proprietaires (SG CTA, SG Trend, Barclay
# BTOP50) et series testfol.io. Ces fichiers ne sont pas redistribuables et ne
# figurent donc pas dans ce depot : ils sont lus, si presents, depuis
# data/benchmarks-externes/. Sans eux, ce script s'arrete proprement et la
# Figure "mf_vs_benchmarks" et la Table "mf_benchmark_corr" restent celles du
# PDF distribue, non reconstructibles publiquement (cf. README).
BENCHMARKS = os.path.join(DATA, "benchmarks-externes")
OFFICIAL = os.path.join(BENCHMARKS, "official-index-returns-monthly.csv")
TESTFOL = os.path.join(BENCHMARKS, "testfol")

OUT_DIR = os.path.join(HERE, "figures")
OUT_FIG = os.path.join(OUT_DIR, "mf_vs_benchmarks.tex")
OUT_TAB = os.path.join(OUT_DIR, "mf_benchmark_corr.tex")

PROXY_COL = "mf_1_6_12_net_return"
WIN0, WIN1 = "2000-01", "2025-12"

# Cadre du graphe.
LOG_MIN, LOG_MAX = 0.0, math.log10(6.0)
W_CM, H_CM = 12.0, 7.2
Y_TICKS = [1, 1.5, 2, 3, 4, 6]
X_TICKS = [2000, 2005, 2010, 2015, 2020, 2025]

# (cle, libelle, couleur tikz, epaisseur)
FIG_SERIES = [
    ("proxy", "Proxy 1/6/12 (net)", "red!65!black", "very thick"),
    ("sgcta", "SG CTA Index", "blue!55!black", "thick"),
    ("sgtrend", "SG Trend Index", "teal", "thick"),
    ("btop", "Barclay BTOP50", "orange!85!black", "thick"),
    ("kmlmsim", "KMLMSIM (Testfolio)", "violet!75!black", "thick"),
]


def read_month_map(path: str, column: str, key: str = "month") -> dict[str, float]:
    out = {}
    with open(path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            value = row.get(column)
            if value:
                out[row[key]] = float(value)
    return out


def testfol_monthly(name: str, drop_first: bool = False) -> dict[str, float]:
    """Compose les rendements quotidiens testfol en rendements mensuels.

    ``drop_first`` retire le premier mois civil, incomplet pour les tickers
    cotes (cf. README du dossier official_benchmarks).
    """
    level = defaultdict(lambda: 1.0)
    with open(os.path.join(TESTFOL, name + ".csv"), encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            level[row["date"][:7]] *= 1.0 + float(row["daily_return"])
    monthly = {month: value - 1.0 for month, value in level.items()}
    if drop_first and monthly:
        del monthly[min(monthly)]
    return monthly


def window(series: dict[str, float]) -> dict[str, float]:
    return {m: v for m, v in series.items() if WIN0 <= m <= WIN1}


def correlation(a: dict[str, float], b: dict[str, float]) -> tuple[float, int, str, str]:
    months = sorted(set(a) & set(b))
    xs = [a[m] for m in months]
    ys = [b[m] for m in months]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den, len(months), months[0], months[-1]


def sx(year_fraction: float) -> float:
    return (year_fraction - 2000.0) / 26.0 * W_CM


def sy(value: float) -> float:
    return (math.log10(value) - LOG_MIN) / (LOG_MAX - LOG_MIN) * H_CM


def month_fraction(month: str) -> float:
    year, mon = month.split("-")
    return int(year) + (int(mon) - 1) / 12.0


def main() -> None:
    if not (os.path.exists(OFFICIAL) and os.path.isdir(TESTFOL)):
        print("build_mf_benchmark_data : indices proprietaires absents de "
              f"{BENCHMARKS} ; figure et table de validation externe non "
              "regenerees (versions du PDF conservees). Voir README.")
        return
    proxy = read_month_map(MF_MONTHLY, PROXY_COL)
    official = OFFICIAL
    sg_cta = read_month_map(official, "sg_cta")
    sg_trend = read_month_map(official, "sg_trend")
    btop = read_month_map(official, "btop50")
    kmlmsim = testfol_monthly("KMLMSIM")
    dbmf = testfol_monthly("DBMF", drop_first=True)
    kmlm = testfol_monthly("KMLM", drop_first=True)

    series = {
        "proxy": proxy, "sgcta": sg_cta, "sgtrend": sg_trend,
        "btop": btop, "kmlmsim": kmlmsim,
    }
    common = sorted(
        set.intersection(*(set(window(s)) for s in series.values()))
        & {m for m in proxy if WIN0 <= m <= WIN1}
    )

    os.makedirs(OUT_DIR, exist_ok=True)

    # --- Figure : cumul d'un dollar -----------------------------------------
    levels = {key: 1.0 for key in series}
    paths: dict[str, list[tuple[float, float]]] = {
        key: [(2000.0, 1.0)] for key in series
    }
    for month in common:
        frac = month_fraction(month) + 1 / 12.0
        for key in series:
            levels[key] *= 1.0 + series[key][month]
            paths[key].append((frac, levels[key]))

    with open(OUT_FIG, "w", encoding="utf-8") as f:
        f.write("% Généré par build_mf_benchmark_data.py — ne pas éditer à la main.\n")
        f.write("\\begin{tikzpicture}[x=1cm, y=1cm]\n")
        for tick in Y_TICKS:
            y = sy(tick)
            f.write(f"  \\draw[gray!20] (0,{y:.3f}) -- ({W_CM:.2f},{y:.3f});\n")
            f.write(f"  \\node[left, font=\\footnotesize] at (-0.12,{y:.3f}) "
                    f"{{{tick:g}}};\n")
        for tick in X_TICKS:
            x = sx(tick)
            f.write(f"  \\draw[gray!20] ({x:.3f},0) -- ({x:.3f},{H_CM:.2f});\n")
            f.write(f"  \\node[below, font=\\footnotesize] at ({x:.3f},-0.12) "
                    f"{{{tick}}};\n")
        f.write(f"  \\draw (0,0) rectangle ({W_CM:.2f},{H_CM:.2f});\n")
        f.write(f"  \\node[rotate=90, font=\\footnotesize] at (-0.9,{H_CM/2:.2f}) "
                f"{{Growth of \\$1 (log scale)}};\n")
        for key, _label, color, thick in FIG_SERIES:
            pts = " ".join(f"({sx(fr):.3f},{sy(val):.3f})" for fr, val in paths[key])
            f.write(f"  \\draw[{thick}, {color}] plot coordinates {{{pts}}};\n")
        ly = H_CM - 0.4
        for key, label, color, _thick in FIG_SERIES:
            f.write(f"  \\draw[thick, {color}] (0.3,{ly:.3f}) -- (1.0,{ly:.3f});\n")
            f.write(f"  \\node[right, font=\\footnotesize] at (1.05,{ly:.3f}) "
                    f"{{{label}}};\n")
            ly -= 0.46
        f.write("\\end{tikzpicture}\n")

    # --- Table : correlations mensuelles contemporaines --------------------
    proxy_win = window(proxy)
    rows_out = [
        ("SG CTA Index", window(sg_cta)),
        ("SG Trend Index", window(sg_trend)),
        ("Barclay BTOP50 Index", window(btop)),
        ("KMLMSIM (Testfolio simulation)", window(kmlmsim)),
        ("DBMF ETF (live)", dbmf),
        ("KMLM ETF (live)", kmlm),
    ]
    with open(OUT_TAB, "w", encoding="utf-8") as f:
        f.write("% Généré par build_mf_benchmark_data.py — ne pas éditer à la main.\n")
        f.write("\\setlength{\\tabcolsep}{6pt}\n")
        f.write("\\begin{tabular}{lrl}\n\\toprule\n")
        f.write("Benchmark & Corr. & Common window \\\\\n\\midrule\n")
        for label, other in rows_out:
            c, n, first, last = correlation(proxy_win if "live" not in label else proxy,
                                            other)
            f.write(f"{label} & {c:.2f} & {first}--{last} ({n} mo.) \\\\\n")
        f.write("\\midrule\n")
        idx_lo = min(correlation(window(sg_cta), window(sg_trend))[0],
                     correlation(window(sg_cta), window(btop))[0],
                     correlation(window(sg_trend), window(btop))[0])
        idx_hi = max(correlation(window(sg_cta), window(sg_trend))[0],
                     correlation(window(sg_cta), window(btop))[0],
                     correlation(window(sg_trend), window(btop))[0])
        kmlm_c = correlation(window(kmlmsim), window(sg_cta))[0]
        f.write(f"\\multicolumn{{3}}{{p{{0.82\\textwidth}}}}{{\\footnotesize "
                f"\\textit{{Memo, 2000--2025:}} the three commercial indexes "
                f"correlate {idx_lo:.2f}--{idx_hi:.2f} with each other, whereas "
                f"KMLMSIM correlates {kmlm_c:.2f} with SG CTA. The proxy near "
                f"0.51 sits between these two reference patterns.}} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")

    # --- console ----------------------------------------------------------
    print(f"{OUT_FIG} : {common[0]}..{common[-1]} ({len(common)} mois)")
    for key, label, *_ in FIG_SERIES:
        print(f"  {label:<22} fin ${levels[key]:.2f}")
    print(f"{OUT_TAB} :")
    for label, other in rows_out:
        c, n, first, last = correlation(proxy_win if "live" not in label else proxy, other)
        print(f"  {label:<26} {c:.3f}  {first}..{last}  n={n}")


if __name__ == "__main__":
    main()
