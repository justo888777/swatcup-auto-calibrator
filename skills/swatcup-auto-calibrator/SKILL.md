---
name: swatcup-auto-calibrator
description: Use when automating SWAT-CUP SUFI2 calibration without the GUI, reproducing a best run from model.in, generating par_val.txt sampling plans, running serial or worker-copy parallel SWAT simulations, narrowing par_inf.txt, or reporting R2 NSE KGE PBIAS metrics for flow or sediment stations.
license: MIT
---

# SWAT-CUP Auto Calibrator

## Overview

This skill helps Codex automate SWAT-CUP/SUFI2 calibration by treating the project folder as a file protocol instead of driving the GUI. Use the included Python runner for parameter editing, SWAT execution, SUFI2 output extraction, metric calculation, sampling, and next-round range narrowing.

## Workflow

1. Inspect the project structure before running anything:
   - Confirm `swat.exe`, `SUFI2_extract_rch.exe`, `SUFI2.IN/par_inf.txt`, `SUFI2.IN/par_val.txt`, and `SUFI2.IN/observed_rch.txt`.
   - Confirm `DirectBase/` exists. If not, use `Backup/` as the baseline.
   - Read `Absolute_SWAT_Values.txt` when parameter meanings or physical ranges are unclear.
2. For a known parameter set, run `single` with `--model-in`.
3. For optimization, run `sample` first with a small number of runs.
4. Use `--workers N` only when there is enough disk space for N full project copies.
5. For SWAT-CUP GUI 95PPU, use `plan` to generate `par_val.txt` and copy it into `SUFI2.IN/par_val.txt`.
6. Use `shrink` after a sample CSV to build a narrower `par_inf.txt` for the next iteration.
7. Report station-level R2, NSE, KGE, and PBIAS. For sediment work, keep sediment metrics separate from the combined score.

## Safety Rules

- Never run parallel simulations in the same SWAT-CUP project directory.
- In parallel mode, each worker must own a separate copied project folder.
- Do not modify the original project while worker copies are running.
- Use `--refresh-workers` after changing the source project, observed file, `par_inf.txt`, `par_val.txt`, or executable set.
- Prefer `DirectBase/` over `Backup/` because it represents the clean non-cumulative baseline for direct editing.
- Keep calibration and validation observed files in clearly named files or folders.

## Commands

Run from the repository root or install the package and use `swatcup-auto`.

```powershell
python -m swatcup_auto single --project "D:\path\Best_CUP.Sufi2.SwatCup" --model-in ".\best_model.in"
```

```powershell
python -m swatcup_auto sample --project "D:\path\Best_CUP.Sufi2.SwatCup" --runs 200 --score-mode sediment --out-csv ".\results\round1.csv"
```

```powershell
python -m swatcup_auto sample --project "D:\path\Best_CUP.Sufi2.SwatCup" --runs 2000 --workers 4 --refresh-workers --score-mode sediment --out-csv ".\results\round1_parallel.csv"
```

```powershell
python -m swatcup_auto plan --project "D:\path\Best_CUP.Sufi2.SwatCup" --runs 2000 --center-model-in ".\best_model.in" --scale 0.15 --out-par-val ".\par_val_2000.txt"
```

```powershell
python -m swatcup_auto shrink --par-inf ".\SUFI2.IN\par_inf.txt" --results-csv ".\results\round1.csv" --factor 0.20 --out-par-inf ".\par_inf_round2.txt"
```

## References

- `references/workflow.md`: bilingual user workflow and publishing notes.
- `references/parallel.md`: worker-copy parallel design and failure modes.
- `scripts/swatcup_auto_runner.py`: self-contained runner copy for skill-only installs.
