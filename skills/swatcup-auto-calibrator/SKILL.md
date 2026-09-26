---
name: swatcup-auto-calibrator
description: Automate and diagnose SWAT-CUP SUFI2 multi-site flow, sediment, reservoir, and remote-sensing-constrained calibration, including adaptive batch searches, process-series and 95PPU evaluation, structural/extraction audits, range narrowing, interrupted-run recovery, and native GUI-ready validation. Use for SWAT or SWAT-CUP calibration, executable or input A/B tests, model.in replay, par_inf/par_val generation, dependency-aware tuning, and delivery of a BAT-runnable GUI project.
metadata:
  version: "1.4.0"
  short-description: "Adaptive multi-site SWAT-CUP calibration and native GUI delivery"
---

# SWAT-CUP Auto Calibrator

Use this skill to improve a SWAT-CUP project without sacrificing process timing, low-flow/event behavior, or native GUI compatibility. Treat the project as a file protocol: inspect structure and extraction, reproduce one known run, diagnose each observed variable, sample in isolated copies, replay the selected whole-model combination, then validate the formal GUI package.

## Non-negotiable rules

- Preserve the user's source project. Run experiments in a full copy.
- Never run two SWAT simulations in one project directory. Give every worker a separate full copy.
- Prefer `DirectBase/` as the direct-edit baseline, falling back to `Backup/` only when necessary.
- Reproduce one known authoritative `model.in` before sampling. If the replay differs, stop and resolve the baseline or executable mismatch.
- Do not assume a root `model.in` is the authoritative accepted state. A delivered project may already have the best inputs baked into root/`DirectBase/`, while `model.in` was left by a native smoke test or the last sampled row. First compare a direct root replay with the documented metrics, then replay `model.in` only after its provenance is confirmed; restore the accepted `model.in` after native smoke testing.
- After an executable, routing, structural-input, or extraction change, use deterministic A/B replays with identical parameters before calibration.
- Prove every observation variable's extraction, time index, length, and unit. File existence alone is not evidence of correct flow or sediment extraction.
- Clear generated files from `SUFI2.OUT/` before every direct or native extraction. Legacy extractors may append to existing variable files, producing duplicated time series that look like a model or observation mismatch.
- Confirm the observation time step. The bundled climatology, lag, peak-month, sparse-index, and plotting heuristics are monthly; for daily, annual, or irregular data, keep basic metrics only until the date/lag adapter is changed and verified for that time step.
- Evaluate process series as well as KGE/NSE. A higher scalar score does not justify wrong peak timing, flattened events, false zero flow, damaged baseflow, or missing sediment events.
- Treat KGE as a diagnostic unless the current request explicitly makes it a hard constraint. Resolve the actual priority among R²/correlation, NSE, log-NSE, PBIAS, low-flow behavior, event timing, and trend fit from the task.
- Derive station dependencies from the current project's `fig.fig`; never carry station IDs, branch groupings, or upstream/downstream chains from another basin. Tune the blocks discovered for this project and replay changes through every affected downstream block.
- Do not merge incompatible per-station optima. A parameter mosaic is accepted only after a single whole-model replay.
- Preserve known-correct point sources, withdrawals, reservoir releases, and record inputs. Structural inputs are not arbitrary calibration knobs.
- Do not edit meteorological forcings or their statistical generators as calibration parameters without explicit evidence of a forcing defect and user authorization. Prefer model input parameters with a defensible process link.
- Stabilize flow before ordinary sediment calibration. During sediment and joint phases, enforce explicit flow guardrails and report flow and sediment aggregates separately.
- Treat legacy control files and custom FIG records as format-sensitive protocols. Verify round-trip parsing and dose response; a successful process exit can still hide a shifted field or wrong coefficient meaning.
- Keep requested and actually applied parameter values traceable. The runner records per-run clipping and excludes clipped candidates from best-model selection unless the active executable/profile has been verified and `--allow-clipped-runs` is explicitly chosen.
- Keep direct-only edits such as selected `.sol`, `.wus`, and `.res` changes out of GUI `par_inf.txt` unless the installed Swat_Edit version is proven to support them. Bake accepted values into root, `Backup/`, and `DirectBase/`.
- Run the original project BAT files for final GUI validation. Keep `Echo/`, Windows CRLF control files, and an empty formal `SUFI2.OUT/`.
- Run legacy native editors through the project's normal `SUFI2_Run.bat` chain in an interactive terminal/PTY. Do not validate `Swat_Edit.exe` by capturing or redirecting its console streams, and do not mistake a direct editor launch with zero-valued edits for a valid GUI run.

## Workflow

1. Inspect `SUFI2.IN`, `fig.fig`, executables, BAT files, `Backup/`, `DirectBase/`, `Echo/`, observed block names/indices/lengths, extraction definitions, and current outputs.
2. Run `audit_structure.py`. Supply a WUS unit or custom transfer schema only after confirming it for this project. Verify routing closures, dependency blocks, facilities, and record inputs.
3. Replay the current best model once with `single`. Save per-variable metrics and process series. If the executable or structural set changed, run an A/B replay before sampling.
4. Choose flow-only, sediment-only-with-flow-guardrails, or joint-local mode from the current evidence. Read `flow-sediment-calibration.md` for mixed observations and `structure-and-extraction.md` when mappings, facilities, custom code, or extraction changed.
5. Run a small canary sized for the current run cost and parameter dimension. Continue in bounded adaptive batches: analyze each completed batch, update only evidence-supported directions, and avoid pre-generating a large fixed search when feedback can change the design. Use the canary success rate to set the attempt limit, then run exactly the successful-sample target requested for this task with `--series-dir` enabled. If the user supplied no target, choose and state one for this project; do not reuse a count from a prior basin.
6. Rank candidates hierarchically: valid process first; current task thresholds and class/variable weights second; flow guardrails third; the configured aggregate objective next; worst-variable, timing, log-NSE, bias, events, low flow, and zero behavior as tie breakers. Treat `multisite_timeseries` as a search heuristic and inspect the CSV and charts.
7. Build 95PPU diagnostics from the raw saved ensemble. Low P-factor with observed events outside a reasonably wide band suggests missing/incorrect structure or inputs, not merely a range that should be narrowed.
8. Narrow only parameters with demonstrated signal and plausible process effects. Keep wider ranges for weakly identified variables; fix structural data before squeezing parameters around a false optimum.
9. Replay the selected whole-model parameter set once, update the clean direct baseline, generate the next GUI `par_val.txt`, and report flow, sediment, global, and worst-variable outcomes separately.
10. Bake accepted direct-only inputs with `sync_baked_inputs.py`. Validate the formal package with `native_gui_check.py`, then run a multi-row native Pre/Run/Post BAT smoke test using the task's configured smoke count. Explicitly verify that the first and last active parameters receive the intended nonzero values, the editor reports real file edits, and the best baseline is restored afterward.

## Primary commands

Run from this skill directory. Define the PowerShell variables from the current project and request before using these templates; none of the counts, thresholds, topology, or paths are skill defaults.

```powershell
python scripts/audit_structure.py --project $project --out-dir $auditDir
```

Add `--wus-unit-m3-per-day $confirmedWusUnit` only when the WUS unit is confirmed. Add `--transfer-schema reach-reservoir-1-2` only when that custom FIG convention is confirmed for the active executable.

```powershell
python scripts/swatcup_auto_runner.py single --project $project --model-in $bestModel
```

```powershell
python scripts/swatcup_auto_runner.py sample --project $project --runs $successfulRuns --max-attempts $attemptLimit --workers $workerCount --refresh-workers --scale $sampleScale --score-mode $scoreMode --min-station-nse $nseFloor --series-dir $seriesDir --out-csv $resultsCsv
```

Choose `$scoreMode` for the current phase: `multisite_timeseries` is a transparent monthly-flow search heuristic, while `kge` is time-step-independent but still requires process checks. When the current task defines non-equal observation-block weights, add `--variable-weights $variableWeights` using `NAME=WEIGHT` pairs. For a mixed flow–sediment objective, use `--class-weights FLOW=$flowWeight,SEDIMENT=$sedimentWeight` to set total class weights; any variable weights remain relative within each class. Add `--class-floors $classFloors` for explicit guards such as accepted flow KGE/NSE floors. Omit these only when an unqualified equal-variable objective was explicitly chosen.

```powershell
python scripts/build_95ppu.py --observed $observedRch --final-series-csv $bestSeries --ensemble-dir $seriesDir --results-csv $resultsCsv --expected-samples $successfulRuns --out-dir $ppuDir
```

```powershell
python scripts/swatcup_auto_runner.py shrink --par-inf $parInf --results-csv $resultsCsv --factor $shrinkFactor --out-par-inf $nextParInf
```

```powershell
python scripts/swatcup_auto_runner.py plan --project $project --runs $formalRuns --center-model-in $bestModel --scale $planScale --out-par-val $formalParVal
```

```powershell
python scripts/native_gui_check.py --project $deliveryProject --source-project $sourceProject --expected-formal-runs $formalRuns --smoke-out $smokeOut --smoke-runs $smokeRuns --best-series-csv $bestSeries --native-edit-log $nativeEditLog --require-native-first-change --require-empty-out --strict --json-out $nativeCheckJson
```

## References

- `references/workflow.md`: end-to-end calibration, selection, and stopping logic.
- `references/adaptive-multiconstraint-calibration.md`: feedback-driven batches, partial-result recovery, single-station elites, process-first ranking, remote-sensing and reservoir guardrails, and stopping rules.
- `references/multisite-timeseries.md`: dependency blocks, process diagnostics, 95PPU, and structural causes.
- `references/flow-sediment-calibration.md`: staged flow–sediment calibration, class-balanced objectives, parameter attribution, and joint guardrails.
- `references/structure-and-extraction.md`: executable/input A/B tests, observation extraction, WUS/reservoir/transfer diagnostics, and fixed-format controls.
- `references/native-gui-delivery.md`: baked inputs and native BAT delivery requirements.
- `references/parallel.md`: worker-copy sampling, cold starts, retries, and resource sizing.
