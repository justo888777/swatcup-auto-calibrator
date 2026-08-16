# Multi-site process and 95PPU diagnosis

## Dependency-aware station blocks

Use `fig.fig` routing closures, not geographic intuition alone. Two gauges on separate branches can be calibrated concurrently. If one gauge is upstream of another, their parameters form a chain block because the downstream hydrograph contains the upstream response. Stations with overlapping upstream source areas also belong to the same review block.

Do not paste together every station's independent best row. Instead, identify parameters whose selectors affect one branch, assemble a candidate by dependency block, and run one complete-model replay. Accept the mosaic only when every affected downstream station remains valid.

## Required station diagnostics

For monthly flow, retain at least:

- KGE, NSE, correlation or R², and PBIAS;
- log1p-NSE for baseflow and proportional error;
- monthly-climatology correlation;
- best lag over a small window and annual peak-month offset;
- simulated flow during observed top-decile months;
- simulated/observed low-flow ratio during observed bottom-decile months;
- simulated zero-flow fraction.

A candidate with a slightly higher KGE but worse lag, lost peaks, or new dry months is not automatically better.

## Interpreting 95PPU

Build 2.5%, 50%, and 97.5% series from the raw small-sample ensemble for each station. P-factor is the fraction of observations inside 95PPU. R-factor is mean band width divided by observed standard deviation.

Pass the result CSV and expected successful sample count to `build_95ppu.py`. The tool must reject duplicate IDs, incomplete station rows, wrong lengths, stale/missing successful IDs, or the wrong ensemble count; otherwise different stations can silently be summarized from different runs.

- Low P-factor and narrow R-factor: ranges may be too narrow or influential parameters are missing.
- Low P-factor despite a broad band: likely structural/input/timing error.
- Observed peaks consistently above 95PPU: inspect rainfall forcing, reservoir release records, diversion/return flow, routing, and gauge mapping.
- Good KGE/NSE but poor line alignment: selection is exploiting mean/variance compensation; add process checks and revisit structure.

95PPU from a deliberately local small sample describes that local search, not total predictive uncertainty.

## Structural symptom map

| Symptom | Check before ordinary parameter tuning |
| --- | --- |
| Smooth seasonal rise instead of sharp peaks | reservoir operation mode, release series coverage/units, recmon mapping, routing lag |
| Frequent zeros or collapsed baseflow | WUS amount and units, return flow, groundwater withdrawal, extraction reach location |
| Correct timing but persistent volume bias | precipitation/area scaling, point sources, diversions, reservoir water balance |
| Upstream fit improves while downstream degrades | shared selectors, station dependency chain, downstream reservoirs/withdrawals |
| Metrics plausible but line is shifted | observation dates, warm-up alignment, monthly aggregation, gauge-to-reach mapping |

When a facility controls the hydrograph, request the real operation or release data. Preserve corrected point-source and reservoir inputs instead of re-tuning them as free statistical offsets.
