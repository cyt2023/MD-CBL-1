from __future__ import annotations

from typing import Dict, List

from .schemas import AgentObservation, AgentPlan, CandidateVehicle


def get_available_chargers(state: Dict[str, object]) -> List[Dict[str, object]]:
    return [charger for charger in state["chargers"] if charger["status"] == "available"]


def estimate_charging_need(vehicle: Dict[str, object], config: Dict[str, object]) -> float:
    target_soc = float(config["target_soc"])
    battery = float(vehicle["battery_capacity_kwh"])
    return round(max(0.0, (target_soc - float(vehicle["soc"])) * battery), 3)


def estimate_action_cost(price_eur_per_mwh: float, energy_kwh: float) -> float:
    return round((price_eur_per_mwh / 1000.0) * energy_kwh, 4)


def summarize_zone_status(state: Dict[str, object]) -> List[Dict[str, object]]:
    available_chargers = get_available_chargers(state)
    current_demand = state["current_demand_by_zone"]
    future_demand = state["future_demand_by_zone"]
    zone_status = []
    for zone in sorted(current_demand.keys()):
        zone_status.append(
            {
                "zone": zone,
                "current_demand": current_demand.get(zone, 0),
                "future_demand": future_demand.get(zone, 0),
                "available_vehicles": state["available_vehicles_by_zone"].get(zone, 0),
                "availability_risk": max(0.0, future_demand.get(zone, 0) - state["available_vehicles_by_zone"].get(zone, 0)),
                "congestion": state["zone_congestion"].get(zone, 1.0),
                "available_charger_ids": [charger["charger_id"] for charger in available_chargers if charger["zone"] == zone],
            }
        )
    return zone_status


def compute_candidate_scores(state: Dict[str, object], config: Dict[str, object]) -> List[Dict[str, object]]:
    weights = config["scheduler_weights"]
    price = float(state["electricity_price"])
    price_series = state["price_series"]
    price_factor = 1.0 - min(price / max(max(price_series), 1.0), 1.0)
    max_future_demand = max(state["future_demand_by_zone"].values() or [1.0])
    candidates = []
    for vehicle in state["vehicles"]:
        if vehicle["status"] != "idle":
            continue
        energy_need = estimate_charging_need(vehicle, config)
        if energy_need <= 0:
            continue
        zone = vehicle["zone"]
        future_demand = float(state["future_demand_by_zone"].get(zone, 0.0))
        availability_risk = max(0.0, future_demand - state["available_vehicles_by_zone"].get(zone, 0))
        low_soc_score = 1.0 - float(vehicle["soc"])
        waiting_score = min(float(vehicle["waiting_time"]) / 5.0, 1.0)
        demand_score = future_demand / max(max_future_demand, 1.0)
        availability_score = min(availability_risk / max(int(state["fleet_size"]), 1), 1.0)
        congestion_score = min(float(state["zone_congestion"].get(zone, 1.0)) / 2.0, 1.0)
        score = round(
            weights["w_soc"] * low_soc_score
            + weights["w_demand"] * demand_score
            + weights["w_availability"] * availability_score
            + weights["w_price"] * price_factor
            + weights["w_wait"] * waiting_score
            + weights["w_congestion"] * congestion_score,
            4,
        )
        candidate = dict(vehicle)
        candidate["future_demand"] = future_demand
        candidate["availability_risk"] = round(availability_risk, 3)
        candidate["estimated_energy_needed_kwh"] = energy_need
        candidate["heuristic_priority_score"] = score
        candidates.append(candidate)
    return candidates


def select_candidate_vehicles(state: Dict[str, object], config: Dict[str, object]) -> List[Dict[str, object]]:
    candidates = compute_candidate_scores(state, config)
    candidates.sort(key=lambda item: (-float(item["heuristic_priority_score"]), float(item["soc"]), item["vehicle_id"]))
    limit = int(config["llm_agent"]["max_candidate_vehicles"])
    return candidates[:limit]


def build_observation(state: Dict[str, object], config: Dict[str, object]) -> AgentObservation:
    selected_candidates = select_candidate_vehicles(state, config)
    zone_status = summarize_zone_status(state)
    return AgentObservation(
        time_step=int(state["time_step"]),
        electricity_price=float(state["electricity_price"]),
        available_chargers=len(get_available_chargers(state)),
        total_chargers=len(state["chargers"]),
        total_demand=float(sum(state["current_demand_by_zone"].values())),
        served_demand_so_far=float(state["served_demand_so_far"]),
        unmet_demand_so_far=float(state["unmet_demand_so_far"]),
        zone_status=zone_status,
        candidate_vehicles=[
            CandidateVehicle(
                vehicle_id=item["vehicle_id"],
                zone=item["zone"],
                soc=float(item["soc"]),
                waiting_time=int(item["waiting_time"]),
                future_demand=float(item["future_demand"]),
                availability_risk=float(item["availability_risk"]),
                estimated_energy_needed_kwh=float(item["estimated_energy_needed_kwh"]),
                heuristic_priority_score=float(item["heuristic_priority_score"]),
            )
            for item in selected_candidates
        ],
    )


def convert_agent_plan_to_charging_decisions(agent_plan: AgentPlan) -> List[Dict[str, object]]:
    return [action.to_dict() for action in agent_plan.actions]
