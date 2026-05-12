from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path
from typing import Dict, List

from .scheduler import AgenticLLMScheduler, BaselineScheduler, SmartPriorityScheduler


def _write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class Simulator:
    def __init__(
        self,
        config: Dict[str, object],
        demand_model: Dict[str, object],
        fleet_assets: Dict[str, object],
        preprocessed: Dict[str, object],
        project_root: Path,
    ):
        self.config = config
        self.demand_model = demand_model
        self.fleet_assets = fleet_assets
        self.preprocessed = preprocessed
        self.project_root = project_root

    def _build_scheduler(self, mode: str):
        if mode == "baseline":
            return BaselineScheduler(self.config)
        if mode == "smart_priority":
            return SmartPriorityScheduler(self.config)
        if mode == "agentic_llm":
            return AgenticLLMScheduler(self.config)
        raise ValueError(f"Unsupported scheduler mode: {mode}")

    def _available_vehicles_by_zone(self, vehicles: List[Dict[str, object]]) -> Dict[str, int]:
        min_soc = float(self.config["min_soc"])
        result: Dict[str, int] = {}
        for zone in self.demand_model["zones"]:
            result[zone] = sum(
                1
                for vehicle in vehicles
                if vehicle["zone"] == zone and vehicle["status"] == "idle" and float(vehicle["soc"]) > min_soc
            )
        return result

    def _build_state(
        self,
        mode: str,
        time_step: int,
        vehicles: List[Dict[str, object]],
        chargers: List[Dict[str, object]],
        total_cost_so_far: float,
        unmet_demand_so_far: int,
        served_demand_so_far: int,
    ) -> Dict[str, object]:
        demand_series = self.demand_model["demand_series"]
        price_series = self.preprocessed["price_series"]
        return {
            "mode": mode,
            "time_step": time_step,
            "vehicles": vehicles,
            "chargers": chargers,
            "fleet_size": len(vehicles),
            "electricity_price": price_series[time_step],
            "price_series": price_series,
            "current_demand_by_zone": demand_series[time_step],
            "future_demand_by_zone": self.demand_model["future_zone_demand"][time_step],
            "available_vehicles_by_zone": self._available_vehicles_by_zone(vehicles),
            "zone_congestion": self.preprocessed["congestion_by_zone"],
            "total_cost_so_far": total_cost_so_far,
            "unmet_demand_so_far": unmet_demand_so_far,
            "served_demand_so_far": served_demand_so_far,
            "timestamps": self.preprocessed["timestamps"],
        }

    def _apply_charging(self, decisions: List[Dict[str, object]], vehicles: List[Dict[str, object]], chargers: List[Dict[str, object]], electricity_price: float) -> Dict[str, float]:
        vehicle_index = {vehicle["vehicle_id"]: vehicle for vehicle in vehicles}
        charger_index = {charger["charger_id"]: charger for charger in chargers}
        total_cost = 0.0
        total_energy = 0.0
        for charger in chargers:
            charger["status"] = "available"
        for vehicle in vehicles:
            if vehicle["status"] == "charging":
                vehicle["status"] = "idle"
                vehicle["current_charger_id"] = None
        for decision in decisions:
            vehicle = vehicle_index[decision["vehicle_id"]]
            charger = charger_index[decision["charger_id"]]
            duration = float(decision["planned_duration_hours"])
            energy_kwh = min(
                float(charger["power_kw"]) * duration,
                max(0.0, (float(decision["target_soc"]) - float(vehicle["soc"])) * float(vehicle["battery_capacity_kwh"])),
            )
            delta_soc = energy_kwh / float(vehicle["battery_capacity_kwh"]) if float(vehicle["battery_capacity_kwh"]) else 0.0
            vehicle["soc"] = round(min(float(decision["target_soc"]), float(vehicle["soc"]) + delta_soc), 3)
            vehicle["status"] = "charging"
            vehicle["current_charger_id"] = charger["charger_id"]
            vehicle["total_charge_kwh"] = round(float(vehicle["total_charge_kwh"]) + energy_kwh, 3)
            cost_eur = (electricity_price / 1000.0) * energy_kwh
            vehicle["total_cost_eur"] = round(float(vehicle["total_cost_eur"]) + cost_eur, 3)
            vehicle["reasoning_summary"] = decision.get("reasoning_summary", "")
            charger["status"] = "occupied"
            total_energy += energy_kwh
            total_cost += cost_eur
        return {"charging_cost_eur": round(total_cost, 3), "charging_energy_kwh": round(total_energy, 3)}

    def _serve_demand(self, vehicles: List[Dict[str, object]], current_demand_by_zone: Dict[str, int]) -> Dict[str, object]:
        min_soc = float(self.config["min_soc"])
        trip_energy_kwh = float(self.config["trip_energy_kwh"])
        served_total = 0
        unmet_total = 0
        waiting_vehicle_hours = 0
        availability_sum = 0
        available_count = 0

        for zone, demand in current_demand_by_zone.items():
            candidates = [
                vehicle
                for vehicle in vehicles
                if vehicle["zone"] == zone and vehicle["status"] == "idle" and float(vehicle["soc"]) > min_soc
            ]
            candidates.sort(key=lambda item: (-float(item["soc"]), item["vehicle_id"]))
            served = min(len(candidates), int(demand))
            for vehicle in candidates[:served]:
                delta_soc = trip_energy_kwh / float(vehicle["battery_capacity_kwh"])
                vehicle["soc"] = round(max(0.0, float(vehicle["soc"]) - delta_soc), 3)
                vehicle["total_trips_served"] = int(vehicle["total_trips_served"]) + 1
                vehicle["waiting_time"] = 0
            for vehicle in candidates[served:]:
                if float(vehicle["soc"]) < float(self.config["target_soc"]):
                    vehicle["waiting_time"] = int(vehicle["waiting_time"]) + 1
            served_total += served
            unmet_total += max(0, int(demand) - served)

        for vehicle in vehicles:
            if vehicle["status"] == "charging":
                vehicle["waiting_time"] = int(vehicle["waiting_time"]) + 1
                waiting_vehicle_hours += 1
            elif vehicle["status"] == "idle" and float(vehicle["soc"]) < float(self.config["target_soc"]):
                waiting_vehicle_hours += 1
            if vehicle["status"] == "idle" and float(vehicle["soc"]) > min_soc:
                availability_sum += 1
            available_count += 1

        for vehicle in vehicles:
            if vehicle["status"] == "charging":
                vehicle["status"] = "idle"
                vehicle["current_charger_id"] = None

        return {
            "served_demand": served_total,
            "unmet_demand": unmet_total,
            "waiting_vehicle_hours": waiting_vehicle_hours,
            "vehicle_availability": round(availability_sum / max(available_count, 1), 3),
        }

    def run_mode(self, mode: str) -> Dict[str, object]:
        scheduler = self._build_scheduler(mode)
        vehicles = deepcopy(self.fleet_assets["vehicles"])
        chargers = deepcopy(self.fleet_assets["chargers"])
        timeseries: List[Dict[str, object]] = []
        charging_plan_rows: List[Dict[str, object]] = []
        total_cost = 0.0
        total_unmet = 0
        total_served = 0

        for time_step in range(int(self.config["simulation_hours"])):
            state = self._build_state(mode, time_step, vehicles, chargers, total_cost, total_unmet, total_served)
            decisions = scheduler.schedule(state)
            charging_plan_rows.extend([{**decision, "time_step": time_step, "scheduler_mode": mode} for decision in decisions])
            charging_effect = self._apply_charging(decisions, vehicles, chargers, state["electricity_price"])
            demand_effect = self._serve_demand(vehicles, state["current_demand_by_zone"])

            total_cost = round(total_cost + charging_effect["charging_cost_eur"], 3)
            total_unmet += int(demand_effect["unmet_demand"])
            total_served += int(demand_effect["served_demand"])
            occupied = sum(1 for charger in chargers if charger["status"] == "occupied")
            avg_soc = round(sum(float(vehicle["soc"]) for vehicle in vehicles) / max(len(vehicles), 1), 3)
            min_soc = round(min(float(vehicle["soc"]) for vehicle in vehicles), 3)
            timeseries.append(
                {
                    "time_step": time_step,
                    "timestamp": state["timestamps"][time_step] if time_step < len(state["timestamps"]) else str(time_step),
                    "scheduler_mode": mode,
                    "electricity_price": state["electricity_price"],
                    "charging_cost_eur": charging_effect["charging_cost_eur"],
                    "cumulative_cost_eur": total_cost,
                    "charging_energy_kwh": charging_effect["charging_energy_kwh"],
                    "served_demand": demand_effect["served_demand"],
                    "unmet_demand": demand_effect["unmet_demand"],
                    "cumulative_unmet_demand": total_unmet,
                    "vehicle_availability": demand_effect["vehicle_availability"],
                    "charger_utilization": round(occupied / max(len(chargers), 1), 3),
                    "average_soc": avg_soc,
                    "minimum_soc": min_soc,
                    "waiting_vehicle_hours": demand_effect["waiting_vehicle_hours"],
                    "llm_used": any(bool(decision.get("llm_used")) for decision in decisions),
                    "fallback_used": any(bool(decision.get("fallback_used")) for decision in decisions),
                }
            )

        results_dir = self.project_root / "outputs" / "results"
        filename_map = {
            "baseline": "baseline_timeseries.csv",
            "smart_priority": "smart_timeseries.csv",
            "agentic_llm": "agentic_timeseries.csv",
        }
        _write_csv(results_dir / filename_map[mode], timeseries)
        if mode == "agentic_llm":
            _write_csv(results_dir / "agentic_charging_plan.csv", charging_plan_rows)
        return {
            "timeseries": timeseries,
            "charging_plan": charging_plan_rows,
        }

    def run_all(self) -> Dict[str, Dict[str, object]]:
        results = {}
        for mode in ("baseline", "smart_priority", "agentic_llm"):
            results[mode] = self.run_mode(mode)
        return results
