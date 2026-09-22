# Household-value framework integration — 6 September 2026

Question: explain composition and exposure within the existing ACO-style
household objective, without replacing it with another optimization problem.
This is an analytical/editorial change. All historical panels, ERC weights,
financing conventions, simulation results and empirical exhibits are unchanged.
The complete pre-edit manuscript is preserved in
`results/erc_refocusing/new_paper-before-utility-framework.tar.gz`.

## Derivation checked against the implementation

Inspected `build_scenario`, `evaluate` and `evaluate_batch` in
`build/compare_lifecycle_utility.py`: contributions precede working-period
returns; retirement payments precede returns; withdrawals equal 4% of initial
retirement wealth; Social Security and the consumption floor are external to
financial wealth; terminal wealth enters shifted bequest utility. Early deaths
have no retirement consumption terms but retain accumulated bequest wealth.

`utility-framework.tex` derives:

- positive homogeneity of financial wealth, actual payments and bequests in
  the contribution rate under the own-capital withdrawal rule;
- nondecreasing utility in saving, with explicit strictness/attainability
  conditions for implicit differentiation of equivalent saving;
- composition and exposure derivatives using dated total utility sensitivities,
  incorporating the change in the retirement target caused by pre-retirement
  returns, not just marginal utility of contemporaneous consumption;
- the difference between these household-value conditions and ERC variance
  contributions, without claiming either tested family is a global optimum;
- own-capital ruin's invariance to positive saving rescaling, apart from the
  half-cent event tolerance, and why a common ACO-income target breaks that
  scaling relation for candidate portfolios.

Differentiation under expectation requires local regularity and integrable
derivatives. Boundary probabilities are not assumed to vanish in a discrete
bootstrap. Necessary first-order conditions are not sufficient for a global
optimum; finite simulations, rather than an unestimated derivative, remain the
empirical evidence. No historical asset ranking is claimed to have been
predicted independently before observing results.

## Verification

From the project root:

```sh
python3 results/erc_refocusing/check_utility_framework.py
```

The deterministic check calls the original scalar engine and verifies wealth
scaling, failure invariance, monotone utility, the composition/exposure chain
rules and the implicit saving derivative. It covers retirement, pre-retirement
death and a depleted account. Dated finite differences explicitly rebuild the
retirement target. These are implementation sanity checks of the identities,
not a new Monte Carlo campaign, an empirical estimate of utility weights, or
a proof of differentiability on every path.

The introduction, results transition and conclusion now refer to this common
framework. The exposure ladders remain the empirical object; no leverage
above 200% is simulated or recommended. The existing bibliography is unchanged:
the identities are derived from the specified engine and elementary calculus,
not attributed to an unconsulted external source.

The quant-research workflow shaped the explicit analytical scope, inspection
of actual accounting conventions and preservation of all numerical evidence.
