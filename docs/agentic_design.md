# Agentic Charging Scheduler Design

The scheduler is agentic because it does more than apply one static rule. At each simulation step it observes system state, gathers deterministic tool outputs, asks a planner for structured charging actions, validates every proposed action, repairs safe mistakes, falls back when needed, and records an explainable trace.

The key design principle is that the LLM is not the source of truth for numerical simulation. The model is allowed to plan and explain, but it is not trusted to execute physics, accounting, capacity checking, or evaluation.

The LLM does not directly control the simulator. Its role is limited to planning within a bounded interface:

- It sees a structured observation.
- It proposes JSON charging actions only.
- It receives deterministic validation feedback if it makes invalid assignments.
- It can revise its plan for a limited number of iterations.
- If it still fails, the system falls back to the smart-priority heuristic.

The LLM may:

- propose a charging strategy
- select among candidate vehicles
- explain decisions
- react to validation feedback
- repair plans
- produce human-readable reasoning summaries

The deterministic code must:

- calculate SOC updates
- calculate charging cost
- calculate charger capacity
- validate constraints
- simulate demand
- compute evaluation metrics
- reject unsafe or invalid plans

Deterministic tools include candidate scoring, charger discovery, charging-need estimation, zone summarisation, action-cost estimation, and plan verification. These tools keep the prompt small, the decision space controlled, and the final actions reproducible.

Validation is necessary because a language model can return malformed JSON, invent IDs, or violate operational constraints. The verifier blocks all such outputs before they reach the simulator. This is safer than directly trusting LLM output because the simulator only consumes validated or repaired actions.

The system remains reproducible because:

- The fleet and demand generation are seeded.
- Baseline and smart-priority modes do not depend on any LLM.
- Agentic mode falls back to a deterministic mock or heuristic if no API key is configured.
- Every decision step is logged in `outputs/agent_traces/`.

Agent traces support explainability by recording the observation, candidate set, raw plan, validation result, repairs, and final committed actions for each time step.
