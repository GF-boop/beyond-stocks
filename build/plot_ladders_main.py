#!/usr/bin/env python3
"""Génère paper/figures/ladders_main.tex : figure centrale à deux panneaux
(ruine et effort d'épargne équivalent en fonction de la volatilité annuelle
pondérée, avec le point ACO 33/67), à partir du JSON vérifié des ladders.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "main_ladders_n10000.json"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "paper" / "figures" / "ladders_main.tex"
VOL_MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 9.0
VOL_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 19.0
X0, X1 = 0.5, 5.5          # volatilité VOL_MIN -> VOL_MAX
HY = 5.5                   # hauteur d'un panneau (cm)
RUIN_MAX = 8.0
SAV_MAX = 16.0
PANEL_GAP = 7.8            # décalage horizontal du second panneau
TICKS = (10, 12, 14, 16, 18)


def parse_strategy(name: str):
  if name.startswith("ACO 33/67"):
    return None
  parts = name.split()[0].split("/")
  weights = [float(w) for w in parts]
  equal = max(weights) - min(weights) < 1e-9
  return equal


def xv(vol: float) -> float:
  return X0 + (vol - VOL_MIN) / (VOL_MAX - VOL_MIN) * (X1 - X0)


def yv(value: float, vmax: float) -> float:
  return value / vmax * HY


def series(d: dict, equal: bool):
  pts = []
  for r in d["results"]:
    if parse_strategy(r["strategy"]) == equal:
      pts.append((r["volatility"] * 100.0,
                  r["ruin_probability"] * 100.0,
                  r["equivalent_savings_rate"] * 100.0))
  return sorted(pts)


def path(pts, vmax, which):
  return " ".join(
      f"({xv(v):.3f},{yv(p if which == 'ruin' else s, vmax):.3f})"
      for v, p, s in pts)


def main():
  d = json.loads(SRC.read_text())
  prop = series(d, equal=False)
  eq = series(d, equal=True)
  bench = next(r for r in d["results"] if r["strategy"] == "ACO 33/67")
  aco_vol = bench["volatility"] * 100.0
  aco_ruin = bench["ruin_probability"] * 100.0
  aco_sav = bench["equivalent_savings_rate"] * 100.0

  out = []
  A = out.append
  A("% Généré par build/plot_ladders_main.py — ne pas éditer à la main.")
  try:
    source = SRC.resolve().relative_to(ROOT).as_posix()
  except ValueError:
    source = SRC.resolve().as_posix()
  A(f"% Source : {source} "
    f"(seed {d['seed']}, {d['runs']} traj.).")
  A("\\begin{tikzpicture}[x=1cm, y=1cm]")

  panels = [
      (0.0, "ruin", RUIN_MAX, 2.0, aco_ruin,
       {0: "0", 2: "2", 4: "4", 6: "6", 8: "8"},
       "(a) Retirement ruin (\\%)"),
      (PANEL_GAP, "saving", SAV_MAX, 4.0, aco_sav,
       {0: "0", 4: "4", 8: "8", 12: "12", 16: "16"},
       "(b) Utility-equivalent saving (\\%)"),
  ]

  for shift, which, vmax, grid, aco, labels, title in panels:
    A(f"\\begin{{scope}}[shift={{({shift},0)}}]")
    level = 0.0
    while level <= vmax + 1e-9:
      y = yv(level, vmax)
      A(f"  \\draw[gray!20] (0,{y:.3f}) -- ({X1 + 0.3:.2f},{y:.3f});")
      A(f"  \\node[left, font=\\footnotesize] at (-0.15,{y:.3f}) {{{labels[level]}}};")
      level += grid
    for t in TICKS:
      x = xv(float(t))
      A(f"  \\draw[gray!20] ({x:.3f},0) -- ({x:.3f},{HY:.3f});")
      A(f"  \\node[below, font=\\footnotesize] at ({x:.3f},-0.12) {{{t}}};")
    A(f"  \\draw[gray!60] (0,0) -- ({X1 + 0.3:.2f},0);")
    A(f"  \\draw[gray!60] (0,0) -- (0,{HY:.3f});")

    # point ACO 33/67 : triangle plein
    ax, ay = xv(aco_vol), yv(aco, vmax)
    A(f"  \\fill ({ax:.3f},{ay:.3f}) -- ++(-0.14,-0.24) -- ++(0.28,0) -- cycle;")
    A(f"  \\node[font=\\footnotesize, anchor=south] at ({ax:.3f},{ay + 0.14:.3f}) "
      f"{{ACO 33/67}};")

    # série proportionnelle : trait plein, cercles pleins
    A(f"  \\draw[thick] plot coordinates {{{path(prop, vmax, which)}}};")
    for v, p, s in prop:
      y = yv((p if which == "ruin" else s), vmax)
      A(f"  \\fill ({xv(v):.3f},{y:.3f}) circle (0.075);")

    # série équipondérée : trait pointillé, carrés ouverts
    A(f"  \\draw[thick, dashed] plot coordinates {{{path(eq, vmax, which)}}};")
    for v, p, s in eq:
      y = yv((p if which == "ruin" else s), vmax)
      A(f"  \\node[draw, thick, rectangle, inner sep=1.6pt, fill=white] "
        f"at ({xv(v):.3f},{y:.3f}) {{}};")

    # titres
    A(f"  \\node[font=\\footnotesize] at ({(X1) / 2:.2f},{HY + 0.45:.2f}) {{{title}}};")
    A(f"  \\node[font=\\footnotesize] at ({(X1) / 2:.2f},-0.62) "
      f"{{Pooled annual volatility (\\%)}};")
    A("\\end{scope}")

  # légende commune sous les panneaux
  ly = -1.35
  lx = 0.6
  A(f"  \\draw[thick] ({lx:.2f},{ly:.2f}) -- ({lx + 0.75:.2f},{ly:.2f});")
  A(f"  \\fill ({lx + 0.375:.2f},{ly:.2f}) circle (0.075);")
  A(f"  \\node[font=\\footnotesize, anchor=west] at ({lx + 0.95:.2f},{ly:.2f}) "
    f"{{60/40/25/25 proportional}};")
  lx2 = 7.8
  A(f"  \\draw[thick, dashed] ({lx2:.2f},{ly:.2f}) -- ({lx2 + 0.75:.2f},{ly:.2f});")
  A(f"  \\node[draw, thick, rectangle, inner sep=1.6pt, fill=white] "
    f"at ({lx2 + 0.375:.2f},{ly:.2f}) {{}};")
  A(f"  \\node[font=\\footnotesize, anchor=west] at ({lx2 + 0.95:.2f},{ly:.2f}) "
    f"{{Equal-weight four-sleeve}};")

  A("\\end{tikzpicture}")
  OUT.write_text("\n".join(out) + "\n")
  print(f"écrit : {OUT}")


if __name__ == "__main__":
  main()
