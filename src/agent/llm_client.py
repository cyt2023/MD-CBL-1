from __future__ import annotations

import json
import os
import socket
import time
from typing import Any, Dict, List
from urllib import error, request


def _extract_observation_json(user_prompt: str) -> Dict[str, Any]:
    marker = "OBSERVATION_JSON:"
    if marker not in user_prompt:
        return {}
    payload = user_prompt.split(marker, 1)[1].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


def _clean_env_value(value: str) -> str:
    cleaned = value.strip()
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u3000": " ",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _is_latin1_compatible(value: str) -> bool:
    try:
        value.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


class MockLLMClient:
    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        observation = _extract_observation_json(user_prompt)
        candidate_vehicles: List[Dict[str, Any]] = observation.get("candidate_vehicles", [])
        available_chargers = observation.get("available_chargers", 0)
        zone_status = observation.get("zone_status", [])
        chargers = []
        zone_lookup: Dict[str, Dict[str, Any]] = {zone["zone"]: zone for zone in zone_status}
        zone_charge_limits: Dict[str, int] = {}
        for zone in zone_status:
            for charger_id in zone.get("available_charger_ids", []):
                chargers.append({"charger_id": charger_id, "zone": zone["zone"]})
            available_vehicles = int(zone.get("available_vehicles", 0))
            current_demand = float(zone.get("current_demand", 0))
            future_demand = float(zone.get("future_demand", 0))
            slack = available_vehicles - max(int(round(current_demand)), int(round(future_demand / 2.0)))
            zone_charge_limits[zone["zone"]] = max(0, min(len(zone.get("available_charger_ids", [])), slack))
        candidate_vehicles.sort(
            key=lambda item: (-float(item.get("heuristic_priority_score", 0.0)), float(item.get("soc", 1.0)), item.get("vehicle_id", ""))
        )
        actions = []
        zone_assigned_counts: Dict[str, int] = {}
        used_chargers = set()
        for vehicle in candidate_vehicles:
            zone = vehicle.get("zone", "")
            zone_meta = zone_lookup.get(zone, {})
            assigned = zone_assigned_counts.get(zone, 0)
            emergency_low_soc = float(vehicle.get("soc", 1.0)) < 0.28
            if assigned >= zone_charge_limits.get(zone, 0) and not emergency_low_soc:
                continue
            charger = next(
                (
                    item
                    for item in chargers
                    if item["zone"] == zone and item["charger_id"] not in used_chargers
                ),
                None,
            )
            if charger is None:
                charger = next((item for item in chargers if item["charger_id"] not in used_chargers), None)
            if charger is None or len(actions) >= available_chargers:
                break
            current_soc = float(vehicle.get("soc", 0.0))
            demand_gap = max(
                0.0,
                float(zone_meta.get("future_demand", 0.0)) - float(zone_meta.get("available_vehicles", 0.0)),
            )
            target_soc = 0.66
            if emergency_low_soc or demand_gap >= 1.0:
                target_soc = 0.72
            if current_soc < 0.22 or demand_gap >= 2.0:
                target_soc = 0.76
            energy_need = max(0.0, float(vehicle.get("estimated_energy_needed_kwh", 0.0)))
            battery_capacity = energy_need / max(0.8 - current_soc, 1e-9) if energy_need else 60.0
            staged_energy_need = max(0.0, (target_soc - current_soc) * battery_capacity)
            duration = round(max(0.05, min(1.0, staged_energy_need / 22.0)), 3)
            if current_soc >= target_soc:
                continue
            if (
                not emergency_low_soc
                and float(zone_meta.get("current_demand", 0)) >= float(zone_meta.get("available_vehicles", 0))
            ):
                continue
            actions.append(
                {
                    "vehicle_id": vehicle["vehicle_id"],
                    "charger_id": charger["charger_id"],
                    "zone": charger["zone"],
                    "target_soc": target_soc,
                    "planned_duration_hours": duration,
                    "reasoning_summary": "Deterministic mock selected the highest-priority candidate.",
                }
            )
            used_chargers.add(charger["charger_id"])
            zone_assigned_counts[zone] = assigned + 1
        rejected = [item["vehicle_id"] for item in candidate_vehicles[len(actions):]]
        return {
            "time_step": observation.get("time_step", 0),
            "strategy_summary": "Mock LLM selected high-priority candidates while preserving near-term zone availability.",
            "actions": actions,
            "rejected_candidates": rejected,
            "risk_notes": ["Fallback mock used deterministic ranking rather than a remote model."],
            "expected_effect": "Should improve near-term SOC readiness in high-priority zones.",
        }


class LLMClient:
    def __init__(self, timeout_seconds: int = 20, max_retries: int = 2):
        self.provider = os.getenv("LLM_PROVIDER", "qwen").strip().lower() or "qwen"
        self.qwen_protocol = os.getenv("QWEN_PROTOCOL", "openai_compatible").strip().lower()
        self.api_key = self._resolve_api_key()
        self.base_url = self._resolve_base_url()
        self.model = self._resolve_model()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.disable_after_failure = os.getenv("LLM_DISABLE_AFTER_FAILURE", "1").strip() != "0"
        self.disabled_reason = ""

    def _resolve_api_key(self) -> str:
        if self.provider == "qwen":
            return _clean_env_value(os.getenv("DASHSCOPE_API_KEY", "").strip())
        return _clean_env_value(os.getenv("LLM_API_KEY", "").strip())

    def _resolve_base_url(self) -> str:
        if self.provider == "qwen":
            if self.qwen_protocol == "openai_compatible":
                default_base = "https://ws-wlm3jok3dxf4za9f.eu-central-1.maas.aliyuncs.com/compatible-mode/v1"
                return _clean_env_value(
                    os.getenv("QWEN_BASE_URL", "").strip()
                    or os.getenv("LLM_BASE_URL", "").strip()
                    or default_base
                )
            default_base = "https://dashscope.aliyuncs.com/api/v1"
            return _clean_env_value(
                os.getenv("QWEN_DASHSCOPE_BASE_URL", "").strip()
                or os.getenv("QWEN_BASE_URL", "").strip()
                or os.getenv("LLM_BASE_URL", "").strip()
                or default_base
            )
        return _clean_env_value(os.getenv("LLM_BASE_URL", "").strip())

    def _resolve_model(self) -> str:
        if self.provider == "qwen":
            return _clean_env_value(
                os.getenv("QWEN_MODEL", "").strip()
                or os.getenv("LLM_MODEL", "").strip()
                or "qwen3.5-flash"
            )
        return _clean_env_value(os.getenv("LLM_MODEL", "").strip())

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def config_summary(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "qwen_protocol": self.qwen_protocol,
            "configured": self.is_configured,
            "api_key_set": bool(self.api_key),
            "base_url": self.base_url,
            "model": self.model,
            "disabled": bool(self.disabled_reason),
            "disabled_reason": self.disabled_reason,
        }

    def _validate_runtime_config(self) -> str:
        if not self.api_key:
            return "API key is missing."
        if not _is_latin1_compatible(f"Bearer {self.api_key}"):
            return "API key contains non-Latin-1 characters. Check for Chinese quotes or copied placeholder text."
        if not self.base_url.startswith("http://") and not self.base_url.startswith("https://"):
            return "Base URL must start with http:// or https://."
        if any(ord(char) > 255 for char in self.base_url):
            return "Base URL contains non-ASCII characters."
        return ""

    def _build_url(self) -> str:
        if self.provider == "qwen" and self.qwen_protocol == "dashscope_native":
            if "/compatible-mode/" in self.base_url:
                base_url = self.base_url.split("/compatible-mode/", 1)[0] + "/api/v1"
            else:
                base_url = self.base_url.rstrip("/")
            return base_url + "/services/aigc/text-generation/generation"
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url.rstrip("/") + "/chat/completions"

    def _extract_message_content(self, payload: Dict[str, Any]) -> str:
        output = payload.get("output", {})
        if isinstance(output, dict):
            choices = output.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    return message.get("content", "")
            text = output.get("text")
            if text:
                return str(text)
        choices = payload.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("content", "")
        output = payload.get("output", [])
        if output:
            parts = output[0].get("content", [])
            text_parts = [item.get("text", "") for item in parts if isinstance(item, dict)]
            return "".join(text_parts)
        return ""

    def _build_payload(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.provider == "qwen" and self.qwen_protocol == "dashscope_native":
            return {
                "model": self.model,
                "input": {"messages": messages},
                "parameters": {
                    "temperature": 0.1,
                    "result_format": "message",
                    "enable_thinking": False,
                },
            }
        if self.provider == "qwen":
            return {
                "model": self.model,
                "messages": messages,
            }
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": messages,
        }
        if self.provider != "qwen":
            payload["response_format"] = {"type": "json_object"}
        return payload

    def generate_json(self, system_prompt: str, user_prompt: str, schema: dict) -> dict:
        if self.disabled_reason:
            return {
                "error": self.disabled_reason,
                "provider": self.provider,
                "fallback_to_mock": True,
            }
        if not self.is_configured:
            missing_message = "DASHSCOPE_API_KEY is not set. Set it locally before running the agentic scheduler."
            if self.provider != "qwen":
                missing_message = f"LLM environment variables are not fully configured for provider={self.provider}."
            return {
                "error": missing_message,
                "fallback_to_mock": True,
            }
        config_error = self._validate_runtime_config()
        if config_error:
            return {
                "error": config_error,
                "provider": self.provider,
                "fallback_to_mock": True,
            }
        payload = self._build_payload(system_prompt, user_prompt)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = request.Request(self._build_url(), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        last_error = "unknown_error"
        for attempt in range(self.max_retries + 1):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    raw_text = response.read().decode("utf-8")
                response_json = json.loads(raw_text)
                content = self._extract_message_content(response_json)
                return json.loads(content)
            except (
                error.HTTPError,
                error.URLError,
                TimeoutError,
                socket.timeout,
                json.JSONDecodeError,
                UnicodeEncodeError,
                ValueError,
            ) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, error.HTTPError):
                    try:
                        body = exc.read().decode("utf-8", errors="replace")
                    except Exception:
                        body = ""
                    if body:
                        last_error = f"{last_error} | response_body={body[:1000]}"
                if attempt >= self.max_retries:
                    break
                time.sleep(0.5 * (attempt + 1))
        if self.disable_after_failure:
            self.disabled_reason = (
                f"Remote {self.provider} planner disabled after failure: {last_error}. "
                "Subsequent steps will use deterministic fallback."
            )
        return {
            "error": "LLM request failed after retries.",
            "details": last_error,
            "provider": self.provider,
            "fallback_to_mock": True,
        }
