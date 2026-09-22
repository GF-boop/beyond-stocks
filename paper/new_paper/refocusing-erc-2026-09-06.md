# Editorial change record: original question, ERC comparator

The revised paper asks whether a wider opportunity set improves transparent
retirement allocation rules under explicit financing conditions. The user
approved retrospective ERC calibration and removing the equal-capital family
from the manuscript, without another appendix devoted to it. The numerical
protocol recorded this choice before ERC outcomes were examined.

## Narrative and scientific boundaries

- Keep the public-data ACO extension as the main contribution, not a novel
  optimal-retirement-allocation method.
- Compare only ACO, proportional weights and retrospective ERC in the central
  results, at common exposures from 100% to 200%.
- Preserve the distinction between utility-equivalent saving, own-capital
  ruin and common-income failure. No ES-experiment figures replace these metrics.
- Remove the separate frontier/exclusion-threshold theory and its empirical
  figures from the compiled manuscript. Old source files have since been
  removed from the repository.
- Report the ERC full-panel common-income reversal and all its targeted cost
  failures; avoid interpreting equal annual risk contributions as household
  optimality or equal risk after financing.
- Use the complete exposure ladder, not a volatility-matched selected point.
- Keep availability evidence explicitly limited to the proportional rule for
  which it was run. Do not transplant prior equal-capital robustness claims
  onto ERC. Broader ERC historical resampling, preference and MF-construction
  sensitivities have not been run in this campaign.

## Reading map

1. Introduction: opportunity set, financing, contribution and principal limits.
2. Data and experimental design: public panel, household objective, fixed versus
   covariance-estimated weights, returns and resampling.
3. Diversification and exposure: benchmark replication, full ladders, ablations.
4. Conditions: common planned income, historical regimes, financing/MF costs.
5. Economic scope, then conclusion.

`appendices-refocused.tex` replaces the previously included appendix file:
A inputs and MF validation; B ERC solver and ablations; C targeted sensitivities
and covariance/availability scope; D common income; E financing/tax/margin
limitations; F reproducibility. It has a linked question-based reading guide.
The old large benchmark matrices and development-history tables are not
automatically carried forward as additional appendix material.

## Evidence, references and preservation

Exhibits are generated from `results/erc_refocusing/n10000_final/` by
`build/render_erc_refocusing.py`, with JSON provenance. Baseline values are
reproduced against the old ladder archive. The source-event check additionally
screens the resident Italy 1942 row, as required by the original workflow.

The ERC formulation was checked against Roncalli's author-posted companion
exercise solutions (arXiv:1403.1889, ERC and risk-budgeting sections), cited in
`references-erc.bib`. The Maillard/Roncalli/Teiletche original PDF could not be
retrieved and is not newly cited as though its full text had been read.
ACO Table VI Panel L was checked in the November 18, 2024 source PDF; no claim
is made that its 37bp assumption is identical to our separately costed 30bp.
CME and the dated Cboe guest financing article were also consulted. Other
source descriptions/citations are retained from the earlier manuscript review,
not represented as a new comprehensive literature or tax review.

The complete pre-edit `new_paper` folder is recoverable from
`results/erc_refocusing/new_paper-before-erc.tar.gz`; all previous research
outputs are preserved. No new manuscript branch was created. The quant-research
workflow materially shaped the pre-outcome contract, provenance checks and
retention of unfavorable findings.
