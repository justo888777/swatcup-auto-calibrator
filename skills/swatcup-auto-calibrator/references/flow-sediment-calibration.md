# Flow–sediment calibration

Read this reference when a project contains both discharge and sediment observations, or when sediment calibration must be added to an existing flow calibration.

## Choose the calibration phase from evidence

Use a staged workflow unless the project already has a stable hydrologic baseline:

1. **Hydrologic structure:** verify routing, observations, reservoirs, withdrawals, point sources, transfers, and the executable/input set.
2. **Flow stabilization:** calibrate runoff generation, evapotranspiration, groundwater/baseflow, and channel routing until flow timing and water balance are credible.
3. **Sediment extraction check:** prove that each sediment variable is extracted from the intended reach, column, equation, period, and unit before sampling sediment parameters.
4. **Sediment search with flow guardrails:** keep accepted flow parameters fixed or in narrow evidence-based ranges. Vary sediment parameters and only hydrologic parameters whose coupling to sediment is physically necessary.
5. **Joint polish:** use small ranges around the accepted flow solution, require flow guardrails, and improve sediment without trading away hydrograph timing or baseflow.

Do not start a large joint search merely because both variable types are present. When discharge is structurally wrong, sediment parameters compensate for the wrong carrier flow and the resulting solution is not transferable.

## Build a class-balanced objective

Treat flow and sediment as two metric classes rather than allowing the class with more variables to dominate automatically. Resolve class weights from the request; if none are given, state a neutral convention such as equal total weight per class and equal station weight within each class. In the runner, express total class weights with `--class-weights` and use `--class-floors` for accepted class guardrails; `--variable-weights` controls relative weight within a class. Then apply, in order:

1. execution, output-length, and finite-value validity;
2. explicit per-variable or per-class floors;
3. flow guardrails during sediment phases;
4. the configured weighted objective;
5. worst-variable and process diagnostics as tie breakers.

Use raw station metrics, not raw discharge or sediment magnitudes, in the aggregate. Large sediment loads must not receive more weight merely because their numeric values are larger.

For flow, review KGE, NSE, R²/correlation, PBIAS, log1p-NSE, seasonal bias, lag, peak capture, low-flow ratio, and zero-flow behavior. For sediment, review KGE, NSE, R²/correlation, PBIAS, event/seasonal peak capture, zero/nonzero agreement, and a transformed metric such as log1p-NSE. Count and report negative simulated values before applying any nonnegative or logarithmic transform; clipping them only for a metric must not hide a model or extraction failure. Transformed sediment metrics are supplementary: many zero months or isolated large events can make them strongly negative even when ordinary NSE improves.

An observed sediment value of zero is data unless the observation metadata explicitly marks it as missing or below a detection convention that should be handled differently. Preserve zeros in alignment and scoring, and report zero/nonzero agreement separately so a long zero season cannot hide missed transport events. Acceptance thresholds for R², NSE, and PBIAS come from the current task or cited evaluation framework; do not hard-code one basin's thresholds into the skill.

## Attribute parameters to processes

Start with the smallest process-consistent group that can explain the symptom:

| Process | Typical parameter families to test |
| --- | --- |
| Surface runoff volume and timing | curve number/retention, soil available water, surface lag, infiltration/runoff partition |
| Evapotranspiration and soil storage | soil evaporation and plant uptake compensation, soil depth/storage, PET-related controls |
| Baseflow and low-flow persistence | aquifer recession, groundwater delay, threshold storage, recharge partition, revap controls |
| Channel attenuation and losses | channel roughness, hydraulic conductivity/loss, reach routing controls |
| Hillslope sediment supply | USLE cover/support/erodibility, slope/length factors, land-cover-specific protection |
| Sediment delivery and routing | overland roughness, lateral sediment delivery, channel erodibility/cover, peak-rate and transport-capacity controls |

Parameter names and supported edit syntax differ by SWAT version and project. Derive the actual candidates from current sensitivity evidence and files; this table is routing guidance, not a mandatory parameter list.

Use the limits declared for the active project and executable. Custom sediment parameters have no universal physical clamp: prove their meaning from the source/build documentation or an explicit project profile. Review each sample row's `clip_count` and requested/applied extrema in `clip_details`, plus the latest `direct_clip_log.csv`; any standard safety clipping must be visible rather than creating a hidden false optimum.

Partition parameters only where selectors have a physical meaning: land use for cover/management, soil class for erodibility/storage, subbasin or routing closure for branch response, and reach class for channel behavior. Do not invent station-number partitions or copy another basin's grouping. Unobserved side branches may be adjusted when their routing contribution is identified, but their values still need plausible bounds and downstream replay.

## Diagnose flow before changing sediment

- Correct peak dates but wrong sediment magnitude: test hillslope supply, delivery, channel erosion/deposition, and units before changing flow.
- Wrong discharge peaks and wrong sediment peaks together: fix rainfall–runoff and routing first.
- Good flow KGE but poor low flow: inspect log1p-NSE, low-flow ratio, withdrawals, return flow, and groundwater; peak-dominated KGE can hide a visibly wrong dry season.
- Good scalar metrics but mismatched hydrographs: treat the candidate as process-invalid until the timing or structural cause is resolved.
- Sediment simulated as near zero for every station: audit extraction, equation choice, print columns, units, and active sediment routing before expanding USLE ranges.

Changing a sediment equation or transport formulation is a structural scenario, not an ordinary calibration parameter. Compare formulations with deterministic A/B replays under the same flow parameters, observations, and extraction definition. Restart sensitivity analysis after choosing the formulation because parameter meaning and response can change.

If different routing reaches genuinely require different supported sediment formulations, treat the mixed formulation as a structural configuration. Combine only formulations that the executable reads independently by reach, then replay the full routing network and compare all sediment stations, downstream flow, reservoir trapping, and mass balance. Do not infer reach-specific support from a direct text edit alone.

## Sample and narrow

Use a canary with the intended executable, extraction path, active variables, and worker layout. Choose successful-sample targets from the current parameter dimension, runtime, stage, and convergence evidence; never encode a universal run count in the skill.

After each batch:

- replay the whole-model best candidate;
- plot flow and sediment processes at every observed variable;
- compare non-flood/baseflow and event periods separately;
- identify bound-hitting or weakly identified parameters;
- narrow only stable, physically credible directions;
- keep broader ranges or stop when the ensemble cannot cover observations for structural reasons.

Use station-level elites to learn which source areas or routing reaches have signal. Test hillslope source parameters by physically meaningful land use or soil class, and channel or reservoir parameters by verified routing scope. Include tributary contributions when they enter the observed reach; do not tune only the gauge reach if upstream branches supply most of the sediment.

During the final joint phase, reduce the hydrologic search radius before the sediment search radius. A sediment gain that violates the accepted flow guardrail is not progress.

## Uncertainty and reporting

Build 95PPU from complete saved time series. For sediment, also report whether observed nonzero events and high-load months fall inside the band; P-factor alone can look acceptable when long zero periods dominate.

The final report should place flow and sediment in one variable-level table with station mapping, KGE, NSE, R², PBIAS, log1p-NSE, process flags, and the stated acceptance rule. Separate calibration and validation periods when making validation claims. Report structural limitations instead of presenting a statistically improved but physically unsupported parameter set as calibrated.
