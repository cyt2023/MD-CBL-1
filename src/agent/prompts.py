from __future__ import annotations

import json

from .schemas import AgentObservation


SYSTEM_PROMPT = """
You are an EV fleet charging planning agent.
Your objective is to reduce charging cost, unmet demand, waiting time, and congestion while preserving vehicle availability.
You are not the source of truth for numerical simulation.
You may propose charging strategy, select among candidate vehicles, explain decisions, react to validation feedback, and repair plans.
You must not invent or assert final SOC updates, charging cost, charger capacity, feasibility, or evaluation metrics as if you computed them.
Those values are computed and enforced by deterministic code outside the model.
You must output valid JSON only.
You must obey charger capacity, SOC limits, and zone constraints.
You should prioritize low-SOC vehicles in high-demand zones, especially when price is low.
You must provide a concise reasoning_summary for each action.
Do not invent vehicle IDs or charger IDs.
Do not assign the same charger to multiple vehicles in the same time step.
Do not charge vehicles already above target SOC.
Do not produce hidden chain-of-thought; only provide concise decision reasons.
""".strip()


def build_planning_prompt(observation: AgentObservation) -> str:
    candidate_lines = []
    for vehicle in observation.candidate_vehicles:
        candidate_lines.append(
            " | ".join(
                [
                    vehicle.vehicle_id,
                    vehicle.zone,
                    f"soc={vehicle.soc:.3f}",
                    f"wait={vehicle.waiting_time}",
                    f"future_demand={vehicle.future_demand:.2f}",
                    f"availability_risk={vehicle.availability_risk:.2f}",
                    f"energy_need_kwh={vehicle.estimated_energy_needed_kwh:.2f}",
                    f"heuristic_score={vehicle.heuristic_priority_score:.4f}",
                ]
            )
        )

    required_json = {
        "time_step": observation.time_step,
        "strategy_summary": "string",
        "actions": [
            {
                "vehicle_id": "string",
                "charger_id": "string",
                "zone": "string",
                "target_soc": 0.8,
                "planned_duration_hours": 1.0,
                "reasoning_summary": "string",
            }
        ],
        "rejected_candidates": ["vehicle_id"],
        "risk_notes": ["string"],
        "expected_effect": "string",
    }
    machine_payload = observation.to_dict()
    return "\n".join(
        [
            f"Current time step: {observation.time_step}",
            f"Electricity price: {observation.electricity_price}",
            f"Available chargers: {observation.available_chargers}/{observation.total_chargers}",
            f"Total demand this step: {observation.total_demand}",
            f"Served demand so far: {observation.served_demand_so_far}",
            f"Unmet demand so far: {observation.unmet_demand_so_far}",
            "Future demand and availability by zone:",
            json.dumps(observation.zone_status, indent=2),
            "Candidate vehicles table:",
            "\n".join(candidate_lines) if candidate_lines else "No candidates available.",
            "Constraints:",
            "- Output valid JSON only.",
            "- You are proposing a plan, not executing the simulation.",
            "- Deterministic code is the source of truth for SOC updates, charging cost, charger capacity, constraint validation, demand simulation, and evaluation metrics.",
            "- Use only listed vehicles and chargers.",
            "- Respect charger availability and zone feasibility.",
            "- Do not exceed target SOC or assign duplicate vehicles/chargers.",
            "Required JSON format:",
            json.dumps(required_json, indent=2),
            "OBSERVATION_JSON:",
            json.dumps(machine_payload, indent=2),
        ]
    )
