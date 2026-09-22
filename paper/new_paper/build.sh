#!/bin/sh
# Compile the paper and its internet appendix; cross-references need two rounds.
set -e
for round in 1 2; do
  for doc in main-styled internet-appendix; do
    pdflatex -interaction=nonstopmode -halt-on-error $doc.tex >/dev/null
    [ $round = 1 ] && biber $doc >/dev/null
  done
done
for doc in main-styled internet-appendix; do pdflatex -interaction=nonstopmode -halt-on-error $doc.tex >/dev/null; done
