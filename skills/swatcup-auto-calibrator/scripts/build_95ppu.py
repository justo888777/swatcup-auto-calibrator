#!/usr/bin/env python3
"""Build process metrics and station-specific 95PPU charts from saved runs."""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit(
        'build_95ppu.py requires NumPy and Pillow; install with: python -m pip install -e ".[ppu]"'
    ) from exc

from swatcup_auto_runner import metrics, read_simulated_series


DATA_RE = re.compile(r"^\s*(\d+)\s+(\S+)\s+([-+0-9.eE]+)\s*$")
VARIABLE_RE = re.compile(r"^\s*(\S+)\s*:\s*this is the name of the variable", re.IGNORECASE)
RUN_RE = re.compile(r"run_(\d+)_series\.csv$", re.IGNORECASE)


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def read_observed(path: Path) -> dict[str, dict[str, list[float] | list[int]]]:
    result: dict[str, dict[str, list[float] | list[int]]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        variable_match = VARIABLE_RE.match(line)
        if variable_match:
            current = variable_match.group(1)
            result[current] = {"values": [], "months": [], "years": []}
            continue
        data_match = DATA_RE.match(line)
        if current is None or not data_match:
            continue
        label = data_match.group(2)
        parts = label.rsplit("_", 2)
        if len(parts) == 3 and parts[-2].isdigit() and parts[-1].isdigit():
            month, year = int(parts[-2]), int(parts[-1])
        else:
            index = int(data_match.group(1)) - 1
            month, year = index % 12 + 1, index // 12
        result[current]["values"].append(float(data_match.group(3)))
        result[current]["months"].append(month)
        result[current]["years"].append(year)
    if not result or any(not row["values"] for row in result.values()):
        raise ValueError(f"No complete observed blocks found in {path}")
    return result


def read_series_csv(path: Path) -> dict[str, np.ndarray]:
    rows: dict[str, np.ndarray] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if row:
                rows[row[0]] = np.asarray([float(value) for value in row[1:]], dtype=float)
    return rows


def read_final(args: argparse.Namespace, variables: list[str]) -> dict[str, np.ndarray]:
    if args.final_series_csv:
        rows = read_series_csv(args.final_series_csv)
        return {name: rows[name] for name in variables}
    return {
        name: np.asarray(read_simulated_series(args.final_sim_dir / f"{name}.txt"), dtype=float)
        for name in variables
    }


def successful_run_ids(path: Path) -> set[int]:
    result: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if not row.get("run"):
                continue
            ok = row.get("status") == "ok" if "status" in row else float(row.get("score", "-999")) > -999.0
            if ok:
                result.add(int(row["run"]))
    return result


def load_ensemble(
    root: Path,
    pattern: str,
    variables: list[str],
    expected_lengths: dict[str, int],
    limit: int | None,
    allowed_ids: set[int] | None,
    expected_samples: int | None,
) -> tuple[dict[str, np.ndarray], list[int]]:
    collected: dict[str, list[np.ndarray]] = {name: [] for name in variables}
    indexed_paths: list[tuple[int, Path]] = []
    for path in sorted(root.rglob(pattern)):
        match = RUN_RE.search(path.name)
        if not match:
            raise ValueError(f"Cannot extract run id from {path}")
        run_id = int(match.group(1))
        if allowed_ids is None or run_id in allowed_ids:
            indexed_paths.append((run_id, path))
    if limit:
        indexed_paths = indexed_paths[:limit]
    run_ids = [run_id for run_id, _ in indexed_paths]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run ids found; use one clean ensemble directory")
    for run_id, path in indexed_paths:
        rows = read_series_csv(path)
        missing_variables = [name for name in variables if name not in rows]
        if missing_variables:
            raise ValueError(f"run {run_id} is incomplete; missing {missing_variables}")
        for name in variables:
            if len(rows[name]) != expected_lengths[name]:
                raise ValueError(
                    f"run {run_id} {name} length={len(rows[name])}, expected={expected_lengths[name]}"
                )
            collected[name].append(rows[name])
    if allowed_ids is not None and limit is None:
        missing_ids = sorted(allowed_ids - set(run_ids))
        if missing_ids:
            raise ValueError(f"Missing series files for successful runs: {missing_ids[:10]}")
    if expected_samples is not None and len(run_ids) != expected_samples:
        raise ValueError(f"Complete ensemble count={len(run_ids)}, expected={expected_samples}")
    missing = [name for name, rows in collected.items() if not rows]
    if missing:
        raise ValueError(f"No ensemble series found for: {', '.join(missing)}")
    return {name: np.vstack(rows) for name, rows in collected.items()}, run_ids


def points(values: np.ndarray, box: tuple[int, int, int, int], ymax: float) -> list[tuple[int, int]]:
    left, top, right, bottom = box
    count = len(values)
    if count < 2:
        return [(left, bottom)]
    return [
        (
            round(left + i * (right - left) / (count - 1)),
            round(bottom - float(value) / ymax * (bottom - top)),
        )
        for i, value in enumerate(values)
    ]


def draw_panel(
    draw: ImageDraw.ImageDraw,
    outer: tuple[int, int, int, int],
    years: np.ndarray,
    obs: np.ndarray,
    final: np.ndarray,
    low: np.ndarray,
    median: np.ndarray,
    high: np.ndarray,
    title: str,
    compact: bool,
) -> None:
    left, top, right, bottom = outer
    plot = (left + 68, top + 42, right - 14, bottom - 42)
    ymax = max(float(np.max(obs)), float(np.max(final)), float(np.max(high)), 1e-9) * 1.06
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = round(plot[3] - fraction * (plot[3] - plot[1]))
        draw.line((plot[0], y, plot[2], y), fill="#dfe5ea", width=1)
        draw.text((left + 3, y - 8), f"{fraction * ymax:.2g}", fill="#5d6973", font=font(11 if compact else 13))
    low_points = points(low, plot, ymax)
    high_points = points(high, plot, ymax)
    draw.polygon(high_points + list(reversed(low_points)), fill="#cfe8f6")
    draw.line(points(median, plot, ymax), fill="#e6952c", width=2)
    draw.line(points(final, plot, ymax), fill="#2474b5", width=2)
    draw.line(points(obs, plot, ymax), fill="#111111", width=2)
    draw.rectangle(plot, outline="#7d8790", width=1)
    tick_indices = sorted({0, len(years) // 3, 2 * len(years) // 3, len(years) - 1})
    for index in tick_indices:
        x = round(plot[0] + index * (plot[2] - plot[0]) / max(1, len(years) - 1))
        draw.text((x - 16, plot[3] + 8), str(int(years[index])), fill="#5d6973", font=font(10 if compact else 12))
    draw.text((left + 5, top + 5), title, fill="#18232d", font=font(14 if compact else 18, bold=True))


def draw_legend(draw: ImageDraw.ImageDraw, x: int, y: int, text_size: int = 14) -> None:
    items = [
        ("#111111", "Observed", False),
        ("#2474b5", "Final", False),
        ("#e6952c", "P50", False),
        ("#cfe8f6", "95PPU", True),
    ]
    for color, label, filled in items:
        if filled:
            draw.rectangle((x, y - 5, x + 34, y + 7), fill=color, outline="#9bb5c5")
        else:
            draw.line((x, y, x + 34, y), fill=color, width=3)
        draw.text((x + 42, y - 9), label, fill="#26313a", font=font(text_size))
        x += 120


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observed", type=Path, required=True)
    final_group = parser.add_mutually_exclusive_group(required=True)
    final_group.add_argument("--final-series-csv", type=Path)
    final_group.add_argument("--final-sim-dir", type=Path)
    parser.add_argument("--ensemble-dir", type=Path, required=True)
    parser.add_argument("--glob", default="run_*_series.csv")
    parser.add_argument("--max-ensemble", type=int)
    parser.add_argument("--results-csv", type=Path, help="Use only run ids marked successful in this sample CSV.")
    parser.add_argument("--expected-samples", type=int, help="Fail unless this many complete runs are loaded.")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    observed = read_observed(args.observed)
    variables = list(observed)
    final = read_final(args, variables)
    expected_lengths = {name: len(observed[name]["values"]) for name in variables}
    allowed_ids = successful_run_ids(args.results_csv) if args.results_csv else None
    ensemble, ensemble_run_ids = load_ensemble(
        args.ensemble_dir,
        args.glob,
        variables,
        expected_lengths,
        args.max_ensemble,
        allowed_ids,
        args.expected_samples,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    panels: list[tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, float], float, float]] = []
    for name in variables:
        obs = np.asarray(observed[name]["values"], dtype=float)
        months = np.asarray(observed[name]["months"], dtype=int)
        years = np.asarray(observed[name]["years"], dtype=int)
        sim = final[name]
        samples = ensemble[name]
        if len(sim) != len(obs) or samples.shape[1] != len(obs):
            raise ValueError(f"{name}: obs={len(obs)} final={len(sim)} ensemble={samples.shape}")
        low, median, high = np.quantile(samples, [0.025, 0.5, 0.975], axis=0)
        p_factor = float(np.mean((obs >= low) & (obs <= high)))
        obs_std = float(np.std(obs))
        r_factor = float(np.mean(high - low) / obs_std) if obs_std else math.nan
        row_metrics = metrics(obs.tolist(), sim.tolist(), years=years.tolist(), months=months.tolist())
        station = name.rsplit("_", 1)[-1]
        summary = {
            "variable": name,
            "station": station,
            "ensemble_samples": len(ensemble_run_ids),
            "p_factor": p_factor,
            "r_factor": r_factor,
            "obs_above_95ppu_fraction": float(np.mean(obs > high)),
            "obs_below_95ppu_fraction": float(np.mean(obs < low)),
            **row_metrics,
        }
        summaries.append(summary)
        panels.append((name, years, obs, sim, low, median, high, row_metrics, p_factor, r_factor))

        image = Image.new("RGB", (1800, 850), "white")
        draw = ImageDraw.Draw(image)
        title = (
            f"{name} | KGE {row_metrics['kge']:.3f} | NSE {row_metrics['nse']:.3f} | "
            f"P {p_factor:.2f} | R {r_factor:.2f} | n={samples.shape[0]}"
        )
        draw_panel(draw, (20, 60, 1780, 830), years, obs, sim, low, median, high, title, compact=False)
        draw.text((30, 15), "Observed / final simulation / small-sample 95PPU", fill="#17202a", font=font(23, bold=True))
        draw_legend(draw, 1060, 34, 14)
        image.save(args.out_dir / f"{name}_95ppu.png")

    columns = min(3, max(1, len(panels)))
    rows = math.ceil(len(panels) / columns)
    overview = Image.new("RGB", (columns * 820, 80 + rows * 500), "white")
    draw = ImageDraw.Draw(overview)
    draw.text((30, 18), "Hydrograph and station-specific 95PPU overview", fill="#17202a", font=font(25, bold=True))
    draw_legend(draw, max(760, columns * 820 - 520), 35, 13)
    for position, panel in enumerate(panels):
        name, years, obs, sim, low, median, high, row_metrics, p_factor, r_factor = panel
        row, column = divmod(position, columns)
        x, y = column * 820 + 10, row * 500 + 75
        title = f"{name} | KGE {row_metrics['kge']:.2f} NSE {row_metrics['nse']:.2f} P {p_factor:.2f} R {r_factor:.2f}"
        draw_panel(draw, (x, y, x + 800, y + 470), years, obs, sim, low, median, high, title, compact=True)
    overview.save(args.out_dir / "all_stations_95ppu_overview.png")
    write_csv(args.out_dir / "process_and_95ppu_metrics.csv", summaries)

    for row in summaries:
        warning = " STRUCTURE/RANGE-CHECK" if float(row["p_factor"]) < 0.5 else ""
        print(
            f"{row['variable']}: KGE={row['kge']:.3f} NSE={row['nse']:.3f} "
            f"P={row['p_factor']:.3f} R={row['r_factor']:.3f} lag={row['best_lag_months']:+.0f}{warning}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
