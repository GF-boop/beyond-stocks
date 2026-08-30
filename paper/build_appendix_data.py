"""Donnees d'annexe sur les classes d'actifs.

Produit trois fichiers autonomes inclus par main.tex :

* ``figures/cumulative_wealth.tex`` : environnement tikzpicture, cumul d'un
  dollar reel par classe d'actifs. Pas de dependance pgfplots : les
  coordonnees sont pre-calculees ici en echelle log decimale et ecrites comme
  des chemins tikz plot coordinates.
* ``figures/mf_diagnostics.tex`` : deux ``tabular`` sur le proxy managed
  futures reconstruit -- moments annuels reels compares aux autres classes, et
  comportement du proxy dans les dix pires annees d'actions mondiales.
* ``figures/mf_convexity.tex`` : tikzpicture a trois panneaux, nuage de points
  annuel (rendement de l'actif en x, rendement du proxy en y) avec parabole
  ajustee et moyennes par quintile, pour actions mondiales, obligations
  couvertes et or.

Une seule residence, les Etats-Unis, pour ne pas melanger les numeraires :
chaque serie est le rendement reel d'un investisseur americain, la meme
convention que le reste du panel. Les rares chiffres pooles cites dans le
texte de l'annexe sont recalcules a part et signales comme tels.
"""

from __future__ import annotations

import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, "..", "data", "replication-panel-trend.csv")
OUT_DIR = os.path.join(HERE, "figures")
OUT = os.path.join(OUT_DIR, "cumulative_wealth.tex")
OUT_MF = os.path.join(OUT_DIR, "mf_diagnostics.tex")
OUT_CONVEX = os.path.join(OUT_DIR, "mf_convexity.tex")

TREND_FEE = 0.0085
TREND_DRAG = 0.0057

# (cle, colonne du panel, couleur tikz, libelle de legende, transformation)
SERIES = [
    ("domestic", "domestic_equity_real", "black",
     "Domestic equity", None),
    ("world_equity", "world_equity_real", "blue!55!black",
     "World equity", None),
    ("mf", "trend_real", "red!65!black",
     "Managed futures (net)", "trend_net"),
    ("world_bond", "world_bond_real", "teal",
     "World bonds (covered)", None),
    ("gold", "gold_real", "orange!85!black",
     "Gold", None),
]

# Cadre du graphe, en coordonnees de donnees.
X_MIN, X_MAX = 1926, 2025
LOG_MIN, LOG_MAX = 0.0, math.log10(2000.0)   # 1 a 2000
# Taille du dessin en cm.
W_CM, H_CM = 12.8, 8.0
X_TICKS = [1930, 1945, 1960, 1975, 1990, 2005, 2020]
Y_TICKS = [1, 3, 10, 30, 100, 300, 1000]


def net_trend(value: float) -> float:
    return (1.0 + value) * (1.0 - TREND_FEE) - 1.0 - TREND_DRAG


def sx(year: float) -> float:
    return (year - X_MIN) / (X_MAX - X_MIN) * W_CM


def sy(value: float) -> float:
    return (math.log10(value) - LOG_MIN) / (LOG_MAX - LOG_MIN) * H_CM


def main() -> None:
    rows = [
        row for row in csv.DictReader(open(PANEL, encoding="utf-8"))
        if row["country"] == "USA"
    ]
    rows.sort(key=lambda r: int(r["year"]))
    if not rows:
        raise SystemExit("Aucune observation pour la residence USA")

    first_year = int(rows[0]["year"])
    levels = {key: 1.0 for key, *_ in SERIES}
    paths: dict[str, list[tuple[float, float]]] = {
        key: [(first_year - 1, 1.0)] for key, *_ in SERIES
    }
    for row in rows:
        year = int(row["year"])
        for key, column, _c, _l, transform in SERIES:
            raw = float(row[column])
            real = net_trend(raw) if transform == "trend_net" else raw
            levels[key] *= 1.0 + real
            paths[key].append((year, levels[key]))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("% Généré par build_appendix_data.py — ne pas éditer à la main.\n")
        f.write("\\begin{tikzpicture}[x=1cm, y=1cm]\n")

        # Grille et graduations Y.
        for tick in Y_TICKS:
            y = sy(tick)
            f.write(f"  \\draw[gray!20] (0,{y:.3f}) -- ({W_CM:.2f},{y:.3f});\n")
            f.write(f"  \\node[left, font=\\footnotesize] at (-0.15,{y:.3f}) "
                    f"{{{tick}}};\n")
        # Graduations X.
        for tick in X_TICKS:
            x = sx(tick)
            f.write(f"  \\draw[gray!20] ({x:.3f},0) -- ({x:.3f},{H_CM:.2f});\n")
            f.write(f"  \\node[below, font=\\footnotesize] at ({x:.3f},-0.15) "
                    f"{{{tick}}};\n")

        # Cadre.
        f.write(f"  \\draw (0,0) rectangle ({W_CM:.2f},{H_CM:.2f});\n")
        f.write(f"  \\node[below, font=\\footnotesize] at ({W_CM/2:.2f},-0.7) "
                f"{{Year}};\n")
        f.write(f"  \\node[rotate=90, font=\\footnotesize] at (-0.95,"
                f"{H_CM/2:.2f}) {{Real value of \\$1 (log scale)}};\n")

        # Courbes.
        for key, _col, color, _label, _t in SERIES:
            pts = " ".join(
                f"({sx(year):.3f},{sy(value):.3f})"
                for year, value in paths[key]
            )
            f.write(f"  \\draw[thick, {color}] plot coordinates {{{pts}}};\n")

        # Légende, en haut à gauche.
        ly = H_CM - 0.45
        for key, _col, color, label, _t in SERIES:
            f.write(f"  \\draw[thick, {color}] (0.35,{ly:.3f}) -- "
                    f"(1.05,{ly:.3f});\n")
            f.write(f"  \\node[right, font=\\footnotesize] at (1.1,{ly:.3f}) "
                    f"{{{label}}};\n")
            ly -= 0.5

        f.write("\\end{tikzpicture}\n")

    span = f"{first_year}-{int(rows[-1]['year'])}"
    ending = ", ".join(f"{k}={levels[k]:.1f}x" for k, *_ in SERIES)
    print(f"{OUT} : {len(rows)} annees ({span})")
    print(f"valeur finale d'un dollar reel : {ending}")

    write_mf_diagnostics(rows, first_year, int(rows[-1]["year"]))


# --- Proxy managed futures : moments et comportement en crise -----------------

# Classes comparees dans la table de moments (cle, colonne, libelle, transfo).
MF_SERIES = [
    ("dom_eq", "domestic_equity_real", "Domestic equity", None),
    ("wld_eq", "world_equity_real", "World equity", None),
    ("wld_bd", "world_bond_real", "World bonds (covered)", None),
    ("gold", "gold_real", "Gold", None),
    ("mf", "trend_real", "Managed-futures proxy (net)", "trend_net"),
]


def _mean(xs):
    return sum(xs) / len(xs)


def _pstdev(xs):
    mu = _mean(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs))


def _skew(xs):
    mu, sd = _mean(xs), _pstdev(xs)
    return _mean([((x - mu) / sd) ** 3 for x in xs])


def _pct(xs, q):
    srt = sorted(xs)
    return srt[int(round(q * (len(srt) - 1)))]


def _max_drawdown(xs):
    level, peak, worst = 1.0, 1.0, 0.0
    for x in xs:
        level *= 1.0 + x
        peak = max(peak, level)
        worst = min(worst, level / peak - 1.0)
    return worst


def _corr(a, b):
    ma, mb = _mean(a), _mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den


def _invert3(mat):
    """Inverse d'une matrice 3x3 par Gauss-Jordan."""
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(3)]
           for i, row in enumerate(mat)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        aug[col] = [v / diag for v in aug[col]]
        for r in range(3):
            if r == col:
                continue
            factor = aug[r][col]
            aug[r] = [aug[r][k] - factor * aug[col][k] for k in range(6)]
    return [row[3:] for row in aug]


def _quad_curvature(xs, ys):
    """Ajustement descriptif y = a + b x + c x^2 par moindres carres.

    Renvoie (c, t) ou c est le coefficient du terme carre et t sa statistique
    de Student calculee avec une variance de White (HC1),
    heteroscedasticite-robuste. La correction est necessaire ici parce que la
    variance des residus est manifestement plus grande dans les annees ou
    l'actif fait un mouvement extreme, ce qui est justement l'objet du nuage ;
    l'autocorrelation des scores etant negligeable sur ce panel annuel, aucune
    correction Newey-West n'est appliquee. Le R^2 n'est pas renvoye : sur un
    nuage annuel il ne dit pas si la courbure est distinguable de zero, seule
    la significativite du coefficient le dit.
    """
    n = len(xs)
    design = [[1.0, x, x * x] for x in xs]
    xtx = [[sum(design[i][a] * design[i][b] for i in range(n))
            for b in range(3)] for a in range(3)]
    xty = [sum(design[i][a] * ys[i] for i in range(n)) for a in range(3)]
    inv = _invert3(xtx)
    beta = [sum(inv[a][k] * xty[k] for k in range(3)) for a in range(3)]
    resid = [ys[i] - sum(beta[k] * design[i][k] for k in range(3))
             for i in range(n)]

    meat = [[sum(design[t][a] * design[t][b] * resid[t] * resid[t]
                 for t in range(n))
             for b in range(3)] for a in range(3)]
    left = [[sum(inv[a][k] * meat[k][b] for k in range(3))
             for b in range(3)] for a in range(3)]
    cov = [[sum(left[a][k] * inv[k][b] for k in range(3))
            for b in range(3)] for a in range(3)]
    hc1 = n / (n - 3)                          # correction petit echantillon
    c = beta[2]
    var_c = cov[2][2] * hc1
    se = math.sqrt(var_c) if var_c > 0 else float("nan")
    return c, c / se


def _quintile_means(xs, ys):
    """Moyenne de ys dans chaque quintile de xs (5 groupes de tailles ~egales)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    size, extra = divmod(len(order), 5)
    groups, start = [], 0
    for q in range(5):
        stop = start + size + (1 if q < extra else 0)
        groups.append(order[start:stop])
        start = stop
    return [_mean([ys[i] for i in g]) for g in groups], \
           [_mean([xs[i] for i in g]) for g in groups]


def write_mf_diagnostics(rows: list[dict], first_year: int, last_year: int) -> None:
    """Ecrit figures/mf_diagnostics.tex : moments et decile de crise du proxy."""
    series = {}
    for key, column, _label, transform in MF_SERIES:
        vals = []
        for row in rows:
            raw = float(row[column])
            vals.append(net_trend(raw) if transform == "trend_net" else raw)
        series[key] = vals
    inflation = [float(row["inflation"]) for row in rows]
    mf = series["mf"]

    corr_row = {k: _corr(mf, series[k]) for k in ("dom_eq", "wld_eq", "wld_bd", "gold")}
    corr_infl = _corr(mf, inflation)

    with open(OUT_MF, "w", encoding="utf-8") as f:
        f.write("% Généré par build_appendix_data.py — ne pas éditer à la main.\n")
        f.write(f"% corr(MF, .) : dom_eq {corr_row['dom_eq']:+.2f}  "
                f"wld_eq {corr_row['wld_eq']:+.2f}  wld_bd {corr_row['wld_bd']:+.2f}  "
                f"gold {corr_row['gold']:+.2f}  inflation {corr_infl:+.2f}\n")

        # Bloc 1 : moments annuels reels, residence americaine.
        f.write("\\setlength{\\tabcolsep}{5pt}\n")
        f.write("\\begin{tabular}{lrrrrrr}\n\\toprule\n")
        f.write("Asset & Mean & SD & Sharpe$_0$ & Skew & 5th pctl & Max DD \\\\\n")
        f.write("\\midrule\n")
        for key, _col, label, _t in MF_SERIES:
            v = series[key]
            f.write(
                f"{label} & {_mean(v) * 100:.2f}\\% & {_pstdev(v) * 100:.2f}\\% & "
                f"{_mean(v) / _pstdev(v):.2f} & {_skew(v):+.2f} & "
                f"{_pct(v, 0.05) * 100:.1f}\\% & {_max_drawdown(v) * 100:.1f}\\% \\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n")

        f.write("\n\\par\\bigskip\n\n")

        # Bloc 2 : le proxy dans les dix pires annees d'actions mondiales.
        we = series["wld_eq"]
        order = sorted(range(len(rows)), key=lambda i: we[i])[:10]
        order.sort(key=lambda i: int(rows[i]["year"]))
        f.write("\\begin{tabular}{lrrrr}\n\\toprule\n")
        f.write("Year & World equity & MF proxy & Gold & U.S. inflation \\\\\n")
        f.write("\\midrule\n")
        for i in order:
            f.write(
                f"{rows[i]['year']} & {we[i] * 100:.1f}\\% & {mf[i] * 100:.1f}\\% & "
                f"{series['gold'][i] * 100:.1f}\\% & {inflation[i] * 100:.1f}\\% \\\\\n"
            )
        f.write("\\bottomrule\n\\end{tabular}\n")

    hits = sum(1 for i in order if mf[i] > 0)
    print(f"{OUT_MF} : {last_year - first_year + 1} annees, "
          f"proxy positif dans {hits}/10 pires annees actions")
    print(f"  proxy net : mean {_mean(mf) * 100:.2f}%  sd {_pstdev(mf) * 100:.2f}%  "
          f"skew {_skew(mf):+.2f}  corr(actions mondiales) {corr_row['wld_eq']:+.2f}")

    write_mf_convexity(rows)


# --- Figure de convexite : nuage de points + parabole ------------------------

# Panneaux : cle, colonne, libelle, bornes x propres (rendement reel annuel)
# arrondies juste au-dela des donnees de chaque actif, et graduations x.
CONVEX_PANELS = [
    ("wld_eq", "world_equity_real", "World equity", (-0.50, 0.60), (-0.4, 0.0, 0.4)),
    ("wld_bd", "world_bond_real", "World bonds (covered)", (-0.22, 0.32), (-0.2, 0.0, 0.2)),
    ("gold", "gold_real", "Gold", (-0.45, 0.65), (-0.4, 0.0, 0.4)),
]

# Geometrie d'un panneau, en cm. L'axe y (rendement du proxy) est commun.
PANEL_W, PANEL_H = 4.3, 4.3
PANEL_GAP = 0.85
Y_MIN, Y_MAX = -0.42, 0.50
Y_TICKS_CONVEX = (-0.3, 0.0, 0.3)


def _panel_xy(value: float, lo: float, hi: float, size: float) -> float:
    return (value - lo) / (hi - lo) * size


def write_mf_convexity(rows: list[dict]) -> None:
    """Ecrit figures/mf_convexity.tex : trois scatters proxy vs classe.

    Axe x propre a chaque panneau (l'amplitude des rendements differe d'un
    actif a l'autre) ; axe y commun, c'est le rendement du proxy qu'on compare.
    """
    mf = [net_trend(float(r["trend_real"])) for r in rows]

    with open(OUT_CONVEX, "w", encoding="utf-8") as f:
        f.write("% Généré par build_appendix_data.py — ne pas éditer à la main.\n")
        f.write("\\begin{tikzpicture}[x=1cm, y=1cm]\n")

        for panel, (key, column, label, xbounds, xticks) in enumerate(CONVEX_PANELS):
            xs = [float(r[column]) for r in rows]
            x0 = panel * (PANEL_W + PANEL_GAP)
            xlo, xhi = xbounds

            def px(v, x0=x0, xlo=xlo, xhi=xhi):
                return x0 + _panel_xy(min(max(v, xlo), xhi), xlo, xhi, PANEL_W)

            def py(v):
                return _panel_xy(min(max(v, Y_MIN), Y_MAX), Y_MIN, Y_MAX, PANEL_H)

            # cadre + axes zero
            f.write(f"  \\draw[gray!35] ({x0:.2f},0) rectangle "
                    f"({x0 + PANEL_W:.2f},{PANEL_H:.2f});\n")
            zx, zy = px(0.0), py(0.0)
            f.write(f"  \\draw[gray!45] ({x0:.2f},{zy:.2f}) -- "
                    f"({x0 + PANEL_W:.2f},{zy:.2f});\n")
            f.write(f"  \\draw[gray!45] ({zx:.2f},0) -- ({zx:.2f},{PANEL_H:.2f});\n")

            # graduations x propres au panneau
            for tick in xticks:
                tx = px(tick)
                f.write(f"  \\draw[gray!45] ({tx:.2f},-0.06) -- ({tx:.2f},0.06);\n")
                f.write(f"  \\node[below, font=\\scriptsize] at ({tx:.2f},-0.1) "
                        f"{{{tick * 100:.0f}}};\n")
            # graduations y communes, etiquetees sur le premier panneau
            for tick in Y_TICKS_CONVEX:
                ty = py(tick)
                f.write(f"  \\draw[gray!45] ({x0 - 0.06:.2f},{ty:.2f}) -- "
                        f"({x0 + 0.06:.2f},{ty:.2f});\n")
                if panel == 0:
                    f.write(f"  \\node[left, font=\\scriptsize] at "
                            f"({x0 - 0.10:.2f},{ty:.2f}) {{{tick * 100:.0f}}};\n")

            # points : annees ou l'actif baisse en rouge, ou il monte en bleu
            for x, y in zip(xs, mf):
                if x < 0:
                    f.write(f"  \\fill[red!70!black, opacity=0.7] "
                            f"({px(x):.2f},{py(y):.2f}) circle (2.0pt);\n")
                else:
                    f.write(f"  \\fill[blue!45!black, opacity=0.5] "
                            f"({px(x):.2f},{py(y):.2f}) circle (1.6pt);\n")

            # parabole ajustee, tracee seulement sur l'intervalle de donnees
            # de l'actif (pas d'extrapolation hors du nuage)
            c, c_t = _quad_curvature(xs, mf)
            a, b = _quad_full(xs, mf)[:2]
            lo, hi = max(min(xs), xlo), min(max(xs), xhi)
            span = [lo + i * (hi - lo) / 60 for i in range(61)]
            pts = " ".join(
                f"({px(t):.2f},{py(a + b * t + c * t * t):.2f})"
                for t in span
                if Y_MIN <= a + b * t + c * t * t <= Y_MAX
            )
            f.write(f"  \\draw[very thick, green!45!black] plot coordinates {{{pts}}};\n")

            # moyennes par quintile (tirets noirs)
            qy, qx = _quintile_means(xs, mf)
            for mx, my in zip(qx, qy):
                f.write(f"  \\draw[black, thick] "
                        f"({px(mx) - 0.12:.2f},{py(my):.2f}) -- "
                        f"({px(mx) + 0.12:.2f},{py(my):.2f});\n")

            # titre + stats, au-dessus du cadre
            f.write(f"  \\node[anchor=north west, font=\\footnotesize] at "
                    f"({x0:.2f},{PANEL_H + 0.78:.2f}) {{{label}}};\n")
            f.write(f"  \\node[anchor=north west, font=\\scriptsize, text=black!65] "
                    f"at ({x0:.2f},{PANEL_H + 0.42:.2f}) "
                    f"{{curv.\\ {c:+.2f} ($t$ {c_t:+.2f})}};\n")

        # legendes d'axes
        mid = (2 * (PANEL_W + PANEL_GAP) + PANEL_W) / 2
        f.write(f"  \\node[font=\\footnotesize] at ({mid:.2f},-0.7) "
                f"{{Asset real return (\\%)}};\n")
        f.write(f"  \\node[rotate=90, font=\\footnotesize] at (-0.75,{PANEL_H / 2:.2f}) "
                f"{{MF proxy real return (\\%)}};\n")
        f.write("\\end{tikzpicture}\n")

    for key, column, label, _xb, _xt in CONVEX_PANELS:
        xs = [float(r[column]) for r in rows]
        c, c_t = _quad_curvature(xs, mf)
        qy, _ = _quintile_means(xs, mf)
        print(f"{OUT_CONVEX} {label:<22}: curv {c:+.2f}  t {c_t:+.2f}  "
              f"Q1 {qy[0]:+.1%}  Q3 {qy[2]:+.1%}  Q5 {qy[4]:+.1%}")


def _quad_full(xs, ys):
    """Comme _quad_curvature mais renvoie (a, b, c) de y = a + b x + c x^2."""
    s = [sum(x ** k for x in xs) for k in range(5)]
    ty = [sum(y * x ** k for x, y in zip(xs, ys)) for k in range(3)]
    mat = [[s[0], s[1], s[2], ty[0]],
           [s[1], s[2], s[3], ty[1]],
           [s[2], s[3], s[4], ty[2]]]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(mat[r][col]))
        mat[col], mat[pivot] = mat[pivot], mat[col]
        for r in range(3):
            if r == col:
                continue
            factor = mat[r][col] / mat[col][col]
            mat[r] = [mat[r][k] - factor * mat[col][k] for k in range(4)]
    return tuple(mat[k][3] / mat[k][k] for k in range(3))


if __name__ == "__main__":
    main()
