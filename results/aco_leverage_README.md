# Matched ACO leverage and risk-aversion audit

ACO 33/67 is evaluated at 100, 125, 150, 175 and 200 percent exposure.
Additional borrowing uses the resident real bill plus 30 bp, exactly as for
the diversified portfolios. Equities remain unhedged. This matches exposure,
not volatility. Utility targets remain unlevered ACO saving 10 percent
(except the explicitly varied contribution-rate experiment).

Reproduce the current-paper experiments after building the panel:

```sh
python3 build/replicate_aco_leverage.py
python3 build/render_aco_comparisons.py
python3 -m unittest discover -s build -p test_aco_leverage.py
python3 build/verify_repository.py
```

Full pipeline: `bash build/replicate_all.sh` (alias of `build/rebuild_all.sh`).
The full pipeline also refreshes supplementary USA/numeraire controls.
Matched-leverage tables are generated in `paper/new_paper/figures/aco_*.tex`.
Simulation logs are under `results/aco_leverage_logs/`. Main experiments use
10,000 paired paths and seed 20260827; source-country omissions use 5,000.
The targeted refresh uses the existing source-omission and screened panels;
the canonical pipeline reconstructs the source omissions.

`results/gamma_fixed_theta_n10000.json` holds annual theta at 2360.
`paper/figures/gamma_sensitivity.json` retains the earlier joint calibration
(theta=2360*12**(3.84-gamma)). This joint calibration is our sensitivity,
not an assertion about ACO's risk-aversion experiment. Both outputs include
consumption/bequest decomposition, tail concentration, and root residuals.

At 175 percent exposure ACO ruin is 14.81 percent and equivalent saving 9.64
percent; equal-weight ruin is 2.79 percent and saving 7.16 percent.
With fixed annual theta, equal-weight 200 percent saving moves from 3.86 to
5.38 percent as gamma moves from 2 to 10; ACO 200 percent moves from 9.23 to
17.60 percent. Gamma acts on household consumption and shifted bequests;
it is not a penalty on return variance. The reference utility changes with
gamma too. At gamma 10 the worst one percent of equal-weight paths accounts
for 90.6 percent of negative utility, so tail sampling remains consequential.
