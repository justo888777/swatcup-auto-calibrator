---
name: swatcup-auto-calibrator
description: Automate and diagnose SWAT-CUP SUFI2 multi-site calibration, including direct small-sample searches, process-line and 95PPU evaluation, fig.fig-based WUS/reservoir co-calibration with physical constraints, parameter-range narrowing, and native GUI-ready project validation. Use for SWAT or SWAT-CUP flow calibration, model.in replay, par_inf/par_val generation, independent-branch or upstream/downstream station tuning, and delivery of a BAT-runnable GUI project.
---

# SWAT-CUP Auto Calibrator

Use this skill to improve a SWAT-CUP project without sacrificing hydrograph timing or native GUI compatibility. Treat the project as a file protocol: inspect structure, reproduce one known run, diagnose each station, sample in isolated copies, replay the selected whole-model combination, then validate the formal GUI package.

## Non-negotiable rules

- Preserve the user's source project. Run experiments in a full copy.
- Never run two SWAT simulations in one project directory. Give every worker a separate full copy.
- Prefer `DirectBase/` as the direct-edit baseline, falling back to `Backup/` only when necessary.
- Reproduce one known `model.in` before sampling. If the replay differs, stop and resolve the baseline or executable mismatch.
- Evaluate the hydrograph as well as KGE/NSE. A higher scalar score does not justify wrong peak timing, flattened floods, false zero flow, or damaged baseflow.
- Derive station dependencies from the current project's `fig.fig`; never carry station IDs, branch groupings, or upstream/downstream chains from another basin. Tune the blocks discovered for this project and replay changes through every affected downstream block.
- Do not merge incompatible per-station optima. A parameter mosaic is accepted only after a single whole-model replay.
- Preserve known-correct point sources, withdrawals, reservoir releases, and record inputs. Structural inputs are not arbitrary calibration knobs.
- Keep direct-only edits such as selected `.sol`, `.wus`, and `.res` changes out of GUI `par_inf.txt` unless the installed Swat_Edit version is proven to support them. Bake accepted values into root, `Backup/`, and `DirectBase/`.
- Run the original project BAT files for final GUI validation. Keep `Echo/`, Windows CRLF control files, and an empty formal `SUFI2.OUT/`.

## Workflow

1. Inspect `SUFI2.IN`, `fig.fig`, executables, BAT files, `Backup/`, `DirectBase/`, `Echo/`, observed block lengths, and current outputs.
2. Run `audit_structure.py`. Verify gauge routing, dependency blocks, WUS magnitude/units, upstream reservoirs, downstream-of-gauge facilities, and `recmon`/`recday`/`reccnst` inputs.
3. Replay the current best model once with `single`. Save station metrics and process lines.
4. Run a small canary sized for the current run cost and parameter dimension. Use its success rate to set the attempt limit, then run exactly the successful-sample target requested for this task with `--series-dir` enabled. If the user supplied no target, choose and state one for this project; do not reuse a count from a prior basin.
5. Rank candidates hierarchically: valid process first; current task thresholds and variable weights second; the configured aggregate objective third; timing, log-NSE, bias, peaks, low flow, and zero-flow behavior next. Use `multisite_timeseries` for process-aware search guidance, but still inspect the CSV and charts.
6. Build 95PPU diagnostics from the raw saved ensemble. Low P-factor with observed peaks outside a reasonably wide band suggests missing/incorrect structure or inputs, not merely a range that should be narrowed.
7. Narrow only parameters with demonstrated signal and plausible process effects. Keep wider ranges for weakly identified stations; fix structural data before squeezing parameters around a false optimum.
8. Replay the selected whole-model parameter set once, update the clean direct baseline, and generate the next GUI `par_val.txt`.
9. Bake accepted direct-only inputs with `sync_baked_inputs.py`. Validate the formal package with `native_gui_check.py`, then run a multi-row native Pre/Run/Post BAT smoke test using the task's configured smoke count.

## Primary commands

Run from this skill directory. Define the PowerShell variables from the current project and request before using these templates; none of the counts, thresholds, topology, or paths are skill defaults.

```powershell
python scripts/audit_structure.py --project $project --out-dir $auditDir
```

```powershell
python scripts/swatcup_auto_runner.py single --project $project --model-in $bestModel
```

```powershell
python scripts/swatcup_auto_runner.py reservoir-scope --project $project --stations $stationIds
```

Only add the reported local/upstream reservoirs to joint sampling. When writing a reservoir-only range file, add `--out-par-inf $reservoirParInf --runs $successfulRuns`; monthly `STARG`, `OFLOWMN`, `OFLOWMX`, and `WURESN` rows retain the current seasonal pattern and use bounded ranges.

```powershell
python scripts/swatcup_auto_runner.py sample --project $project --runs $successfulRuns --max-attempts $attemptLimit --workers $workerCount --refresh-workers --scale $sampleScale --score-mode multisite_timeseries --min-station-nse $nseFloor --series-dir $seriesDir --out-csv $resultsCsv
```

When the current task defines non-equal observation-block weights, add `--variable-weights $variableWeights` using `NAME=WEIGHT` pairs. Omit it for an explicitly chosen equal-weight objective.

```powershell
python scripts/build_95ppu.py --observed $observedRch --final-series-csv $bestSeries --ensemble-dir $seriesDir --results-csv $resultsCsv --expected-samples $successfulRuns --out-dir $ppuDir
```

`build_95ppu.py` requires NumPy and Pillow. Install the repository with `python -m pip install -e ".[ppu]"` when they are not already available.

```powershell
python scripts/swatcup_auto_runner.py shrink --par-inf $parInf --results-csv $resultsCsv --factor $shrinkFactor --out-par-inf $nextParInf
```

```powershell
python scripts/swatcup_auto_runner.py plan --project $project --runs $formalRuns --center-model-in $bestModel --scale $planScale --out-par-val $formalParVal
```

```powershell
python scripts/sync_baked_inputs.py --project $deliveryProject --model-in $bestModel --dry-run
python scripts/sync_baked_inputs.py --project $deliveryProject --model-in $bestModel
```

Review the dry-run scope before synchronizing accepted direct-only `.sol`, `.wus`, and `.res` inputs into `Backup/` and `DirectBase/`.

```powershell
python scripts/native_gui_check.py --project $deliveryProject --source-project $sourceProject --expected-formal-runs $formalRuns --smoke-out $smokeOut --smoke-runs $smokeRuns --best-series-csv $bestSeries --require-empty-out --strict --json-out $nativeCheckJson
```

## References

- `references/workflow.md`: end-to-end calibration, selection, and stopping logic.
- `references/multisite-timeseries.md`: dependency blocks, process diagnostics, 95PPU, and structural causes.
- `references/native-gui-delivery.md`: baked inputs and native BAT delivery requirements.
- `references/parallel.md`: worker-copy sampling, cold starts, retries, and resource sizing.
