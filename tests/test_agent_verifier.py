import unittest

from src.agent.schemas import AgentPlan
from src.agent.verifier import PlanVerifier


def _state():
    return {
        "vehicles": [
            {"vehicle_id": "vehicle_001", "zone": "Z1", "soc": 0.3, "status": "idle", "battery_capacity_kwh": 60},
            {"vehicle_id": "vehicle_002", "zone": "Z1", "soc": 0.85, "status": "idle", "battery_capacity_kwh": 60},
        ],
        "chargers": [
            {"charger_id": "charger_001", "zone": "Z1", "status": "available", "power_kw": 22},
            {"charger_id": "charger_002", "zone": "Z1", "status": "available", "power_kw": 22},
        ],
        "future_demand_by_zone": {"Z1": 1},
        "available_vehicles_by_zone": {"Z1": 2},
    }


def _config():
    return {"target_soc": 0.8, "min_soc": 0.2}


class AgentVerifierTests(unittest.TestCase):
    def test_duplicate_charger_assignment_is_rejected(self):
        plan = AgentPlan.from_dict(
            {
                "time_step": 0,
                "strategy_summary": "bad",
                "actions": [
                    {
                        "vehicle_id": "vehicle_001",
                        "charger_id": "charger_001",
                        "zone": "Z1",
                        "target_soc": 0.8,
                        "planned_duration_hours": 1.0,
                        "reasoning_summary": "a",
                    },
                    {
                        "vehicle_id": "vehicle_002",
                        "charger_id": "charger_001",
                        "zone": "Z1",
                        "target_soc": 0.8,
                        "planned_duration_hours": 1.0,
                        "reasoning_summary": "b",
                    },
                ],
                "rejected_candidates": [],
                "risk_notes": [],
                "expected_effect": "bad",
            }
        )
        result = PlanVerifier(_config()).validate_plan(plan, _state())
        self.assertTrue(result["rejected_actions"])

    def test_target_soc_above_allowed_limit_is_repaired_or_rejected(self):
        plan = AgentPlan.from_dict(
            {
                "time_step": 0,
                "strategy_summary": "repair",
                "actions": [
                    {
                        "vehicle_id": "vehicle_001",
                        "charger_id": "charger_001",
                        "zone": "Z1",
                        "target_soc": 0.95,
                        "planned_duration_hours": 1.0,
                        "reasoning_summary": "a",
                    }
                ],
                "rejected_candidates": [],
                "risk_notes": [],
                "expected_effect": "repair",
            }
        )
        result = PlanVerifier(_config()).validate_plan(plan, _state())
        validated = result["validated_actions"][0]
        self.assertEqual(validated.target_soc, 0.8)

    def test_nonexistent_vehicle_id_is_rejected(self):
        plan = AgentPlan.from_dict(
            {
                "time_step": 0,
                "strategy_summary": "reject",
                "actions": [
                    {
                        "vehicle_id": "vehicle_missing",
                        "charger_id": "charger_001",
                        "zone": "Z1",
                        "target_soc": 0.8,
                        "planned_duration_hours": 1.0,
                        "reasoning_summary": "a",
                    }
                ],
                "rejected_candidates": [],
                "risk_notes": [],
                "expected_effect": "reject",
            }
        )
        result = PlanVerifier(_config()).validate_plan(plan, _state())
        self.assertEqual(result["rejected_actions"][0]["validation_errors"][0], "vehicle_id does not exist")

    def test_charging_above_target_soc_is_rejected(self):
        plan = AgentPlan.from_dict(
            {
                "time_step": 0,
                "strategy_summary": "reject",
                "actions": [
                    {
                        "vehicle_id": "vehicle_002",
                        "charger_id": "charger_002",
                        "zone": "Z1",
                        "target_soc": 0.8,
                        "planned_duration_hours": 1.0,
                        "reasoning_summary": "a",
                    }
                ],
                "rejected_candidates": [],
                "risk_notes": [],
                "expected_effect": "reject",
            }
        )
        result = PlanVerifier(_config()).validate_plan(plan, _state())
        self.assertTrue(any("vehicle is already above target_soc" in err for err in result["validation_errors"]))
