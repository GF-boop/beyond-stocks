# Concentration, monthly margin and ablation ladders

The main manuscript now reports the complete raw/source-screened comparison
side by side. Raw data remain available; the screen is not claimed to identify
an ex ante tradable panel. Its 33 exclusions combine the existing closure list,
realized annual CPI thresholds and audit-selected Italy 1942. Italy 1942 is
not flagged by the original filter. Exclusions apply to the reconstructed
international-equity and global-bond sources as well as resident observations.
The monthly MF input is fixed. The separate 0.5% winsorization clips five
risky sleeve columns after currency conversion, before leverage and fees;
cash, inflation and bootstrap support are unchanged. These are distinct tests.

Reproduce from the current canonical data:

```sh
python3 build/panel_concentration_comparison.py
python3 build/sleeve_ablation.py --ladder --runs 10000 --output-json results/sleeve_ablation_ladders_n10000.json
python3 build/sleeve_ablation.py --ladder --runs 10000 --panel results/panel_concentration/panel-screened.csv --output-json results/panel_concentration/screened_ablation_ladders_n10000.json
python3 build/monthly_margin_diagnostic.py
python3 build/render_panel_margin_ablation.py
python3 -m unittest discover -s build -p test_panel_margin_ablation.py
```

All steps are also in `build/replicate_all.sh` through `build/rebuild_all.sh`.
The full portfolio comparisons and ablations use 10,000 paths, seed 20260827.
Each panel has its own unlevered ACO utility target. Pairing is within panels;
equal seeds do not create identical paths across different panel supports.
The original 175% ablation results were reproduced to 1e-12 in all three
reported metrics by the 45-strategy ladder. The complete raw comparison
exactly reproduced the existing main-ladder result rows.

Monthly margin outputs are in `results/margin_monthly/`: the input snapshot,
provenance and results are retained. This is a USD proxy test over 56 complete
years, 1970–2025: US/ex-US equity TR simulations, US Treasury TR proxy for
global bonds, gold spot and reconstructed MF net. Fixed sleeve quantities
within each year, annual reset, nominal cash plus 30bp borrowing. Month-end
and year-end tests share the same paths. The 10,000 bootstrap paths contain
86 years each, with mean ten-year blocks and fresh random start at sample end.
Crossings are recorded without forced liquidation. The test does not establish
intramonth margin safety or reconstruct the annual 16-resident panel monthly.

Tests cover zero borrowing, a monthly breach hidden by year-end recovery,
and preservation of gross exposure in each ablation. Every annual threshold
crossing is also a monthly crossing by construction and checked in the runner.
