# SWAT-CUP Auto Calibrator

GUI-free SWAT-CUP/SUFI2 calibration automation with safe parallel sampling.

无需打开 SWAT-CUP 图形界面，直接读写 SUFI2 工程文件、运行 `swat.exe` 和 `SUFI2_extract_rch.exe`，计算 R2、NSE、KGE、PBIAS，并支持安全并行采样。

## Why

SWAT-CUP is reliable, but high-volume calibration is slow when every test must be driven through the GUI. This project treats a SWAT-CUP SUFI2 folder as a file-based protocol:

1. Restore editable SWAT input files from `DirectBase/` or `Backup/`.
2. Apply parameter values from `model.in`, `par_inf.txt`, or generated samples.
3. Run `swat.exe`.
4. Run `SUFI2_extract_rch.exe`.
5. Compare `SUFI2.OUT/*.txt` with `SUFI2.IN/observed_rch.txt`.
6. Rank runs by KGE or a sediment-focused score.

这个工具的设计来自滇池案例中的成功复现：跳过 GUI，直接操作 SWAT-CUP 工程目录。并行时每个 worker 都复制一份完整工程，避免多个进程同时覆盖同一个 `model.in`、`SUFI2.OUT` 或 SWAT 输出文件。

## Features 功能

- Single-run reproduction from `model.in` or one row in `par_val.txt`.
- Serial or parallel parameter sampling.
- Worker-copy parallelism: each process owns an independent SWAT-CUP project copy.
- `par_val.txt` planning for users who still want to run 95PPU in SWAT-CUP.
- Automatic best-run export as `*.best_model.in`.
- Next-round `par_inf.txt` narrowing from a result CSV.
- Metrics: R2, NSE, KGE, PBIAS.
- Codex skill included under `skills/swatcup-auto-calibrator/`.

- 支持从 `model.in` 或 `par_val.txt` 单次复现。
- 支持串行或并行采样寻优。
- 并行采用“每个 worker 一份工程副本”，避免文件互相覆盖。
- 可生成 SWAT-CUP 软件可直接使用的 `par_val.txt`。
- 自动输出最佳参数 `*.best_model.in`。
- 可根据结果 CSV 缩小下一轮 `par_inf.txt`。
- 内置 R2、NSE、KGE、PBIAS 指标。
- 附带 Codex skill，可让代理按规范执行率定流程。

## Requirements 环境要求

- Windows is recommended because most SWAT-CUP projects contain Windows executables.
- Python 3.10 or newer.
- A SWAT-CUP SUFI2 project folder containing:
  - `swat.exe`
  - `SUFI2_extract_rch.exe`
  - `SUFI2.IN/par_inf.txt`
  - `SUFI2.IN/par_val.txt`
  - `SUFI2.IN/observed_rch.txt`
  - `DirectBase/` or `Backup/` with editable SWAT input files.

建议在 Windows 上运行，因为大多数 SWAT-CUP 工程包含 Windows 可执行文件。工程目录必须包含 `swat.exe`、`SUFI2_extract_rch.exe`、`SUFI2.IN` 参数和观测文件，以及 `DirectBase/` 或 `Backup/` 基准输入文件。

## Install 安装

```powershell
git clone https://github.com/<your-name>/swatcup-auto-calibrator.git
cd swatcup-auto-calibrator
python -m pip install -e .
```

Or run without installation:

```powershell
python -m swatcup_auto --help
```

## Quick Start 快速开始

Single run from a known parameter file:

```powershell
swatcup-auto single `
  --project "D:\Projects\Dianchi\SWAT_CUP\Best_CUP.Sufi2.SwatCup" `
  --model-in ".\best_model.in"
```

Run 200 samples serially:

```powershell
swatcup-auto sample `
  --project "D:\Projects\Dianchi\SWAT_CUP\Best_CUP.Sufi2.SwatCup" `
  --runs 200 `
  --score-mode sediment `
  --sediment-weight 3 `
  --out-csv ".\results\sediment_round1.csv"
```

Run 2000 samples in parallel with 4 independent worker copies:

```powershell
swatcup-auto sample `
  --project "D:\Projects\Dianchi\SWAT_CUP\Best_CUP.Sufi2.SwatCup" `
  --runs 2000 `
  --workers 4 `
  --refresh-workers `
  --score-mode sediment `
  --out-csv ".\results\sediment_round1_parallel.csv"
```

Generate a `par_val.txt` plan for SWAT-CUP 95PPU:

```powershell
swatcup-auto plan `
  --project "D:\Projects\Dianchi\SWAT_CUP\Best_CUP.Sufi2.SwatCup" `
  --runs 2000 `
  --center-model-in ".\results\sediment_round1_parallel.best_model.in" `
  --scale 0.15 `
  --out-par-val ".\results\par_val_2000.txt"
```

Narrow `par_inf.txt` for the next iteration:

```powershell
swatcup-auto shrink `
  --par-inf "D:\Projects\Dianchi\SWAT_CUP\Best_CUP.Sufi2.SwatCup\SUFI2.IN\par_inf.txt" `
  --results-csv ".\results\sediment_round1_parallel.csv" `
  --factor 0.20 `
  --out-par-inf ".\results\par_inf_round2.txt"
```

## Parallel Design 并行设计

Do not run multiple SWAT simulations in the same folder. SWAT and SUFI2 write fixed file names, so shared-folder parallelism will corrupt runs.

不要在同一个工程目录中同时跑多个 SWAT 进程。SWAT 和 SUFI2 会写固定文件名，共享目录并行很容易互相覆盖。

This tool uses worker-copy parallelism:

- Worker 1 runs in `*_workers/worker_01`.
- Worker 2 runs in `*_workers/worker_02`.
- Each worker restores from its own `DirectBase/` or `Backup/`.
- Results are merged after workers finish.

## Parameter Names 参数命名

The runner supports common SWAT-CUP SUFI2 parameter forms:

- `v__PARAM.ext...`: replace value.
- `r__PARAM.ext...`: relative change, `old * (1 + value)`.
- `a__PARAM.ext...`: additive change, `old + value`.

Supported SWAT input extensions include `.bsn`, `.hru`, `.mgt`, `.sol`, `.rte`, `.sub`, and `.gw`.

## Codex Skill

The repository includes a Codex skill:

```text
skills/swatcup-auto-calibrator/
```

Use it when a Codex agent needs to automate SWAT-CUP calibration, reproduce a best run, create a `par_val.txt` plan, run worker-copy parallel sampling, or summarize metrics.

## Notes 注意事项

- Keep a clean `DirectBase/` copy when possible. It prevents cumulative relative-parameter drift.
- Use `--refresh-workers` when the source project, `obs`, or parameter ranges changed.
- The tool does not replace SWAT-CUP licensing or executables. It only automates a local project you already have.
- For publication workflows, keep calibration and validation periods explicit in separate observed files or result folders.

- 建议保留干净的 `DirectBase/`，避免相对参数被重复叠加。
- 工程、观测文件或参数范围变化后，并行采样请加 `--refresh-workers`。
- 本工具不包含也不替代 SWAT-CUP 授权和可执行文件，只自动化你本地已有工程。
- 写论文时建议把率定期和验证期观测文件、结果目录明确分开。
