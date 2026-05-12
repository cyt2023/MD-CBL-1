import unittest

from src.agent.charging_agent import AgenticChargingPlanner
from src.agent.llm_client import MockLLMClient
from src.agent.schemas import AgentPlan
from src.agent.verifier import PlanVerifier
from src.scheduler import SmartPriorityScheduler


def _config():
    return {
        "random_seed": 42,
        "simulation_hours": 2,
        "fleet_size": 3,
        "number_of_chargers": 2,
        "battery_capacity_kwh": 60,
        "charger_power_kw": 22,
        "min_soc": 0.2,
        "target_soc": 0.8,
        "baseline_charge_threshold": 0.35,
        "trip_energy_kwh": 6,
        "future_demand_horizon": 2,
        "llm_agent": {
            "enabled": True,
            "provider": "openai_compatible",
            "model": "configured_by_env",
            "temperature": 0.2,
            "max_iterations_per_step": 2,
            "max_candidate_vehicles": 5,
            "fallback_to_heuristic": True,
            "log_agent_trace": True,
        },
        "agent_constraints": {},
        "scheduler_weights": {
            "w_soc": 0.35,
            "w_demand": 0.25,
            "w_availability": 0.2,
            "w_price": 0.1,
            "w_wait": 0.05,
            "w_congestion": 0.05,
        },
    }


def _state():
    return {
        "mode": "agentic_llm",
        "time_step": 0,
        "vehicles": [
            {
                "vehicle_id": "vehicle_000",
                "zone": "Z1",
                "soc": 0.25,
                "battery_capacity_kwh": 60,
                "waiting_time": 2,
                "status": "idle",
                "current_charger_id": None,
                "total_charge_kwh": 0.0,
                "total_cost_eur": 0.0,
                "total_trips_served": 0,
                "availability_failures": 0,
                "reasoning_summary": "",
                "heuristic_priority_score": 0.0,
            },
            {
                "vehicle_id": "vehicle_001",
                "zone": "Z1",
                "soc": 0.4,
                "battery_capacity_kwh": 60,
                "waiting_time": 1,
                "status": "idle",
                "current_charger_id": None,
                "total_charge_kwh": 0.0,
                "total_cost_eur": 0.0,
                "total_trips_served": 0,
                "availability_failures": 0,
                "reasoning_summary": "",
                "heuristic_priority_score": 0.0,
            },
        ],
        "chargers": [
            {"charger_id": "charger_000", "zone": "Z1", "power_kw": 22, "status": "available", "provider": "x"},
            {"charger_id": "charger_001", "zone": "Z1", "power_kw": 22, "status": "available", "provider": "x"},
        ],
        "fleet_size": 2,
        "electricity_price": 50.0,
        "price_series": [50.0, 60.0],
        "current_demand_by_zone": {"Z1": 2},
        "future_demand_by_zone": {"Z1": 3},
        "available_vehicles_by_zone": {"Z1": 2},
        "zone_congestion": {"Z1": 1.0},
        "total_cost_so_far": 0.0,
        "unmet_demand_so_far": 0,
        "served_demand_so_far": 0,
        "timestamps": ["2025-01-01T00:00:00"],
    }


class AgentSchedulerTests(unittest.TestCase):
    def test_agentic_scheduler_returns_valid_decision_format(self):
        planner = AgenticChargingPlanner(_config(), SmartPriorityScheduler(_config()))
        decisions = planner.plan_charging_actions(_state())
        self.assertTrue(decisions)
        self.assertIn("vehicle_id", decisions[0])
        self.assertIn("agent_used", decisions[0])

    def test_agentic_scheduler_falls_back_when_llm_returns_invalid_json(self):
        class BadPlanner(AgenticChargingPlanner):
            def _call_planner(self, observation_prompt, schema):
                return {"bad": "json", "_client": "real_llm"}

        planner = BadPlanner(_config(), SmartPriorityScheduler(_config()))
        decisions = planner.plan_charging_actions(_state())
        self.assertTrue(decisions[0]["fallback_used"])

    def test_mock_llm_produces_deterministic_output(self):
        mock = MockLLMClient()
        prompt = "OBSERVATION_JSON: {\"time_step\":0,\"available_chargers\":1,\"zone_status\":[{\"zone\":\"Z1\",\"available_charger_ids\":[\"charger_001\"]}],\"candidate_vehicles\":[{\"vehicle_id\":\"vehicle_001\",\"soc\":0.2,\"estimated_energy_needed_kwh\":20,\"heuristic_priority_score\":0.9}]}"
        first = mock.generate_json("sys", prompt, {})
        second = mock.generate_json("sys", prompt, {})
        self.assertEqual(first, second)

    def test_final_accepted_actions_always_pass_verifier(self):
        planner = AgenticChargingPlanner(_config(), SmartPriorityScheduler(_config()))
        decisions = planner.plan_charging_actions(_state())
        plan = AgentPlan.from_dict(
            {
                "time_step": 0,
                "strategy_summary": "wrapped",
                "actions": [
                    {
                        "vehicle_id": item["vehicle_id"],
                        "charger_id": item["charger_id"],
                        "zone": item["zone"],
                        "target_soc": item["target_soc"],
                        "planned_duration_hours": item["planned_duration_hours"],
                        "reasoning_summary": item["reasoning_summary"],
                    }
                    for item in decisions
                ],
                "rejected_candidates": [],
                "risk_notes": [],
                "expected_effect": "ok",
            }
        )
        result = PlanVerifier(_config()).validate_plan(plan, _state())
        self.assertFalse(result["rejected_actions"])
