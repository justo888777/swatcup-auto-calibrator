# Adaptive multi-constraint calibration

Read this reference when a calibration must improve several stations or data products without sacrificing an accepted baseline, when a long GUI run stopped partway, or when the user wants large-sample exploration informed by intermediate results.

## Recover evidence before rerunning

An interrupted ensemble is still useful if completed runs can be identified unambiguously. Before launching replacements:

1. inspect active SWAT, SUFI2, and orchestration processes and do not start a duplicate batch;
2. identify complete run IDs from result rows and complete extracted series, not from a nominal counter or file count alone;
3. reject partial runs with missing variables, wrong time indices, truncated files, non-finite values, or absent edit receipts;
4. merge worker archives by deterministic run ID and detect duplicates before counting successes;
5. preserve the recovered sample as a separate immutable analysis input, then allocate only the remaining successful-run target.

Do not infer completion from a process exit or a partially written summary. A valid run needs the full observation-variable set, expected indices, and a parameter receipt.

## Use feedback-driven batches

Prefer a sequence of bounded batches over one blind large matrix when calibration direction is uncertain. A practical loop is:

1. include the accepted baseline, whole-model elites, selected station elites, targeted one-at-a-time probes, and exploratory space-filling rows;
2. execute the batch in isolated worker copies;
3. analyze validity, constraint pass counts, process metrics, station-level gains, parameter effects, and bound hits;
4. replay promising candidates with the complete objective, including constraints that were omitted from the fast search;
5. generate the next batch from validated directions and retain deliberate exploration to avoid premature collapse.

The batch size is a runtime and information decision, not a fixed skill default. Stop expanding a direction when repeated batches show no feasible improvement, only trade one failure among stations, or reveal a structural limit.

## Rank hierarchically, not by one scalar

Use the task's acceptance thresholds. A robust default ordering is:

1. successful execution, correct extraction, and physically valid series;
2. hard constraints such as required station pass counts, PBIAS bounds, reservoir behavior, or no-regression conditions;
3. process validity: timing, low-flow/baseflow, event capture, zero behavior, and trend shape;
4. primary metrics named by the user, commonly R²/correlation, NSE, and log-NSE;
5. aggregate score and worst-variable performance;
6. secondary diagnostics such as KGE when it is not a requested hard constraint.

Report class means and counts separately. An improvement in a mean can hide one degraded upstream station, and a pass count can hide severe deterioration inside the passing range.

## Treat station elites as hypotheses

Keep per-station best rows because they reveal attainable responses and useful parameter directions. Do not assemble a final model by copying each station's best values independently.

For every proposed mosaic:

- map each parameter selector to its routing closure, land use, soil, reach, or facility scope;
- resolve conflicts on shared upstream areas and shared global parameters;
- keep upstream improvements before tuning their downstream receivers;
- replay the combined parameter set once through the entire model;
- accept it only if all required downstream, reservoir, sediment, and auxiliary constraints still pass.

If the combined replay fails while isolated station elites look strong, report the conflict as dependency evidence rather than hiding it with a synthetic score.

## Diagnose process residuals

Use a symptom-to-process hypothesis before opening ranges:

- poor dry-season flow or exaggerated recession: test groundwater threshold, recession, delay, recharge partition, channel loss, and known withdrawals;
- good peak correlation but wrong event magnitude: test runoff partition, routing attenuation, reservoir operation, and basin water balance;
- good ordinary NSE but poor log-NSE: target low-flow/baseflow processes and check zero or detection-limit handling;
- correct sediment timing but wrong magnitude: test hillslope supply, land-use-specific protection, lateral delivery, channel cover/erodibility, transport capacity, and reservoir trapping;
- sediment events missing or displaced: audit carrier flow, extraction, equation choice, routing, and observations before magnitude parameters;
- one persistently poor branch: compare precipitation/forcing representativeness and upstream structural inputs before expanding unrelated global parameters.

Uncommon parameters are valid probes only when their file location, selector, edit syntax, units, and process direction are verified for the active SWAT build.

## Add remote-sensing constraints without changing their meaning

Remote-sensing products usually have different spatial supports and should be evaluated separately before aggregation. Align dates, aggregation, masks, and units for each product. Report raw-series correlation and anomaly correlation separately:

- raw correlation includes seasonal cycle and long-term level;
- anomaly correlation measures departures after removing the chosen climatology or baseline.

For evapotranspiration and soil moisture, use the model state or flux that matches the product depth and temporal support. For terrestrial water storage anomaly, construct the documented total storage consistently from the model components that are actually printed, typically soil water, groundwater, snow, and surface-water or reservoir storage. Do not tune an arbitrary initial offset to manufacture correlation; correlation is insensitive to a constant offset, while trends and component balance are not.

Use RS metrics as task-defined objectives or guardrails. Recheck discharge, sediment, and water balance after any parameter intended to improve RS agreement.

## Preserve reservoirs as physical constraints

When reservoir inflow, release, storage, or level observations exist, keep their accepted performance as an explicit guardrail. Adjust operation, initial storage, seepage, evaporation, and sediment-trapping parameters only when the corresponding data and model semantics support the change. A downstream flow gain obtained by degrading a well-observed release series is not a valid improvement.

## Select and deliver the next formal GUI plan

Choose the next GUI center from complete full-objective replays, not from the fastest screening score. Prefer a balanced candidate that preserves hard constraints and improves the requested process metrics, even when another row has a slightly higher aggregate mean.

For formal sampling:

- center ranges on the accepted replayed baseline;
- narrow parameters with repeatable signal while retaining exploration on weak but plausible directions;
- keep direct-only or unsupported parameters baked out of `par_inf.txt`;
- place the verified best in root, `Backup/`, and `DirectBase/`;
- generate exactly the requested row count and validate every row width;
- run the native BAT chain in a PTY, prove the first active parameter changes a real target file, and verify a tail parameter to detect line truncation;
- restore the best baseline, formal row count, and full interval, then leave formal `SUFI2.OUT/` empty.

The final report should distinguish: recovered samples, newly executed samples, feasible counts, selected whole-model best, rejected station mosaics, structural limitations, and the exact formal GUI parameter set.
