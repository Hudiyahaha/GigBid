# ADR 0001: Build our own GigSim and persona corpus
**Context:** the starter kit contained no simulator, personas or dev set. **Decision:** a GigSim-compatible simulator
(`gigsim/`) plus deterministic synthetic personas, calibrated with real Kaggle market data. **Consequence:** fully
reproducible evaluation; absolute numbers are optimistic because labels and text come from one generator, so
comparisons between designs are what we report.
