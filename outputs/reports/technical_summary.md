# Technical Summary

The pipeline loads the Eindhoven mobility, hub, congestion, load, and electricity price datasets, builds a synthetic but reproducible fleet, and runs four comparable 24-hour simulations from the same initial state.

The nearest-available scheduler represents a naive individual behaviour: charge at the same-zone charger if possible without fleet-level planning. The baseline scheduler uses a fixed threshold. The smart priority scheduler uses deterministic weighted scoring. The agentic LLM scheduler uses deterministic candidate ranking, an optional LLM planning loop, strict validation and repair, heuristic fallback, and trace logging.

Outputs include comparison metrics, charging plans, time series, figures, reports, and agent decision traces.

Limitations: spatial matching is simplified to zone-level assignment, the LLM is bounded to structured JSON planning, and final actions only enter the simulator after deterministic verification.