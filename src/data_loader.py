from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple


def infer_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
    if ";" in sample and sample.count(";") > sample.count(","):
        return ";"
    return ","


def load_csv(path: Path) -> List[Dict[str, str]]:
    delimiter = infer_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [dict(row) for row in reader]


def load_matrix_csv(path: Path) -> Tuple[List[str], List[List[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    header = rows[0]
    return header, rows[1:]


def load_project_data(project_root: Path) -> Dict[str, object]:
    dataset_paths = {
        "od_matrix": project_root / "Dataset 1 – Mobility Demand (Origin–Destination)/eindhoven_od_matrix.csv",
        "mobility_hubs": project_root / "Dataset 2 – Shared Mobility Hubs/Locaties Deelmobiliteit Hubs (punt)/locaties-deelmobiliteit-hubs-punt.csv",
        "charging_points": project_root / "Dataset 3 – Existing EV Charging Points/oplaadpalen.csv",
        "grid_congestion": project_root / "Dataset 5 – Grid Congestion & Constraints/congestie_pc6.csv",
        "zonal_load": project_root / "Dataset 6 – Electricity Load (Demand)/eindhoven_zonal_load.csv",
        "districts": project_root / "Dataset 6 – Electricity Load (Demand)/eindhoven_districts.csv",
        "prices": project_root / "Dataset 7 – Electricity Prices/european_wholesale_electricity_price_data_hourly/Netherlands.csv",
    }

    od_header, od_rows = load_matrix_csv(dataset_paths["od_matrix"])
    data: Dict[str, object] = {
        "od_matrix_header": od_header,
        "od_matrix_rows": od_rows,
        "mobility_hubs": load_csv(dataset_paths["mobility_hubs"]),
        "grid_congestion": load_csv(dataset_paths["grid_congestion"]),
        "zonal_load": load_csv(dataset_paths["zonal_load"]),
        "districts": load_csv(dataset_paths["districts"]),
        "prices": load_csv(dataset_paths["prices"]),
        "charging_points": [],
    }
    if dataset_paths["charging_points"].exists():
        data["charging_points"] = load_csv(dataset_paths["charging_points"])
    return data
