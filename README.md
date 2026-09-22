# Beyond all-equity: levered diversification over the lifecycle

Replication code, data and results for the paper
[`paper/new_paper/main-styled.pdf`](paper/new_paper/main-styled.pdf) and its
[internet appendix](paper/new_paper/internet-appendix.pdf).

The paper asks whether the case for all-equity lifecycle portfolios of
Anarkulova, Cederburg and O'Doherty (ACO, 2025) survives when households can
borrow and invest in global bonds, gold and managed futures. In ACO's
lifecycle model, a multi-asset strategy levered to the volatility of unlevered
equities matches the all-equity utility with a 6.35% savings rate instead of
10%, lowers the probability of ruin from 7.0% to 2.3%, and funds the
all-equity retirement income more reliably. Managed futures drive the gains; a
strategy of stocks and managed futures alone does better still.

Three strategies are compared with the ACO all-equity benchmark (33% domestic,
67% international stocks): a proportional mix, risk parity, and stocks plus
managed futures, each levered to the volatility of unlevered equities. Results
are reported on three separate measures: the utility-equivalent savings rate,
the probability of ruin, and the failure to fund the all-equity income along
the same path. The design of the main experiment is fixed in
[`results/main/PROTOCOL.md`](results/main/PROTOCOL.md).

Returns are currency-consistent: every foreign asset is converted into the
currency of the country of residence and deflated by that country's inflation.

## Repository layout

| Path | Contents |
| --- | --- |
| `build/` | Simulation, rendering and verification scripts |
| `build/managed_futures/` | Managed-futures engine (monthly trend-following proxy) |
| `data/` | Source data and reconstructed panels ([`data/SOURCES.md`](data/SOURCES.md)) |
| `data/mf-inputs/` | Monthly futures-equivalent returns read by the managed-futures engine |
| `results/main/` | Main run (`n10000_final/`, 10,000 lifecycles per strategy), its protocol and checks |
| `results/equal_volatility/` | Equal-volatility exposures, sensitivity cases (`sensitivity/`), resampled histories (`histories/`), MF variants |
| `results/robustness/` | Resampled histories at 175%, Italy 1942 exclusion panel, bill-rate quintiles |
| `results/audit/` | Deflator, bond-fee and futures-consistent MF checks (not in the paper) |
| `results/historical_availability/` | Gold and MF markets added as they opened |
| `results/` (files) | ACO replication, exposure ladders, composition value, preferences, margin tests |
| `paper/new_paper/` | Manuscript, internet appendix, exhibits and [build guide](paper/new_paper/README.md) |
| `paper/figures/` | Shared tables included by the internet appendix |

## Main scripts

| File | Role |
| --- | --- |
| [`build/managed_futures/run_managed_futures.py`](build/managed_futures/run_managed_futures.py) | Monthly managed-futures proxy from `data/mf-inputs/` |
| [`build/international_equity.py`](build/international_equity.py) | Foreign and world equity by currency of residence |
| [`build/build_replication_panel.py`](build/build_replication_panel.py) | Local panel, inflation and exchange rates |
| [`build/panel_managed_futures.py`](build/panel_managed_futures.py) | Monthly managed futures → real annual series |
| [`build/panel_replication_tendance.py`](build/panel_replication_tendance.py) | Resident conversion of bonds, bills, gold and managed futures |
| [`build/erc_refocusing.py`](build/erc_refocusing.py) | Main experiment, ablations and sensitivity cases |
| [`build/revision_checks.py`](build/revision_checks.py) | Equal-volatility exposures, bond-free strategies, sleeve Sharpe ratios |
| [`build/eqvol_sensitivity.py`](build/eqvol_sensitivity.py) | Sensitivity cases at equal volatility |
| [`build/historical_panel_bootstrap_eqvol.py`](build/historical_panel_bootstrap_eqvol.py) | Resampled calendar histories at equal volatility |
| [`build/mf_variant_lifecycle.py`](build/mf_variant_lifecycle.py) | Managed-futures signal and fee variants |
| [`build/composition_value.py`](build/composition_value.py) | Contribution of each asset class |
| [`build/compare_fixed_stacked_utility.py`](build/compare_fixed_stacked_utility.py) | Replication of ACO (`--portfolio-set core`) and exposure ladders |
| [`build/historical_availability.py`](build/historical_availability.py) | Gold and managed-futures markets added as they opened |
| [`build/bill_quintiles.py`](build/bill_quintiles.py) | Returns of leverage by real-bill quintile |
| [`build/gamma_sensitivity.py`](build/gamma_sensitivity.py), [`build/policy_sensitivity.py`](build/policy_sensitivity.py) | Risk aversion, saving and withdrawal policies |
| [`build/margin_call_experiment.py`](build/margin_call_experiment.py), [`build/monthly_margin_diagnostic.py`](build/monthly_margin_diagnostic.py) | Annual and monthly margin tests |
| [`build/deflator_fee_check.py`](build/deflator_fee_check.py), [`build/mf_excess_return_check.py`](build/mf_excess_return_check.py) | Audit checks on deflators, bond fees and futures-consistent returns |
| `build/render_*.py` | Tables and figures of the paper |
| [`build/verify_repository.py`](build/verify_repository.py) | Consistency checks after a rebuild |
| [`build/income_process.py`](build/income_process.py), [`build/social_security.py`](build/social_security.py), [`build/mortality.py`](build/mortality.py) | Incomes, Social Security and mortality |

## Lifecycle model

- couple aged 25, retirement at 65;
- two stochastic GKOS incomes, model 6;
- contribution if individual income exceeds $15,000;
- Social Security computed career by career, SSI floor;
- mortality by sex calibrated to ACO's SSA moments;
- fixed real withdrawal of 4% of wealth at 65;
- CRRA utility `gamma=3.84`, bequest `theta=2,360`, `k=490,000`;
- stationary block bootstrap over 16 developed countries, 1927–2025 (mean block of 10 years);
- borrowing at the local bill rate plus 0.30%.

ACO multiply `theta` by `12**gamma` in their monthly model. The annual
aggregation uses `theta=2,360`, which is exactly the normalisation obtained
by dividing the whole monthly utility by that factor under uniform
consumption.

## Rebuild

```bash
pip install -r requirements.txt   # numpy and pandas, Python 3.10+
bash build/rebuild_all.sh         # full rebuild, several hours
python3 build/verify_repository.py
cd paper/new_paper && bash build.sh   # paper and internet appendix (LaTeX with biber)
```

Each step of `rebuild_all.sh` can be rerun on its own. The comparison with
commercial trend-following indexes and funds reads SG, BarclayHedge, testfol
and fund series that are not redistributed; without them, those figures stay
as versioned in the manuscript and the rest of the rebuild proceeds.

## Licence

Original code and documentation are released under the Creative Commons
Attribution 4.0 International licence ([`LICENSE`](LICENSE)). Third-party
inputs keep the terms given in [`data/SOURCES.md`](data/SOURCES.md) and must
be cited.

## AI assistance

OpenAI Codex and Anthropic Claude Code were used for code development,
reproducibility checks and manuscript editing. The author is responsible for
the research design, interpretations, code and final manuscript.
