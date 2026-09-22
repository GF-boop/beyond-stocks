"""Construction variants of the managed-futures proxy.

The paper uses a single trend rule: a blend of 1-, 6- and 12-month signals, a
10% volatility target capped at 3x, inverse-volatility sector weights, net of a
0.85% fee and a turnover cost. A referee may ask whether this precise choice
drives the conclusions. This script rebuilds the same real annual series for
four construction variants and reports their moments and their annual
correlation with the retained version.

Annual recipe, identical to ``build/panel_managed_futures.py``: each month, the
variant's gross USD return is deflated by US CPI, the twelve months of a
complete calendar year are compounded, then the fees are applied. Turnover
costs are those actually measured for each variant (column
``*_transaction_cost`` of the monthly file), not the value of the canonical
version, so that a faster signal carries its higher turnover cost.

Variants:

* ``1_6_12``      : the retained version (reference, correlation 1 by construction);
* ``1_3_12``      : AQR-style blend;
* ``12m``         : slow signal only, the original specification of Moskowitz,
                    Ooi and Pedersen (2012);
* ``1m``          : fast signal only, the other extreme;
* ``1_6_12_2fee`` : retained version with the management fee doubled to 1.70%.

Outputs:

* ``figures/mf_variants.json``: full audit;
* ``figures/mf_variants.tex``: table included by Appendix B.
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
MONTHLY = os.path.join(DATA, "managed-futures-monthly.csv")
CPI = os.path.join(DATA, "cpi-monthly.csv")

OUT_DIR = os.path.join(HERE, "..", "paper", "figures")
OUT_JSON = os.path.join(OUT_DIR, "mf_variants.json")
OUT_TEX = os.path.join(OUT_DIR, "mf_variants.tex")

TREND_FEE = 0.0085                       # commission de gestion canonique
REFERENCE_KEY = "1_6_12"

# (key, label, gross-return column, turnover-cost column,
#  commission de gestion appliquee)
VARIANTS = [
    ("1_6_12", "1/6/12 blend (baseline)",
     "mf_1_6_12_gross_return", "mf_1_6_12_transaction_cost", TREND_FEE),
    ("1_3_12", "1/3/12 blend",
     "mf_1_3_12_gross_return", "mf_1_3_12_transaction_cost", TREND_FEE),
    ("12m", "12-month signal only",
     "signal_12m_gross_return", "signal_12m_transaction_cost", TREND_FEE),
    ("1m", "1-month signal only",
     "signal_1m_gross_return", "signal_1m_transaction_cost", TREND_FEE),
    ("1_6_12_2fee", "1/6/12 blend, fee doubled to 1.70\\%",
     "mf_1_6_12_gross_return", "mf_1_6_12_transaction_cost", 2.0 * TREND_FEE),
]


def previous_month(month: str) -> str:
  year, mon = (int(part) for part in month.split("-"))
  mon -= 1
  if mon == 0:
    year, mon = year - 1, 12
  return f"{year:04d}-{mon:02d}"


def month_number(month: str) -> int:
  year, mon = (int(part) for part in month.split("-"))
  return year * 12 + mon - 1


def read_cpi() -> dict[str, float]:
  """Monthly US CPI, with an isolated missing month filled.

  Reproduces ``fill_isolated_gaps`` of ``build/panel_managed_futures.py``: the
  BLS did not publish October 2025, and without that single month the year 2025
  would be lost although its twelve returns exist. Only a gap of exactly one
  month is filled, by the geometric mean of its neighbours, never an endpoint.
  """
  with open(CPI, encoding="utf-8") as handle:
    cpi = {row["month"]: float(row["cpi"])
           for row in csv.DictReader(handle) if row.get("cpi")}
  months = sorted(cpi)
  for index in range(1, len(months)):
    earlier, later = months[index - 1], months[index]
    if month_number(later) - month_number(earlier) != 2:
      continue
    cpi[previous_month(later)] = (cpi[earlier] * cpi[later]) ** 0.5
  return cpi


def annual_real_net(gross_col: str, cost_col: str, fee: float,
                    cpi: dict[str, float]) -> dict[int, float]:
  """Net real annual series of a variant.

  Deflation month by month before compounding, complete calendar years only,
  then deduction of the measured monthly turnover cost and, at year-end, of
  the annual management fee.
  """
  by_year_real: dict[int, list[float]] = {}
  by_year_cost: dict[int, list[float]] = {}
  with open(MONTHLY, encoding="utf-8") as handle:
    for row in csv.DictReader(handle):
      gross = row.get(gross_col)
      if not gross:
        continue
      month = row["month"]
      earlier = previous_month(month)
      if month not in cpi or earlier not in cpi:
        continue
      deflator = cpi[month] / cpi[earlier]
      real_gross = (1.0 + float(gross)) / deflator - 1.0
      cost = float(row.get(cost_col) or 0.0)
      by_year_real.setdefault(int(month[:4]), []).append(real_gross)
      by_year_cost.setdefault(int(month[:4]), []).append(cost)

  annual: dict[int, float] = {}
  for year, months in by_year_real.items():
    if len(months) != 12:
      continue
    costs = by_year_cost[year]
    compounded = 1.0
    for real_gross, cost in zip(months, costs):
      compounded *= 1.0 + real_gross - cost
    annual[year] = compounded * (1.0 - fee) - 1.0
  return annual


def moments(series: list[float]) -> dict[str, float]:
  n = len(series)
  mean = statistics.fmean(series)
  sd = statistics.stdev(series)
  m3 = sum((x - mean) ** 3 for x in series) / n
  skew = m3 / sd ** 3
  ordered = sorted(series)
  # 5e centile par interpolation lineaire
  pos = 0.05 * (n - 1)
  lo = int(math.floor(pos))
  frac = pos - lo
  p5 = ordered[lo] + frac * (ordered[min(lo + 1, n - 1)] - ordered[lo])
  return {"mean": mean, "sd": sd, "sharpe0": mean / sd, "skew": skew,
          "p5": p5}


def correlation(a: list[float], b: list[float]) -> float:
  ma, mb = statistics.fmean(a), statistics.fmean(b)
  num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
  den = math.sqrt(sum((x - ma) ** 2 for x in a)
                  * sum((y - mb) ** 2 for y in b))
  return num / den


def main() -> None:
  cpi = read_cpi()
  built = {}
  for key, label, gross_col, cost_col, fee in VARIANTS:
    built[key] = annual_real_net(gross_col, cost_col, fee, cpi)

  reference = built[REFERENCE_KEY]
  common = sorted(set.intersection(*(set(s) for s in built.values())))
  ref_series = [reference[y] for y in common]

  results = []
  for key, label, _g, _c, fee in VARIANTS:
    series = [built[key][y] for y in common]
    stats = moments(series)
    corr = correlation(series, ref_series)
    results.append({
        "key": key,
        "label": label,
        "management_fee": fee,
        "mean": stats["mean"],
        "sd": stats["sd"],
        "sharpe0": stats["sharpe0"],
        "skew": stats["skew"],
        "p5": stats["p5"],
        "corr_with_baseline": corr,
    })

  payload = {
      "years_first": common[0],
      "years_last": common[-1],
      "n_years": len(common),
      "reference": REFERENCE_KEY,
      "trend_fee_baseline": TREND_FEE,
      "results": results,
  }
  os.makedirs(OUT_DIR, exist_ok=True)
  with open(OUT_JSON, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")

  with open(OUT_TEX, "w", encoding="utf-8") as f:
    f.write("% Generated by build/mf_variants.py -- do not edit.\n")
    f.write("\\begin{tabular}{lrrrrrr}\n\\toprule\n")
    f.write("Variant & Mean & SD & Mean/SD & Skew & 5th pctl & "
            "Corr.\\ baseline \\\\\n\\midrule\n")
    for r in results:
      marker = "$^{\\dagger}$" if r["key"] == REFERENCE_KEY else ""
      f.write(f"{r['label']}{marker} & {100 * r['mean']:.2f}\\% & "
              f"{100 * r['sd']:.2f}\\% & {r['sharpe0']:.2f} & "
              f"{r['skew']:+.2f} & {100 * r['p5']:.1f}\\% & "
              f"{r['corr_with_baseline']:.3f} \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

  print(f"{OUT_JSON}\n{OUT_TEX}")
  print(f"years {common[0]}--{common[-1]} ({len(common)})")
  for r in results:
    print(f"  {r['label']:<40} mean {100*r['mean']:5.2f}%  sd {100*r['sd']:5.2f}%  "
          f"skew {r['skew']:+.2f}  corr {r['corr_with_baseline']:.3f}")


if __name__ == "__main__":
  main()
