# Public replication of ACO and a multi-asset extension

This folder partially replicates Anarkulova, Cederburg and O'Doherty (ACO),
*Beyond the Status Quo* (revision of 10 July 2025), and then evaluates global
portfolios, gold and a managed-futures proxy in the same lifecycle model.

The complete mapping number → script → command → output → paper table is in
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md); the canonical rebuild order is
documented in [`build/rebuild_all.sh`](build/rebuild_all.sh).

The current manuscript is [`paper/new_paper/main-styled.pdf`](paper/new_paper/main-styled.pdf).
Its source and technical appendices are in [`paper/new_paper/`](paper/new_paper/).
It supersedes
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

The main panel contains 1,561 raw country-years, 16 countries and each of
the 99 years 1927–2025. The investability filter is an explicitly labelled
sensitivity, not the central case. The fixed-notional global-bond basket has
13 to 16 issuers over the analysis window.

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

The current 10,000-path outputs are versioned in `results/` and reported in
the manuscript. Under the 1927–2025 baseline, the equal-weight four-sleeve
rule at 175% exposure has 17.30% annual volatility, 2.61% retirement ruin and
7.02% equivalent saving after removing the Italy-1942 source event; ACO has
18.17%, 7.19% and 10.00%, respectively. The two further source-influence
diagnostics have the same ordering. At 100% exposure, the diversified rules
reduce volatility and ruin without portfolio-level borrowing, while utility
parity requires additional saving. These are post-audit diagnostics rather
than independent validation; the paper describes their scope and the return,
timing, and hedging limitations.

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
- `pip install -r requirements.txt` (numpy and pandas). `pandas` is only used
  in step 1 (reading `data/JSTdatasetR6.dta`); the reconstructed panels
  `data/replication-panel*.csv`, `data/international-equity.csv` and
  `data/managed-futures-annual-real.csv` are versioned, so the experiment and
  the sensitivities run without `pandas`.
- A LaTeX distribution with `biber` for the PDF.

This folder is self-contained: no script reads outside `Cederburg_lifecycle/`.
The external-validation scripts
([`paper/build_mf_benchmark_data.py`](paper/build_mf_benchmark_data.py) and
[`paper/build_mf_pack_matrix.py`](paper/build_mf_pack_matrix.py)) additionally
read SG, BarclayHedge, testfol and fund series that are not redistributed.
Without them, the canonical rebuild skips those diagnostics and the external
figure and tables remain versioned in the manuscript, but are not publicly
rebuildable. To regenerate
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
age-optimised policy or their proprietary TDF. World bonds cover 12 to 16
developed sovereigns, not the global investable universe. Their hedging relies
on covered interest parity and a fixed
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
