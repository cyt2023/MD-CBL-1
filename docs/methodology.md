# Methodology

The project compares three scheduler modes under the same initial fleet and charger state:

1. `baseline`
2. `smart_priority`
3. `agentic_llm`

The baseline scheduler charges vehicles below a fixed SOC threshold. The smart-priority scheduler uses weighted deterministic scoring with SOC, future demand, availability risk, electricity price, waiting time, and congestion. The agentic LLM scheduler first applies deterministic candidate pre-ranking, then asks a bounded planning agent for structured JSON actions, validates the result, repairs safe issues, and falls back to the heuristic scheduler if needed.

In agentic mode, the LLM is explicitly separated from numerical simulation. It proposes plans, but deterministic code remains responsible for SOC transitions, charging-cost accounting, charger-capacity enforcement, demand simulation, and final metric computation.

The agentic scheduler is not judged by whether it sounds smart. It is judged by quantitative operational metrics and validated decision traces.

Primary metrics:

- total charging cost
- percentage cost reduction vs baseline
- average vehicle availability
- total unmet demand
- unmet demand reduction vs baseline
- average and peak charger utilization
- total waiting vehicle-hours
- average and minimum SOC
- operational score
