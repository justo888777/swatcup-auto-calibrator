#!/usr/bin/env python3
"""Check a SWAT-CUP GUI project and optional native-BAT smoke outputs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from swatcup_auto_runner import parse_par_inf, parse_par_val, read_observed_blocks


def first_ints(path: Path, count: int) -> list[int]:
    values: list[int] = []
    for line in path.read_text(errors="ignore").splitlines():
        match = re.match(r"\s*(\d+)", line)
        if match:
            values.append(int(match.group(1)))
        if len(values) == count:
            break
    return values


def has_windows_line_endings(path: Path) -> bool:
    data = path.read_bytes()
    return b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")


def native_blocks(path: Path) -> dict[int, int]:
    blocks: dict[int, int] = {}
    current: int | None = None
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) == 1 and parts[0].isdigit():
            current = int(parts[0])
            blocks[current] = 0
        elif current is not None and len(parts) >= 2 and parts[0].isdigit():
            blocks[current] += 1
    return blocks


def native_values(path: Path) -> dict[int, list[float]]:
    blocks: dict[int, list[float]] = {}
    current: int | None = None
    for line in path.read_text(errors="ignore").splitlines():
        parts = line.split()
        if len(parts) == 1 and parts[0].isdigit():
            current = int(parts[0])
            blocks[current] = []
        elif current is not None and len(parts) >= 2 and parts[0].isdigit():
            blocks[current].append(float(parts[1]))
    return blocks


def read_series_csv(path: Path) -> dict[str, list[float]]:
    rows: dict[str, list[float]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if row:
                rows[row[0]] = [float(value) for value in row[1:]]
    return rows


def active_bat_executables(project: Path) -> list[str]:
    names: set[str] = set()
    ignored = {"cmd.exe", "powershell.exe", "timeout.exe"}
    for bat_name in ("SUFI2_Pre.bat", "SUFI2_Run.bat", "SUFI2_Post.bat"):
        for line in (project / bat_name).read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("::") or stripped.lower().startswith("rem "):
                continue
            stripped = re.sub(r"%~dp0", "", stripped, flags=re.IGNORECASE)
            for match in re.finditer(r"([A-Za-z0-9_.-]+\.exe)\b", stripped, re.IGNORECASE):
                name = match.group(1)
                if name.lower() not in ignored:
                    names.add(name)
    return sorted(names, key=str.lower)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--source-project", type=Path, help="Compare native BAT bytes with an original project.")
    parser.add_argument("--smoke-out", type=Path)
    parser.add_argument("--smoke-runs", type=int, help="Required with --smoke-out; use the configured smoke-plan row count.")
    parser.add_argument("--expected-formal-runs", type=int)
    parser.add_argument("--best-series-csv", type=Path, help="Compare smoke run 1 with this verified process series.")
    parser.add_argument("--best-tolerance", type=float, default=1e-4)
    parser.add_argument("--require-empty-out", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.smoke_out and (args.smoke_runs is None or args.smoke_runs < 1):
        parser.error("--smoke-runs must be positive when --smoke-out is supplied")
    project = args.project.resolve()
    issues: list[str] = []
    warnings: list[str] = []
    required = [
        "SUFI2_Pre.bat", "SUFI2_Run.bat", "SUFI2_Post.bat", "Swat_Edit.exe",
        "SUFI2_execute.exe", "SUFI2.IN/par_inf.txt", "SUFI2.IN/par_val.txt",
        "SUFI2.IN/observed_rch.txt", "SUFI2_swEdit.def", "Backup", "Echo", "SUFI2.OUT",
    ]
    missing = [name for name in required if not (project / name).exists()]
    if missing:
        issues.append(f"Missing required paths: {missing}")

    checks: dict[str, object] = {"missing": missing}
    checks["direct_base_present"] = (project / "DirectBase").is_dir()
    if not checks["direct_base_present"]:
        warnings.append("DirectBase is absent; direct edits will fall back to Backup")
    if not missing:
        par_inf_path = project / "SUFI2.IN" / "par_inf.txt"
        par_val_path = project / "SUFI2.IN" / "par_val.txt"
        swedit_path = project / "SUFI2_swEdit.def"
        header = first_ints(par_inf_path, 2)
        ranges = parse_par_inf(par_inf_path)
        samples = parse_par_val(par_val_path)
        swedit = first_ints(swedit_path, 2)
        checks.update({
            "par_inf_header": header,
            "parameter_rows": len(ranges),
            "par_val_rows": len(samples),
            "swedit_range": swedit,
            "echo_files": len(list((project / "Echo").glob("*"))),
            "par_inf_crlf": has_windows_line_endings(par_inf_path),
            "par_val_crlf": has_windows_line_endings(par_val_path),
            "swedit_crlf": has_windows_line_endings(swedit_path),
        })
        referenced_executables = active_bat_executables(project)
        executable_candidates = set(referenced_executables) | {"Swat_Edit.exe", "SUFI2_execute.exe"}
        executable_status = {
            name: (project / name).is_file() and (project / name).stat().st_size > 0
            for name in sorted(executable_candidates, key=str.lower)
        }
        checks["referenced_executables_nonempty"] = executable_status
        if not all(executable_status.values()):
            issues.append(f"Missing or empty native executables: {[name for name, ok in executable_status.items() if not ok]}")
        swat_programs = [
            path.name for path in project.glob("swat*.exe")
            if path.name.lower() != "swat_edit.exe" and path.stat().st_size > 0
        ]
        extract_programs = [path.name for path in project.glob("SUFI2*extr*.exe") if path.stat().st_size > 0]
        checks["swat_programs"] = swat_programs
        checks["extract_programs"] = extract_programs
        if not swat_programs:
            issues.append("No non-empty SWAT model executable found")
        if not extract_programs:
            issues.append("No non-empty SUFI2 extraction executable found")
        if len(header) != 2:
            issues.append("Cannot read parameter/simulation counts from par_inf.txt")
        else:
            parameter_count, simulation_count = header
            if len(ranges) != parameter_count:
                issues.append(f"par_inf declares {parameter_count} parameters but has {len(ranges)} rows")
            if len(samples) != simulation_count:
                issues.append(f"par_inf declares {simulation_count} simulations but par_val has {len(samples)} rows")
            if samples and any(len(values) != parameter_count for _, values in samples):
                issues.append("At least one par_val row has the wrong parameter count")
            if samples and [run for run, _ in samples] != list(range(1, simulation_count + 1)):
                issues.append("par_val run ids are not continuous from 1 to the declared simulation count")
            if swedit != [1, simulation_count]:
                issues.append(f"SUFI2_swEdit.def range {swedit} does not match 1..{simulation_count}")
            if args.expected_formal_runs is not None and simulation_count != args.expected_formal_runs:
                issues.append(
                    f"Formal simulation count={simulation_count}, expected={args.expected_formal_runs}"
                )
        if not checks["par_inf_crlf"] or not checks["par_val_crlf"] or not checks["swedit_crlf"]:
            issues.append("par_inf.txt, par_val.txt, and SUFI2_swEdit.def must use Windows CRLF")

        observed = read_observed_blocks(project / "SUFI2.IN" / "observed_rch.txt")
        checks["observed_variables"] = {name: len(rows) for name, rows in observed.items()}
        if args.require_empty_out and any((project / "SUFI2.OUT").iterdir()):
            issues.append("Formal SUFI2.OUT is not empty")

        if args.source_project:
            source = args.source_project.resolve()
            bat_equal = {
                name: (project / name).read_bytes() == (source / name).read_bytes()
                for name in ("SUFI2_Pre.bat", "SUFI2_Run.bat", "SUFI2_Post.bat")
            }
            checks["native_bat_bytes_match_source"] = bat_equal
            if not all(bat_equal.values()):
                issues.append("One or more native BAT files differ from the source project")

        if args.smoke_out:
            smoke_out = args.smoke_out.resolve()
            for name in ("goal.txt", "95ppu.txt", "95ppu_g.txt"):
                if not (smoke_out / name).is_file() or (smoke_out / name).stat().st_size == 0:
                    issues.append(f"Smoke Post output missing or empty: {name}")
            expected_blocks = set(range(1, args.smoke_runs + 1))
            shapes: dict[str, dict[int, int]] = {}
            best_series = read_series_csv(args.best_series_csv.resolve()) if args.best_series_csv else None
            first_run_differences: dict[str, float] = {}
            for variable, observations in observed.items():
                path = smoke_out / f"{variable}.txt"
                if not path.exists():
                    issues.append(f"Smoke output missing {path.name}")
                    continue
                blocks = native_blocks(path)
                shapes[variable] = blocks
                if set(blocks) != expected_blocks or any(count != len(observations) for count in blocks.values()):
                    issues.append(f"Smoke output shape mismatch for {variable}: {blocks}")
                if best_series is not None:
                    if variable not in best_series:
                        issues.append(f"Verified best series is missing {variable}")
                        continue
                    smoke_first = native_values(path).get(1, [])
                    expected = best_series[variable]
                    if len(smoke_first) != len(expected):
                        issues.append(f"Smoke/best series length mismatch for {variable}")
                        continue
                    maximum = max((abs(actual - target) for actual, target in zip(smoke_first, expected)), default=0.0)
                    first_run_differences[variable] = maximum
                    scale = max([1.0, *[abs(value) for value in expected]])
                    if maximum > args.best_tolerance * scale:
                        issues.append(
                            f"Smoke run 1 differs from verified best for {variable}: max_abs={maximum:.6g}"
                        )
            checks["smoke_shapes"] = shapes
            if best_series is not None:
                checks["smoke_run1_max_abs_difference"] = first_run_differences
    if (project / "SUFI2.OUT").is_dir() and not any((project / "SUFI2.OUT").iterdir()):
        warnings.append("SUFI2.OUT is empty, which is correct for a clean formal delivery")

    receipt = {"ok": not issues, "project": str(project), "checks": checks, "warnings": warnings, "issues": issues}
    text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if args.strict and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
