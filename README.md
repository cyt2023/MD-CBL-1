# Agentic EV Charging Scheduler

A reproducible, data-driven charging scheduler for shared mobility and rental EV fleets in Eindhoven. The project compares three charging strategies and adds an agentic LLM planner that proposes charging actions, while deterministic software remains the source of truth for simulation, validation, cost, and evaluation.

## Project Goal

Fleet operators need to decide which EVs should charge, when they should charge, where they should charge, and how long charging should last. The scheduler balances:

- charging cost,
- unmet mobility demand,
- fleet availability,
- charger congestion,
- vehicle state of charge (SOC),
- future zone-level demand.

The current implementation runs a 24-hour simulation over the Eindhoven fleet scenario and produces comparable metrics, figures, reports, and per-step agent traces.

## Scheduler Modes

The system supports three modes:

| Mode | Description | Requires LLM |
|---|---|---|
| `baseline` | Fixed threshold scheduler. Vehicles below a SOC threshold are charged. | No |
| `smart_priority` | Deterministic priority scheduler using SOC, demand, availability risk, waiting time, price, and congestion weights. | No |
| `agentic_llm` | Agentic planner that observes state, proposes structured actions, receives deterministic validation, repairs or falls back, and logs decision traces. | Optional |

If no API key is configured, or if the remote LLM fails, `agentic_llm` automatically falls back to a deterministic mock planner plus heuristic support. This keeps the project runnable during grading.

## What Makes It Agentic

The LLM is not used as a blind optimizer. It is used as a bounded planning agent inside a controlled loop:

```text
System state
    -> deterministic observation builder
    -> candidate vehicle pre-ranking
    -> LLM or mock planner proposes JSON actions
    -> deterministic verifier validates and repairs
    -> invalid plans are rejected or fallback is used
    -> deterministic simulator executes SOC, cost, demand, and charger updates
    -> trace logger stores an explainable decision record
```

The agentic behavior is implemented mainly in:

- `src/agent/charging_agent.py`: agent loop and fallback orchestration.
- `src/agent/planning_tools.py`: deterministic observation, scoring, candidate selection, and tool-like helpers.
- `src/agent/prompts.py`: strict planner instructions and JSON-only prompt format.
- `src/agent/schemas.py`: structured input/output models for observations, plans, actions, and traces.
- `src/agent/verifier.py`: deterministic safety layer for LLM-proposed actions.
- `src/agent/trace_logger.py`: per-step JSON traces and summary CSV.

## Safety and Reproducibility Principle

The LLM is not the source of truth for numerical simulation.

The LLM can:

- propose a charging strategy,
- select among candidate vehicles,
- provide concise reasoning summaries,
- react to validation feedback,
- repair invalid JSON plans.

Deterministic code must:

- calculate SOC updates,
- calculate charging cost,
- enforce charger capacity,
- validate constraints,
- simulate demand,
- compute evaluation metrics,
- reject unsafe or invalid plans.

No LLM output enters the simulator unless it passes the deterministic verifier. This separation makes the project explainable, reproducible, and defensible for a university software deliverable.

## Current Results

Latest deterministic fallback/mock run:

| Scheduler | Cost (EUR) | Charged Energy (kWh) | Unmet Demand | Avg Availability | Operational Score |
|---|---:|---:|---:|---:|---:|
| `baseline` | 88.473 | 2420.000 | 7 | 0.836 | 37.210 |
| `smart_priority` | 93.784 | 2565.236 | 9 | 0.889 | 31.807 |
| `agentic_llm` | 89.917 | 2459.428 | 4 | 0.839 | 48.128 |

In this run, the agentic scheduler charges more energy than the baseline while reducing unmet demand from 7 to 4. Because the first 24-hour electricity price window is effectively constant, lower total cost and higher total kWh cannot both be guaranteed against the same baseline. The implemented objective is therefore to improve operational value per euro: more useful charging, fewer missed requests, and traceable decisions with cost close to baseline.

## Repository Structure

```text
src/
  agent/
    llm_client.py
    prompts.py
    schemas.py
    planning_tools.py
    charging_agent.py
    verifier.py
    trace_logger.py
  data_audit.py
  data_loader.py
  preprocessing.py
  demand_model.py
  fleet_model.py
  scheduler.py
  simulator.py
  evaluation.py
  visualization.py
  reporting.py
  main.py

config/
  default_config.json

docs/
  agentic_design.md
  assumptions.md
  methodology.md
  technical_design.md
  demo_checklist.md

tests/
  test_agent_schemas.py
  test_agent_verifier.py
  test_agent_scheduler.py
  test_simulator.py
  test_evaluation.py

outputs/
  agent_traces/
  results/
  figures/
  reports/
```

## Data

The project uses the provided Eindhoven datasets:

- Dataset 1: mobility demand origin-destination matrix.
- Dataset 2: shared mobility hubs.
- Dataset 5: grid congestion and constraints.
- Dataset 6: electricity load and zonal demand.
- Dataset 7: electricity prices.
- Dataset 3: existing EV charging points, if available.

One large raw hourly price file is excluded from Git because it exceeds GitHub's regular file-size limit. The runnable project uses smaller included price files.

## Setup

Use Python 3.9 or newer.

```bash
cd /path/to/Data_Set_副本
python3 -m src.main
```

If `pytest` is installed:

```bash
python3 -m pytest
```

## Running With Qwen / DashScope

Do not commit API keys. The project reads the Qwen key from your local environment:

```bash
export LLM_PROVIDER=qwen
export DASHSCOPE_API_KEY="your_dashscope_api_key_here"
export QWEN_PROTOCOL=openai_compatible
export QWEN_BASE_URL="https://ws-wlm3jok3dxf4za9f.eu-central-1.maas.aliyuncs.com/compatible-mode/v1"
export QWEN_MODEL="qwen3.5-flash"
python3 -m src.main
```

You can also copy `.env.example` as a local reference, but do not commit a real `.env` file. The repository ignores `.env`.

If the API key is missing, the model endpoint is unavailable, or the model returns invalid JSON, the scheduler falls back to deterministic planning and still completes the full simulation.

## Outputs

After running `python3 -m src.main`, the project writes:

- `outputs/results/baseline_timeseries.csv`
- `outputs/results/smart_timeseries.csv`
- `outputs/results/agentic_timeseries.csv`
- `outputs/results/agentic_charging_plan.csv`
- `outputs/results/comparison_summary.csv`
- `outputs/agent_traces/agent_trace_timestep_*.json`
- `outputs/agent_traces/agent_trace_summary.csv`
- `outputs/figures/*.png`
- `outputs/reports/executive_summary.md`
- `outputs/reports/technical_summary.md`

The most important explainability files are the agent traces. They show the observation, candidate vehicles, raw LLM or mock JSON plan, validation results, rejected actions, repair notes, and final committed actions for each timestep.

## Evaluation Metrics

The comparison summary includes:

- total charging cost,
- total charged energy,
- cost per kWh,
- kWh per EUR,
- percentage cost reduction versus baseline,
- average vehicle availability,
- total unmet demand,
- unmet demand reduction versus baseline,
- average and peak charger utilization,
- total waiting vehicle-hours,
- average and minimum SOC,
- operational score.

The agentic scheduler is judged by quantitative operational metrics and validated decision traces, not by whether the LLM explanation sounds convincing.

## Research Background

This project is inspired by two research areas: LLM-based agents and EV fleet charging optimization.

Useful references:

- Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", 2022. This motivates interleaving reasoning with actions/tool use rather than relying on one-shot generation. https://arxiv.org/abs/2210.03629
- Schick et al., "Toolformer: Language Models Can Teach Themselves to Use Tools", 2023. This supports the design idea that language models should call external tools instead of internally inventing all facts. https://arxiv.org/abs/2302.04761
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", 2023. This motivates validation feedback and repair loops. https://arxiv.org/abs/2303.11366
- Huang et al., "Understanding the Planning of LLM Agents: A Survey", 2024. This frames LLMs as planning modules in autonomous agents. https://arxiv.org/abs/2402.02716
- Masterman et al., "The Landscape of Emerging AI Agent Architectures for Reasoning, Planning, and Tool Calling: A Survey", 2024. This provides context for agent architectures involving planning, execution, and tool calling. https://arxiv.org/abs/2404.11584
- Li, "A Review of Prominent Paradigms for LLM-Based Agents: Tool Use, Planning, and Feedback Learning", 2024. This connects tool use, planning, and feedback learning as common agentic paradigms. https://arxiv.org/abs/2406.05804
- Tan et al., "Fleet Management and Charging Scheduling for Shared Mobility-on-Demand System: A Systematic Review", IEEE Open Access Journal of Power and Energy, 2022. This gives background on shared mobility fleet dispatching, rebalancing, and charging. https://doi.org/10.17023/8v1g-px64
- Elghanam et al., "Optimization Techniques in Electric Vehicle Charging Scheduling, Routing and Spatio-Temporal Demand Coordination: A Systematic Review", IEEE Open Journal of Vehicular Technology, 2024. This gives context on EV charging scheduling, routing, and demand coordination. https://doi.org/10.1109/OJVT.2024.3420244

## Limitations

- The simulator is a course-scale model, not a production-grade digital twin.
- LLM output quality depends on endpoint availability and model latency.
- The first 24-hour price window currently has little price variation, limiting cost shifting opportunities.
- The project prioritizes reproducibility and safety over unconstrained LLM autonomy.

## Quick Commands

```bash
python3 -m src.main
python3 -m pytest
```

