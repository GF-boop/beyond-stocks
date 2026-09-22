# ERC comparison and manuscript refocusing — 6 September 2026

## Authoritative outputs

The completed production run is `n10000_final/`. It evaluates 10,000 paired
households per specification, seed 20260827, using the original ACO-style
utility and withdrawal engine. Read [PROTOCOL.md](PROTOCOL.md) for the design
fixed before ERC performance was examined. There is no expected-return forecast
or household-outcome optimization. ERC covariance and weights are retrospective.

Unscaled weights (equities, global bonds, gold, MF):
14.5272%, 47.4674%, 12.0540%, 25.9514%. Exposure multiplies these weights;
at 175% their notionals are approximately 25.42%, 83.07%, 21.09%, 45.42%,
with borrowing of 75% of NAV. Annual risk contributions are equal before
financing, not after including the stochastic bill leg.

The run covers the three five-point exposure ladders, six 175% pro-rata
ablations, and seven targeted sensitivity cases. Common ACO-income failure
is evaluated alongside own-capital ruin for every policy. This is 49 policy-case
evaluations, not 49 independent datasets. All baseline ACO and proportional
ruin/saving values reproduce the original archive within 1e-7.

At 175%, proportional/ ERC own-capital ruin is 2.13% / 3.79%, equivalent
saving 5.87% / 8.29%, and common-income failure 2.17% / 14.25%.
Unlevered ACO has 6.98% failure under either withdrawal definition, with
10% reference saving. The unfavorable full-panel ERC common-income result
and its cost sensitivity remain prominent in the revised manuscript.

## Reproduction

From the project root, with NumPy, SciPy and Matplotlib available:

```sh
python3 -m pytest build/test_erc_refocusing.py -q
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 build/erc_refocusing.py --runs 10000 --full --tag fresh
python3 build/render_erc_refocusing.py
```

The simulation refuses to overwrite an existing run directory. The renderer
reads `n10000_final/`; reproducing figures from a fresh run requires explicitly
reviewing and changing that source, not silently overwriting the reference.
The manifest fingerprints the input panel, protocol, existing build Python
sources and JSON inputs. The source-event panel hash is recorded separately in
`calibration_sensitivities.json`. The reconstruction provenance is in
`results/method_review/source_exclusions/provenance.json`.

## Audit and retained attempts

- `n100/`: smoke test, not performance evidence. One small-sample utility target
  cannot be reached within the saving bracket; its NaN is not a production result.
- `n10000/`: incomplete first attempt, stopped by an archive field-name mismatch
  after baseline calculations. It is not a completed result source.
- `n10000_verified/`: superseded. Its Italy source diagnostic removed the source
  from global baskets but initially omitted the separate resident-row screen.
  Baseline/cost/post-1970 outcomes are unaffected; do not cite its source-event
  calibration or simulation as the full source-exclusion check.
- `n10000_final/`: fixes that screen, keeps 1,560 observations for the source
  case, and preserves every baseline allocation, cost and seed. The regression
  test explicitly retains other Italian years. No outcome-based tuning.

`new_paper-before-erc.tar.gz` preserves the complete pre-edit manuscript folder.
SHA256: `eb7fca9762bdf6e39c62cd2c97f0445bb78d83242d6ae49c62fd85ac9e97d397`.
The fixed-design manifest and equal-capital results remain unchanged by this
campaign. The abandoned theory-first and beyond-stocks manuscripts and the ES
experiments have since been removed from the repository.
Source code and outputs are research artifacts, not personal investment advice.
