from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List


REQUIRED_DATASETS = {
    "dataset_1_od_matrix": Path("Dataset 1 – Mobility Demand (Origin–Destination)/eindhoven_od_matrix.csv"),
    "dataset_2_hubs": Path("Dataset 2 – Shared Mobility Hubs/Locaties Deelmobiliteit Hubs (punt)/locaties-deelmobiliteit-hubs-punt.csv"),
    "dataset_5_congestion": Path("Dataset 5 – Grid Congestion & Constraints/congestie_pc6.csv"),
    "dataset_6_load": Path("Dataset 6 – Electricity Load (Demand)/eindhoven_zonal_load.csv"),
    "dataset_7_prices": Path("Dataset 7 – Electricity Prices/european_wholesale_electricity_price_data_hourly/Netherlands.csv"),
}

OPTIONAL_DATASETS = {
    "dataset_3_chargers": Path("Dataset 3 – Existing EV Charging Points/oplaadpalen.csv"),
}


def _count_rows(path: Path, delimiter: str) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        row_count = -1
        for row_count, _ in enumerate(reader):
            pass
    return max(row_count, 0)


def _infer_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(2048)
    if ";" in sample and sample.count(";") > sample.count(","):
        return ";"
    return ","


def run_data_audit(project_root: Path) -> Dict[str, object]:
    findings: List[Dict[str, object]] = []
    for dataset_name, rel_path in {**REQUIRED_DATASETS, **OPTIONAL_DATASETS}.items():
        path = project_root / rel_path
        exists = path.exists()
        record: Dict[str, object] = {
            "dataset": dataset_name,
            "path": str(rel_path),
            "exists": exists,
            "required": dataset_name in REQUIRED_DATASETS,
        }
        if exists and path.suffix.lower() == ".csv":
            delimiter = _infer_delimiter(path)
            record["delimiter"] = delimiter
            record["rows"] = _count_rows(path, delimiter)
        findings.append(record)

    missing_required = [item["dataset"] for item in findings if item["required"] and not item["exists"]]
    summary = {
        "status": "ok" if not missing_required else "missing_required_datasets",
        "missing_required": missing_required,
        "datasets": findings,
    }

    reports_dir = project_root / "outputs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    audit_path = reports_dir / "data_audit_summary.json"
    audit_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
