from __future__ import annotations

from typing import Dict, List

from .schemas import AgentPlan, ValidatedChargingAction


class PlanVerifier:
    def __init__(self, config: Dict[str, object]):
        self.config = config

    def validate_plan(self, plan: AgentPlan, state: Dict[str, object]) -> Dict[str, object]:
        vehicles = {vehicle["vehicle_id"]: vehicle for vehicle in state["vehicles"]}
        chargers = {charger["charger_id"]: charger for charger in state["chargers"]}
        available_chargers = {charger["charger_id"] for charger in state["chargers"] if charger["status"] == "available"}
        target_soc_cap = float(self.config["target_soc"])
        min_soc = float(self.config["min_soc"])
        final_actions: List[ValidatedChargingAction] = []
        rejected_actions: List[Dict[str, object]] = []
        repair_notes: List[str] = []
        seen_vehicles = set()
        seen_chargers = set()

        for action in plan.actions:
            original = action.to_dict()
            errors: List[str] = []
            repaired = None
            if action.vehicle_id not in vehicles:
                errors.append("vehicle_id does not exist")
            if action.charger_id not in chargers:
                errors.append("charger_id does not exist")
            if action.vehicle_id in seen_vehicles:
                errors.append("duplicate vehicle assignment")
            if action.charger_id in seen_chargers:
                errors.append("duplicate charger assignment")
            vehicle = vehicles.get(action.vehicle_id)
            charger = chargers.get(action.charger_id)
            if vehicle and vehicle["status"] == "charging":
                errors.append("vehicle is already charging")
            if charger and action.charger_id not in available_chargers:
                errors.append("charger is not available")
            if charger and action.zone != charger["zone"]:
                errors.append("charger zone does not match action zone")
            if vehicle and charger and vehicle["zone"] != charger["zone"]:
                errors.append("vehicle zone is not compatible with charger zone")
            if action.target_soc <= min_soc:
                errors.append("target_soc must be above min_soc")
            if vehicle and action.target_soc <= float(vehicle["soc"]):
                errors.append("target_soc must be above current_soc")
            if vehicle and float(vehicle["soc"]) >= target_soc_cap:
                errors.append("vehicle is already above target_soc")
            if action.planned_duration_hours <= 0:
                errors.append("planned_duration_hours must be positive")
            if action.target_soc > target_soc_cap:
                repaired = dict(original)
                repaired["target_soc"] = target_soc_cap
                repair_notes.append(
                    f"Clipped target_soc for {action.vehicle_id} from {action.target_soc} to {target_soc_cap}."
                )
                action.target_soc = target_soc_cap
            if charger and float(charger["power_kw"]) <= 0:
                errors.append("charger capacity is invalid")
            if vehicle:
                zone = vehicle["zone"]
                zone_future = float(state["future_demand_by_zone"].get(zone, 0.0))
                zone_available = int(state["available_vehicles_by_zone"].get(zone, 0))
                if zone_available <= 1 and zone_future > zone_available and float(vehicle["soc"]) > 0.5:
                    errors.append("action risks avoidable availability failure in a constrained zone")

            if errors:
                rejected_actions.append(
                    {
                        "action": original,
                        "validation_errors": errors,
                        "repaired_from_original": repaired,
                    }
                )
                continue

            seen_vehicles.add(action.vehicle_id)
            seen_chargers.add(action.charger_id)
            final_actions.append(
                ValidatedChargingAction(
                    vehicle_id=action.vehicle_id,
                    charger_id=action.charger_id,
                    zone=action.zone,
                    target_soc=action.target_soc,
                    planned_duration_hours=action.planned_duration_hours,
                    reasoning_summary=action.reasoning_summary,
                    is_valid=True,
                    validation_errors=[],
                    repaired_from_original=repaired,
                )
            )

        return {
            "validated_actions": final_actions,
            "rejected_actions": rejected_actions,
            "repair_notes": repair_notes,
            "is_fully_valid": len(rejected_actions) == 0,
            "validation_errors": [error for item in rejected_actions for error in item["validation_errors"]],
        }
