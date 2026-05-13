from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + chunk_type + data + struct.pack("!I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)


def _write_png(path: Path, width: int, height: int, pixels: List[List[Tuple[int, int, int]]]) -> None:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b in row:
            raw.extend((r, g, b))
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(_chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0)))
    png.extend(_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)))
    png.extend(_chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(png))


def _blank_canvas(width: int = 900, height: int = 500) -> List[List[Tuple[int, int, int]]]:
    return [[(247, 244, 236) for _ in range(width)] for _ in range(height)]


def _draw_rect(canvas, x0, y0, x1, y1, color):
    height = len(canvas)
    width = len(canvas[0])
    for y in range(max(0, y0), min(height, y1)):
        row = canvas[y]
        for x in range(max(0, x0), min(width, x1)):
            row[x] = color


def _draw_line(canvas, x0, y0, x1, y1, color):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= y0 < len(canvas) and 0 <= x0 < len(canvas[0]):
            canvas[y0][x0] = color
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _plot_line_chart(path: Path, series_map: Dict[str, Sequence[float]], title_seed: int = 0) -> None:
    width, height = 900, 500
    canvas = _blank_canvas(width, height)
    colors = [(92, 74, 58), (32, 80, 120), (206, 98, 56), (72, 130, 96)]
    _draw_rect(canvas, 70, 40, 72, 430, (70, 70, 70))
    _draw_rect(canvas, 70, 428, 840, 430, (70, 70, 70))
    all_values = [value for series in series_map.values() for value in series]
    min_value = min(all_values) if all_values else 0.0
    max_value = max(all_values) if all_values else 1.0
    span = max(max_value - min_value, 1e-9)
    for idx, (name, series) in enumerate(series_map.items()):
        color = colors[idx % len(colors)]
        points = []
        length = max(len(series) - 1, 1)
        for index, value in enumerate(series):
            x = 80 + int((740 * index) / length)
            y = 420 - int(((value - min_value) / span) * 330)
            points.append((x, y))
        for start, end in zip(points, points[1:]):
            _draw_line(canvas, start[0], start[1], end[0], end[1], color)
        legend_y = 50 + (idx * 22)
        _draw_rect(canvas, 700, legend_y, 718, legend_y + 12, color)
        for letter_index, _ in enumerate(name[:10]):
            x = 724 + (letter_index * 8)
            y = legend_y + 2
            _draw_rect(canvas, x, y, x + 4, y + 8, (110 + title_seed, 110, 110))
    _write_png(path, width, height, canvas)


def _plot_bar_chart(path: Path, labels: Sequence[str], values: Sequence[float]) -> None:
    width, height = 900, 500
    canvas = _blank_canvas(width, height)
    colors = [(92, 74, 58), (32, 80, 120), (206, 98, 56), (72, 130, 96)]
    _draw_rect(canvas, 70, 40, 72, 430, (70, 70, 70))
    _draw_rect(canvas, 70, 428, 840, 430, (70, 70, 70))
    max_value = max(values) if values else 1.0
    for index, value in enumerate(values):
        spacing = max(120, int(680 / max(len(values), 1)))
        x0 = 110 + (index * spacing)
        x1 = x0 + min(110, max(55, spacing - 35))
        y1 = 420
        y0 = 420 - int((value / max(max_value, 1e-9)) * 300)
        _draw_rect(canvas, x0, y0, x1, y1, colors[index % len(colors)])
    _write_png(path, width, height, canvas)


def generate_figures(
    simulation_results: Dict[str, Dict[str, object]],
    comparison_rows: List[Dict[str, object]],
    project_root: Path,
) -> List[Path]:
    figures_dir = project_root / "outputs" / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    modes = ["nearest_available", "baseline", "smart_priority", "agentic_llm"]
    metrics = {
        "availability_over_time.png": "vehicle_availability",
        "unmet_demand_over_time.png": "cumulative_unmet_demand",
        "charger_utilization_over_time.png": "charger_utilization",
        "average_soc_over_time.png": "average_soc",
        "waiting_vehicles_over_time.png": "waiting_vehicle_hours",
    }
    written_paths: List[Path] = []
    for filename, metric in metrics.items():
        series_map = {mode: [row[metric] for row in simulation_results[mode]["timeseries"]] for mode in modes}
        path = figures_dir / filename
        _plot_line_chart(path, series_map, title_seed=len(metric))
        written_paths.append(path)

    cost_path = figures_dir / "cost_comparison.png"
    _plot_bar_chart(cost_path, modes, [row["total_charging_cost_eur"] for row in comparison_rows])
    written_paths.append(cost_path)

    score_path = figures_dir / "agentic_vs_heuristic_score.png"
    _plot_bar_chart(
        score_path,
        ["smart_priority", "agentic_llm"],
        [
            next(row["operational_score"] for row in comparison_rows if row["scheduler_mode"] == "smart_priority"),
            next(row["operational_score"] for row in comparison_rows if row["scheduler_mode"] == "agentic_llm"),
        ],
    )
    written_paths.append(score_path)

    breakdown_path = figures_dir / "agent_decision_breakdown.png"
    agentic_rows = simulation_results["agentic_llm"]["charging_plan"]
    accepted = len(agentic_rows)
    llm_actions = sum(1 for row in agentic_rows if row.get("llm_used"))
    fallback_actions = sum(1 for row in agentic_rows if row.get("fallback_used"))
    _plot_bar_chart(breakdown_path, ["accepted", "llm", "fallback"], [accepted, llm_actions, fallback_actions])
    written_paths.append(breakdown_path)
    return written_paths
