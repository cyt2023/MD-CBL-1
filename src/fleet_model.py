from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List


def build_fleet_and_chargers(
    preprocessed: Dict[str, object], demand_model: Dict[str, object], config: Dict[str, object]
) -> Dict[str, object]:
    seed = int(config["random_seed"])
    random.seed(seed)
    zones: List[str] = demand_model["zones"]
    demand_series: List[Dict[str, int]] = demand_model["demand_series"]
    total_zone_demand = defaultdict(int)
    for step in demand_series:
        for zone, demand in step.items():
            total_zone_demand[zone] += demand

    ordered_zones = sorted(zones, key=lambda zone: (-total_zone_demand[zone], zone))
    vehicles: List[Dict[str, object]] = []
    fleet_size = int(config["fleet_size"])
    battery_capacity = float(config["battery_capacity_kwh"])
    min_soc = float(config["min_soc"])

    zone_cycle: List[str] = []
    for zone in ordered_zones:
        weight = max(total_zone_demand[zone], 1)
        repeats = max(1, int(round((weight / max(sum(total_zone_demand.values()), 1)) * fleet_size)))
        zone_cycle.extend([zone] * repeats)
    if not zone_cycle:
        zone_cycle = zones[:]

    for index in range(fleet_size):
        zone = zone_cycle[index % len(zone_cycle)]
        soc = max(min_soc, min(0.95, 0.28 + (((index * 11) % 55) / 100)))
        vehicles.append(
            {
                "vehicle_id": f"vehicle_{index:03d}",
                "zone": zone,
                "soc": round(soc, 3),
                "battery_capacity_kwh": battery_capacity,
                "waiting_time": index % 4,
                "status": "idle",
                "current_charger_id": None,
                "total_charge_kwh": 0.0,
                "total_cost_eur": 0.0,
                "total_trips_served": 0,
                "availability_failures": 0,
                "reasoning_summary": "",
                "heuristic_priority_score": 0.0,
            }
        )

    chargers: List[Dict[str, object]] = []
    charger_power = float(config["charger_power_kw"])
    source_chargers = preprocessed.get("prepared_chargers", [])
    number_of_chargers = int(config["number_of_chargers"])
    for index in range(number_of_chargers):
        source = source_chargers[index] if index < len(source_chargers) else {}
        zone = source.get("zone") or ordered_zones[index % len(ordered_zones)]
        chargers.append(
            {
                "charger_id": source.get("charger_id", f"charger_{index:03d}"),
                "zone": zone,
                "power_kw": charger_power,
                "status": "available",
                "provider": source.get("provider", "synthetic"),
            }
        )

    return {
        "vehicles": vehicles,
        "chargers": chargers,
    }
