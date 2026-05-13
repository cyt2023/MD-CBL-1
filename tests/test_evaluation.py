import unittest
from pathlib import Path

from src.evaluation import evaluate_results


class EvaluationTests(unittest.TestCase):
    def test_comparison_summary_includes_all_three_strategies(self):
        results = {
            "nearest_available": {
                "timeseries": [
                    {
                        "cumulative_cost_eur": 12.0,
                        "cumulative_unmet_demand": 6,
                        "vehicle_availability": 0.76,
                        "charger_utilization": 0.7,
                        "waiting_vehicle_hours": 3,
                        "average_soc": 0.57,
                        "minimum_soc": 0.2,
                    }
                ]
            },
            "baseline": {
                "timeseries": [
                    {
                        "cumulative_cost_eur": 10.0,
                        "cumulative_unmet_demand": 5,
                        "vehicle_availability": 0.8,
                        "charger_utilization": 0.6,
                        "waiting_vehicle_hours": 2,
                        "average_soc": 0.55,
                        "minimum_soc": 0.2,
                    }
                ]
            },
            "smart_priority": {
                "timeseries": [
                    {
                        "cumulative_cost_eur": 9.0,
                        "cumulative_unmet_demand": 4,
                        "vehicle_availability": 0.82,
                        "charger_utilization": 0.5,
                        "waiting_vehicle_hours": 2,
                        "average_soc": 0.58,
                        "minimum_soc": 0.22,
                    }
                ]
            },
            "agentic_llm": {
                "timeseries": [
                    {
                        "cumulative_cost_eur": 8.0,
                        "cumulative_unmet_demand": 3,
                        "vehicle_availability": 0.84,
                        "charger_utilization": 0.55,
                        "waiting_vehicle_hours": 1,
                        "average_soc": 0.6,
                        "minimum_soc": 0.24,
                    }
                ]
            },
        }
        summary = evaluate_results(results, Path.cwd())
        self.assertEqual({row["scheduler_mode"] for row in summary}, {"nearest_available", "baseline", "smart_priority", "agentic_llm"})
        agentic = next(row for row in summary if row["scheduler_mode"] == "agentic_llm")
        self.assertEqual(agentic["percentage_cost_reduction_vs_nearest_available"], 33.33)
