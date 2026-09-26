# Structure, executable, and extraction diagnostics

Read this reference when files, routing, facilities, a custom executable, observation mappings, or native extraction changed; when output changes at an unexpected station; or when a variable cannot be extracted.

## Deterministic A/B isolation

Before sampling after a structural or executable change, run deterministic replays with identical parameters, observations, period, and warm-up:

- **A:** last reproducible executable and structural-input set;
- **B:** one coherent replacement group;
- optionally **C:** the accepted calibrated parameters replayed on B.

Compare every observed variable and relevant reach/reservoir series, not just the intended target. Replace one coherent group at a time—executable, routing, reservoir records, transfers, or extraction definitions—so the effect remains attributable. A change at an unexpected downstream or side-branch variable is evidence to inspect routing order and source/destination identifiers, not permission to compensate with unrelated parameters.

## Observation and extraction contract

An observed variable is usable only when all of these agree:

1. its block name and length in `observed_rch.txt`;
2. the reach/inflow/outflow definition in routing and extraction control files;
3. the column actually printed by the active SWAT executable;
4. the native or direct extractor's column index and format assumptions;
5. the simulation period, warm-up offset, aggregation, unit, and missing-value convention;
6. the extracted variable file name and per-run block length.

Changing `FLOW_OUT` to `FLOW_IN`, moving a gauge, adding a tributary, or adding sediment observations can require coordinated edits to several SUFI2 control files; changing only the observation label is insufficient. Run one native extraction before calibration and compare selected months directly against `output.rch`.

The bundled structure audit auto-discovers the conventional `FLOW|SED_(IN|OUT)_<numeric reach>` names. If a project uses aliases, nonnumeric identifiers, or other constituents, provide an explicit mapping or extend the discovery adapter for that project; do not rename observations merely to make the audit pass.

If native sediment extraction fails, first check whether the requested sediment field is present in `output.rch`. Then check print selection, header/data column order, fixed-width versus whitespace parsing, the extraction definition, and whether the active sediment equation changes the meaning or availability of the column. Recompiling the executable cannot recover a column that is neither printed nor correctly indexed.

## Structural water inputs

Treat measured or otherwise trusted releases, withdrawals, return flows, point sources, and transfers as data. Do not continuously retune them to absorb hydrologic parameter error.

- **Reservoirs:** set documented physical capacity/area and operation data as fixed inputs when available. Calibrate ordinary watershed parameters around them. Direct diagnostic tests may vary uncertain initial storage, seepage, evaporation, or unmeasured withdrawals within evidence-based bounds, but unsupported GUI edits should be baked rather than placed in `par_inf.txt`.
- **WUS/withdrawals:** begin with the supplied time series and units. If water balance and low flow remain biased after runoff, ET, groundwater, and routing checks, test bounded seasonal or monthly scaling. Avoid a single large multiplier that destroys dry-season flow or hides missing year-to-year demand variation. If residual bias reverses sign between years or operating eras, a static monthly multiplier is structurally incapable of fitting both; obtain time-varying demand/return-flow data or report the limitation.
- **Point sources and interbasin transfers:** verify sign, source, destination, routing order, timing basis, and whether the quantity is fixed or proportional. Test the direct target and every downstream observation.

When a facility lies upstream of the gauge, validate the routed downstream response; when it lies downstream, it should not be used to explain that gauge. If SWAT places an in-subbasin reservoir at an outlet, explicitly verify whether the desired gauge represents inflow, reservoir release, or post-reservoir reach flow.

For record inflows intended to enter a reservoir, verify that the `recmon`/`recday` node reaches the reservoir before its water-balance and release operation in routing order. Adding the same record after `routres`, or to a nearby reach ID, can change a downstream gauge while leaving reservoir storage and release unchanged. Check storage continuity, inflow, evaporation/seepage/withdrawal, prescribed release, spill, and outlet flow together; a release file cannot discharge water that the modeled reservoir never received.

## Custom transfer and FIG records

Treat `fig.fig` and similar legacy controls as fixed-format protocols unless the reader source proves otherwise. Preserve field width, column position, spacing, trailing control tokens, line endings, and accepted numeric notation. A longer decimal can shift later fields while the executable still exits successfully, producing a false sensitivity result.

Apply the same discipline to SWAT input lines whose numeric field is followed by `|` and a description. Use an untouched file from the same SWAT project as the layout reference, preserve the delimiter column and descriptive text, and test that both the direct editor and native editor change the intended field. A visually plausible line with a shifted delimiter can be read from the wrong columns by legacy code.

For every new or modified custom transfer implementation, run a small response test with at least:

- zero/off;
- the current value;
- a lower nonzero value;
- a higher value;
- one repeat of the baseline.

Check target inflow/outflow, source balance, downstream variables, reservoir storage/release, and monotonic direction. If a supposed proportion produces an inverse, discontinuous, duplicated, or no response, stop calibrating it and audit initialization, multiplication/division direction, source water variable, route order, and parsing. Extreme coefficients that improve metrics only by exploiting such behavior are diagnostic evidence, not physical calibration values.

## Structural stop signals

Ordinary parameter sampling should pause when any of these persist across plausible ranges:

- observed releases or sediment events cannot be produced;
- the wrong station changes after a local structural edit;
- a variable is identical across materially different inputs;
- low flow collapses only when trusted withdrawals are active;
- coefficients respond in the wrong direction;
- output lengths, headers, or extraction columns change between executables;
- a broad 95PPU still misses the same events or seasons.

Report the failed mechanism, affected variables and periods, A/B evidence, and the missing or suspect input. Resume calibration only after the structural state is reproducible.

Do not use meteorological inputs or weather-generator parameters as convenient calibration knobs when the residual can be explained by runoff, groundwater, routing, reservoirs, withdrawals, or extraction. Change forcing data only after an evidence-based forcing audit identifies a defect and the task authorizes the correction; preserve the original forcing and document the A/B comparison.
