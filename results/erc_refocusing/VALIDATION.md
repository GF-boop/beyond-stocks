# Delivery validation — 6 September 2026

This records the ERC delivery before the subsequent household-value text
integration. Its numerical checks remain applicable; the PDF page count and
hash below refer to that earlier edition. Later editorial changes do not alter
simulation outputs.

- Final run: `n10000_final/completion.json`, all eight cases complete.
- 49 policy-case results have finite utility-equivalent saving estimates.
- Own-target common-income event identity: zero mismatches in every policy-case.
- No evaluated policy-case has an annual gross return at or below zero on its
  corresponding historical support (the inherited wealth-floor convention remains).
- All ten ACO/proportional baseline points reproduce archived ruin and
  equivalent saving within 1e-7.
- The final source-exclusion case has 1,560 observations and reproduces archived
  unlevered ACO, ACO 175%, and proportional 175% ruin and equivalent saving
  within 1e-7. Other Italian years remain in the panel.
- Deterministic regression suite: 33 tests pass, including five ERC tests.
- `git diff --check`: clean.
- Biber and repeated pdflatex passes succeed; final LaTeX log has no undefined
  references/citations, overfull boxes, underfull boxes or warnings.
- PDF: 28 pages. Main figure, results layout and sensitivity/calibration tables
  inspected visually. Tables and figures use the final run, not prior attempts.
- Final PDF SHA256:
  `eecff94de7636902cd3f2cbc3521ad6487abc17e1a9793f26089be4a4e54a709`.

These checks establish numerical consistency and document delivery. They do
not establish historical-parameter certainty, out-of-sample performance or
unrestricted household optimality.
