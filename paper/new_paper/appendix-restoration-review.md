# Numerical appendix restoration — 6 September 2026

The parent manuscript is the source of the broader coverage, not a superseded
scientific baseline. Restoration uses compatible corrected outputs rather than
copying obsolete panel or currency-hedging conventions. No simulations were run
for this editorial revision. The previous manuscript is preserved in
`results/erc_refocusing/new_paper-before-appendix-restoration.tar.gz`.

| Legacy material | Treatment in the current manuscript |
| --- | --- |
| Asset return histories and pooled moments | Restored using the reviewed return exhibits. |
| MF commercial benchmarks, correlations and regressions | Restored; related KMLM series are not treated as independent validation. |
| MF annual moments, convexity and signal variants | Restored descriptive exhibits. |
| Old MF-variant lifecycle estimates | Not transplanted: their ACO baseline differs from the corrected current baseline. |
| Allocation and exposure ladders | Current ACO/proportional/ERC results retained; no duplicate legacy ladders. |
| Calendar-history uncertainty | Restored corrected 1,561-observation outer-bootstrap results for the proportional allocation. |
| Historical availability | Existing proportional-only experiment retained with its explicit coverage rule. |
| Risk aversion and bequests | Restored both fixed annual bequest weight and fixed legacy coefficient conventions. |
| Saving and withdrawal policies | Restored matched ACO/proportional results. |
| Real-bill attribution | Restored ACO/proportional decomposition. |
| Annual and monthly margin diagnostics | Restored with distinct annual-account and monthly-proxy interpretations. |
| Older leave-country-out and alternative-numeraire tables | Not transplanted where the panel or hedge convention differs; a compatible rerun would be needed. |
| Reproduction appendix | Rewritten as economic conventions, data availability and descriptive repository links. |

The equal-capital family remains archived, not included in the manuscript.
Legacy household tests do not establish ERC robustness: coverage is stated
next to the relevant tables, including limitations and unfavorable findings.

`build/render_restored_appendices.py` projects archived results without changing
estimates and records source hashes in `figures/restored/provenance.json`.
The main renderer verifies the frozen simulation inputs; its own presentation
code is exempt from the old renderer hash and its current hash is recorded in
the exhibit provenance. The immutable simulation manifest is not rewritten.

Figure markers now have an explicit five-level gross-exposure legend, separate
from the three allocation-family lines. Repository links describe their contents
instead of displaying function names. These links use the repository's existing
main-branch convention; newly added local files require publication before their
remote links become available. This revision does not publish or push files.
