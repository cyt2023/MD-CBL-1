from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

from .agent.charging_agent import AgenticChargingPlanner


def _energy_needed_to_target(vehicle: Dict[str, object], target_soc: float) -> float:
    battery = float(vehicle["battery_capacity_kwh"])
    current = float(vehicle["soc"])
    return max(0.0, (target_soc - current) * battery)


def _duration_hours(energy_kwh: float, charger_power_kw: float) -> float:
    if charger_power_kw <= 0:
        return 0.0
    return round(max(0.05, min(1.0, energy_kwh / charger_power_kw)), 3)


class BaselineScheduler:
    name = "baseline"

    def __init__(self, config: Dict[str, object]):
        self.config = config

    def schedule(self, state: Dict[str, object]) -> List[Dict[str, object]]:
        threshold = float(self.config["baseline_charge_threshold"])
        target_soc = float(self.config["target_soc"])
        available_chargers = [charger for charger in state["chargers"] if charger["status"] == "available"]
        decisions: List[Dict[str, object]] = []
        low_soc_vehicles = [
            vehicle
            for vehicle in state["vehicles"]
            if vehicle["status"] == "idle" and float(vehicle["soc"]) < threshold
        ]
        low_soc_vehicles.sort(key=lambda item: (float(item["soc"]), -float(item["waiting_time"]), item["vehicle_id"]))

        for vehicle, charger in zip(low_soc_vehicles, available_chargers):
            energy_needed = _energy_needed_to_target(vehicle, target_soc)
            duration = _duration_hours(energy_needed, float(charger["power_kw"]))
            decisions.append(
                {
                    "vehicle_id": vehicle["vehicle_id"],
                    "charger_id": charger["charger_id"],
                    "zone": charger["zone"],
                    "target_soc": target_soc,
                    "planned_duration_hours": duration,
                    "reasoning_summary": "Baseline threshold rule selected low-SOC vehicle.",
                    "agent_used": "baseline",
                    "llm_used": False,
                    "fallback_used": False,
                    "validation_errors": "",
                    "heuristic_priority_score": 0.0,
                    "agent_strategy_summary": "Charge any vehicle below the fixed threshold until chargers are full.",
                }
            )
        return decisions


class NearestAvailableScheduler:
    name = "nearest_available"

    def __init__(self, config: Dict[str, object]):
        self.config = config

    def schedule(self, state: Dict[str, object]) -> List[Dict[str, object]]:
        target_soc = float(self.config["target_soc"])
        available_chargers = [charger for charger in state["chargers"] if charger["status"] == "available"]
        charging_drivers = [
            vehicle
            for vehicle in state["vehicles"]
            if vehicle["status"] == "idle" and float(vehicle["soc"]) < target_soc
        ]
        charging_drivers.sort(key=lambda item: (-int(item["waiting_time"]), item["zone"], item["vehicle_id"]))

        decisions: List[Dict[str, object]] = []
        for vehicle in charging_drivers:
            if not available_chargers:
                break
            charger = next((item for item in available_chargers if item["zone"] == vehicle["zone"]), None)
            if charger is None:
                charger = available_chargers[0]
            energy_needed = _energy_needed_to_target(vehicle, target_soc)
            duration = _duration_hours(energy_needed, float(charger["power_kw"]))
            decisions.append(
                {
                    "vehicle_id": vehicle["vehicle_id"],
                    "charger_id": charger["charger_id"],
                    "zone": charger["zone"],
                    "target_soc": target_soc,
                    "planned_duration_hours": duration,
                    "reasoning_summary": "Naive nearest-available behavior: charge at the same-zone charger if possible.",
                    "agent_used": "nearest_available",
                    "llm_used": False,
                    "fallback_used": False,
                    "validation_errors": "",
                    "heuristic_priority_score": 0.0,
                    "agent_strategy_summary": "Individual vehicles seek the nearest available charger without fleet-level planning.",
                }
            )
            available_chargers = [item for item in available_chargers if item["charger_id"] != charger["charger_id"]]
        return decisions


class SmartPriorityScheduler:
    name = "smart_priority"

    def __init__(self, config: Dict[str, object]):
        self.config = config

    def _score_vehicle(self, vehicle: Dict[str, object], state: Dict[str, object]) -> float:
        weights = self.config["scheduler_weights"]
        zone = vehicle["zone"]
        zone_demand = state["future_demand_by_zone"].get(zone, 0.0)
        max_zone_demand = max(state["future_demand_by_zone"].values() or [1.0])
        availability = state["available_vehicles_by_zone"].get(zone, 0)
        risk = max(0.0, zone_demand - availability)
        price = float(state["electricity_price"])
        max_price = max(state["price_series"]) if state["price_series"] else max(price, 1.0)
        low_price_score = 1.0 - min(price / max(max_price, 1.0), 1.0)
        waiting_score = min(float(vehicle["waiting_time"]) / 5.0, 1.0)
        low_soc_score = 1.0 - float(vehicle["soc"])
        demand_score = zone_demand / max(max_zone_demand, 1.0)
        availability_score = min(risk / max(state["fleet_size"], 1), 1.0)
        congestion_score = min(state["zone_congestion"].get(zone, 1.0) / 2.0, 1.0)
        return round(
            weights["w_soc"] * low_soc_score
            + weights["w_demand"] * demand_score
            + weights["w_availability"] * availability_score
            + weights["w_price"] * low_price_score
            + weights["w_wait"] * waiting_score
            + weights["w_congestion"] * congestion_score,
            4,
        )

    def schedule(self, state: Dict[str, object]) -> List[Dict[str, object]]:
        target_soc = float(self.config["target_soc"])
        available_chargers = [charger for charger in state["chargers"] if charger["status"] == "available"]
        candidates = [vehicle for vehicle in state["vehicles"] if vehicle["status"] == "idle" and float(vehicle["soc"]) < target_soc]
        for vehicle in candidates:
            vehicle["heuristic_priority_score"] = self._score_vehicle(vehicle, state)
        candidates.sort(key=lambda item: (-float(item["heuristic_priority_score"]), float(item["soc"]), item["vehicle_id"]))

        decisions: List[Dict[str, object]] = []
        used_vehicles = set()
        for vehicle in candidates:
            if vehicle["vehicle_id"] in used_vehicles:
                continue
            charger = next((item for item in available_chargers if item["zone"] == vehicle["zone"]), None)
            if charger is None:
                charger = next((item for item in available_chargers if item["charger_id"] not in {d["charger_id"] for d in decisions}), None)
            if charger is None:
                break
            energy_needed = _energy_needed_to_target(vehicle, target_soc)
            duration = _duration_hours(energy_needed, float(charger["power_kw"]))
            decisions.append(
                {
                    "vehicle_id": vehicle["vehicle_id"],
                    "charger_id": charger["charger_id"],
                    "zone": charger["zone"],
                    "target_soc": target_soc,
                    "planned_duration_hours": duration,
                    "reasoning_summary": "Heuristic score prioritised this vehicle for charging.",
                    "agent_used": "smart_priority",
                    "llm_used": False,
                    "fallback_used": False,
                    "validation_errors": "",
                    "heuristic_priority_score": float(vehicle["heuristic_priority_score"]),
                    "agent_strategy_summary": "Weighted heuristic combining SOC, demand, availability, price, wait, and congestion.",
                }
            )
            used_vehicles.add(vehicle["vehicle_id"])
            available_chargers = [item for item in available_chargers if item["charger_id"] != charger["charger_id"]]
        return decisions


class AgenticLLMScheduler:
    name = "agentic_llm"

    def __init__(self, config: Dict[str, object]):
        self.config = config
        self.smart_scheduler = SmartPriorityScheduler(config)
        self.planner = AgenticChargingPlanner(config=config, fallback_scheduler=self.smart_scheduler)

    def schedule(self, state: Dict[str, object]) -> List[Dict[str, object]]:
        planner_state = deepcopy(state)
        return self.planner.plan_charging_actions(planner_state)
