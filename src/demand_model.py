from __future__ import annotations

from typing import Dict, List


def build_demand_model(preprocessed: Dict[str, object], config: Dict[str, object]) -> Dict[str, object]:
    zones: List[str] = preprocessed["zones"]
    load_series: List[Dict[str, float]] = preprocessed["zonal_load_series"]
    mobility_weights: Dict[str, float] = preprocessed["mobility_weights"]
    fleet_size = int(config["fleet_size"])

    max_total_load = max(sum(step.values()) for step in load_series) if load_series else 1.0
    demand_series: List[Dict[str, int]] = []
    hours = len(load_series)

    for step_index, zone_loads in enumerate(load_series):
        total_load = sum(zone_loads.values()) or 1.0
        zone_demand: Dict[str, int] = {}
        for zone in zones:
            load_share = zone_loads.get(zone, 0.0) / total_load
            mobility_multiplier = 0.5 + (mobility_weights.get(zone, 0.0) * len(zones))
            scaled = (sum(zone_loads.values()) / max_total_load) * fleet_size * 0.32 * load_share * mobility_multiplier
            zone_demand[zone] = max(0, int(round(scaled)))
        demand_series.append(zone_demand)

    future_zone_demand: List[Dict[str, float]] = []
    for step_index in range(hours):
        horizon = int(config["future_demand_horizon"])
        horizon_totals: Dict[str, float] = {zone: 0.0 for zone in zones}
        for future_index in range(step_index, min(step_index + horizon, hours)):
            for zone in zones:
                horizon_totals[zone] += demand_series[future_index].get(zone, 0)
        future_zone_demand.append(horizon_totals)

    return {
        "zones": zones,
        "demand_series": demand_series,
        "future_zone_demand": future_zone_demand,
    }
