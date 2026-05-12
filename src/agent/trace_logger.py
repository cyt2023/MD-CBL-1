from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List


class AgentTraceLogger:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.summary_path = self.output_dir / "agent_trace_summary.csv"

    def log_trace(self, time_step: int, payload: Dict[str, object]) -> None:
        trace_path = self.output_dir / f"agent_trace_timestep_{time_step:03d}.json"
        trace_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        summary_row = {
            "time_step": time_step,
            "candidate_count": len(payload.get("candidate_vehicles", [])),
            "validated_action_count": len(payload.get("validated_actions", [])),
            "rejected_action_count": len(payload.get("rejected_actions", [])),
            "fallback_used": payload.get("fallback_used", False),
            "llm_used": payload.get("llm_used", False),
        }
        rows: List[Dict[str, object]] = []
        if self.summary_path.exists() and self.summary_path.stat().st_size > 0:
            with self.summary_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        rows = [row for row in rows if int(row["time_step"]) != time_step]
        rows.append(summary_row)
        rows.sort(key=lambda row: int(row["time_step"]))
        with self.summary_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary_row.keys()))
            writer.writeheader()
            writer.writerows(rows)
