import unittest
from pathlib import Path

from src.demand_model import build_demand_model
from src.fleet_model import build_fleet_and_chargers
from src.preprocessing import preprocess_inputs
from src.simulator import Simulator


def _config():
    return {
        "random_seed": 42,
        "simulation_hours": 2,
        "fleet_size": 6,
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


def _raw_data():
    return {
        "od_matrix_rows": [["EHV_001", "10", "5"], ["EHV_002", "4", "9"]],
        "zonal_load": [
            {"timestamp": "1/1/2025 0:00", "zone_id": "Z1", "demand_MW": "100"},
            {"timestamp": "1/1/2025 0:00", "zone_id": "Z2", "demand_MW": "80"},
            {"timestamp": "1/1/2025 1:00", "zone_id": "Z1", "demand_MW": "90"},
            {"timestamp": "1/1/2025 1:00", "zone_id": "Z2", "demand_MW": "85"},
        ],
        "prices": [
            {"Price (EUR/MWhe)": "50"},
            {"Price (EUR/MWhe)": "60"},
        ],
        "grid_congestion": [{"afname": "1.0"}],
        "mobility_hubs": [{"NAAM": "Hub A", "CAPACITEIT_AUTO": "3"}],
        "charging_points": [{"AANBIEDER": "x", "STATUS": "Bestaand"}],
    }


class SimulatorTests(unittest.TestCase):
    def test_simulator_can_run_all_modes(self):
        config = _config()
        preprocessed = preprocess_inputs(_raw_data(), config)
        demand_model = build_demand_model(preprocessed, config)
        fleet_assets = build_fleet_and_chargers(preprocessed, demand_model, config)
        simulator = Simulator(config, demand_model, fleet_assets, preprocessed, Path.cwd())
        results = simulator.run_all()
        self.assertEqual(set(results.keys()), {"nearest_available", "baseline", "smart_priority", "agentic_llm"})

    def test_all_timeseries_have_required_columns(self):
        config = _config()
        preprocessed = preprocess_inputs(_raw_data(), config)
        demand_model = build_demand_model(preprocessed, config)
        fleet_assets = build_fleet_and_chargers(preprocessed, demand_model, config)
        simulator = Simulator(config, demand_model, fleet_assets, preprocessed, Path.cwd())
        results = simulator.run_all()
        required = {"time_step", "scheduler_mode", "cumulative_cost_eur", "vehicle_availability", "average_soc"}
        for mode in results:
            self.assertTrue(required.issubset(results[mode]["timeseries"][0].keys()))
