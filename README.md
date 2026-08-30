# Public replication of ACO and a multi-asset extension

This folder partially replicates Anarkulova, Cederburg and O'Doherty (ACO),
*Beyond the Status Quo* (revision of 10 July 2025), and then evaluates global
portfolios, gold and a managed-futures proxy in the same lifecycle model.

The complete mapping number → script → command → output → paper table is in
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md); the canonical rebuild order is
documented in [`build/rebuild_all.sh`](build/rebuild_all.sh).

The current manuscript is [`paper/main.pdf`](paper/main.pdf). It supersedes
the first version of the extension, which mixed U.S. real returns and local
returns. The old global numbers must no longer be used.

## Numeraire correction

One row of the panel is a household residing in a given country. Each
unhedged foreign asset is therefore:

1. reconstructed as a nominal return in its original currency;
2. converted into the currency of the country of residence;
3. deflated by that country's inflation.

The equity sleeve of each extension is now exactly ACO's: 33% domestic and
67% international in the resident's numeraire. Gold follows the spot exchange
rate. Bonds and managed futures are covered with carry: their excess return
over the bill or collateral actually embedded is added to the resident's
bill. Financing remains local and the base case subtracts a 0.10% friction on
the covered notionals.

The main panel contains the 1,557 raw country-years, 16 countries and each of
the 99 years 1927–2025. The investability filter drops 30 rows and is now an
explicitly labelled sensitivity, not the central case. A consistent control
uses only the 99 rows of the U.S. resident. The exclusion rule is the ex ante
filter of [`build/investability.py`](build/investability.py). The bond basket
has two issuers in 1946–1947, three in a few early observations and four in
the large majority of the panel.

The resident's numeraire is an assumption of the experiment, not a mere
display convention. The `--usd-numeraire` control keeps the same
country-year blocks but converts them all into real dollars and finances at
the U.S. bill. On the 1,534 convertible common observations of the full
panel, ACO 33/67 ruin falls from 7.05% (resident numeraire) to 3.04% (fixed
dollar); the MF and gold gains shrink from 3.95 to 2.79 points and from 2.79
to 1.17 points respectively. This counterfactual is not a literal U.S.
portfolio, because the so-called domestic sleeve remains the source country's
sleeve. It shows that the pooled results are conditional on the numeraire
choice. The paired outputs are
[`control_usd_common_n10000.json`](results/control_usd_common_n10000.json)
and
[`control_usd_numeraire_n10000.json`](results/control_usd_numeraire_n10000.json).
The first file also contains the constant-real-exchange-rate counterfactual:
ruin is 4.25% there, with 7.30% mean return and 15.72% volatility, against
7.46% and 17.39% in the resident case at observed exchange rates. These three
constructions are distinct diagnostics, not an additive attribution.

The multi-numeraire test confirms that the effect is not specific to fixing
one currency: on 1,428 common states, ACO ruin is 7.05% under the resident
numeraire, 2.20% in dollars, 7.17% under the German numeraire and 9.90% in
yen. Germany represents its own historical numeraire, not a reconstructed
euro. The paired results and intervals are in
[`control_numeraires_n20000.json`](results/control_numeraires_n20000.json).

## Corrected central results

10,000 paired paths, mean blocks of ten years, 0.30% spread, ACO's fixed
33/67 portfolio as the benchmark at a 10% saving rate:

| Strategy | Equivalent saving | Ruin |
| --- | ---: | ---: |
| Domestic equity | 16.75% | 14.95% |
| ACO 33/67 at constant real exchange rate | 9.05% | 4.57% |
| **ACO 33/67** | **10.00%** | **7.36%** |
| Domestic balanced | 18.53% | 13.81% |
| Balanced/I | 14.79% | 9.58% |
| 90/60 local | 9.91% | 8.52% |
| **90/60 covered world bonds** | **9.77%** | **7.81%** |
| 60/40 ACO/covered | 14.41% | 8.90% |
| 60/40 ACO + 33.33% managed futures | 8.70% | 3.29% |
| 60/40 ACO + 33.33% gold | 11.00% | 4.38% |
| 54/36/20/20 ACO | 9.76% | 3.19% |
| 90/60/25/25 ACO | 5.36% | 1.96% |

Two fixed-leverage ladders complete these recipes: a family proportional to
60/40/25/25 and an equal-weight family across equity / bonds / gold / MF,
each at 100%, 125%, 150%, 175% and 200% gross exposure. They target no
volatility. Within the ±1-point band around ACO's 17.43%, the 200% level of
the 60/40/25/25 family reaches 17.80% volatility, 5.32% equivalent saving and
1.83% ruin; the 200% equal-weight family reaches 17.02%, 6.40% and 2.51%. At
a comparable risk budget, both families therefore have both higher utility
and lower ruin than ACO's 33/67 (10.00% equivalent saving and 7.36% ruin).
This is the central result: in the extended asset universe and under the
model's explicit assumptions, diversification is more efficient than ACO's
100%-equity portfolio. The comparison is demanding: ACO's 33/67 is selected
by a grid search that maximises mean utility on their historical panel, while
the two families above are fixed rules, not fitted to moments or to simulated
utility. This is an in-sample selection advantage for ACO, not a claim that
the household anticipates future returns. Full tables are in the detailed
results.

Before 1968, the gold price is administered. An availability variant
reallocates the gold sleeve then in equal parts to the non-gold sleeves
already active, without changing leverage or financing. It improves the 60/40
with gold to 9.50% equivalent saving and 1.12% ruin, and the 54/36/20/20 to
8.94% and 0.55%. It is reported in the appendix and in the detailed results;
it is not a counterfactual gold-return assumption.

Equivalent saving equalises expected lifecycle utility with ACO 33/67 at a
10% saving rate; it does not equalise wealth at age 65.

The clean test keeps the 33/67 equity sleeve, the weights and local financing
unchanged. The covered bond basket cuts volatility from 17.44% to 16.83% and
ruin from 8.52% to 7.81%. Diversification therefore reduces risk; utility
remains almost identical to that of the 33/67.

For the 60/40 ACO + 33.33% MF portfolio, ruin is **3.29%** in the full panel,
**0.37%** for the consistent U.S. resident and **0.95%** in the investability
sensitivity. These three numbers replace the old U.S. real return copied to
all residents.

The multi-asset gains remain sensitive to assumptions: with a 2% managed
futures haircut, the moderate MF portfolio requires 10.46% saving. At a 1.40%
spread alone, it remains favourable at 9.62%; with the 2% haircut added, it
rises to 11.61%. Over 1927–1969, no multi-asset strategy evaluated dominates
the 33/67. Full tables are regenerated by the sensitivity scripts
(`build/central_cost_sensitivity.py`, `build/historical_uncertainty.py`) into
`paper/figures/`.

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

## Main scripts

| File | Role |
| --- | --- |
| [`build/international_equity.py`](build/international_equity.py) | Foreign and world equity by currency of residence |
| [`build/build_replication_panel.py`](build/build_replication_panel.py) | Local panel, inflation and exchange rates |
| [`build/panel_managed_futures.py`](build/panel_managed_futures.py) | Monthly managed-futures proxy → real annual series |
| [`build/panel_replication_tendance.py`](build/panel_replication_tendance.py) | Resident conversion of bonds, bills, gold and MF |
| [`build/compare_fixed_stacked_utility.py`](build/compare_fixed_stacked_utility.py) | Main experiment, sensitivities and paired CIs |
| [`build/experiment_fixed_numeraire.py`](build/experiment_fixed_numeraire.py) | Paired control under dollars, German marks and yen |
| [`build/income_process.py`](build/income_process.py) | GKOS incomes |
| [`build/social_security.py`](build/social_security.py) | SSA and SSI benefits |
| [`build/mortality.py`](build/mortality.py) | Mortality |

The older scripts `replicate_*`, `compare_equal_vol.py` and
`compare_lifecycle_utility.py` remain exploratory experiments. The current
manuscript rests on `compare_fixed_stacked_utility.py`, with no leverage
calibrated on observed volatility.

## Dependencies

- Python 3.10 or newer.
- `pip install -r requirements.txt` (numpy). `pandas` is only required for
  step 1 (reading `data/JSTdatasetR6.dta`); the reconstructed panels
  `data/replication-panel*.csv`, `data/international-equity.csv` and
  `data/managed-futures-annual-real.csv` are versioned, so the experiment and
  the sensitivities run without `pandas`.
- A LaTeX distribution with `biber` for the PDF.

This folder is self-contained: no script reads outside `Cederburg_lifecycle/`.
The only exception is the external validation of the managed-futures proxy
([`paper/build_mf_benchmark_data.py`](paper/build_mf_benchmark_data.py)), which
reads proprietary SG and BarclayHedge indexes that are not redistributed.
Without them, that script stops cleanly and the "proxy vs indexes" figure and
the correlation table remain those of
[`paper/main.pdf`](paper/main.pdf), not publicly rebuildable. To regenerate
them, place `official-index-returns-monthly.csv` and the `testfol/` folder
under `data/benchmarks-externes/`.

The provenance, licence and consuming script of every file in `data/` are in
[`data/SOURCES.md`](data/SOURCES.md). The primary sources (JST Macrohistory,
Global Macro Database, Big Bang Database, MeasuringWorth) are freely
accessible for non-commercial research and must be cited per their terms.

## Rebuild and execution

The full canonical order (data → main experiment → controls → sweeps →
sensitivities → figures → PDF) is in [`build/rebuild_all.sh`](build/rebuild_all.sh).
Each step is independent and can be rerun in isolation; the mapping number →
script → output → table is in [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

```bash
bash build/rebuild_all.sh
```

Compiling the paper alone:

```bash
cd paper
pdflatex -interaction=nonstopmode main.tex
biber main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

## Licence

Code, documentation and reconstructed data in this repository are released
under the Creative Commons Attribution 4.0 International licence
([`LICENSE`](LICENSE)). Third-party primary sources keep their own terms; see
[`data/SOURCES.md`](data/SOURCES.md) for the terms applicable to each file.
Proprietary index data (SG, BarclayHedge) and fund price files are not
redistributed.

## Limitations

The replication is annual and partial: it does not reproduce ACO's exactly
age-optimised policy or their proprietary TDF. World bonds cover only two to
four sovereigns. Their hedging relies on covered interest parity and a fixed
friction, with no historical basis data. The constant-real-exchange-rate
equity counterfactual is not an investable hedge. Gold includes an
administered-price regime. The managed-futures proxy uses incomplete
historical prices, omits some rolls and correlates only 0.49–0.53 with modern
CTA indexes. Finally, the weights are fixed and not estimated, but the family
of strategies was not pre-registered on an independent sample.

## AI assistance

An AI assistant was used to help with drafting and English wording, to
prototype some scripts and to write documentation. All method, modelling and
data decisions were made, reviewed and validated by the author, who checked
the results. Any remaining errors are the author's sole responsibility.
