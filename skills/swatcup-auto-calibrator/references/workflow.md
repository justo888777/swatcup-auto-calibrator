# End-to-end workflow

## 1. Establish a reproducible baseline

Work in a complete copy. Record the active executable set, observation file, simulation period, warm-up assumptions, active `par_inf.txt`, and accepted direct-only input changes. Confirm `DirectBase/` represents the intended non-cumulative baseline.

Identify the authoritative accepted state before replay. Some delivered projects already bake the best state into root and `DirectBase/`, while root `model.in` can be a stale native-smoke or last-sample row. First run the baked root and compare it with the documented metrics; replay `model.in` only after its provenance is confirmed. The metrics and time series must match the claimed baseline before optimization begins. A mismatch usually means stale worker copies, the wrong baseline, unsupported edit syntax, a different executable, or a changed structural input.

Clear generated files from `SUFI2.OUT/` before each extraction. Legacy SUFI2 extractors can append a second series to existing variable files instead of overwriting them; doubled lengths are an extraction-state error, not a hydrologic result.

## 2. Audit structure before expanding parameter ranges

Run `audit_structure.py` and manually verify its assumptions, especially WUS units. Use `fig.fig` to answer:

- Which observed stations share upstream area?
- Which stations are genuinely independent branches?
- Is a reservoir upstream of the extracted reach, or downstream of the gauge?
- Are `recmon`, `recday`, or constant records active, complete, correctly dated, and in the expected units?
- Are withdrawals and return flows plausible relative to observed mean and low flow?

If a simulated line slowly rises while observed flow has sharp released-flow peaks, inspect reservoir operations and extraction location before widening groundwater parameters. If baseflow collapses or zeros appear, inspect WUS and return flow before forcing aquifer parameters to compensate.

## 3. Size the experiment from the current task

Run a small canary using the exact planned baseline, ranges, executable, worker layout, and observation file. Size it from parameter dimension, runtime, and the amount of evidence needed to expose execution failures. Confirm every observation block has the expected period count and reasonable metrics.

Then run the task's requested number of successful simulations. If no count was requested, choose one from parameter dimension, runtime, convergence behavior, and the calibration stage, and state that choice explicitly. Derive `--max-attempts` from the canary failure rate plus a stated margin; never import either count from another basin. The command exits nonzero if it cannot reach `--runs` successful simulations. Enable `--series-dir`; summary metrics alone cannot reconstruct 95PPU or diagnose hydrograph shape.

When calibration direction remains uncertain, split the successful-run target into bounded adaptive batches. Analyze each batch before generating the next one. Carry forward validated whole-model elites, useful station-level hypotheses, targeted probes, and enough space-filling exploration to avoid local collapse. Do not pre-generate a long sequence of batches whose design cannot react to evidence.

If a GUI or direct run stops, recover only complete run IDs with the full variable set, correct indices, finite values, and parameter receipts. Inspect active processes first and never restart an already running batch. Count recovered successes toward the requested target and run only the remainder.

## 4. Select candidates without gaming the score

Resolve variable weights and thresholds from the current request or project configuration. Do not reuse weights from another calibration. If none are defined, state the neutral convention used by the run. Selection should be hierarchical:

1. Reject failed runs, wrong output lengths, and visibly invalid processes.
2. Enforce the explicit variable-level constraints for this task.
3. Compare the configured aggregate objective within the threshold-feasible set.
4. Break ties with the process-aware score and then worst-station KGE/NSE.
5. Inspect correlation, log-NSE, PBIAS, seasonal climatology, peak timing, top-decile peak capture, low-flow ratio, and simulated zero fraction before acceptance.

KGE is a hard constraint only when the current task says so. Otherwise keep it as a diagnostic and rank primarily by the requested metrics and process behavior. Apply auxiliary remote-sensing and reservoir criteria as explicit objectives or guardrails rather than blending everything into an opaque scalar.

`multisite_timeseries` is a search score, not an acceptance certificate. Set non-equal current-task weights with `--variable-weights NAME=WEIGHT,...`; omission means an explicitly chosen equal-weight objective. When thresholds are supplied, no feasible run means failure and no `best_model.in`; feasible candidates are ordered first by the configured score, then by weighted mean KGE and worst-variable diagnostics. Always inspect the per-variable metrics and charts.

## 5. Narrow ranges conservatively

Choose `--scale` and shrink `--factor` for the current parameter ranges and calibration stage; both are explicit inputs rather than inherited defaults. Narrow parameters only when repeated samples show a stable direction and the change has a physically credible effect. Avoid shrinking a weak station around a statistically convenient but structurally wrong solution. When the best value lies on a bound, decide whether the bound is physically artificial or the structure is forcing compensation.

For formal GUI sampling, keep all sensitive and GUI-supported parameters relevant to the full station set. A small direct search can use direct-only fields, but accepted values must be baked and removed from the GUI-active set if Swat_Edit cannot edit them reliably.

## 6. Replay and package

Any station-specific parameter mosaic must be replayed once as a complete model. Recheck downstream stations because upstream edits propagate. Save the final process series and rebuild metrics and 95PPU.

Before preferring a station mosaic, compare it with the best feasible whole-model row. A local gain that disappears or reverses in a combined replay is evidence of shared-parameter or routing conflict, not a value to copy into the baseline.

Use `plan` to create a `par_val.txt` with exactly the formal run count requested for the current task. Put the verified best parameter set in the first row when the intended workflow relies on it, while keeping later rows exploratory. Apply native-delivery checks in `native-gui-delivery.md`.

## 7. Calibration versus validation

Metrics over the entire observation period are calibration diagnostics, not independent validation. For publication-grade claims, use an explicit temporal split or a separate validation period and report both.
