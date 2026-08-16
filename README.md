# SWAT-CUP Auto Calibrator

English | [简体中文](README_CN.md)

Process-aware, GUI-free SWAT-CUP/SUFI2 calibration for multi-station projects.

无需持续操作 SWAT-CUP 图形界面。工具可直接复现 `model.in`、在相互隔离的工程副本中采样、计算逐站 R2/NSE/KGE/PBIAS 与时序诊断指标，并准备可由原生 BAT 和 GUI 继续运行的工程。

## Version 1.1.0

This release expands the original runner into a complete calibration and delivery workflow:

- Multi-station process diagnostics: correlation, log-NSE, monthly climatology, lag, peak offset, peak capture, low-flow ratio, and false-zero detection.
- Saved per-run hydrographs and strict station-specific 95PPU ensemble construction.
- `fig.fig` topology audit for station dependencies, record inputs, `.wus` withdrawals, and local/upstream reservoirs.
- Conservative joint `.wus`/`.res` calibration. Monthly reservoir targets, outflow limits, and withdrawals keep their seasonal structure instead of being flattened to one annual value.
- Per-station weights and NSE/KGE acceptance thresholds for candidate selection.
- Failed-run accounting and retry limits so a requested sample count means successful simulations.
- Native GUI project checks, baked-input synchronization, and BAT smoke-test validation.

1.1.0 removes the old basin-specific `sediment` and `hhb_flow` score modes. Use equal or explicit variable weights with `kge`, or use `multisite_timeseries` for process-aware multi-station search.

## Safety Model

SWAT and SUFI2 write fixed file names. Never run concurrent simulations in one project directory. Each worker receives a full project copy and restores only the files touched by the active parameter set.

Keep the source project unchanged. Reproduce one known parameter set before sampling, derive station and reservoir scope from the current `fig.fig`, and replay the selected whole-model combination before delivery. Direct-only `.sol`, `.wus`, and `.res` edits should be baked into the root project, `Backup/`, and `DirectBase/` when the installed Swat_Edit cannot change them.

## Requirements

- Python 3.10 or newer.
- A Windows SWAT-CUP SUFI2 project containing `swat.exe`, `SUFI2_extract_rch.exe`, `SUFI2.IN/`, and `DirectBase/` or `Backup/`.
- NumPy and Pillow only for 95PPU charts.

```powershell
git clone https://github.com/justo888777/swatcup-auto-calibrator.git
cd swatcup-auto-calibrator
python -m pip install -e .

# Include 95PPU chart dependencies
python -m pip install -e ".[ppu]"
```

The package command is `swatcup-auto`. The same runner is embedded in the Codex Skill at `skills/swatcup-auto-calibrator/scripts/swatcup_auto_runner.py`.

## Quick Start

Audit topology and structural inputs:

```powershell
python skills/swatcup-auto-calibrator/scripts/audit_structure.py `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --out-dir ".\results\structure"
```

Reproduce a known parameter set:

```powershell
swatcup-auto single `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --model-in ".\best_model.in"
```

Run 200 successful samples in four isolated workers, allowing up to 240 attempts:

```powershell
swatcup-auto sample `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --runs 200 `
  --max-attempts 240 `
  --workers 4 `
  --refresh-workers `
  --center-model-in ".\best_model.in" `
  --scale 0.15 `
  --score-mode multisite_timeseries `
  --variable-weights "FLOW_OUT_17=2,FLOW_OUT_60=2" `
  --series-dir ".\results\series" `
  --out-csv ".\results\round1.csv"
```

Optional `--min-station-nse` and `--min-station-kge` thresholds require every observation block to pass before `*.best_model.in` is exported.

Build station-specific 95PPU diagnostics from complete successful runs:

```powershell
python skills/swatcup-auto-calibrator/scripts/build_95ppu.py `
  --observed "D:\Projects\HHB\Project.Sufi2.SwatCup\SUFI2.IN\observed_rch.txt" `
  --final-series-csv ".\results\series\run_42_series.csv" `
  --ensemble-dir ".\results\series" `
  --results-csv ".\results\round1.csv" `
  --expected-samples 200 `
  --out-dir ".\results\95ppu"
```

## Reservoir And WUS Scope

Report only reservoirs local to or upstream of selected observation stations:

```powershell
swatcup-auto reservoir-scope `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --stations "17,60"
```

Write conservative reservoir parameter rows when a separate range file is useful:

```powershell
swatcup-auto reservoir-scope `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --stations "17,60" `
  --out-par-inf ".\results\reservoir_par_inf.txt" `
  --runs 200
```

Monthly `STARG(month)`, `OFLOWMN(month)`, `OFLOWMX(month)`, and `WURESN(month)` ranges are centered on the current month. Existing minimum/maximum outflow ordering is preserved by the generated ranges. The command does not sample reservoir operating modes such as `IRESCO` by default.

`.wus` parameters use the same syntax, for example `v__WURCH(7).wus________17`. Verify project-specific WUS units and physical records before treating withdrawals as calibration variables.

## GUI Planning And Delivery

Generate a GUI `par_val.txt` plan with the exact accepted center in row 1:

```powershell
swatcup-auto plan `
  --project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --runs 1000 `
  --center-model-in ".\results\round1.best_model.in" `
  --scale 0.10 `
  --out-par-val ".\results\par_val_1000.txt"
```

Review and synchronize accepted direct-only files:

```powershell
python skills/swatcup-auto-calibrator/scripts/sync_baked_inputs.py `
  --project "D:\Projects\HHB\Delivery.Sufi2.SwatCup" `
  --model-in ".\results\round1.best_model.in" `
  --dry-run

python skills/swatcup-auto-calibrator/scripts/sync_baked_inputs.py `
  --project "D:\Projects\HHB\Delivery.Sufi2.SwatCup" `
  --model-in ".\results\round1.best_model.in"
```

Validate the formal project after its native Pre/Run/Post BAT smoke test:

```powershell
python skills/swatcup-auto-calibrator/scripts/native_gui_check.py `
  --project "D:\Projects\HHB\Delivery.Sufi2.SwatCup" `
  --source-project "D:\Projects\HHB\Project.Sufi2.SwatCup" `
  --expected-formal-runs 1000 `
  --smoke-out ".\results\smoke\SUFI2.OUT" `
  --smoke-runs 3 `
  --require-empty-out `
  --strict
```

## Codex Skill

The repository includes the installable Skill directory:

```text
skills/swatcup-auto-calibrator/
```

Its workflow requires source-project preservation, topology-derived calibration scope, process-aware diagnostics, whole-model replay, physical constraints for WUS/reservoir changes, and native GUI validation.

## License

MIT. SWAT and SWAT-CUP executables and licenses are not included.
