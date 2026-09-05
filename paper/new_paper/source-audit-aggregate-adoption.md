# Source audit: individual allocation and aggregate adoption

Initially added as Section 5.8 on September 5, 2026; approximately one page, with a
forward reference in the introduction. This is an interpretation of the
existing experiment, not a new capacity estimate or a change to simulations.

| Reference | Evidence used | Boundary retained in the manuscript |
| --- | --- | --- |
| Gabaix and Koijen (2023), December 23 working-paper revision, DOI 10.2139/ssrn.3686935 | Institutional constraints, low demand elasticity, and valuation responses to flows. Authors' abstract and revision metadata consulted on SSRN; year checked against Gabaix's Harvard page. | No numerical flow multiplier imported into our experiment. Implications for retirement reallocations are explicitly our interpretation. |
| Erb and Harvey (2013), Financial Analysts Journal 69(4), 10–42 | Demand scenarios involving emerging economies and the historical relation between real gold prices and subsequent returns. Published article consulted through Harvey's Duke page. | No universal mean-reversion forecast, capacity threshold, or prediction of future correlations. |
| Baltas (2019), Financial Analysts Journal 75(3), 89–104 | Publisher-indexed article text and abstract report weaker subsequent performance of crowded divergence premia, including cross-sectional momentum. | Distinguished from time-series momentum; motivates a mechanism, not a capacity estimate for our proxy. |
| Baltas and Kosowski (2013), January 5 working paper, DOI 10.2139/ssrn.1968996 | Authors' abstract in the Singapore Management University repository reports no statistically significant capacity constraints in their historical study. | Absence of detectable constraints in that sample is not evidence of unlimited capacity or a current industry assessment. |

Sources:

- [Gabaix–Koijen author abstract](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4108272_code374406.pdf?abstractid=3686935&mirid=1), [Harvard record](https://xgabaix.scholars.harvard.edu/publications/search-origins-financial-fluctuations-inelastic-markets-hypothesis).
- [Erb–Harvey published article](https://people.duke.edu/~charvey/Research/Published_Papers/P113_The_golden_dilemma.pdf).
- [Baltas publisher article](https://www.tandfonline.com/doi/abs/10.1080/0015198X.2019.1600955). Direct opening returned HTTP 403; indexed publisher text was available. The publisher's practitioner summary was also consulted but is not substituted for the author in the bibliography.
- [Baltas–Kosowski author abstract and bibliographic record](https://ink.library.smu.edu.sg/bnp_research/17/).

The price-taking assumption and fixed historical return environment describe
our simulation design. Statements about ownership transfers, prices at fixed
expected cash flows, market clearing, and limits of the cost stresses are
economic reasoning applied to this design, not new empirical findings.

Validation: pdflatex, biber, and two further pdflatex passes completed;
final log has no warnings, undefined references, or overfull/underfull boxes.
The subsection appears on pages 20–21, immediately before the conclusion;
its length is approximately one page in the existing typography.

## Second annotation round

The discussion is now a standalone section, and introduction and conclusion
use unnumbered headings. The sentence disclaiming an estimated adjustment
to ACO's results was removed as requested. Gold and trend-following paragraphs
were rewritten in plain language while retaining the scope of each citation.
The closing paragraph now explicitly identifies the historical-return
assumption shared with ACO. This was checked against the local July 2025
paper, `../../papers/Anarkulova_Cederburg_ODoherty_2025_Beyond_Status_Quo.pdf`,
especially its description of resampling returns and optimizing household
weights over those draws.

The four annotations are preserved in
`main-styled-annotated-round2-2026-09-05.pdf`:

- `a9a44952`: delete the final sentence of the equity paragraph — done.
- `e2da00f7`: simplify the gold paragraph — done.
- `77d5dacb`: simplify the trend-following paragraph — done.
- `57b2ae51`: explain that ACO also does not model aggregate adoption,
  separate the discussion from Results, and unnumber Introduction and
  Conclusion — done.
