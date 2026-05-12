# Technical Design

Project structure:

- `src/agent/`: LLM client, prompts, schemas, planning tools, planner, verifier, and trace logger
- `src/data_audit.py`: dataset availability and row-count checks
- `src/data_loader.py`: CSV ingestion
- `src/preprocessing.py`: zone, price, load, and congestion preparation
- `src/demand_model.py`: hourly zonal demand construction
- `src/fleet_model.py`: reproducible fleet and charger generation
- `src/scheduler.py`: baseline, smart-priority, and agentic schedulers
- `src/simulator.py`: three-mode simulation and CSV exports
- `src/evaluation.py`: strategy comparison metrics
- `src/visualization.py`: PNG figure generation without external plotting dependencies
- `src/reporting.py`: markdown report generation
- `src/main.py`: full pipeline entry point

The LLM interface is provider-aware with two supported configuration styles:

- Qwen / DashScope mode via `LLM_PROVIDER=qwen`, `DASHSCOPE_API_KEY`, `QWEN_BASE_URL`, and `QWEN_MODEL`
- Generic OpenAI-compatible mode via `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`

If these are absent, the planner uses a deterministic mock response generator and can still complete the full project pipeline.

The Qwen wrapper reads the API key from the local `DASHSCOPE_API_KEY` environment variable. By default it uses the Europe OpenAI-compatible Alibaba Cloud Model Studio endpoint: `https://ws-wlm3jok3dxf4za9f.eu-central-1.maas.aliyuncs.com/compatible-mode/v1`. The default Qwen model is `qwen3.5-flash`, but it can be overridden with `QWEN_MODEL`.

Execution boundary:

- `src/agent/*` proposes structured charging plans and logs decision traces.
- `src/agent/verifier.py` is the deterministic gatekeeper for safety and feasibility.
- `src/simulator.py` computes SOC changes, charging energy, cost, and demand outcomes.
- `src/evaluation.py` computes comparative performance metrics.

This boundary ensures the LLM remains an explainable planning component rather than a hidden numerical simulator.
