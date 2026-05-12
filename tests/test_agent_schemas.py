import unittest

from src.agent.schemas import AgentObservation, AgentPlan, SchemaValidationError


class AgentSchemaTests(unittest.TestCase):
    def test_valid_observation_can_be_created(self):
        observation = AgentObservation.from_dict(
            {
                "time_step": 0,
                "electricity_price": 55.0,
                "available_chargers": 2,
                "total_chargers": 4,
                "total_demand": 6.0,
                "served_demand_so_far": 2.0,
                "unmet_demand_so_far": 1.0,
                "zone_status": [{"zone": "Z1"}],
                "candidate_vehicles": [
                    {
                        "vehicle_id": "vehicle_001",
                        "zone": "Z1",
                        "soc": 0.3,
                        "waiting_time": 2,
                        "future_demand": 4.0,
                        "availability_risk": 1.0,
                        "estimated_energy_needed_kwh": 30.0,
                        "heuristic_priority_score": 0.8,
                    }
                ],
            }
        )
        self.assertEqual(observation.time_step, 0)
        self.assertEqual(observation.candidate_vehicles[0].vehicle_id, "vehicle_001")

    def test_valid_plan_can_be_parsed(self):
        plan = AgentPlan.from_dict(
            {
                "time_step": 0,
                "strategy_summary": "Charge urgent vehicles first.",
                "actions": [
                    {
                        "vehicle_id": "vehicle_001",
                        "charger_id": "charger_001",
                        "zone": "Z1",
                        "target_soc": 0.8,
                        "planned_duration_hours": 1.0,
                        "reasoning_summary": "Low SOC in high-demand zone.",
                    }
                ],
                "rejected_candidates": [],
                "risk_notes": [],
                "expected_effect": "Improved readiness.",
            }
        )
        self.assertEqual(plan.actions[0].charger_id, "charger_001")

    def test_invalid_plan_is_rejected(self):
        with self.assertRaises(SchemaValidationError):
            AgentPlan.from_dict({"time_step": 0, "strategy_summary": "bad"})
