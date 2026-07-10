# Parallel Sampling / 并行采样

## Core Rule

Never run multiple SWAT simulations in the same project folder. SWAT and SUFI2 write fixed output names such as `output.rch`, `SUFI2.OUT/*.txt`, logs, and temporary files. Shared-folder parallelism can silently mix outputs and produce false metrics.

## Worker-Copy Pattern

The safe pattern is:

1. Copy the full SWAT-CUP project to `worker_01`, `worker_02`, and so on.
2. Each worker restores its own editable files from `DirectBase/` or `Backup/`.
3. Each worker edits only its own `model.in` equivalent and SWAT input files.
4. Each worker runs `swat.exe` and `SUFI2_extract_rch.exe` in its own current working directory.
5. The controller merges rows after all workers finish.

## When To Refresh Workers

Use `--refresh-workers` when any of these changed:

- `observed_rch.txt`
- `par_inf.txt`
- `par_val.txt`
- `DirectBase/` or `Backup/`
- `swat.exe` or extraction executables
- Any SWAT input files

## 中文要点

不要多个进程共享同一个 SWAT-CUP 工程目录。安全并行必须为每个 worker 复制一份完整工程。工程、观测、参数范围或基准输入文件变化后，要加 `--refresh-workers`，否则 worker 可能继续使用旧文件。
