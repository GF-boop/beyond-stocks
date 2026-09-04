# Paper coherence audit — 2026-09-05

Scope: `paper/new_paper/main-styled.tex`, its revised appendices, referenced
numerical exhibits, and the MF-dependent replication paths.

## Construction and provenance

The repository monthly MF snapshot matches the upstream engine output byte
for byte. The central convention converts synthetic bond excess P&L without
adding foreign principal; price-index equities retain principal FX exposure.
This inner construction is distinct from the annual fixed-notional hedge on
the resulting USD NAV in the resident panel. Both are now described explicitly.

Annual lifecycle calculations use the measured turnover deduction (0.6146%
per year) and 0.85% management fee. Monthly validation uses the monthly net
series. The signal-variant table compounds realized monthly transaction costs;
its baseline annual real mean is 7.91%, versus 8.10% under the flat annual
cost convention in the annual diagnostics. The caption explains this difference.

## Reconciled exhibits

- Abstract, introduction, baseline and conclusion: equal-weight 175% has
  2.48% ruin and 6.53% equivalent saving, versus 6.98% and 10% for ACO 100%.
- Complete raw/source-screened comparison, annual moments, and winsorization
  table are generated from the three archived panel experiments.
- Ablations cover five exposures in both families, with matched-leverage ACO;
  the 175% rows reproduce the earlier standalone ablation exactly.
- Policy sensitivity now imports its generated table rather than a stale copy.
- Construction checks were rerun. The frozen legacy screen retains its
  country-year membership but now takes returns from the current panel.
- All sixteen source-country omissions were rebuilt and rerun (5,000 paths
  per omission). Proportional/equal-weight 200% ruin ranges are 0.90–2.88%
  and 1.36–3.16%; equivalent saving ranges are 4.65–4.89% and 5.07–5.56%.
- Event exclusions, financing sensitivities, preference sensitivities, and
  monthly benchmark/fund comparisons were reconciled with their outputs.
- Annual margin experiment now imports current MF costs; its minimum equity
  shares are 48.91% (equal-weight 175%), 38.59% (proportional 200%), and
  40.39% (equal-weight 200%).

## Interpretation retained in the paper

The raw 1927–2025 panel remains the baseline, with the complete source-screened
comparison alongside it. The screen includes realized inflation and an
audit-selected Italy 1942 exclusion; it is not described as an ex ante trading
rule. Cross-panel saving rates target different ACO utilities.

The monthly margin control uses USD total-return simulations since 1970 and
a US Treasury proxy for global bonds. It measures month-end versus year-end
threshold crossings on identical paths within that control. It does not
reconstruct the sixteen-country monthly panel, intramonth extrema, or forced
liquidation. External MF correlations characterize contemporary overlap;
they do not establish historical futures implementability.

## Checks

`python3 build/verify_repository.py` checks canonical metadata/costs, panel
hashes for concentration and annual margin, MF hash for monthly margin,
exact agreement between the raw complete comparison and baseline ladders,
and current returns in the frozen legacy-membership panel.

`python3 build/test_panel_margin_ablation.py` checks a monthly breach hidden
by annual recovery, full equity ownership without borrowing, and preservation
of gross exposure under each ablation. Both commands passed during this audit.

The curves were visually inspected and the revised LaTeX manuscript compiled.
The full multi-hour upstream-to-PDF pipeline was not rerun as a single command
during this coherence audit; affected experiments were run individually.
