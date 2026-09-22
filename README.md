# Currency-consistent lifecycle investing: the ERC refocusing

The current manuscript is
[`paper/new_paper/main-styled.pdf`](paper/new_paper/main-styled.pdf), with
source and technical appendices in [`paper/new_paper/`](paper/new_paper/).
Its [replication guide](paper/new_paper/README.md) documents the execution and
document build, and
[`results/erc_refocusing/PROTOCOL.md`](results/erc_refocusing/PROTOCOL.md)
fixes the design of the main experiment before any performance was examined.

The paper partially replicates Anarkulova, Cederburg and O'Doherty (ACO),
*Beyond the Status Quo*, and evaluates global portfolios, gold and a
managed-futures proxy in the same lifecycle model. It then compares fixed
proportional and equal-weight four-sleeve ladders against an
equal-risk-contribution (ERC) portfolio whose covariance is retrospective. The
analysis is currency-consistent: every foreign asset is reconstructed as a
nominal return in its original currency, converted into the currency of the
country of residence, and deflated by that country's inflation. The resident's
numeraire is an assumption of the experiment, not a display convention.

The canonical rebuild order is documented and executable in
[`build/rebuild_all.sh`](build/rebuild_all.sh). Each step is independent and
can be rerun in isolation.

## Repository layout

| Path | Contents |
| --- | --- |
| `build/` | Simulation, diagnostic, rendering and verification scripts |
| `data/` | Versioned reconstructed panels and source metadata (`data/SOURCES.md`) |
| `results/` | Frozen JSON outputs; `results/erc_refocusing/` holds the main run |
| `paper/new_paper/` | Current manuscript, figures and build guide |
| `paper/figures/` | Shared generated LaTeX tables included by the appendices |
| `papers/` | Non-redistributed reference PDFs (ignored by git) |

## Main scripts

| File | Role |
| --- | --- |
| [`build/international_equity.py`](build/international_equity.py) | Foreign and world equity by currency of residence |
| [`build/build_replication_panel.py`](build/build_replication_panel.py) | Local panel, inflation and exchange rates |
| [`build/panel_managed_futures.py`](build/panel_managed_futures.py) | Monthly managed-futures proxy → real annual series |
| [`build/panel_replication_tendance.py`](build/panel_replication_tendance.py) | Resident conversion of bonds, bills, gold and MF |
| [`build/erc_refocusing.py`](build/erc_refocusing.py) | Main ERC experiment, ablations and sensitivity cases |
| [`build/composition_value.py`](build/composition_value.py) | Value of composition across the historical panel |
| [`build/compare_fixed_stacked_utility.py`](build/compare_fixed_stacked_utility.py) | Shared stacked-utility engine and baseline archive |
| [`build/source_exclusion_diagnostics.py`](build/source_exclusion_diagnostics.py) | Source-event exclusion panels |
| [`build/gamma_sensitivity.py`](build/gamma_sensitivity.py) | Joint preference calibration and fixed-bequest comparison |
| [`build/policy_sensitivity.py`](build/policy_sensitivity.py) | Household-policy grid |
| [`build/historical_panel_bootstrap.py`](build/historical_panel_bootstrap.py) | Nested calendar-history bootstrap |
| [`build/margin_call_experiment.py`](build/margin_call_experiment.py) | Annual maintenance-margin diagnostic |
| [`build/monthly_margin_diagnostic.py`](build/monthly_margin_diagnostic.py) | Monthly monitoring diagnostic |
| [`build/mf_variants.py`](build/mf_variants.py) | Managed-futures variants |
| [`build/mf_fund_correlations.py`](build/mf_fund_correlations.py) | External fund correlations (non-redistributed inputs) |
| [`build/render_erc_refocusing.py`](build/render_erc_refocusing.py) | ERC tables and ladder figure from the frozen run |
| [`build/render_composition_value.py`](build/render_composition_value.py) | Composition-value exhibits |
| [`build/render_restored_appendices.py`](build/render_restored_appendices.py) | Restored appendix tables |
| [`build/render_panel_margin_ablation.py`](build/render_panel_margin_ablation.py) | Monthly maintenance-margin table |
| [`build/verify_repository.py`](build/verify_repository.py) | Post-rebuild artefact verification |
| [`build/income_process.py`](build/income_process.py) | GKOS incomes |
| [`build/social_security.py`](build/social_security.py) | SSA and SSI benefits |
| [`build/mortality.py`](build/mortality.py) | Mortality |

## Lifecycle model

- couple aged 25, retirement at 65;
- two stochastic GKOS incomes, model 6;
- contribution if individual income exceeds $15,000;
- Social Security computed career by career and SSI floor;
- mortality by sex calibrated to ACO's SSA moments;
- fixed real withdrawal of 4% of wealth at 65;
- CRRA utility `gamma=3.84`, bequest `theta=2,360`, `k=490,000`;
- equivalent saving rate relative to the 33/67 at 10%.

ACO multiply `theta` by `12**gamma` in their monthly model. The annual
aggregation uses `theta=2,360`, which is exactly the normalisation obtained
by dividing the whole monthly utility by that factor under uniform
consumption.

## Dependencies

- Python 3.10 or newer.
- `pip install -r requirements.txt` (numpy and pandas). `pandas` is only used
  in step 1 (reading `data/JSTdatasetR6.dta`); the reconstructed panels
  `data/replication-panel*.csv`, `data/international-equity.csv` and
  `data/managed-futures-annual-real.csv` are versioned, so the experiment and
  the sensitivities run without `pandas`.
- A LaTeX distribution with `biber` for the PDF.

The reconstruction of the panels from primary sources needs the upstream
managed-futures engine under `../CTO_vs_PEA/`; when it is absent the versioned
panel is kept and the rest of the rebuild proceeds. The external-validation
scripts ([`paper/build_mf_benchmark_data.py`](paper/build_mf_benchmark_data.py)
and [`paper/build_mf_pack_matrix.py`](paper/build_mf_pack_matrix.py))
additionally read SG, BarclayHedge, testfol and fund series that are not
redistributed. Without them, the canonical rebuild skips those diagnostics and
the external figures and tables remain versioned in the manuscript, but are
not publicly rebuildable.

The provenance, licence and consuming script of every file in `data/` are in
[`data/SOURCES.md`](data/SOURCES.md). The primary sources (JST Macrohistory,
Global Macro Database, Big Bang Database, MeasuringWorth) are freely
accessible for non-commercial research and must be cited per their terms.

## Rebuild and execution

```bash
bash build/rebuild_all.sh
```

Compiling the paper alone:

```bash
cd paper/new_paper
pdflatex -interaction=nonstopmode main-styled.tex
biber main-styled
pdflatex -interaction=nonstopmode main-styled.tex
pdflatex -interaction=nonstopmode main-styled.tex
```

## Licence

Original code and documentation in this repository are released under the
Creative Commons Attribution 4.0 International licence ([`LICENSE`](LICENSE)).
Third-party inputs and reconstructed data derived from them retain the source
terms identified in [`data/SOURCES.md`](data/SOURCES.md); the repository-wide
licence does not override those terms.
Proprietary index data (SG, BarclayHedge) and fund price files are not
redistributed.

## Limitations

The replication is annual and partial: it does not reproduce ACO's exactly
age-optimised policy or their proprietary TDF. World bonds cover 13 to 16
developed sovereigns, not the global investable universe. Their hedging relies
on covered interest parity and a fixed friction, with no historical basis
data. The constant-real-exchange-rate equity counterfactual is not an
investable hedge. Gold includes an administered-price regime. The
managed-futures proxy uses incomplete historical prices, omits some rolls and
correlates only 0.49–0.53 with modern CTA indexes. ERC covariance and weights
are retrospective, with no expected-return forecast or outcome optimisation.
Finally, the weights are fixed and not estimated, but the family of strategies
was not pre-registered on an independent sample.

## AI assistance

An AI assistant was used to help with drafting and English wording, to
prototype some scripts and to write documentation. All method, modelling and
data decisions were made, reviewed and validated by the author, who checked
the results. Any remaining errors are the author's sole responsibility.
