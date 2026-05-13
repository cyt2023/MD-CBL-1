from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def generate_reports(
    comparison_rows: List[Dict[str, object]],
    simulation_results: Dict[str, Dict[str, object]],
    project_root: Path,
) -> Dict[str, Path]:
    reports_dir = project_root / "outputs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    comparison_lookup = {row["scheduler_mode"]: row for row in comparison_rows}
    agentic_used_llm = any(row["llm_used"] for row in simulation_results["agentic_llm"]["timeseries"])
    fallback_used = any(row["fallback_used"] for row in simulation_results["agentic_llm"]["timeseries"])
    executive = reports_dir / "executive_summary.md"
    executive.write_text(
        "\n".join(
            [
                "# Executive Summary",
                "",
                "This project evaluates four charging strategies for a shared EV fleet in Eindhoven: nearest-available naive charging, baseline threshold charging, smart priority, and agentic LLM.",
                "",
                f"- Nearest-available naive cost: EUR {comparison_lookup['nearest_available']['total_charging_cost_eur']}",
                f"- Baseline cost: EUR {comparison_lookup['baseline']['total_charging_cost_eur']}",
                f"- Smart priority cost: EUR {comparison_lookup['smart_priority']['total_charging_cost_eur']}",
                f"- Agentic LLM cost: EUR {comparison_lookup['agentic_llm']['total_charging_cost_eur']}",
                f"- Agentic cost reduction vs nearest-available naive: {comparison_lookup['agentic_llm']['percentage_cost_reduction_vs_nearest_available']}%",
                f"- Agentic unmet demand: {comparison_lookup['agentic_llm']['total_unmet_demand']}",
                f"- Real LLM used: {agentic_used_llm}",
                f"- Fallback heuristic used: {fallback_used}",
                "",
                "The agentic scheduler is evaluated by quantitative operational metrics and validated decision traces, not by subjective language quality.",
            ]
        ),
        encoding="utf-8",
    )

    technical = reports_dir / "technical_summary.md"
    technical.write_text(
        "\n".join(
            [
                "# Technical Summary",
                "",
                "The pipeline loads the Eindhoven mobility, hub, congestion, load, and electricity price datasets, builds a synthetic but reproducible fleet, and runs four comparable 24-hour simulations from the same initial state.",
                "",
                "The nearest-available scheduler represents a naive individual behaviour: charge at the same-zone charger if possible without fleet-level planning. The baseline scheduler uses a fixed threshold. The smart priority scheduler uses deterministic weighted scoring. The agentic LLM scheduler uses deterministic candidate ranking, an optional LLM planning loop, strict validation and repair, heuristic fallback, and trace logging.",
                "",
                "Outputs include comparison metrics, charging plans, time series, figures, reports, and agent decision traces.",
                "",
                "Limitations: spatial matching is simplified to zone-level assignment, the LLM is bounded to structured JSON planning, and final actions only enter the simulator after deterministic verification.",
            ]
        ),
        encoding="utf-8",
    )
    return {"executive_summary": executive, "technical_summary": technical}
