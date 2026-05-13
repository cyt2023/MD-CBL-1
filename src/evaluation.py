from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List


def _write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def evaluate_results(simulation_results: Dict[str, Dict[str, object]], project_root: Path) -> List[Dict[str, object]]:
    baseline_rows = simulation_results["baseline"]["timeseries"]
    baseline_cost = baseline_rows[-1]["cumulative_cost_eur"] if baseline_rows else 0.0
    baseline_unmet = baseline_rows[-1]["cumulative_unmet_demand"] if baseline_rows else 0
    nearest_rows = simulation_results.get("nearest_available", {}).get("timeseries", [])
    nearest_cost = nearest_rows[-1]["cumulative_cost_eur"] if nearest_rows else baseline_cost
    nearest_unmet = nearest_rows[-1]["cumulative_unmet_demand"] if nearest_rows else baseline_unmet
    summary_rows: List[Dict[str, object]] = []

    for mode, result in simulation_results.items():
        rows = result["timeseries"]
        total_cost = rows[-1]["cumulative_cost_eur"] if rows else 0.0
        total_energy = round(sum(row.get("charging_energy_kwh", 0.0) for row in rows), 3)
        total_unmet = rows[-1]["cumulative_unmet_demand"] if rows else 0
        avg_availability = round(sum(row["vehicle_availability"] for row in rows) / max(len(rows), 1), 3)
        avg_utilization = round(sum(row["charger_utilization"] for row in rows) / max(len(rows), 1), 3)
        peak_utilization = max((row["charger_utilization"] for row in rows), default=0.0)
        waiting_vehicle_hours = sum(row["waiting_vehicle_hours"] for row in rows)
        avg_soc = round(sum(row["average_soc"] for row in rows) / max(len(rows), 1), 3)
        min_soc = min((row["minimum_soc"] for row in rows), default=0.0)
        cost_reduction = round(((baseline_cost - total_cost) / baseline_cost) * 100, 2) if baseline_cost else 0.0
        unmet_reduction = round(((baseline_unmet - total_unmet) / baseline_unmet) * 100, 2) if baseline_unmet else 0.0
        cost_reduction_vs_nearest = round(((nearest_cost - total_cost) / nearest_cost) * 100, 2) if nearest_cost else 0.0
        unmet_reduction_vs_nearest = round(((nearest_unmet - total_unmet) / nearest_unmet) * 100, 2) if nearest_unmet else 0.0
        operational_score = round(
            (avg_availability * 40)
            + ((1.0 - min(total_cost / max(baseline_cost, 1.0), 2.0)) * 20)
            + ((1.0 - min(total_unmet / max(baseline_unmet or 1, 1), 2.0)) * 25)
            + (avg_soc * 10)
            + ((1.0 - peak_utilization) * 5),
            3,
        )
        summary_rows.append(
            {
                "scheduler_mode": mode,
                "total_charging_cost_eur": round(total_cost, 3),
                "total_charging_energy_kwh": total_energy,
                "cost_per_kwh_eur": round(total_cost / total_energy, 4) if total_energy else 0.0,
                "kwh_per_eur": round(total_energy / total_cost, 3) if total_cost else 0.0,
                "percentage_cost_reduction_vs_baseline": cost_reduction,
                "percentage_cost_reduction_vs_nearest_available": cost_reduction_vs_nearest,
                "average_vehicle_availability": avg_availability,
                "total_unmet_demand": total_unmet,
                "unmet_demand_reduction_vs_baseline": unmet_reduction,
                "unmet_demand_reduction_vs_nearest_available": unmet_reduction_vs_nearest,
                "average_charger_utilization": avg_utilization,
                "peak_charger_utilization": peak_utilization,
                "total_waiting_vehicle_hours": waiting_vehicle_hours,
                "average_soc": avg_soc,
                "minimum_soc": min_soc,
                "operational_score": operational_score,
            }
        )

    _write_csv(project_root / "outputs" / "results" / "comparison_summary.csv", summary_rows)
    return summary_rows
