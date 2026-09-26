#!/usr/bin/env python3
"""Copy already-applied SWAT inputs into Backup and DirectBase."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from swatcup_auto_runner import parse_model_in, target_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--model-in", type=Path, required=True)
    parser.add_argument("--destinations", default="Backup,DirectBase")
    parser.add_argument(
        "--extensions",
        default="sol,wus,res",
        help="Only bake these direct-only extensions by default.",
    )
    parser.add_argument("--files", help="Optional comma-separated explicit root input filenames.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    project = args.project.resolve()
    parameters = parse_model_in(args.model_in.resolve())
    allowed_extensions = {value.strip().lower().lstrip(".") for value in args.extensions.split(",") if value.strip()}
    explicit_files = {value.strip() for value in args.files.split(",") if value.strip()} if args.files else None
    files: dict[str, Path] = {}
    for parameter in parameters:
        if parameter.extension not in allowed_extensions:
            continue
        for path in target_files(project, parameter):
            if explicit_files is None or path.name in explicit_files:
                files[path.name] = path
    if not files:
        raise ValueError("No direct-only input files matched --extensions/--files")
    if explicit_files is not None:
        unresolved = sorted(explicit_files - set(files))
        if unresolved:
            raise ValueError(f"Explicit files were not resolved from matching model parameters: {unresolved}")
    destinations = [value.strip() for value in args.destinations.split(",") if value.strip()]
    for directory_name in destinations:
        directory = project / directory_name
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        for name, source in files.items():
            destination = directory / name
            if not destination.exists():
                raise FileNotFoundError(destination)
            if not args.dry_run:
                shutil.copy2(source, destination)
    action = "would_sync" if args.dry_run else "synchronized"
    print(
        f"parameters={len(parameters)} direct_extensions={','.join(sorted(allowed_extensions))} "
        f"files={len(files)} {action} "
        f"destinations={','.join(destinations)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
