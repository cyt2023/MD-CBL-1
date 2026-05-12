from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class SchemaValidationError(ValueError):
    """Raised when agent JSON does not satisfy the expected structure."""


def _require(data: Dict[str, Any], field_name: str, expected_type):
    if field_name not in data:
        raise SchemaValidationError(f"Missing required field: {field_name}")
    value = data[field_name]
    if expected_type is float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise SchemaValidationError(f"Field {field_name} must be numeric") from exc
    if expected_type is int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise SchemaValidationError(f"Field {field_name} must be integer") from exc
    if expected_type is str:
        if value is None:
            raise SchemaValidationError(f"Field {field_name} must be string")
        return str(value)
    if expected_type is list:
        if not isinstance(value, list):
            raise SchemaValidationError(f"Field {field_name} must be list")
        return value
    if not isinstance(value, expected_type):
        raise SchemaValidationError(f"Field {field_name} must be of type {expected_type.__name__}")
    return value


@dataclass
class CandidateVehicle:
    vehicle_id: str
    zone: str
    soc: float
    waiting_time: int
    future_demand: float
    availability_risk: float
    estimated_energy_needed_kwh: float
    heuristic_priority_score: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateVehicle":
        return cls(
            vehicle_id=_require(data, "vehicle_id", str),
            zone=_require(data, "zone", str),
            soc=_require(data, "soc", float),
            waiting_time=_require(data, "waiting_time", int),
            future_demand=_require(data, "future_demand", float),
            availability_risk=_require(data, "availability_risk", float),
            estimated_energy_needed_kwh=_require(data, "estimated_energy_needed_kwh", float),
            heuristic_priority_score=_require(data, "heuristic_priority_score", float),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChargingAction:
    vehicle_id: str
    charger_id: str
    zone: str
    target_soc: float
    planned_duration_hours: float
    reasoning_summary: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChargingAction":
        return cls(
            vehicle_id=_require(data, "vehicle_id", str),
            charger_id=_require(data, "charger_id", str),
            zone=_require(data, "zone", str),
            target_soc=_require(data, "target_soc", float),
            planned_duration_hours=_require(data, "planned_duration_hours", float),
            reasoning_summary=_require(data, "reasoning_summary", str),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentObservation:
    time_step: int
    electricity_price: float
    available_chargers: int
    total_chargers: int
    total_demand: float
    served_demand_so_far: float
    unmet_demand_so_far: float
    zone_status: List[Dict[str, Any]]
    candidate_vehicles: List[CandidateVehicle]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentObservation":
        return cls(
            time_step=_require(data, "time_step", int),
            electricity_price=_require(data, "electricity_price", float),
            available_chargers=_require(data, "available_chargers", int),
            total_chargers=_require(data, "total_chargers", int),
            total_demand=_require(data, "total_demand", float),
            served_demand_so_far=_require(data, "served_demand_so_far", float),
            unmet_demand_so_far=_require(data, "unmet_demand_so_far", float),
            zone_status=_require(data, "zone_status", list),
            candidate_vehicles=[CandidateVehicle.from_dict(item) for item in _require(data, "candidate_vehicles", list)],
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["candidate_vehicles"] = [item.to_dict() for item in self.candidate_vehicles]
        return payload


@dataclass
class AgentPlan:
    time_step: int
    strategy_summary: str
    actions: List[ChargingAction]
    rejected_candidates: List[str]
    risk_notes: List[str]
    expected_effect: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentPlan":
        actions = [ChargingAction.from_dict(item) for item in _require(data, "actions", list)]
        return cls(
            time_step=_require(data, "time_step", int),
            strategy_summary=_require(data, "strategy_summary", str),
            actions=actions,
            rejected_candidates=[str(item) for item in _require(data, "rejected_candidates", list)],
            risk_notes=[str(item) for item in _require(data, "risk_notes", list)],
            expected_effect=_require(data, "expected_effect", str),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["actions"] = [item.to_dict() for item in self.actions]
        return payload

    @staticmethod
    def json_schema() -> Dict[str, Any]:
        return {
            "type": "object",
            "required": [
                "time_step",
                "strategy_summary",
                "actions",
                "rejected_candidates",
                "risk_notes",
                "expected_effect",
            ],
            "properties": {
                "time_step": {"type": "integer"},
                "strategy_summary": {"type": "string"},
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": [
                            "vehicle_id",
                            "charger_id",
                            "zone",
                            "target_soc",
                            "planned_duration_hours",
                            "reasoning_summary",
                        ],
                    },
                },
                "rejected_candidates": {"type": "array", "items": {"type": "string"}},
                "risk_notes": {"type": "array", "items": {"type": "string"}},
                "expected_effect": {"type": "string"},
            },
        }


@dataclass
class ValidatedChargingAction(ChargingAction):
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)
    repaired_from_original: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentDecisionTrace:
    time_step: int
    observation_summary: Dict[str, Any]
    llm_plan: Dict[str, Any]
    validation_result: Dict[str, Any]
    final_actions: List[Dict[str, Any]]
    repair_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
