# Manuscript sources

The manuscript is [`new_paper/main-styled.pdf`](new_paper/main-styled.pdf),
with its [internet appendix](new_paper/internet-appendix.pdf). Sources
(`main-styled.tex`, `internet-appendix.tex`, `appendices-refocused.tex`,
`preamble.tex`, `references.bib`, `references-erc.bib`) and exhibits live under
[`new_paper/`](new_paper/); `new_paper/build.sh` compiles both documents. The
build guide is [`new_paper/README.md`](new_paper/README.md).

[`figures/`](figures/) holds shared tables included by the internet appendix.
They are produced by `build_appendix_data.py`, `build_mf_benchmark_data.py` and
`build_mf_pack_matrix.py` in this folder and by the `render_*` scripts
described in [`../build/README.md`](../build/README.md).
