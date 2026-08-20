from __future__ import annotations

import argparse
import csv
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


EDIT_EXTENSIONS = {"bsn", "hru", "mgt", "sol", "rte", "sub", "gw", "res", "wus"}
SOL_LABELS = {
    "SOL_AWC": "Ave. AW Incl. Rock Frag",
    "SOL_K": "Ksat. (est.)",
    "USLE_K": "Erosion K",
}
RES_ARRAY_LABELS = {"OFLOWMX", "OFLOWMN", "STARG", "WURESN"}
WUS_ARRAY_LABELS = {"WUPND", "WURCH", "WUSHAL", "WUDEEP"}
FIG_COMMANDS = {
    "subbasin",
    "route",
    "routres",
    "add",
    "recmon",
    "recday",
    "reccnst",
    "transfer",
    "saveconc",
    "finish",
}
FIG_FILE_PATTERN = re.compile(
    r"(?:\d{9}\.(?:sub|rte|swq|res|lwq|pnd|wus)|[A-Za-z0-9_.-]+\.dat)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Parameter:
    operation: str
    name: str
    layer_index: int | None
    extension: str
    selector: str | None
    value: float
    raw_name: str


@dataclass(frozen=True)
class FigNode:
    op: str
    node_id: int
    object_id: int | None
    upstream_ids: tuple[int, ...]
    files: tuple[str, ...]


@dataclass(frozen=True)
class ReservoirScope:
    station_id: int
    relation: str
    res_file: str
    selector: int
    local_subbasin: int | None
    res_node_id: int
    upstream_node_id: int | None


def parse_parameter(raw_name: str, value: float) -> Parameter:
    if len(raw_name) < 5 or raw_name[1:3] != "__":
        raise ValueError(f"Unsupported parameter name: {raw_name}")

    operation = raw_name[0].lower()
    body = raw_name[3:]
    param_name, rest = body.split(".", 1)
    layer_index = None
    layer_match = re.fullmatch(r"([A-Za-z0-9_]+)(?:\((\d+)\))?", param_name)
    if layer_match:
        param_name = layer_match.group(1)
        if layer_match.group(2):
            layer_index = int(layer_match.group(2))
    else:
        param_name = param_name.replace("()", "")

    rest_lower = rest.lower()
    extension = next((ext for ext in sorted(EDIT_EXTENSIONS, key=len, reverse=True) if rest_lower.startswith(ext)), None)
    if extension is None:
        raise ValueError(f"Unsupported parameter extension in: {raw_name}")
    selector = rest[len(extension):].replace("_", "") or None
    return Parameter(operation, param_name, layer_index, extension, selector, value, raw_name)


def parse_model_in(path: Path) -> list[Parameter]:
    params: list[Parameter] = []
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) >= 2 and "__" in parts[0]:
            params.append(parse_parameter(parts[0], float(parts[1])))
    return params


def parse_model_values(path: Path) -> dict[str, float]:
    return {param.raw_name: param.value for param in parse_model_in(path)}


def parse_par_inf(path: Path) -> list[tuple[str, float, float]]:
    lines = path.read_text(errors="ignore").splitlines()
    expected: int | None = None
    for line in lines:
        parts = line.split()
        if parts and parts[0].isdigit():
            expected = int(parts[0])
            break

    rows: list[tuple[str, float, float]] = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 3 and "__" in parts[0]:
            rows.append((parts[0], float(parts[1]), float(parts[2])))
    if expected is not None and len(rows) != expected:
        raise ValueError(f"{path}: declares {expected} parameters but contains {len(rows)} rows")
    return rows


def parse_par_val(path: Path) -> list[tuple[int, list[float]]]:
    rows: list[tuple[int, list[float]]] = []
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            rows.append((int(parts[0]), [float(x) for x in parts[1:]]))
    return rows


def params_from_names_values(names: list[str], values: list[float]) -> list[Parameter]:
    if len(names) != len(values):
        raise ValueError(f"Parameter count mismatch: {len(names)} names vs {len(values)} values")
    return [parse_parameter(name, value) for name, value in zip(names, values)]


def subbasin_id(path: Path) -> int | None:
    stem = path.stem
    if len(stem) >= 5 and stem[:5].isdigit():
        return int(stem[:5])
    return None


def reservoir_sub_id(path: Path) -> int | None:
    if path.suffix.lower() != ".res":
        return None
    try:
        for line in path.read_text(errors="ignore").splitlines():
            if "| RES_SUB" in line.upper():
                return int(numeric_before_pipe(line))
    except (OSError, ValueError):
        return None
    return None


def reservoir_file_subbasin(path_or_name: Path | str) -> int | None:
    name = Path(path_or_name).name
    stem = Path(name).stem
    if len(stem) >= 5 and stem[:5].isdigit():
        return int(stem[:5])
    return None


def hru_first_line(project: Path, file_path: Path) -> str:
    hru_path = project / f"{file_path.stem}.hru"
    if not hru_path.exists():
        return ""
    with hru_path.open(errors="ignore") as handle:
        return handle.readline()


def selector_matches(project: Path, file_path: Path, selector: str | None) -> bool:
    if not selector:
        return True

    if re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", selector):
        selected: set[int] = set()
        for token in selector.split(","):
            if "-" in token:
                start, end = (int(x) for x in token.split("-", 1))
                selected.update(range(min(start, end), max(start, end) + 1))
            else:
                selected.add(int(token))
        sid = subbasin_id(file_path)
        if sid in selected:
            return True
        rid = reservoir_sub_id(file_path)
        return rid in selected

    token = f"Luse:{selector.upper()}"
    return token in hru_first_line(project, file_path)


def target_files(project: Path, param: Parameter) -> list[Path]:
    if param.extension == "bsn":
        return [project / "basins.bsn"]

    files = [path for path in sorted(project.glob(f"*.{param.extension}")) if path.stem.isdigit()]
    return [path for path in files if selector_matches(project, path, param.selector)]


def apply_operation(old_value: float, param: Parameter) -> float:
    if param.operation == "v":
        new_value = param.value
    elif param.operation == "r":
        new_value = old_value * (1.0 + param.value)
    elif param.operation == "a":
        new_value = old_value + param.value
    else:
        raise ValueError(f"Unsupported operation: {param.operation}")

    if param.name in {"ADJ_PKR", "PRF_BSN"}:
        new_value = min(2.0, max(0.0, new_value))
    elif param.name in {"CH_COV1", "CH_COV2", "USLE_P", "SOL_AWC"}:
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "SOL_K":
        new_value = min(2000.0, max(0.0, new_value))
    elif param.name == "CN2":
        new_value = min(98.0, max(35.0, new_value))
    elif param.name == "SLSUBBSN":
        new_value = min(150.0, max(10.0, new_value))
    elif param.name == "SPCON":
        new_value = max(0.0, new_value)
    elif param.name == "SPEXP":
        new_value = min(2.0, max(1.0, new_value))
    elif param.name == "SURLAG":
        new_value = min(24.0, max(0.05, new_value))
    elif param.name == "GW_DELAY":
        new_value = min(500.0, max(0.0, new_value))
    elif param.name == "ALPHA_BF":
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "GWQMN":
        new_value = min(5000.0, max(0.0, new_value))
    elif param.name == "GW_REVAP":
        new_value = min(0.2, max(0.02, new_value))
    elif param.name == "REVAPMN":
        new_value = min(500.0, max(0.0, new_value))
    elif param.name == "RCHRG_DP":
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "ESCO":
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "EPCO":
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "OV_N":
        new_value = min(30.0, max(0.01, new_value))
    elif param.name == "LAT_TTIME":
        new_value = max(0.0, new_value)
    elif param.name == "SLSOIL":
        new_value = max(0.0, new_value)
    elif param.name == "CH_N2":
        new_value = min(0.3, max(0.01, new_value))
    elif param.name == "CH_K2":
        new_value = min(500.0, max(0.0, new_value))
    elif param.name == "HRU_SLP":
        new_value = min(1.0, max(0.0, new_value))
    elif param.name in {"IRESCO", "IFLOD1R", "IFLOD2R", "NDTARGR"}:
        new_value = max(0.0, round(new_value))
        if param.name == "IRESCO":
            new_value = min(3.0, new_value)
        elif param.name in {"IFLOD1R", "IFLOD2R"}:
            new_value = min(12.0, max(1.0, new_value))
        elif param.name == "NDTARGR":
            new_value = min(365.0, new_value)
    elif param.name in {"EVRSV", "WURTNF", "OFLOWMN_FPS", "STARG_FPS"}:
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "RES_K":
        new_value = min(10.0, max(0.0, new_value))
    elif param.name == "RES_RR":
        new_value = min(500.0, max(0.0, new_value))
    elif param.name in {"RES_VOL", "RES_PVOL", "RES_EVOL", "STARG"}:
        new_value = min(50000.0, max(0.0, new_value))
    elif param.name in {"OFLOWMX", "OFLOWMN"}:
        new_value = min(1000.0, max(0.0, new_value))
    elif param.name == "WURESN":
        new_value = min(5000.0, max(0.0, new_value))
    elif param.name in WUS_ARRAY_LABELS:
        new_value = min(10000.0, max(0.0, new_value))
    elif param.name == "LAT_SED":
        new_value = max(0.0, new_value)
    elif param.name in {"CH_L1", "CH_L2"}:
        new_value = min(500.0, max(0.05, new_value))
    elif param.name in {"CH_S1", "CH_S2"}:
        new_value = min(10.0, max(0.0001, new_value))
    elif param.name in {"CH_W1", "CH_W2"}:
        new_value = min(1000.0, max(1.0, new_value))
    elif param.name == "CH_K1":
        new_value = min(300.0, max(0.0, new_value))
    elif param.name == "CH_N1":
        new_value = min(30.0, max(0.01, new_value))
    elif param.name == "FILTERW":
        new_value = min(100.0, max(0.0, new_value))
    elif param.name == "BIOMIX":
        new_value = min(1.0, max(0.0, new_value))
    elif param.name == "EROS_SPL":
        new_value = min(3.1, max(0.9, new_value))
    elif param.name == "RILL_MULT":
        new_value = min(2.0, max(0.5, new_value))
    elif param.name == "EROS_EXPO":
        new_value = min(3.0, max(0.9, new_value))
    elif param.name == "SUBD_CHSED":
        new_value = min(2.0, max(0.0, round(new_value)))
    elif param.name == "C_FACTOR":
        new_value = min(0.45, max(0.001, new_value))
    elif param.name == "CH_D50":
        new_value = min(100.0, max(10.0, new_value))
    elif param.name == "SIG_G":
        new_value = min(5.0, max(1.0, new_value))

    return new_value


def format_pipe_line(new_value: float, rest: str) -> str:
    return f"{new_value:16.6f}    |{rest}"


INTEGER_PIPE_PARAMETERS = {
    "CH_EQN",
    "SUBD_CHSED",
    "ICFAC",
    "ICN",
    "IRESCO",
    "IFLOD1R",
    "IFLOD2R",
    "NDTARGR",
}


def numeric_before_pipe(line: str) -> float:
    before = line.split("|", 1)[0]
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", before)
    if not match:
        raise ValueError(f"No numeric field found in line: {line!r}")
    return float(match.group(0))


def edit_pipe_parameter(path: Path, backup_path: Path, param: Parameter) -> int:
    lines = path.read_text(errors="ignore").splitlines(keepends=True)
    backup_lines = backup_path.read_text(errors="ignore").splitlines(keepends=True)
    count = 0
    pattern = re.compile(rf"\|\s*{re.escape(param.name)}\b", re.IGNORECASE)
    new_lines: list[str] = []

    for line_no, line in enumerate(lines):
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        if pattern.search(body):
            _, after = body.split("|", 1)
            old_value = numeric_before_pipe(body)
            new_value = apply_operation(old_value, param)
            if param.name in INTEGER_PIPE_PARAMETERS:
                body = f"{int(round(new_value)):16d}    |{after}"
            else:
                body = format_pipe_line(new_value, after)
            count += 1
        new_lines.append(body + newline)

    path.write_text("".join(new_lines), newline="")
    return count


def sol_values(line: str) -> list[float]:
    if ":" not in line:
        return []
    values_text = line.split(":", 1)[1]
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", values_text)]


def edit_sol_parameter(path: Path, backup_path: Path, param: Parameter) -> int:
    label = SOL_LABELS.get(param.name)
    if not label:
        raise ValueError(f"Unsupported .sol parameter: {param.name}")

    lines = path.read_text(errors="ignore").splitlines(keepends=True)
    backup_lines = backup_path.read_text(errors="ignore").splitlines(keepends=True)
    count = 0
    new_lines: list[str] = []
    for line_no, line in enumerate(lines):
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        if label in body:
            prefix, _ = body.split(":", 1)
            values = sol_values(body)
            new_values = values[:]
            if param.layer_index is None:
                new_values = [apply_operation(v, param) for v in values]
                count += len(new_values)
            else:
                value_index = param.layer_index - 1
                if value_index >= len(values):
                    raise RuntimeError(f"{path.name}: {param.raw_name} layer index exceeds soil layer count")
                new_values[value_index] = apply_operation(values[value_index], param)
                count += 1
            body = f"{prefix}:{''.join(f'{v:12.2f}' for v in new_values)}"
        new_lines.append(body + newline)

    path.write_text("".join(new_lines), newline="")
    return count


def res_values(line: str) -> list[float]:
    return [float(x) for x in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", line)]


def format_res_array_line(values: list[float]) -> str:
    return "".join(f"{value:10.4f}" for value in values)


def edit_res_array_parameter(path: Path, backup_path: Path, param: Parameter) -> int:
    lines = path.read_text(errors="ignore").splitlines(keepends=True)
    count = 0
    month_offset = 0
    new_lines: list[str] = []
    i = 0
    label_pattern = re.compile(rf"^\s*{re.escape(param.name)}\s*:", re.IGNORECASE)

    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        body = line.rstrip("\n")
        if label_pattern.search(body) and i + 1 < len(lines):
            i += 1
            value_line = lines[i]
            newline = "\n" if value_line.endswith("\n") else ""
            values = res_values(value_line)
            if values:
                new_values = values[:]
                for value_index, value in enumerate(values):
                    month_index = month_offset + value_index + 1
                    if param.layer_index is None or param.layer_index == month_index:
                        new_values[value_index] = apply_operation(value, param)
                        count += 1
                value_line = format_res_array_line(new_values) + newline
                month_offset += len(values)
            new_lines.append(value_line)
        i += 1

    path.write_text("".join(new_lines), newline="")
    return count


def edit_res_parameter(path: Path, backup_path: Path, param: Parameter) -> int:
    if param.name in RES_ARRAY_LABELS:
        return edit_res_array_parameter(path, backup_path, param)
    return edit_pipe_parameter(path, backup_path, param)


def edit_wus_parameter(path: Path, backup_path: Path, param: Parameter) -> int:
    if param.name not in WUS_ARRAY_LABELS:
        raise ValueError(f"Unsupported .wus parameter: {param.name}")
    lines = path.read_text(errors="strict").splitlines()
    if len(lines) < 11:
        raise ValueError(f"Unexpected .wus layout in {path}")
    values: list[float] = []
    for line in lines[3:11]:
        values.extend(float(value) for value in line.split())
    if len(values) != 48:
        raise ValueError(f"Expected 48 values in {path}, got {len(values)}")
    start = {"WUPND": 0, "WURCH": 12, "WUSHAL": 24, "WUDEEP": 36}[param.name]
    count = 0
    for month in range(1, 13):
        if param.layer_index is None or param.layer_index == month:
            index = start + month - 1
            values[index] = apply_operation(values[index], param)
            count += 1
    data_lines = ["".join(f"{value:10.1f}" for value in values[index:index + 6]) for index in range(0, 48, 6)]
    path.write_text("\n".join(lines[:3] + data_lines + lines[11:]) + "\n", encoding="utf-8")
    return count


def is_fig_command(line: str) -> bool:
    parts = line.split()
    return bool(parts) and parts[0].lower() in FIG_COMMANDS


def integer_tokens(parts: list[str]) -> list[int]:
    values: list[int] = []
    for part in parts:
        if re.fullmatch(r"[-+]?\d+", part):
            values.append(int(part))
    return values


def parse_fig(path: Path) -> dict[int, FigNode]:
    nodes: dict[int, FigNode] = {}
    lines = path.read_text(errors="ignore").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        parts = line.split()
        if not parts or parts[0].lower() not in FIG_COMMANDS:
            index += 1
            continue

        op = parts[0].lower()
        ints = integer_tokens(parts[1:])
        files: tuple[str, ...] = ()
        if index + 1 < len(lines) and not is_fig_command(lines[index + 1]):
            files = tuple(match.group(0) for match in FIG_FILE_PATTERN.finditer(lines[index + 1]))

        node: FigNode | None = None
        if op == "subbasin" and len(ints) >= 3:
            node = FigNode(op, ints[1], ints[2], (), files)
        elif op == "route" and len(ints) >= 4:
            node = FigNode(op, ints[1], ints[2], (ints[3],), files)
        elif op == "routres" and len(ints) >= 4:
            node = FigNode(op, ints[1], ints[2], (ints[3],), files)
        elif op == "add" and len(ints) >= 4:
            node = FigNode(op, ints[1], None, (ints[2], ints[3]), files)
        elif op in {"recmon", "recday", "reccnst"} and len(ints) >= 2:
            node = FigNode(op, ints[1], ints[2] if len(ints) >= 3 else None, (), files)
        elif op in {"transfer", "saveconc", "finish"}:
            # These are commands, not hydrograph-routing nodes. Transfers are
            # parsed separately by audit_structure.py as source/destination couplings.
            node = None

        if node is not None:
            nodes[node.node_id] = node
        index += 1
    return nodes


def upstream_closure(nodes: dict[int, FigNode], start_ids: list[int]) -> set[int]:
    seen: set[int] = set()
    stack = list(start_ids)
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = nodes.get(node_id)
        if node:
            stack.extend(upstream for upstream in node.upstream_ids if upstream not in seen)
    return seen


def read_res_scalar(path: Path, name: str) -> float | None:
    pattern = re.compile(rf"\|\s*{re.escape(name)}\b", re.IGNORECASE)
    for line in path.read_text(errors="ignore").splitlines():
        if pattern.search(line):
            return numeric_before_pipe(line)
    return None


def read_res_array(path: Path, name: str) -> list[float]:
    lines = path.read_text(errors="ignore").splitlines()
    values: list[float] = []
    label_pattern = re.compile(rf"^\s*{re.escape(name)}\s*:", re.IGNORECASE)
    for index, line in enumerate(lines):
        if label_pattern.search(line) and index + 1 < len(lines):
            values.extend(res_values(lines[index + 1]))
    return values


def reservoir_scope(project: Path, station_ids: list[int], fig_path: Path | None = None) -> list[ReservoirScope]:
    fig = fig_path or project / "fig.fig"
    if not fig.exists():
        raise FileNotFoundError(fig)
    nodes = parse_fig(fig)
    route_nodes_by_sub: dict[int, list[int]] = {}
    for node in nodes.values():
        if node.op == "route" and node.object_id is not None:
            route_nodes_by_sub.setdefault(node.object_id, []).append(node.node_id)

    scopes: list[ReservoirScope] = []
    for station_id in station_ids:
        upstream_ids = upstream_closure(nodes, route_nodes_by_sub.get(station_id, []))
        for node in nodes.values():
            if node.op != "routres":
                continue
            res_file = next((file for file in node.files if file.lower().endswith(".res")), "")
            if not res_file:
                continue
            res_path = project / res_file
            local_sub = None
            upstream_id = node.upstream_ids[0] if node.upstream_ids else None
            upstream_node = nodes.get(upstream_id) if upstream_id is not None else None
            if upstream_node and upstream_node.op == "route":
                local_sub = upstream_node.object_id
            if local_sub is None:
                local_sub = reservoir_file_subbasin(res_file)
            selector_value = None
            if res_path.exists():
                scalar = read_res_scalar(res_path, "RES_SUB")
                selector_value = int(scalar) if scalar is not None else None
            selector_value = selector_value or local_sub or reservoir_file_subbasin(res_file)
            if selector_value is None:
                continue
            if node.node_id in upstream_ids:
                relation = "local" if local_sub == station_id else "upstream"
                scopes.append(
                    ReservoirScope(
                        station_id=station_id,
                        relation=relation,
                        res_file=res_file,
                        selector=selector_value,
                        local_subbasin=local_sub,
                        res_node_id=node.node_id,
                        upstream_node_id=upstream_id,
                    )
                )
    return sorted(set(scopes), key=lambda item: (item.station_id, item.relation, item.res_file))


def station_ids_from_observed(project: Path, observed_path: Path | None = None) -> list[int]:
    observed = read_observed_blocks(observed_path or project / "SUFI2.IN" / "observed_rch.txt")
    station_ids: list[int] = []
    for name in observed:
        match = re.fullmatch(r"FLOW_OUT_(\d+)", name)
        if match:
            station_ids.append(int(match.group(1)))
    return sorted(set(station_ids))


def bounded_range(value: float, lo: float, hi: float, min_span: float = 0.0) -> tuple[float, float]:
    lo = min(value, lo)
    hi = max(value, hi)
    if min_span and hi - lo < min_span:
        half = min_span / 2.0
        lo = value - half
        hi = value + half
    return lo, hi


def conservative_res_parameter_rows(project: Path, scopes: list[ReservoirScope]) -> list[tuple[str, float, float]]:
    rows: list[tuple[str, float, float]] = []
    seen_files: set[str] = set()
    for scope in scopes:
        if scope.res_file in seen_files:
            continue
        seen_files.add(scope.res_file)
        res_path = project / scope.res_file
        if not res_path.exists():
            continue
        selector = scope.selector
        res_rr = read_res_scalar(res_path, "RES_RR")
        if res_rr is not None and res_rr > 0:
            center = min(res_rr, 500.0)
            rows.append((f"v__RES_RR.res________{selector}", max(0.0, center * 0.75), min(500.0, center * 1.25)))

        ndtargr = read_res_scalar(res_path, "NDTARGR")
        if ndtargr is not None and ndtargr > 0:
            rows.append((f"v__NDTARGR.res________{selector}", max(1.0, ndtargr * 0.70), min(365.0, ndtargr * 1.30)))

        evrsv = read_res_scalar(res_path, "EVRSV")
        if evrsv is not None:
            rows.append((f"v__EVRSV.res________{selector}", max(0.30, evrsv - 0.10), min(1.00, evrsv + 0.10)))

        res_k = read_res_scalar(res_path, "RES_K")
        if res_k is not None:
            if res_k == 0:
                rows.append((f"v__RES_K.res________{selector}", 0.0, 0.05))
            else:
                rows.append((f"v__RES_K.res________{selector}", max(0.0, res_k * 0.50), min(1.0, res_k * 2.0)))

        starg = read_res_array(res_path, "STARG")
        pvol = read_res_scalar(res_path, "RES_PVOL") or 0.0
        evol = read_res_scalar(res_path, "RES_EVOL") or 0.0
        for month, value in enumerate(starg, start=1):
            if value <= 0:
                continue
            lower = max(0.0, value * 0.90)
            upper = value * 1.10
            if 0 < pvol * 0.60 <= value:
                lower = max(lower, pvol * 0.60)
            if evol >= value:
                upper = min(upper, evol)
            rows.append((f"v__STARG({month}).res________{selector}", lower, upper))

        wuresn = read_res_array(res_path, "WURESN")
        nonzero_wuresn = [(index + 1, value) for index, value in enumerate(wuresn) if value > 0]
        for month, value in nonzero_wuresn:
            rows.append((f"v__WURESN({month}).res________{selector}", max(0.0, value * 0.70), value * 1.30))
        if nonzero_wuresn:
            wurtnf = read_res_scalar(res_path, "WURTNF")
            if wurtnf is not None:
                rows.append((f"v__WURTNF.res________{selector}", max(0.0, wurtnf - 0.20), min(1.0, wurtnf + 0.20)))

        oflow_min = read_res_array(res_path, "OFLOWMN")
        oflow_max = read_res_array(res_path, "OFLOWMX")
        for month, (minimum, maximum) in enumerate(zip(oflow_min, oflow_max), start=1):
            if minimum > 0 and maximum > 0 and minimum <= maximum:
                midpoint = (minimum + maximum) / 2.0
                rows.append(
                    (
                        f"v__OFLOWMN({month}).res________{selector}",
                        minimum * 0.75,
                        min(minimum * 1.25, midpoint),
                    )
                )
                rows.append(
                    (
                        f"v__OFLOWMX({month}).res________{selector}",
                        max(maximum * 0.75, midpoint),
                        maximum * 1.25,
                    )
                )
            elif minimum > 0 and maximum == 0:
                rows.append(
                    (f"v__OFLOWMN({month}).res________{selector}", minimum * 0.75, minimum * 1.25)
                )
            elif maximum > 0 and minimum == 0:
                rows.append(
                    (f"v__OFLOWMX({month}).res________{selector}", maximum * 0.75, maximum * 1.25)
                )
    return rows


def apply_parameters(project: Path, params: list[Parameter]) -> dict[str, int]:
    backup = project / "DirectBase"
    if not backup.exists():
        backup = project / "Backup"
    if not backup.exists():
        raise FileNotFoundError(f"Missing baseline directory: {backup}")
    counts: dict[str, int] = {}
    files_by_param: list[tuple[Parameter, list[Path]]] = []
    restore_paths: dict[Path, Path] = {}

    for param in params:
        files = target_files(project, param)
        files_by_param.append((param, files))
        for path in files:
            if not path.exists():
                raise FileNotFoundError(path)
            backup_path = backup / path.name
            if not backup_path.exists():
                raise FileNotFoundError(backup_path)
            restore_paths[path] = backup_path

    # Restore only the files touched by the active parameter set. Restoring
    # every editable file causes severe disk contention with several workers.
    for path, backup_path in restore_paths.items():
        shutil.copyfile(backup_path, path)

    for param, files in files_by_param:
        edited = 0
        for path in files:
            backup_path = backup / path.name
            if param.extension == "sol":
                edited += edit_sol_parameter(path, backup_path, param)
            elif param.extension == "res":
                edited += edit_res_parameter(path, backup_path, param)
            elif param.extension == "wus":
                edited += edit_wus_parameter(path, backup_path, param)
            else:
                edited += edit_pipe_parameter(path, backup_path, param)
        counts[param.raw_name] = edited
        if edited == 0:
            raise RuntimeError(f"No fields edited for {param.raw_name}")

    (project / "direct_edit_log.txt").write_text(
        "\n".join(f"{name}\t{count}" for name, count in counts.items()) + "\n",
        encoding="utf-8",
    )
    return counts


def clear_sufi2_out(project: Path) -> None:
    out_dir = project / "SUFI2.OUT"
    out_dir.mkdir(exist_ok=True)
    for path in out_dir.iterdir():
        if path.is_file():
            path.unlink()


def clear_swat_outputs(project: Path) -> None:
    patterns = (
        "output.*",
        "input.std",
        "fin.fin",
        "watout.dat",
        "hyd.out",
        "chan.deg",
        "bmp-*.out",
        "septic.out",
        "swat_output.txt",
    )
    for pattern in patterns:
        for path in project.glob(pattern):
            if path.is_file():
                path.unlink()


def run_program(project: Path, exe: str, log_name: str) -> None:
    with (project / log_name).open("w", encoding="utf-8", errors="ignore") as log:
        result = subprocess.run(
            [str(project / exe)],
            cwd=project,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            errors="ignore",
            timeout=1800,
        )
    if result.returncode != 0:
        raise RuntimeError(f"{exe} failed with exit code {result.returncode}; see {project / log_name}")


def run_model(project: Path) -> None:
    clear_sufi2_out(project)
    clear_swat_outputs(project)
    run_program(project, "swat.exe", "direct_swat.log")
    run_program(project, "SUFI2_extract_rch.exe", "direct_extract.log")


def read_simulated_series(path: Path) -> list[float]:
    values: list[float] = []
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) == 1:
            continue
        if len(parts) >= 2 and parts[0].isdigit():
            values.append(float(parts[1]))
    return values


def read_observed_blocks(path: Path) -> dict[str, list[tuple[int, float]]]:
    lines = path.read_text(errors="ignore").splitlines()
    blocks: dict[str, list[tuple[int, float]]] = {}
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]+)\s+:", line)
        if not match:
            idx += 1
            continue

        name = match.group(1)
        idx += 1
        while idx < len(lines) and not re.match(r"^\s*\d+\s*: number of data points", lines[idx]):
            idx += 1
        if idx >= len(lines):
            break
        count = int(lines[idx].split()[0])
        idx += 2
        data: list[tuple[int, float]] = []
        while idx < len(lines) and len(data) < count:
            parts = lines[idx].split()
            if len(parts) >= 3 and parts[0].isdigit():
                data.append((int(parts[0]), float(parts[2])))
            idx += 1
        blocks[name] = data
    return blocks


PROCESS_METRIC_KEYS = (
    "r2", "nse", "kge", "pbias", "r", "log_nse", "clim_r",
    "best_lag_months", "best_lag_r", "peak_offset_months",
    "peak_capture", "lowflow_ratio", "sim_zero_fraction",
)


def _corr(obs: list[float], sim: list[float]) -> float:
    if len(obs) < 3 or len(obs) != len(sim):
        return float("nan")
    mean_o = sum(obs) / len(obs)
    mean_s = sum(sim) / len(sim)
    ss_obs = sum((x - mean_o) ** 2 for x in obs)
    ss_sim = sum((x - mean_s) ** 2 for x in sim)
    cov = sum((o - mean_o) * (s - mean_s) for o, s in zip(obs, sim))
    return cov / math.sqrt(ss_obs * ss_sim) if ss_obs > 0 and ss_sim > 0 else float("nan")


def _nse(obs: list[float], sim: list[float]) -> float:
    mean_o = sum(obs) / len(obs)
    den = sum((x - mean_o) ** 2 for x in obs)
    return 1.0 - sum((o - s) ** 2 for o, s in zip(obs, sim)) / den if den > 0 else float("nan")


def metrics(
    obs: list[float],
    sim: list[float],
    years: list[int] | None = None,
    months: list[int] | None = None,
) -> dict[str, float]:
    n = len(obs)
    if n == 0 or n != len(sim):
        raise ValueError(f"Series length mismatch: obs={len(obs)} sim={len(sim)}")

    mean_o = sum(obs) / n
    mean_s = sum(sim) / n
    ss_obs = sum((x - mean_o) ** 2 for x in obs)
    ss_sim = sum((x - mean_s) ** 2 for x in sim)
    cov = sum((o - mean_o) * (s - mean_s) for o, s in zip(obs, sim))
    r = cov / math.sqrt(ss_obs * ss_sim) if ss_obs > 0 and ss_sim > 0 else 0.0
    nse = 1.0 - sum((o - s) ** 2 for o, s in zip(obs, sim)) / ss_obs if ss_obs > 0 else float("nan")
    alpha = math.sqrt(ss_sim / ss_obs) if ss_obs > 0 else float("nan")
    beta = mean_s / mean_o if mean_o != 0 else float("nan")
    kge = 1.0 - math.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2)
    pbias = 100.0 * sum(s - o for o, s in zip(obs, sim)) / sum(obs) if sum(obs) != 0 else float("nan")
    log_nse = _nse([math.log1p(max(0.0, x)) for x in obs], [math.log1p(max(0.0, x)) for x in sim])
    months = months or [i % 12 + 1 for i in range(n)]
    years = years or [i // 12 for i in range(n)]
    if len(months) != n or len(years) != n:
        raise ValueError(f"Date length mismatch: values={n} months={len(months)} years={len(years)}")
    climatology_months = [month for month in range(1, 13) if month in months]
    obs_clim = [
        sum(o for o, m in zip(obs, months) if m == month) / sum(1 for m in months if m == month)
        for month in climatology_months
    ]
    sim_clim = [
        sum(s for s, m in zip(sim, months) if m == month) / sum(1 for m in months if m == month)
        for month in climatology_months
    ]

    best_lag = 0
    best_lag_r = -2.0
    for lag in range(-3, 4):
        if lag > 0:
            lag_r = _corr(obs[:-lag], sim[lag:])
        elif lag < 0:
            lag_r = _corr(obs[-lag:], sim[:lag])
        else:
            lag_r = r
        if math.isfinite(lag_r) and (
            lag_r > best_lag_r + 1e-12
            or (abs(lag_r - best_lag_r) <= 1e-12 and abs(lag) < abs(best_lag))
        ):
            best_lag, best_lag_r = lag, lag_r

    offsets: list[int] = []
    for year in sorted(set(years)):
        indices = [i for i, y in enumerate(years) if y == year]
        if not indices:
            continue
        oi = max(indices, key=lambda i: obs[i])
        si = max(indices, key=lambda i: sim[i])
        raw = abs(months[oi] - months[si])
        offsets.append(min(raw, 12 - raw))
    offsets.sort()
    peak_offset = float(offsets[len(offsets) // 2]) if offsets else float("nan")

    top_n = max(1, math.ceil(n * 0.10))
    ordered = sorted(range(n), key=lambda i: obs[i])
    high_indices = ordered[-top_n:]
    low_indices = ordered[:top_n]
    high_obs = sum(obs[i] for i in high_indices)
    peak_capture = sum(sim[i] for i in high_indices) / high_obs if high_obs else float("nan")
    low_obs = sum(obs[i] for i in low_indices) / top_n
    lowflow_ratio = (sum(sim[i] for i in low_indices) / top_n) / low_obs if low_obs else float("nan")

    return {
        "r2": r * r,
        "nse": nse,
        "kge": kge,
        "pbias": pbias,
        "r": r,
        "log_nse": log_nse,
        "clim_r": _corr(obs_clim, sim_clim),
        "best_lag_months": float(best_lag),
        "best_lag_r": best_lag_r,
        "peak_offset_months": peak_offset,
        "peak_capture": peak_capture,
        "lowflow_ratio": lowflow_ratio,
        "sim_zero_fraction": sum(1 for x in sim if x <= 1e-10) / n,
    }


def evaluate_outputs(project: Path, observed_path: Path | None = None) -> dict[str, dict[str, float]]:
    observed = read_observed_blocks(observed_path or project / "SUFI2.IN" / "observed_rch.txt")
    result: dict[str, dict[str, float]] = {}
    for name, pairs in observed.items():
        sim_all = read_simulated_series(project / "SUFI2.OUT" / f"{name}.txt")
        obs_values = [obs_value for _, obs_value in pairs]
        sim_values = sim_all
        if len(obs_values) != len(sim_values):
            raise ValueError(f"{name}: series length mismatch obs={len(obs_values)} sim={len(sim_values)}")
        years: list[int] = []
        months: list[int] = []
        for index, _obs_value in pairs:
            zero_index = index - 1
            years.append(zero_index // 12)
            months.append(zero_index % 12 + 1)
        result[name] = metrics(obs_values, sim_values, years=years, months=months)
    return result


def parse_variable_weights(value: str | None, variable_names: list[str]) -> dict[str, float]:
    weights = {name: 1.0 for name in variable_names}
    if not value:
        return weights
    for item in value.split(","):
        name, separator, raw_weight = item.strip().partition("=")
        if not separator or name not in weights:
            raise ValueError(f"Invalid --variable-weights item: {item!r}")
        weight = float(raw_weight)
        if not math.isfinite(weight) or weight <= 0.0:
            raise ValueError(f"Weight for {name} must be finite and positive")
        weights[name] = weight
    return weights


def combined_score(
    result: dict[str, dict[str, float]],
    variable_weights: dict[str, float] | None = None,
) -> float:
    """Return the configured weighted mean KGE across current observation blocks."""
    weights = variable_weights or {name: 1.0 for name in result}
    total_weight = sum(weights[name] for name in result)
    return sum(result[name]["kge"] * weights[name] for name in result) / total_weight


def multisite_timeseries_score(
    result: dict[str, dict[str, float]],
    variable_weights: dict[str, float] | None = None,
) -> float:
    """Weighted multi-variable score rewarding shape, timing, balance, and positive NSE."""
    weights = variable_weights or {name: 1.0 for name in result}
    station_scores: list[tuple[float, float]] = []
    negative_nse_penalty = 0.0
    total_weight = 0.0
    for name, row in result.items():
        weight = weights[name]
        kge_value = max(-1.5, min(1.0, row["kge"]))
        nse_value = max(-1.5, min(1.0, row["nse"]))
        r_value = max(-1.0, min(1.0, row["r"]))
        log_nse_value = max(-1.5, min(1.0, row["log_nse"]))
        clim_value = max(-1.0, min(1.0, row["clim_r"]))
        timing_penalty = min(abs(row["best_lag_months"]), 3.0) / 3.0
        peak_offset_penalty = min(row["peak_offset_months"], 6.0) / 6.0
        capture = max(0.05, min(20.0, row["peak_capture"]))
        capture_penalty = min(abs(math.log(capture)), 2.0) / 2.0
        zero_penalty = min(row["sim_zero_fraction"], 0.60) / 0.60
        station_scores.append((weight,
            0.35 * kge_value
            + 0.23 * nse_value
            + 0.12 * r_value
            + 0.12 * log_nse_value
            + 0.10 * clim_value
            - 0.025 * timing_penalty
            - 0.025 * peak_offset_penalty
            - 0.025 * capture_penalty
            - 0.025 * zero_penalty
        ))
        negative_nse_penalty += weight * max(0.0, -row["nse"])
        total_weight += weight
    mean_score = sum(weight * score for weight, score in station_scores) / total_weight
    worst_score = min(score for _weight, score in station_scores)
    return mean_score + 0.12 * worst_score - 0.30 * negative_nse_penalty / total_weight


def print_result(result: dict[str, dict[str, float]]) -> None:
    for name, row in result.items():
        print(
            f"{name}: R2={row['r2']:.4f} NSE={row['nse']:.4f} "
            f"KGE={row['kge']:.4f} PBIAS={row['pbias']:.2f}"
        )
    print(f"Equal-weight mean KGE={combined_score(result):.4f}")


def command_single(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    if args.model_in:
        params = parse_model_in(Path(args.model_in))
    else:
        if args.sim_id is None:
            raise ValueError("Supply --model-in or explicitly select --sim-id")
        names = [row[0] for row in parse_par_inf(project / "SUFI2.IN" / "par_inf.txt")]
        rows = parse_par_val(project / "SUFI2.IN" / "par_val.txt")
        row_map = {sim_id: values for sim_id, values in rows}
        if args.sim_id not in row_map:
            raise KeyError(f"sim_id {args.sim_id} not found in par_val.txt")
        params = params_from_names_values(names, row_map[args.sim_id])

    counts = apply_parameters(project, params)
    print("Edited fields:", sum(counts.values()))
    run_model(project)
    result = evaluate_outputs(project, Path(args.observed_rch).resolve() if args.observed_rch else None)
    print_result(result)


def sample_values(
    ranges: list[tuple[str, float, float]],
    center: list[float],
    scale: float,
    rng: random.Random | None = None,
) -> list[float]:
    rng = rng or random
    values: list[float] = []
    for (_, lo, hi), c in zip(ranges, center):
        c = max(lo, min(hi, c))
        span = (hi - lo) * scale
        a = max(lo, c - span)
        b = min(hi, c + span)
        values.append(rng.uniform(a, b))
    return values


def score_result(
    result: dict[str, dict[str, float]],
    score_mode: str,
    variable_weights: dict[str, float],
) -> float:
    if score_mode == "multisite_timeseries":
        return multisite_timeseries_score(result, variable_weights)
    return combined_score(result, variable_weights)


def metric_fieldnames(variable_names: list[str]) -> list[str]:
    names: list[str] = []
    for variable in variable_names:
        names.extend([f"{variable}_{key}" for key in PROCESS_METRIC_KEYS])
    return names


def flatten_result(
    run_id: int,
    score: float,
    values: list[float],
    result: dict[str, dict[str, float]],
    variable_names: list[str],
    elapsed: float,
    status: str,
    error: str,
) -> dict[str, float | int | str]:
    row: dict[str, float | int | str] = {
        "run": run_id,
        "status": status,
        "error": error,
        "score": score,
        "elapsed_seconds": elapsed,
    }
    for i, value in enumerate(values, start=1):
        row[f"par_{i}"] = value
    for variable in variable_names:
        metric_row = result.get(variable, {})
        for key in PROCESS_METRIC_KEYS:
            row[f"{variable}_{key}"] = metric_row.get(key, float("nan"))
    return row


def load_ranges_and_center(args: argparse.Namespace, project: Path) -> tuple[list[tuple[str, float, float]], list[str], list[float]]:
    project = Path(args.project).resolve()
    if not math.isfinite(args.scale) or args.scale <= 0.0:
        raise ValueError("--scale must be finite and positive")
    ranges = parse_par_inf(Path(args.par_inf).resolve()) if args.par_inf else parse_par_inf(project / "SUFI2.IN" / "par_inf.txt")
    names = [row[0] for row in ranges]
    if getattr(args, "center_zero", False):
        center = [0.0 for _ in ranges]
    elif args.center_model_in:
        center_values = parse_model_values(Path(args.center_model_in).resolve())
        center = [center_values.get(name, (lo + hi) / 2.0) for name, lo, hi in ranges]
    else:
        base_rows = parse_par_val(project / "SUFI2.IN" / "par_val.txt")
        center = dict(base_rows).get(args.center_sim)
        if center is None or len(center) != len(ranges):
            center = [(lo + hi) / 2.0 for _, lo, hi in ranges]
    return ranges, names, center


def run_sample_batch(
    project: Path,
    run_ids: list[int],
    ranges: list[tuple[str, float, float]],
    center: list[float],
    seed: int,
    scale: float,
    observed_path: Path | None,
    score_mode: str,
    variable_weights: dict[str, float],
    variable_names: list[str],
    series_dir: Path | None = None,
    progress: bool = False,
) -> list[dict[str, float | int | str]]:
    names = [row[0] for row in ranges]
    rows: list[dict[str, float | int | str]] = []
    for offset, run_id in enumerate(run_ids, start=1):
        rng = random.Random(seed + run_id * 104729)
        values = sample_values(ranges, center, scale, rng)
        params = params_from_names_values(names, values)
        started = time.time()
        status = "ok"
        error = ""
        try:
            apply_parameters(project, params)
            run_model(project)
            result = evaluate_outputs(project, observed_path)
            score = score_result(result, score_mode, variable_weights)
            if series_dir is not None:
                series_dir.mkdir(parents=True, exist_ok=True)
                series_rows: list[tuple[str, list[float]]] = []
                for variable in variable_names:
                    series_rows.append((variable, read_simulated_series(project / "SUFI2.OUT" / f"{variable}.txt")))
                series_length = max((len(values) for _, values in series_rows), default=0)
                series_path = series_dir / f"run_{run_id:04d}_series.csv"
                temporary_path = series_path.with_suffix(series_path.suffix + ".tmp")
                with temporary_path.open("w", newline="", encoding="utf-8") as series_handle:
                    series_writer = csv.writer(series_handle)
                    series_writer.writerow(["variable", *[f"t{i}" for i in range(1, series_length + 1)]])
                    for variable, values_row in series_rows:
                        series_writer.writerow([variable, *values_row])
                temporary_path.replace(series_path)
        except Exception as exc:
            result = {
                variable: {key: float("nan") for key in PROCESS_METRIC_KEYS}
                for variable in variable_names
            }
            score = -999.0
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            with (project / "direct_failed_runs.log").open("a", encoding="utf-8") as handle:
                handle.write(f"run={run_id}\t{error}\n")
        elapsed = time.time() - started
        rows.append(flatten_result(run_id, score, values, result, variable_names, elapsed, status, error))
        write_rows_csv(project / "direct_partial_results.csv", rows, names, variable_names)
        if progress:
            valid_kge = [row["kge"] for row in result.values() if math.isfinite(row["kge"])]
            mean_kge = sum(valid_kge) / len(valid_kge) if valid_kge else float("nan")
            print(
                f"run {offset}/{len(run_ids)} (global {run_id}): score={score:.4f} "
                f"mean_KGE={mean_kge:.4f} elapsed={elapsed:.1f}s",
                flush=True,
            )
    return rows


def copy_worker_project(source_project: Path, worker_root: Path, worker_index: int, refresh: bool) -> Path:
    if worker_root == source_project or source_project in worker_root.parents:
        raise ValueError(f"Worker directory must be outside the source project: {worker_root}")
    dest = worker_root / f"worker_{worker_index:02d}"
    if refresh and dest.exists():
        shutil.rmtree(dest)
    if not dest.exists():
        ignore = shutil.ignore_patterns(
            "SUFI2.OUT",
            "direct_*.log",
            "direct_edit_log.txt",
            "output.*",
            "swat_output.txt",
            "Iterations",
            "Calibration_Evidence",
            "Parameter_Ranges",
        )
        shutil.copytree(source_project, dest, ignore=ignore)
    (dest / "SUFI2.OUT").mkdir(exist_ok=True)
    return dest


def write_best_model(path: Path, names: list[str], row: dict[str, float | int | str]) -> None:
    values = [float(row[f"par_{i}"]) for i in range(1, len(names) + 1)]
    path.write_text(
        "\n".join(f"{name}     {value:.6f}" for name, value in zip(names, values)) + "\n",
        encoding="utf-8",
    )


def write_rows_csv(
    out_csv: Path,
    rows: list[dict[str, float | int | str]],
    names: list[str],
    variable_names: list[str],
) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["run", "status", "error", "score", "elapsed_seconds"] + [f"par_{i + 1}" for i in range(len(names))]
        fieldnames.extend(metric_fieldnames(variable_names))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def select_best_row(
    rows: list[dict[str, float | int | str]],
    variable_names: list[str],
    variable_weights: dict[str, float],
    min_station_nse: float | None,
    min_station_kge: float | None,
) -> tuple[dict[str, float | int | str], int]:
    successful = [row for row in rows if row.get("status") == "ok"]
    if not successful:
        raise RuntimeError(f"All {len(rows)} sample attempts failed")
    if min_station_nse is None and min_station_kge is None:
        return max(successful, key=lambda row: float(row["score"])), len(successful)

    feasible = [
        row for row in successful
        if all(
            (min_station_nse is None or float(row[f"{variable}_nse"]) >= min_station_nse)
            and (min_station_kge is None or float(row[f"{variable}_kge"]) >= min_station_kge)
            for variable in variable_names
        )
    ]
    if not feasible:
        raise RuntimeError("No successful run met every station threshold; no best_model.in was exported")

    def hierarchy(row: dict[str, float | int | str]) -> tuple[float, float, float, float]:
        kge_values = [float(row[f"{variable}_kge"]) for variable in variable_names]
        nse_values = [float(row[f"{variable}_nse"]) for variable in variable_names]
        weighted_mean_kge = sum(
            float(row[f"{variable}_kge"]) * variable_weights[variable]
            for variable in variable_names
        ) / sum(variable_weights.values())
        return (
            float(row["score"]),
            weighted_mean_kge,
            min(kge_values),
            min(nse_values),
        )

    return max(feasible, key=hierarchy), len(feasible)


def command_sample(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    if args.runs < 1 or args.workers < 1:
        raise ValueError("--runs and --workers must be positive")
    ranges, names, center = load_ranges_and_center(args, project)
    observed_path = Path(args.observed_rch).resolve() if args.observed_rch else None
    observed_for_names = observed_path or project / "SUFI2.IN" / "observed_rch.txt"
    variable_names = list(read_observed_blocks(observed_for_names).keys())
    variable_weights = parse_variable_weights(args.variable_weights, variable_names)
    print(
        "Variable weights: "
        + ", ".join(f"{name}={variable_weights[name]:g}" for name in variable_names)
    )
    out_csv = Path(args.out_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    series_dir = Path(args.series_dir).resolve() if args.series_dir else None
    best_path = out_csv.with_suffix(".best_model.in")
    if best_path.exists():
        best_path.unlink()
    max_attempts = args.max_attempts or args.runs
    if max_attempts < args.runs:
        raise ValueError("--max-attempts cannot be smaller than --runs")
    worker_root: Path | None = None
    retry_project = project

    if args.workers <= 1:
        rows = run_sample_batch(
            project,
            list(range(1, args.runs + 1)),
            ranges,
            center,
            args.seed,
            args.scale,
            observed_path,
            args.score_mode,
            variable_weights,
            variable_names,
            series_dir,
            progress=True,
        )
    else:
        if args.workers_dir:
            worker_root = Path(args.workers_dir).resolve()
        else:
            worker_root = out_csv.parent / f"{out_csv.stem}_workers"
            if worker_root == project or project in worker_root.parents:
                worker_root = project.parent / f"{project.name}_{out_csv.stem}_workers"
        worker_root.mkdir(parents=True, exist_ok=True)
        futures = []
        rows = []
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            for worker_index in range(1, args.workers + 1):
                run_ids = list(range(worker_index, args.runs + 1, args.workers))
                if not run_ids:
                    continue
                worker_project = copy_worker_project(project, worker_root, worker_index, args.refresh_workers)
                if worker_index == 1:
                    retry_project = worker_project
                futures.append(
                    executor.submit(
                        run_sample_batch,
                        worker_project,
                        run_ids,
                        ranges,
                        center,
                        args.seed,
                        args.scale,
                        observed_path,
                        args.score_mode,
                        variable_weights,
                        variable_names,
                        series_dir,
                        False,
                    )
                )
            for future in as_completed(futures):
                batch_rows = future.result()
                rows.extend(batch_rows)
                print(f"finished worker batch with {len(batch_rows)} runs", flush=True)
        rows.sort(key=lambda item: int(item["run"]))
    successful_count = sum(row.get("status") == "ok" for row in rows)
    while successful_count < args.runs and len(rows) < max_attempts:
        batch_size = min(args.runs - successful_count, max_attempts - len(rows))
        start_id = len(rows) + 1
        retry_rows = run_sample_batch(
            retry_project,
            list(range(start_id, start_id + batch_size)),
            ranges,
            center,
            args.seed,
            args.scale,
            observed_path,
            args.score_mode,
            variable_weights,
            variable_names,
            series_dir,
            progress=True,
        )
        rows.extend(retry_rows)
        successful_count = sum(row.get("status") == "ok" for row in rows)
        write_rows_csv(out_csv, rows, names, variable_names)

    failed_count = len(rows) - successful_count
    print(
        f"Sampling summary: attempted={len(rows)} succeeded={successful_count} "
        f"failed={failed_count} target={args.runs}",
        flush=True,
    )
    if args.cleanup_workers and worker_root is not None:
        shutil.rmtree(worker_root)

    write_rows_csv(out_csv, rows, names, variable_names)
    if successful_count < args.runs:
        raise RuntimeError(
            f"Only {successful_count}/{args.runs} successful runs after {len(rows)} attempts; "
            "fix logged failures or increase --max-attempts"
        )

    best_row, feasible_count = select_best_row(
        rows, variable_names, variable_weights, args.min_station_nse, args.min_station_kge
    )
    if args.min_station_nse is not None or args.min_station_kge is not None:
        print(f"Threshold-feasible runs={feasible_count}/{successful_count} successful")
        mean_kge = sum(
            float(best_row[f"{name}_kge"]) * variable_weights[name] for name in variable_names
        ) / sum(variable_weights.values())
        print(
            f"Selection hierarchy: thresholds passed; configured score={float(best_row['score']):.4f}; "
            f"weighted mean KGE={mean_kge:.4f}"
        )
    print(f"Best run={best_row['run']} score={float(best_row['score']):.4f}")
    for variable in variable_names:
        print(
            f"{variable}: R2={float(best_row[f'{variable}_r2']):.4f} "
            f"NSE={float(best_row[f'{variable}_nse']):.4f} "
            f"KGE={float(best_row[f'{variable}_kge']):.4f} "
            f"PBIAS={float(best_row[f'{variable}_pbias']):.2f}"
        )
    write_best_model(best_path, names, best_row)
    print(f"Best model.in: {best_path}")


def command_plan(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    ranges, names, center = load_ranges_and_center(args, project)
    if args.center_model_in:
        center_values = parse_model_values(Path(args.center_model_in).resolve())
        missing = [name for name in names if name not in center_values]
        if missing:
            raise ValueError(f"Center model is missing {len(missing)} active parameters: {missing[:5]}")
    out_par_val = Path(args.out_par_val).resolve()
    out_par_val.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    first_random_run = 1
    if args.center_model_in and args.runs >= 1:
        lines.append(f"{1:<8d}" + "".join(f"{value:14.6f}" for value in center))
        first_random_run = 2
    for run_id in range(first_random_run, args.runs + 1):
        values = sample_values(ranges, center, args.scale, random.Random(args.seed + run_id * 104729))
        lines.append(f"{run_id:<8d}" + "".join(f"{value:14.6f}" for value in values))
    out_par_val.write_text("\n".join(lines) + "\n", encoding="utf-8")
    suffix = " with exact center in row 1" if args.center_model_in else ""
    print(f"Wrote {args.runs} rows to {out_par_val}{suffix}")


def command_shrink(args: argparse.Namespace) -> None:
    if not math.isfinite(args.factor) or args.factor <= 0.0:
        raise ValueError("--factor must be finite and positive")
    par_inf = Path(args.par_inf).resolve()
    ranges = parse_par_inf(par_inf)
    best_row: dict[str, str] | None = None
    with Path(args.results_csv).resolve().open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if best_row is None:
                best_row = row
                continue
            current = float(row[args.score_column])
            best = float(best_row[args.score_column])
            if current > best:
                best_row = row
    if best_row is None:
        raise ValueError(f"No rows found in {args.results_csv}")

    replacement: dict[str, tuple[float, float]] = {}
    for index, (name, lo, hi) in enumerate(ranges, start=1):
        best_value = float(best_row[f"par_{index}"])
        half_span = (hi - lo) * args.factor
        replacement[name] = (max(lo, best_value - half_span), min(hi, best_value + half_span))

    out_lines: list[str] = []
    for line in par_inf.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in replacement:
            lo, hi = replacement[parts[0]]
            out_lines.append(f"{parts[0]}    {lo:.6f}    {hi:.6f}")
        else:
            out_lines.append(line)
    out_path = Path(args.out_par_inf).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote narrowed par_inf.txt to {out_path}")


def parse_station_arg(value: str | None) -> list[int]:
    if not value:
        return []
    station_ids: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = (int(part) for part in token.split("-", 1))
            station_ids.update(range(min(start, end), max(start, end) + 1))
        else:
            station_ids.add(int(token))
    return sorted(station_ids)


def command_reservoir_scope(args: argparse.Namespace) -> None:
    project = Path(args.project).resolve()
    observed_path = Path(args.observed_rch).resolve() if args.observed_rch else None
    station_ids = parse_station_arg(args.stations) or station_ids_from_observed(project, observed_path)
    if not station_ids:
        raise ValueError("No station ids supplied and no FLOW_OUT_* blocks found in observed_rch.txt")

    fig_path = Path(args.fig).resolve() if args.fig else project / "fig.fig"
    scopes = reservoir_scope(project, station_ids, fig_path)
    if scopes:
        print("station,relation,res_file,selector,local_subbasin,res_node,upstream_node")
        for scope in scopes:
            print(
                f"{scope.station_id},{scope.relation},{scope.res_file},{scope.selector},"
                f"{scope.local_subbasin if scope.local_subbasin is not None else ''},"
                f"{scope.res_node_id},{scope.upstream_node_id if scope.upstream_node_id is not None else ''}"
            )
    else:
        print("No local or upstream reservoirs found for requested stations.")

    rows = conservative_res_parameter_rows(project, scopes)
    if args.out_par_inf:
        if args.runs is None or args.runs < 1:
            raise ValueError("--runs must be positive when --out-par-inf is used")
        out_path = Path(args.out_par_inf).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"{len(rows):<9d}: Number of Parameters",
            f"{args.runs:<9d}: number of simulations",
            "",
        ]
        lines.extend(f"{name:<58} {lo:.6f}   {hi:.6f}" for name, lo, hi in rows)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote conservative reservoir par_inf rows to {out_path}")
    elif rows:
        print("")
        print("Conservative reservoir parameter rows:")
        for name, lo, hi in rows:
            print(f"{name:<58} {lo:.6f}   {hi:.6f}")


def add_sampling_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--center-sim", type=int)
    parser.add_argument("--center-model-in")
    parser.add_argument("--center-zero", action="store_true", help="Use zero as the center for relative/additive searches.")
    parser.add_argument("--par-inf")
    parser.add_argument("--scale", type=float, required=True)
    parser.add_argument("--seed", type=int, default=0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("single")
    single.add_argument("--project", required=True)
    single.add_argument("--sim-id", type=int)
    single.add_argument("--model-in")
    single.add_argument("--observed-rch")
    single.set_defaults(func=command_single)

    sample = sub.add_parser("sample")
    add_sampling_arguments(sample)
    sample.add_argument(
        "--score-mode",
        choices=["kge", "multisite_timeseries"],
        default="kge",
    )
    sample.add_argument(
        "--variable-weights",
        help="Optional comma-separated observation-block weights, for example NAME_A=2,NAME_B=1.",
    )
    sample.add_argument("--out-csv", required=True)
    sample.add_argument("--observed-rch")
    sample.add_argument("--workers", type=int, default=1)
    sample.add_argument("--workers-dir")
    sample.add_argument("--refresh-workers", action="store_true")
    sample.add_argument("--cleanup-workers", action="store_true")
    sample.add_argument("--series-dir", help="Optional directory for per-run hydrographs used to build 95PPU.")
    sample.add_argument(
        "--max-attempts",
        type=int,
        help="Maximum attempts used to obtain --runs successful simulations (default: same as --runs).",
    )
    sample.add_argument("--min-station-nse", type=float, help="Require every station to meet this NSE.")
    sample.add_argument("--min-station-kge", type=float, help="Require every station to meet this KGE.")
    sample.set_defaults(func=command_sample)

    plan = sub.add_parser("plan")
    add_sampling_arguments(plan)
    plan.add_argument("--out-par-val", required=True)
    plan.set_defaults(func=command_plan)

    shrink = sub.add_parser("shrink")
    shrink.add_argument("--par-inf", required=True)
    shrink.add_argument("--results-csv", required=True)
    shrink.add_argument("--out-par-inf", required=True)
    shrink.add_argument("--factor", type=float, required=True)
    shrink.add_argument("--score-column", default="score")
    shrink.set_defaults(func=command_shrink)

    reservoir_parser = sub.add_parser("reservoir-scope")
    reservoir_parser.add_argument("--project", required=True)
    reservoir_parser.add_argument("--stations", help="Comma/range station ids. Defaults to FLOW_OUT_* blocks in observed_rch.txt.")
    reservoir_parser.add_argument("--observed-rch")
    reservoir_parser.add_argument("--fig")
    reservoir_parser.add_argument("--out-par-inf")
    reservoir_parser.add_argument("--runs", type=int, help="Simulation count written to --out-par-inf.")
    reservoir_parser.set_defaults(func=command_reservoir_scope)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
