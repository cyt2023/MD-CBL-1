from __future__ import annotations

import json
from pathlib import Path

from .data_audit import run_data_audit
from .data_loader import load_project_data
from .demand_model import build_demand_model
from .evaluation import evaluate_results
from .fleet_model import build_fleet_and_chargers
from .preprocessing import preprocess_inputs
from .reporting import generate_reports
from .simulator import Simulator
from .visualization import generate_figures


def _load_config(project_root: Path) -> dict:
    config_path = project_root / "config" / "default_config.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config = _load_config(project_root)
    print("Step 1/12: Running data audit...")
    audit_summary = run_data_audit(project_root)
    print("Step 2/12: Loading raw datasets...")
    raw_data = load_project_data(project_root)
    print("Step 3/12: Preprocessing inputs...")
    preprocessed = preprocess_inputs(raw_data, config)
    print("Step 4/12: Building demand model...")
    demand_model = build_demand_model(preprocessed, config)
    print("Step 5/12: Building fleet and chargers...")
    fleet_assets = build_fleet_and_chargers(preprocessed, demand_model, config)
    simulator = Simulator(config, demand_model, fleet_assets, preprocessed, project_root)
    print("Step 6/12: Running baseline simulation...")
    simulation_results = {}
    simulation_results["baseline"] = simulator.run_mode("baseline")
    print("Step 7/12: Running smart-priority simulation...")
    simulation_results["smart_priority"] = simulator.run_mode("smart_priority")
    print("Step 8/12: Running agentic LLM simulation...")
    simulation_results["agentic_llm"] = simulator.run_mode("agentic_llm")
    print("Step 9/12: Evaluating strategies...")
    comparison_rows = evaluate_results(simulation_results, project_root)
    print("Step 10/12: Generating figures...")
    generate_figures(simulation_results, comparison_rows, project_root)
    print("Step 11/12: Generating reports...")
    generate_reports(comparison_rows, simulation_results, project_root)
    print("Step 12/12: Finalising summary...")

    comparison_lookup = {row["scheduler_mode"]: row for row in comparison_rows}
    agentic_llm_used = any(row["llm_used"] for row in simulation_results["agentic_llm"]["timeseries"])
    agentic_fallback_used = any(row["fallback_used"] for row in simulation_results["agentic_llm"]["timeseries"])

    print("Charging Scheduler Summary")
    print(f"Data audit status: {audit_summary['status']}")
    print(f"Baseline cost: EUR {comparison_lookup['baseline']['total_charging_cost_eur']}")
    print(f"Smart priority cost: EUR {comparison_lookup['smart_priority']['total_charging_cost_eur']}")
    print(f"Agentic cost: EUR {comparison_lookup['agentic_llm']['total_charging_cost_eur']}")
    print(
        "Cost reduction vs baseline: "
        f"{comparison_lookup['agentic_llm']['percentage_cost_reduction_vs_baseline']}%"
    )
    print(
        "Unmet demand comparison: "
        f"baseline={comparison_lookup['baseline']['total_unmet_demand']}, "
        f"smart={comparison_lookup['smart_priority']['total_unmet_demand']}, "
        f"agentic={comparison_lookup['agentic_llm']['total_unmet_demand']}"
    )
    print(
        "Availability comparison: "
        f"baseline={comparison_lookup['baseline']['average_vehicle_availability']}, "
        f"smart={comparison_lookup['smart_priority']['average_vehicle_availability']}, "
        f"agentic={comparison_lookup['agentic_llm']['average_vehicle_availability']}"
    )
    print(f"Real LLM used: {agentic_llm_used}")
    print(f"Fallback/mock used: {agentic_fallback_used or not agentic_llm_used}")
    print(f"Agent traces saved to: {project_root / 'outputs' / 'agent_traces'}")


if __name__ == "__main__":
    main()
