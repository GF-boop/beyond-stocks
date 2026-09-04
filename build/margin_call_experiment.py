#!/usr/bin/env python3
"""Expérience appel de marge pour la stratégie du papier.

Le compte sur marge personnel porte exactement les poids figés des familles à
levier (deux familles 200 % et échelle couverte 150 %) et suit la même
discipline que le moteur principal : rééquilibrage ANNUEL vers l'exposition
brute cible. La marge de maintenance (25 % des actifs) est testée en fin
d'année — la granularité des données annuelles — avant le rééquilibrage qui
restaure le coussin de marge. Mêmes chemins bootstrap que les tables
(10 000, seed 20260827).

CONSÉQUENCE MÉCANIQUE : le rééquilibrage annuel remet le compte à 50 % de
capitaux propres (brut 2×) ou 67 % (brut 1,5×) à chaque début d'année. Un
appel en fin d'année exige donc une perte SUR UNE SEULE ANNÉE au-delà du seuil
déduit du taux nominal : environ −31 % à brut 2×, −54 % à brut 1,5×. Le
cumul d'un drawdown pluriannuel — qui pilote un compte buy-and-hold non
rééquilibré — est effacé par le rééquilibrage et ne peut pas déclencher
d'appel ici.

CONVENTION NOMINALE : un compte sur marge est un contrat nominal — le broker
compare la valeur nominale des actifs à la dette nominale. Les rendements du
panel étant réels-résidents, on reconstruit les nominaux exacts :
R_nom = (1+R_réel_par_actif)×(1+π_résident)−1, où R_réel_par_actif est le
rendement réel du livret d'actifs par dollar d'actifs, et bill nominal idem.
L'inflation érode la dette nominale : les épisodes hyperinflationnistes ne
déclenchent pas d'appel, contrairement à ce qu'un test en réel suggérerait
à tort.
"""

import json
import hashlib
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compare_fixed_stacked_utility import (  # noqa: E402
    return_functions,
)
from replicate_extended import (  # noqa: E402
    MAX_AGE,
    START_AGE,
    block_bootstrap,
    read_panel,
)

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = 10000
SEED = 20260827
SPREAD = 0.003
MAINTENANCE = 0.25
# (nom moteur, label, exposition brute). Les deux familles 200 % viennent du
# manifeste gele ; l'echelle couverte 150 % est la lambda "90/60 oblig.
# mondiales" (90 % actions ACO + 60 % obligations mondiales couvertes).
LEVERED = (("80/53.33/33.33/33.33 ACO", "proportional_200", 2.0),
           ("ACO 33/67 175%", "aco_175", 1.75),
           ("ACO 33/67 200%", "aco_200", 2.0),
           ("43.75/43.75/43.75/43.75 ACO", "equal_weight_175", 1.75),
           ("50/50/50/50 ACO", "equal_weight_200", 2.0),
           ("90/60 oblig. mondiales", "covered_150", 1.5))


def nominal(real, pi):
  return (1.0 + real) * (1.0 + pi) - 1.0


def main():
  rows = read_panel(os.path.join(HERE, "..", "data",
                                 "replication-panel-trend.csv"))
  functions = return_functions(
    rows, SPREAD, 0.0085, 0.00566285264726086, 0.0, 0.001)
  horizon = MAX_AGE - START_AGE + 1
  rng = random.Random(SEED)

  # Facture nominale mediane du financement, pour chiffrer le seuil de perte
  # annuelle qui declencherait un appel.
  bills = sorted(nominal(row["world_bill"], row["inflation"]) for row in rows)
  median_bill = bills[len(bills) // 2]

  stats = {label: {"calls": 0, "paths_with_call": 0, "wipes": 0,
                   "path_years": 0, "min_year_end_ratio": 1.0,
                   "worst_asset_book_year": 0.0}
           for _, label, _ in LEVERED}
  for _ in range(RUNS):
    path = block_bootstrap(rows, horizon, rng, 10.0)
    for name, label, gross in LEVERED:
      fn = functions[name]
      st = stats[label]
      equity = 1.0
      called = wiped = False
      for row in path:
        pi = row["inflation"]
        bill_nom = nominal(row["world_bill"], pi)
        # Rendement du livret d'actifs par dollar d'actifs : le moteur
        # remunere la richesse (capitaux propres), on rajoute la facture de
        # financement (G-1)x(bill+spread) puis on divise par l'exposition
        # brute. Les nominaux sont reconstruits PAR ACTIF : nominaliser le
        # rendement leve produirait des nominaux impossibles des que
        # G x R < -100 %.
        per_asset = (fn(row) + (gross - 1.0)
                     * (row["world_bill"] + SPREAD)) / gross
        gross_nom = nominal(per_asset, pi)
        st["worst_asset_book_year"] = min(st["worst_asset_book_year"],
                                          gross_nom)
        # Debut d'annee : compte remis a l'exposition cible (G actifs,
        # G-1 de dette, par dollar de capitaux propres), puis une annee de
        # rendements sans rebalancement intra-annuel.
        assets = gross * equity * (1.0 + gross_nom)
        debt = (gross - 1.0) * equity * (1.0 + bill_nom + SPREAD * (1.0 + pi))
        eq = assets - debt
        assert math.isclose(eq / equity, (1.0 + fn(row)) * (1.0 + pi),
                            rel_tol=1e-10, abs_tol=1e-10)
        ratio = eq / assets if assets > 0 else 0.0
        st["min_year_end_ratio"] = min(st["min_year_end_ratio"], ratio)
        st["path_years"] += 1
        if eq <= 0.0:
          st["calls"] += 1
          wiped = True
          called = True
          break
        if ratio < MAINTENANCE:
          called = True
          st["calls"] += 1
        equity = 1.0  # ratios are scale invariant; normalize after rebalancing
      if called:
        st["paths_with_call"] += 1
      if wiped:
        st["wipes"] += 1

  out = {"seed": SEED, "runs": RUNS, "maintenance_margin": MAINTENANCE,
         "panel_rows": len(rows), "hedge_mode": "fixed_notional",
         "bootstrap_end_treatment": "aco", "mean_block_years": 10,
         "horizon": horizon, "spread_real": SPREAD,
         "panel_sha256": hashlib.sha256(open(os.path.join(HERE, '..', 'data',
                                    'replication-panel-trend.csv'), 'rb').read()).hexdigest(),
         "design": ("compte aux poids de la strategie, rebalance chaque "
                    "annee vers l'exposition cible ; marge testee en fin "
                    "d'annee ; nominaux reconstruits par actif"),
         "families": {}}
  for name, label, gross in LEVERED:
    st = stats[label]
    thresholds = sorted((gross - 1.0) * (1.0 + nominal(row['world_bill'], row['inflation'])
                         + SPREAD * (1.0 + row['inflation']))
                        / ((1.0 - MAINTENANCE) * gross) - 1.0 for row in rows)
    threshold = thresholds[len(thresholds) // 2]
    st["gross_exposure"] = gross
    st["single_year_loss_threshold"] = round(threshold, 4)
    out["families"][label] = st
    print(label, f"brut {gross:.0%}",
          {k: v for k, v in st.items() if k != "path_years"},
          f"| annees-compte: {st['path_years']:,}")
  out["median_nominal_bill"] = round(median_bill, 4)
  print(f"bill nominal median: {median_bill:.3%}")
  path = os.path.join(HERE, "..", "results", "margin_call_n10000.json")
  with open(path, "w") as fh:
    json.dump(out, fh, indent=1)
  print("->", path)


if __name__ == "__main__":
  main()
