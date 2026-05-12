from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: str) -> datetime:
    for fmt in ("%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported timestamp format: {value}")


def preprocess_inputs(raw_data: Dict[str, object], config: Dict[str, object]) -> Dict[str, object]:
    zonal_load = raw_data["zonal_load"]
    zones = sorted({row["zone_id"] for row in zonal_load if row.get("zone_id")})
    hours = int(config["simulation_hours"])

    load_by_time: Dict[datetime, Dict[str, float]] = defaultdict(dict)
    for row in zonal_load:
        timestamp = _parse_timestamp(row["timestamp"])
        load_by_time[timestamp][row["zone_id"]] = _safe_float(row["demand_MW"])

    ordered_times = sorted(load_by_time.keys())[:hours]
    zonal_load_series: List[Dict[str, float]] = []
    for timestamp in ordered_times:
        zonal_load_series.append(
            {zone: load_by_time[timestamp].get(zone, 0.0) for zone in zones}
        )

    prices = raw_data["prices"]
    price_series = [_safe_float(row["Price (EUR/MWhe)"]) for row in prices[:hours]]
    if len(price_series) < hours:
        price_series.extend([price_series[-1] if price_series else 50.0] * (hours - len(price_series)))

    zone_districts: Dict[str, List[str]] = defaultdict(list)
    od_rows = raw_data["od_matrix_rows"]
    district_ids = [row[0] for row in od_rows]
    for index, district in enumerate(district_ids):
        zone_districts[zones[index % len(zones)]].append(district)

    od_totals: Dict[str, float] = {}
    for row in od_rows:
        district = row[0]
        values = [_safe_float(value) for value in row[1:]]
        od_totals[district] = sum(values)

    mobility_weights: Dict[str, float] = {}
    total_mobility = sum(od_totals.values()) or 1.0
    for zone in zones:
        zone_total = sum(od_totals.get(district, 0.0) for district in zone_districts.get(zone, []))
        mobility_weights[zone] = zone_total / total_mobility

    congestion_rows = raw_data["grid_congestion"]
    raw_congestion_score = 0.0
    counted = 0
    for row in congestion_rows[: min(len(congestion_rows), 5000)]:
        raw_congestion_score += _safe_float(row.get("afname", 0.0))
        counted += 1
    avg_congestion = raw_congestion_score / counted if counted else 1.0
    congestion_by_zone = {
        zone: round(0.8 + ((index + 1) / max(len(zones), 1)) * min(avg_congestion, 1.2), 3)
        for index, zone in enumerate(zones)
    }

    hubs = raw_data["mobility_hubs"]
    prepared_hubs = []
    for index, row in enumerate(hubs):
        prepared_hubs.append(
            {
                "hub_id": f"hub_{index:03d}",
                "name": row.get("NAAM", f"Hub {index + 1}"),
                "zone": zones[index % len(zones)],
                "capacity_auto": _safe_float(row.get("CAPACITEIT_AUTO", 0.0), 0.0),
            }
        )

    charging_points = raw_data.get("charging_points", [])
    prepared_chargers = []
    if charging_points:
        for index, row in enumerate(charging_points[: max(int(config["number_of_chargers"]) * 2, int(config["number_of_chargers"]))]):
            prepared_chargers.append(
                {
                    "charger_id": f"charger_{index:03d}",
                    "zone": zones[index % len(zones)],
                    "provider": row.get("AANBIEDER", "unknown"),
                    "status": row.get("STATUS", "unknown"),
                }
            )

    return {
        "zones": zones,
        "zonal_load_series": zonal_load_series,
        "price_series": price_series,
        "mobility_weights": mobility_weights,
        "zone_districts": dict(zone_districts),
        "congestion_by_zone": congestion_by_zone,
        "prepared_hubs": prepared_hubs,
        "prepared_chargers": prepared_chargers,
        "timestamps": [timestamp.isoformat() for timestamp in ordered_times],
    }
