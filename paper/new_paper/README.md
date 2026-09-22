# Beyond All-Equity: Levered Diversification over the Lifecycle

Current manuscript: [main-styled.pdf](main-styled.pdf) (28 pages, exhibits next to the text) and its
separate [internet-appendix.pdf](internet-appendix.pdf) (25 pages).

The paper compares three families of fixed-weight strategies on the same
100–200% gross-exposure grid: all-equity (ACO 33/67), proportional
(40/27/17/17), and retrospective risk parity (ERC). The main outcomes are the
equivalent savings rate, the probability of financial ruin, and the
probability of failing to fund a common income (4% of the paired all-equity
retirement wealth). It does not claim that any strategy maximizes household
utility, that 175% is an optimum, or that the calibration is out of sample.

## Revision of September 22, 2026

Changes made after an internal review, keeping the paper within its previous size:

- equal-volatility comparison (Table II, Panel E; Table VI, Panel E): each
  diversified strategy is scaled to the 25.28% volatility of unlevered
  all-equity. Risk parity needs 265% exposure and then beats the proportional
  strategy on saving, but not under a 3% managed-futures haircut;
- bond-free variants (Table II, Panel D): stocks/gold/MF and stocks/MF;
- Sharpe ratios in excess of bills (Table I); bonds 0.29 versus stocks 0.31;
- proxy versus SG CTA, SG Trend and BTOP50 by subperiod (Section 3);
- intra-year margin evidence brought into the main text; Italy 1942
  exclusion explained; ACO spread wording harmonized; introduction made less
  number-dense, with a concrete common-income example;
- the internet appendix is now a separate document linked with `xr-hyper`;
- second pass (same day): "Key findings" box on the title page; Asness (2024),
  Bhansali et al. (forthcoming) and Gordillo and Hoffstein (2021) cited; new
  Section 6 on implementation for French/European households (UCITS funds with
  embedded leverage, box spreads in an ordinary securities account, flat tax,
  derivative-loss offsetting). Product and tax facts checked online on
  September 22, 2026; the tax statements should be confirmed by a tax adviser.
- third pass (same day), answering an external review: equal volatility is
  the main basis of comparison (proportional 166%, risk parity 265%, stocks
  and MF 132%); "common income" renamed "path-matched income"; new Table II
  separating the three measures, including the path-matched failure at each
  strategy's own equivalent savings rate; Tables VI (resampled histories) and
  VII (sensitivity, now with managed-futures signal variants in Panel E)
  recomputed at equal volatility; exposure and independent-information
  paragraphs; abstract states results only. Exhibits follow the text; set
  `\submissiontrue` in `main-styled.tex` to move them after the references.

Source numbers: `../../results/revision_2026-09-22/`. Earlier states of the
manuscript are in the git history.

## Files

- `preamble.tex` — shared preamble.
- `main-styled.tex` — paper; tables and figures after the references.
- `internet-appendix.tex` — assembles `appendices-refocused.tex` (Appendices
  A–D) with its own reference list.
- `build.sh` — compiles both documents in the order cross-references need.

The utility framework lives in Section B.4 of the internet appendix.

## Evidence and rebuild

Authoritative run: `../../results/erc_refocusing/n10000_final/` (protocol in
`../../results/erc_refocusing/PROTOCOL.md`). Revision checks:
`build/revision_checks.py`, which reuses seed 20260827 and asserts that the
published baseline is reproduced exactly.

From the project root:

```sh
OPENBLAS_NUM_THREADS=1 python3 build/revision_checks.py
OPENBLAS_NUM_THREADS=1 python3 build/revision_checks.py 0.03   # 3% MF haircut
OPENBLAS_NUM_THREADS=1 python3 build/eqvol_sensitivity.py
OPENBLAS_NUM_THREADS=1 python3 build/mf_variant_lifecycle.py
for b in 5 10 20; do OPENBLAS_NUM_THREADS=1 python3 build/historical_panel_bootstrap_eqvol.py --outer-mean-block $b; done
python3 build/render_sleeve_properties.py
python3 build/render_erc_refocusing.py
python3 build/render_composition_value.py
python3 build/render_restored_appendices.py
```

Then, from this directory, `./build.sh`. Compilation runs no simulation.
The proxy-versus-index statistics require the licensed files in
`data/benchmarks-externes/`; without them the stored JSON is used as is.
