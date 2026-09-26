#!/usr/bin/env python3
"""Audit gauge routing, reservoirs, record inputs, and WUS withdrawals."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

from swatcup_auto_runner import parse_fig, read_observed_blocks, read_res_scalar, upstream_closure


WUS_NAMES = ("WUPND", "WURCH", "WUSHAL", "WUDEEP")


def read_wus(path: Path) -> dict[str, list[float]]:
    values: list[float] = []
    lines = path.read_text(errors="ignore").splitlines()
    for line in lines[3:11]:
        values.extend(float(token) for token in line.split())
    if len(values) != 48:
        raise ValueError(f"{path}: expected 48 WUS values, got {len(values)}")
    return {name: values[index * 12:(index + 1) * 12] for index, name in enumerate(WUS_NAMES)}


def observed_reaches(observed: dict[str, list[tuple[int, float]]]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for name in observed:
        match = re.fullmatch(r"(?:FLOW|SED)_(?:IN|OUT)_(\d+)", name)
        if match:
            result.setdefault(int(match.group(1)), []).append(name)
    return {reach: sorted(names) for reach, names in sorted(result.items())}


def flow_observations(
    observed: dict[str, list[tuple[int, float]]],
    reach: int,
) -> tuple[str | None, list[tuple[int, float]]]:
    for name in (f"FLOW_OUT_{reach}", f"FLOW_IN_{reach}"):
        if name in observed:
            return name, observed[name]
    return None, []


def related_reservoirs(project: Path, nodes: dict, route_ids: list[int]) -> list[dict[str, object]]:
    route_closure: set[int] = set()
    for route_id in route_ids:
        route_closure.update(upstream_closure(nodes, [route_id]))
    rows: list[dict[str, object]] = []
    for node in nodes.values():
        if node.op != "routres":
            continue
        reservoir_closure = upstream_closure(nodes, [node.node_id])
        if node.node_id in route_closure:
            relation = "upstream_of_gauge"
        elif any(route_id in reservoir_closure for route_id in route_ids):
            relation = "downstream_of_gauge"
        else:
            continue
        filename = next((name for name in node.files if name.lower().endswith(".res")), "")
        path = project / filename if filename else None
        source_subbasins = sorted(
            int(nodes[node_id].object_id)
            for node_id in reservoir_closure
            if node_id in nodes and nodes[node_id].op == "subbasin" and nodes[node_id].object_id is not None
        )
        rows.append({
            "relation": relation,
            "file": filename,
            "reservoir_id": node.object_id,
            "source_subbasins": source_subbasins,
            "iresco": read_res_scalar(path, "IRESCO") if path and path.exists() else None,
            "res_sub": read_res_scalar(path, "RES_SUB") if path and path.exists() else None,
        })
    return rows


def read_transfer_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1):
        parts = line.split()
        if not parts or parts[0].lower() != "transfer":
            continue
        record: dict[str, object] = {
            "line": line_number,
            "raw": line,
            "tokens": parts[1:],
        }
        if len(parts) >= 8:
            try:
                record.update({
                    "source_type": int(parts[2]),
                    "source_id": int(parts[3]),
                    "destination_type": int(parts[4]),
                    "destination_id": int(parts[5]),
                    "amount": float(parts[6]),
                    "transfer_code": int(parts[7]),
                    "sequence": (
                        int(parts[8])
                        if len(parts) > 8 and parts[8].lstrip("+-").isdigit()
                        else None
                    ),
                })
            except ValueError as exc:
                record["parse_error"] = str(exc)
        else:
            record["parse_error"] = "too few tokens for the optional reach-reservoir-1-2 schema"
        records.append(record)
    return records


def record_input_status(project: Path, nodes: dict) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    issues: list[str] = []
    for node in nodes.values():
        if node.op not in {"recmon", "recday", "reccnst"}:
            continue
        files: list[dict[str, object]] = []
        for name in node.files:
            path = project / name
            exists = path.is_file()
            size = path.stat().st_size if exists else 0
            data_rows = 0
            if exists:
                for line in path.read_text(errors="ignore").splitlines():
                    if line.split() and re.match(r"[-+0-9.]", line.lstrip()):
                        data_rows += 1
            files.append({"name": name, "exists": exists, "size": size, "data_rows": data_rows})
            if not exists or size == 0:
                issues.append(f"{node.op} node {node.node_id} input is missing or empty: {name}")
        if not files:
            issues.append(f"{node.op} node {node.node_id} has no parsed input filename")
        rows.append({"command": node.op, "node_id": node.node_id, "files": files})
    return rows, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--observed-rch", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--wus-unit-m3-per-day",
        type=float,
        help="Cubic metres per day represented by one WUS value. Omit when the unit is unconfirmed.",
    )
    parser.add_argument(
        "--transfer-schema",
        choices=("reach-reservoir-1-2",),
        help="Interpret custom transfer records only after confirming the active executable's schema.",
    )
    args = parser.parse_args()
    project = args.project.resolve()
    observed_path = args.observed_rch.resolve() if args.observed_rch else project / "SUFI2.IN" / "observed_rch.txt"
    observed = read_observed_blocks(observed_path)
    reach_variables = observed_reaches(observed)
    stations = sorted(reach_variables)
    nodes = parse_fig(project / "fig.fig")
    routes: dict[int, list[int]] = {}
    for node in nodes.values():
        if node.op == "route" and node.object_id is not None:
            routes.setdefault(int(node.object_id), []).append(node.node_id)

    station_closures: dict[int, set[int]] = {}
    station_sources: dict[int, set[int]] = {}
    for station in stations:
        closure: set[int] = set()
        for route_id in routes.get(station, []):
            closure.update(upstream_closure(nodes, [route_id]))
        station_closures[station] = closure
        station_sources[station] = {
            int(nodes[node_id].object_id)
            for node_id in closure
            if node_id in nodes and nodes[node_id].op == "subbasin" and nodes[node_id].object_id is not None
        }

    dependencies: list[dict[str, int]] = []
    for downstream in stations:
        for upstream in stations:
            if upstream == downstream:
                continue
            if any(route_id in station_closures[downstream] for route_id in routes.get(upstream, [])):
                dependencies.append({"upstream_station": upstream, "downstream_station": downstream})

    transfers = read_transfer_records(project / "fig.fig")
    transfer_issues: list[str] = []
    transfer_links: set[frozenset[int]] = set()
    if args.transfer_schema == "reach-reservoir-1-2":
        for transfer in transfers:
            if "parse_error" in transfer:
                transfer_issues.append(
                    f"Transfer line {transfer['line']} cannot be parsed with the confirmed schema: {transfer['parse_error']}"
                )
                transfer["source_affected_stations"] = []
                transfer["destination_affected_stations"] = []
                continue
            if transfer["source_type"] not in {1, 2} or transfer["destination_type"] not in {1, 2}:
                transfer_issues.append(
                    f"Transfer line {transfer['line']} has a type outside the confirmed 1=reach, 2=reservoir schema"
                )
                transfer["source_affected_stations"] = []
                transfer["destination_affected_stations"] = []
                continue
            source_op = "route" if transfer["source_type"] == 1 else "routres"
            destination_op = "route" if transfer["destination_type"] == 1 else "routres"
            source_nodes = {
                node.node_id for node in nodes.values()
                if node.op == source_op and node.object_id == transfer["source_id"]
            }
            destination_nodes = {
                node.node_id for node in nodes.values()
                if node.op == destination_op and node.object_id == transfer["destination_id"]
            }
            if not source_nodes:
                transfer_issues.append(
                    f"Transfer line {transfer['line']} source object was not resolved in fig.fig"
                )
            if not destination_nodes:
                transfer_issues.append(
                    f"Transfer line {transfer['line']} destination object was not resolved in fig.fig"
                )
            source_stations = sorted(
                station for station, closure in station_closures.items() if closure & source_nodes
            )
            destination_stations = sorted(
                station for station, closure in station_closures.items() if closure & destination_nodes
            )
            transfer["source_affected_stations"] = source_stations
            transfer["destination_affected_stations"] = destination_stations
            for source_station in source_stations:
                for destination_station in destination_stations:
                    if source_station != destination_station:
                        transfer_links.add(frozenset({source_station, destination_station}))

    remaining = set(stations)
    calibration_blocks: list[list[int]] = []
    while remaining:
        block = {remaining.pop()}
        changed = True
        while changed:
            changed = False
            for candidate in list(remaining):
                if any(
                    station_sources[candidate] & station_sources[member]
                    or frozenset({candidate, member}) in transfer_links
                    for member in block
                ):
                    block.add(candidate)
                    remaining.remove(candidate)
                    changed = True
        calibration_blocks.append(sorted(block))

    record_inputs, record_issues = record_input_status(project, nodes)
    payload: dict[str, object] = {
        "wus_unit_assumption_m3_per_day": args.wus_unit_m3_per_day,
        "wus_dimensional_comparison": (
            "enabled" if args.wus_unit_m3_per_day is not None else "skipped: WUS unit was not supplied"
        ),
        "transfer_schema": args.transfer_schema,
        "transfer_interpretation": (
            "enabled" if args.transfer_schema else "skipped: records retained for manual review"
        ),
        "stations": {},
        "station_dependencies": dependencies,
        "calibration_blocks": sorted(calibration_blocks, key=lambda block: block[0]),
        "transfers_for_manual_review": transfers,
        "record_inputs_for_manual_review": record_inputs,
        "project_level_issues": record_issues + transfer_issues,
    }
    wus_rows: list[dict[str, object]] = []
    seconds_per_day = 86400.0
    for station in stations:
        route_ids = routes.get(station, [])
        if not route_ids:
            payload["stations"][str(station)] = {
                "observed_variables": reach_variables[station],
                "issues": ["No matching route node in fig.fig"],
            }
            continue
        closure = station_closures[station]
        sources = sorted(station_sources[station])
        monthly = {name: [0.0] * 12 for name in WUS_NAMES}
        missing_wus: list[str] = []
        malformed_wus: list[str] = []
        for source in sources:
            path = project / f"{source:05d}0000.wus"
            if path.exists():
                try:
                    data = read_wus(path)
                except (OSError, ValueError) as exc:
                    malformed_wus.append(f"{path.name}: {exc}")
                    data = {name: [0.0] * 12 for name in WUS_NAMES}
            else:
                missing_wus.append(path.name)
                data = {name: [0.0] * 12 for name in WUS_NAMES}
            for name in WUS_NAMES:
                monthly[name] = [a + b for a, b in zip(monthly[name], data[name])]
            wus_rows.append({
                "station": station,
                "source_subbasin": source,
                "annual_wurch_units": sum(data["WURCH"]),
                "annual_wushal_units": sum(data["WUSHAL"]),
            })
        flow_name, flow_series = flow_observations(observed, station)
        obs_values = [value for _, value in flow_series]
        obs_mean = sum(obs_values) / len(obs_values) if obs_values else None
        river_max_units = max(monthly["WURCH"])
        shallow_max_units = max(monthly["WUSHAL"])
        river_max = None
        shallow_max = None
        combined_ratio = None
        if args.wus_unit_m3_per_day is not None:
            river_max = river_max_units * args.wus_unit_m3_per_day / seconds_per_day
            shallow_max = shallow_max_units * args.wus_unit_m3_per_day / seconds_per_day
            if obs_mean is not None:
                combined_ratio = (river_max + shallow_max) / obs_mean if obs_mean > 0 else math.inf
        reservoirs = related_reservoirs(project, nodes, route_ids)
        issues: list[str] = []
        notes: list[str] = []
        if missing_wus:
            issues.append(f"Missing WUS files for upstream subbasins: {missing_wus[:10]}")
        if malformed_wus:
            issues.append(f"Unrecognized WUS layout; dimensional totals exclude these files: {malformed_wus[:5]}")
        if any(row["relation"] == "downstream_of_gauge" for row in reservoirs):
            issues.append("Reservoir is downstream of extracted reach; verify gauge location and output variable")
        if combined_ratio is not None and combined_ratio > 1.0:
            issues.append("Maximum WUS river+shallow withdrawal exceeds mean observed flow")
        if args.wus_unit_m3_per_day is None:
            notes.append("WUS dimensional comparison skipped because no verified unit was supplied")
        if flow_name is None:
            notes.append("No FLOW_IN/FLOW_OUT observation exists at this reach; flow-based WUS ratio was skipped")
        payload["stations"][str(station)] = {
            "observed_variables": reach_variables[station],
            "route_node_ids": route_ids,
            "source_subbasins": sources,
            "upstream_observed_stations": [
                row["upstream_station"] for row in dependencies if row["downstream_station"] == station
            ],
            "reservoirs": reservoirs,
            "flow_observation_used_for_wus_check": flow_name,
            "observed_mean_flow": obs_mean,
            "max_monthly_wurch_raw_units": river_max_units,
            "max_monthly_wushal_raw_units": shallow_max_units,
            "max_monthly_wurch_m3s": river_max,
            "max_monthly_wushal_m3s": shallow_max,
            "max_withdrawal_to_mean_flow_ratio": combined_ratio,
            "missing_wus_files": missing_wus,
            "malformed_wus_files": malformed_wus,
            "issues": issues,
            "notes": notes,
        }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "routing_structure.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.out_dir / "routing_wus_sources.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = ["station", "source_subbasin", "annual_wurch_units", "annual_wushal_units"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(wus_rows)
    print(json.dumps(payload["stations"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
