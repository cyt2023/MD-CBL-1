from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .llm_client import LLMClient, MockLLMClient
from .planning_tools import build_observation
from .prompts import SYSTEM_PROMPT, build_planning_prompt
from .schemas import AgentDecisionTrace, AgentPlan, SchemaValidationError
from .trace_logger import AgentTraceLogger
from .verifier import PlanVerifier


class AgenticChargingPlanner:
    def __init__(self, config: Dict[str, object], fallback_scheduler):
        self.config = config
        self.fallback_scheduler = fallback_scheduler
        self.verifier = PlanVerifier(config)
        self.llm_client = LLMClient()
        self.mock_client = MockLLMClient()
        project_root = Path(__file__).resolve().parent.parent.parent
        self.trace_logger = AgentTraceLogger(project_root / "outputs" / "agent_traces")

    def _fallback_decisions(self, state: Dict[str, object], reason: str) -> List[Dict[str, object]]:
        fallback_decisions = self.fallback_scheduler.schedule(state)
        for decision in fallback_decisions:
            decision["agent_used"] = "agentic_llm"
            decision["llm_used"] = False
            decision["fallback_used"] = True
            decision["validation_errors"] = reason
            decision["agent_strategy_summary"] = "Fallback to deterministic smart-priority scheduler."
        return fallback_decisions

    def _merge_with_heuristic_support(
        self,
        state: Dict[str, object],
        planned_decisions: List[Dict[str, object]],
        strategy_summary: str,
    ) -> List[Dict[str, object]]:
        available_chargers = sum(1 for charger in state["chargers"] if charger["status"] == "available")
        current_demand = float(sum(state["current_demand_by_zone"].values()))
        future_demand = float(sum(state["future_demand_by_zone"].values()))
        available_vehicles = float(sum(state["available_vehicles_by_zone"].values()))
        vehicle_socs = [float(vehicle["soc"]) for vehicle in state["vehicles"]]
        average_soc = sum(vehicle_socs) / max(len(vehicle_socs), 1)
        minimum_soc = min(vehicle_socs) if vehicle_socs else 1.0
        need_extra_support = (
            len(planned_decisions) < available_chargers
            and (
                state["unmet_demand_so_far"] > 0
                or future_demand > available_vehicles
                or current_demand >= max(available_vehicles - 1.0, 1.0)
                or average_soc < 0.4
                or minimum_soc < 0.2
            )
        )
        if not need_extra_support:
            return planned_decisions

        heuristic_decisions = self.fallback_scheduler.schedule(state)
        vehicles_by_id = {vehicle["vehicle_id"]: vehicle for vehicle in state["vehicles"]}
        chargers_by_id = {charger["charger_id"]: charger for charger in state["chargers"]}
        used_vehicles = {decision["vehicle_id"] for decision in planned_decisions}
        used_chargers = {decision["charger_id"] for decision in planned_decisions}
        completed_plan = list(planned_decisions)
        for decision in heuristic_decisions:
            if len(completed_plan) >= available_chargers:
                break
            if decision["vehicle_id"] in used_vehicles or decision["charger_id"] in used_chargers:
                continue
            vehicle = vehicles_by_id.get(decision["vehicle_id"])
            charger = chargers_by_id.get(decision["charger_id"])
            if vehicle and charger:
                current_soc = float(vehicle["soc"])
                future_zone_demand = float(state["future_demand_by_zone"].get(vehicle["zone"], 0.0))
                available_zone_vehicles = float(state["available_vehicles_by_zone"].get(vehicle["zone"], 0.0))
                urgent_gap = max(0.0, future_zone_demand - available_zone_vehicles)
                staged_target = 0.66
                if urgent_gap >= 1.0:
                    staged_target = 0.71
                if urgent_gap >= 2.0 or state["unmet_demand_so_far"] > 0 or minimum_soc < 0.18:
                    staged_target = 0.76
                new_target_soc = max(current_soc + 0.06, min(float(decision["target_soc"]), staged_target))
                battery_kwh = float(vehicle["battery_capacity_kwh"])
                power_kw = float(charger["power_kw"])
                energy_needed_kwh = max(0.0, (new_target_soc - current_soc) * battery_kwh)
                staged_duration = round(max(0.05, min(1.0, energy_needed_kwh / max(power_kw, 1e-9))), 3)
                decision["target_soc"] = round(new_target_soc, 3)
                decision["planned_duration_hours"] = staged_duration
            decision["agent_used"] = "agentic_llm"
            decision["llm_used"] = False
            decision["fallback_used"] = False
            decision["validation_errors"] = ""
            decision["reasoning_summary"] = (
                decision.get("reasoning_summary", "")
                + " Deterministic support layer used shallow charging to fill unused safe capacity."
            ).strip()
            decision["agent_strategy_summary"] = (
                strategy_summary
                + " Deterministic support layer supplemented the plan to protect availability."
            )
            completed_plan.append(decision)
            used_vehicles.add(decision["vehicle_id"])
            used_chargers.add(decision["charger_id"])
        return completed_plan

    def _call_planner(self, observation_prompt: str, schema: dict) -> Dict[str, object]:
        if self.config["llm_agent"]["enabled"] and self._should_use_real_llm():
            response = self.llm_client.generate_json(SYSTEM_PROMPT, observation_prompt, schema)
            if not response.get("fallback_to_mock"):
                response["_client"] = "real_llm"
                return response
            primary_error = {
                "provider": response.get("provider", self.llm_client.provider),
                "error": response.get("error", "unknown_error"),
                "details": response.get("details", ""),
            }
            response = self.mock_client.generate_json(SYSTEM_PROMPT, observation_prompt, schema)
            response["_client"] = "mock_llm"
            response["_primary_llm_error"] = primary_error
            return response
        response = self.mock_client.generate_json(SYSTEM_PROMPT, observation_prompt, schema)
        response["_client"] = "mock_llm"
        if self.config["llm_agent"]["enabled"]:
            response["_primary_llm_error"] = {
                "provider": self.llm_client.provider,
                "error": "Real LLM call skipped for this time step.",
                "details": self._real_llm_skip_reason(),
            }
        return response

    def _real_llm_skip_reason(self) -> str:
        if not self.llm_client.is_configured:
            return "DASHSCOPE_API_KEY is missing from this Python process." if self.llm_client.provider == "qwen" else "LLM client is not configured."
        interval = int(self.config["llm_agent"].get("real_llm_call_interval", 1))
        min_step = int(self.config["llm_agent"].get("real_llm_min_time_step", 0))
        return f"Real LLM is configured to run only every {interval} step(s), starting at step {min_step}."

    def _should_use_real_llm(self) -> bool:
        if not self.llm_client.is_configured:
            return False
        return True

    def plan_charging_actions(self, state: Dict[str, object]) -> List[Dict[str, object]]:
        observation = build_observation(state, self.config)
        time_step = int(state["time_step"])
        schema = AgentPlan.json_schema()
        user_prompt = build_planning_prompt(observation)
        raw_plan: Dict[str, object] = {}
        validation_result: Dict[str, object] = {"validated_actions": [], "rejected_actions": [], "repair_notes": []}
        llm_used = False
        fallback_used = False
        final_decisions: List[Dict[str, object]] = []
        repair_feedback = ""
        last_error = ""
        completed_iterations = 0

        for iteration in range(int(self.config["llm_agent"]["max_iterations_per_step"])):
            completed_iterations = iteration + 1
            prompt = user_prompt
            if repair_feedback:
                prompt = (
                    user_prompt
                    + "\nValidation feedback from the deterministic verifier:\n"
                    + repair_feedback
                    + "\nReturn a repaired JSON plan using only valid actions."
                )
            interval = int(self.config["llm_agent"].get("real_llm_call_interval", 1))
            min_step = int(self.config["llm_agent"].get("real_llm_min_time_step", 0))
            use_real_this_step = time_step >= min_step and (time_step - min_step) % max(interval, 1) == 0
            if not use_real_this_step and self.llm_client.is_configured:
                raw_plan = self.mock_client.generate_json(SYSTEM_PROMPT, prompt, schema)
                raw_plan["_client"] = "mock_llm"
                raw_plan["_primary_llm_error"] = {
                    "provider": self.llm_client.provider,
                    "error": "Real LLM call skipped for this time step.",
                    "details": self._real_llm_skip_reason(),
                }
            else:
                raw_plan = self._call_planner(prompt, schema)
            llm_used = raw_plan.get("_client") == "real_llm"
            try:
                parsed_plan = AgentPlan.from_dict(raw_plan)
            except SchemaValidationError as exc:
                last_error = f"Invalid JSON plan structure: {exc}"
                repair_feedback = last_error
                continue
            validation_result = self.verifier.validate_plan(parsed_plan, state)
            if validation_result["validated_actions"]:
                final_decisions = [action.to_dict() for action in validation_result["validated_actions"]]
                break
            if validation_result["validation_errors"]:
                last_error = "; ".join(validation_result["validation_errors"])
                repair_feedback = last_error

        if not final_decisions:
            fallback_used = True
            final_decisions = self._fallback_decisions(state, last_error or "planner returned no valid actions")

        strategy_summary = raw_plan.get(
            "strategy_summary",
            "Fallback to deterministic strategy after validation failures.",
        )
        if not fallback_used:
            final_decisions = self._merge_with_heuristic_support(state, final_decisions, strategy_summary)
        for decision in final_decisions:
            decision.setdefault("agent_used", "agentic_llm")
            decision.setdefault("llm_used", llm_used)
            decision.setdefault("fallback_used", fallback_used)
            decision.setdefault("validation_errors", "; ".join(validation_result.get("validation_errors", [])))
            decision.setdefault("reasoning_summary", "Validated agentic charging action.")
            decision.setdefault("heuristic_priority_score", 0.0)
            decision.setdefault("agent_strategy_summary", strategy_summary)

        trace = AgentDecisionTrace(
            time_step=observation.time_step,
            observation_summary=observation.to_dict(),
            llm_plan=raw_plan,
            validation_result={
                "validated_actions": [action.to_dict() for action in validation_result.get("validated_actions", [])],
                "rejected_actions": validation_result.get("rejected_actions", []),
            },
            final_actions=final_decisions,
            repair_notes=validation_result.get("repair_notes", []),
        )
        self.trace_logger.log_trace(
            observation.time_step,
            {
                "planner_role": "LLM or mock planner proposes structured actions only; deterministic code validates and executes.",
                "deterministic_source_of_truth": {
                    "soc_updates": "simulator",
                    "charging_cost": "simulator",
                    "charger_capacity": "verifier_and_simulator",
                    "constraint_validation": "verifier",
                    "demand_simulation": "simulator",
                    "evaluation_metrics": "evaluation",
                },
                "llm_config_summary": self.llm_client.config_summary(),
                "iterations_used": completed_iterations,
                "observation_summary": trace.observation_summary,
                "candidate_vehicles": [item.to_dict() for item in observation.candidate_vehicles],
                "llm_raw_json_plan": raw_plan,
                "validated_actions": trace.validation_result.get("validated_actions", []),
                "rejected_actions": trace.validation_result.get("rejected_actions", []),
                "repair_notes": trace.repair_notes,
                "final_committed_actions": trace.final_actions,
                "fallback_used": fallback_used,
                "llm_used": llm_used,
            },
        )
        return final_decisions
