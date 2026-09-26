# Parallel sampling

## Isolation rule

SWAT and SUFI2 write fixed names such as `output.rch`, extracted observation-variable files, and logs. Shared-folder parallelism can silently combine files from different simulations. Every worker therefore owns a full project copy and its own current working directory.

## Safe worker lifecycle

1. Benchmark one complete simulation, including extraction and first-start overhead.
2. Choose a worker count from measured single-run cost, disk throughput, memory, CPU, and executable behavior. Record the chosen value for the current project; do not carry it across projects without remeasuring.
3. Refresh workers after changes to observations, executables, `fig.fig`, `DirectBase/`, `Backup/`, control files, or structural inputs.
4. Restore only files touched by the active parameters before each run. Full-folder restores create unnecessary disk contention.
5. Give each run a deterministic ID and seed. Save worker-local partial CSVs immediately after each result.
6. Merge only completed rows and retain failures with their messages. Rerun missing IDs in fresh worker copies.

Before starting or resuming a batch, inspect active SWAT, SUFI2, and orchestration processes together with worker-local records. Do not launch a second copy merely because the controlling terminal disappeared. A worker is complete only when its metrics and complete indexed series are present.

## Cold starts and slow first simulations

Reservoir record modes and native executables can make the first run much slower than later runs. Use a realistic timeout and watch for output progress. Do not kill a first run solely because it exceeds the warm-run time. Distinguish a slow cold start from a hung process by checking file updates and process activity.

`Swat_Edit.exe` may require an interactive console. Redirecting its standard streams can cause .NET or prompt failures. Use a terminal/PTY for the native Pre step and wait for its prompt before continuing.

## Restart strategy

Keep `direct_partial_results.csv` in every worker and the saved time series in a shared result directory using unique run IDs. Failed attempts carry `status` and `error`; replacement IDs continue until the requested successful count or `--max-attempts`. Never trust a summary CSV if the corresponding complete process series or output-length checks are missing.

For adaptive searches, finish and analyze the current batch before materializing later batches. The next matrix should reflect validated elites, station conflicts, sensitivity direction, clipping, and no-regression counts. Parallelism accelerates one evidence-defined batch; it does not replace feedback between batches.
