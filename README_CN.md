# Agentic EV Charging Scheduler 中文说明

[English README](README.md)

这是一个面向荷兰 Eindhoven 共享出行 / 租赁电动车队运营商的可复现充电调度项目。项目比较四种充电策略，并实现了一个 agentic LLM 规划器：LLM 负责提出结构化充电计划和解释，确定性的程序负责仿真、约束验证、SOC 更新、成本计算和指标评估。

## 项目目标

车队运营商需要决定：

- 哪些车应该优先充电，
- 什么时候充电，
- 在哪里充电，
- 充多久，
- 如何在降低成本、减少 unmet demand、减少充电桩拥堵的同时保持车辆可用性。

当前项目运行一个 24 小时 Eindhoven 场景仿真，并输出对比指标、图表、报告和每一步 agent 决策轨迹。

## 调度模式

项目支持四种模式：

| 模式 | 含义 | 是否需要 LLM |
|---|---|---|
| `nearest_available` | 普通最近充电行为：车辆想充电时优先使用同区域可用充电桩，否则使用下一个可用桩。不做车队级规划。 | 否 |
| `baseline` | 固定 SOC 阈值规则：车辆低于阈值就充电。 | 否 |
| `smart_priority` | 确定性优先级调度：综合 SOC、未来需求、可用性风险、等待时间、电价和拥堵权重。 | 否 |
| `agentic_llm` | Agentic LLM 调度：观察系统状态，提出 JSON 行动，接受确定性验证，必要时修复或 fallback，并记录决策轨迹。 | 可选 |

如果没有配置 API key，或远程 LLM 调用失败，`agentic_llm` 会自动退回 deterministic mock planner 和 heuristic scheduler。因此项目在没有真实 LLM 的情况下也能完整运行，适合课程评分和复现实验。

## 为什么这是 Agentic

这个项目不是简单地“问 LLM 该怎么充电”。LLM 被限制在一个 observe -> plan -> verify -> repair/fallback -> trace 的闭环里：

```text
系统状态
    -> 确定性 observation builder
    -> 候选车辆预筛选和优先级打分
    -> LLM 或 mock planner 输出 JSON 充电计划
    -> deterministic verifier 检查和修复
    -> 非法计划被拒绝或 fallback
    -> deterministic simulator 执行 SOC、成本、需求和充电桩状态更新
    -> trace logger 保存可解释决策记录
```

Agentic 相关代码主要在：

- `src/agent/charging_agent.py`：agent 主循环和 fallback 编排。
- `src/agent/planning_tools.py`：确定性的 observation、候选车筛选、打分和规划工具。
- `src/agent/prompts.py`：强约束 prompt，要求 JSON 输出、不能编造车辆或充电桩。
- `src/agent/schemas.py`：结构化 observation、plan、action、trace 数据模型。
- `src/agent/verifier.py`：确定性安全验证层。
- `src/agent/trace_logger.py`：每个 timestep 的 agent trace 和 summary CSV。

## 为什么要用 Agentic Scheduler

普通充电规划可以用最近充电、固定规则、加权启发式或数学优化来实现。这些方法都有价值，所以本项目保留它们作为 baseline。但共享 EV 车队是一个动态运营问题：不同区域的需求会变化，车辆 SOC 和等待时间不同，充电桩可用性也会变化，而且运营商需要能解释“为什么这样调度”。

Agentic 架构的优势在于，它把灵活规划和确定性控制结合起来：

- 相比普通最近充电，agent 从整个车队角度规划，而不是让每辆车独立占用最近充电桩。
- 相比固定阈值规则，agent 能根据当前状态调整策略，而不是每个 timestep 都用同一个阈值。
- 相比简单加权启发式，agent 能给出更高层的运营理由，例如在高需求区域保留车辆可用性，同时用空闲充电能力做浅充。
- 相比一次性 LLM 答案，agent 更安全，因为每个行动都必须经过 schema check 和 constraint verifier。
- 相比黑盒优化，agent trace 能显示它看到了什么、提出了什么、哪些行动被拒绝、最终执行了什么。
- 相比直接相信 LLM，所有数值计算仍然由确定性代码完成，因此结果可复现、可审计。

简而言之：LLM 提供规划灵活性和解释，确定性工具提供运营事实和安全边界。

## 优化策略

这个 scheduler 不是单纯追求最低充电成本，而是一个带安全边界的多目标优化系统。原因很简单：如果只是少充电，成本会变低，但 unmet demand 可能变高，服务质量会变差。因此本项目同时考虑成本、有效充电量、需求满足、车辆可用性和充电桩拥堵。

当前已经加入的优化能力包括：

- 更高的真实 LLM 参与频率：如果配置了真实模型，默认每 3 个 timestep 调用一次 LLM；如果 LLM 失败，仍然会自动 fallback。
- 可用性感知补电：确定性 support layer 会避免把当前车辆已经紧张的区域继续拉车去充电，除非 SOC 风险或未来需求风险很高。
- 可选的电价感知 refinement：如果配置了非恒定电价窗口，高价时可以延后非紧急充电，低价时增加浅充。
- 可复现的电价窗口实验：默认使用数据中的第一个窗口；如果要做变动电价实验，可以在 `config/default_config.json` 里启用 `price_window_strategy = "first_variable_positive"`。

默认 README 中汇报的是保守、可复现设置下的结果。电价感知实验可以作为额外 scenario 报告，因为更换电价窗口会改变所有 scheduler 的实验环境。

## 安全和可复现原则

LLM 不是数值仿真的事实来源。

LLM 可以：

- 提出充电策略，
- 在候选车辆中选择，
- 给出简短 reasoning summary，
- 根据验证反馈修复 JSON 计划。

确定性代码必须：

- 更新 SOC，
- 计算充电成本，
- 检查充电桩容量，
- 验证约束，
- 模拟需求，
- 计算评估指标，
- 拒绝不安全或非法计划。

任何 LLM 输出如果没有通过 verifier，都不会进入 simulator。这是本项目可解释、可复现、可作为大学课程项目答辩的关键。

## 当前结果

最新 deterministic fallback/mock 运行结果：

| 策略 | 成本 EUR | 充电量 kWh | Unmet Demand | 平均可用性 | Operational Score |
|---|---:|---:|---:|---:|---:|
| `nearest_available` | 90.097 | 2464.376 | 29 | 0.775 | 10.043 |
| `baseline` | 88.473 | 2420.000 | 7 | 0.836 | 37.210 |
| `smart_priority` | 93.784 | 2565.236 | 9 | 0.889 | 31.807 |
| `agentic_llm` | 89.917 | 2459.428 | 4 | 0.839 | 48.128 |

和普通最近充电相比，agentic scheduler 成本从 EUR 90.097 降到 EUR 89.917，节省约 0.2%，同时 unmet demand 从 29 降到 4，降低约 86.21%。这说明 agentic 规划不是靠“少服务”省钱，而是在接近相同成本下显著提升服务质量。

和固定阈值 baseline 相比，agentic 充电量更多，同时 unmet demand 从 7 降到 4。由于当前 24 小时电价窗口几乎是常数，所以在同一电价下“总充电量更多且总成本更低”并不总是物理上可同时满足。本项目更合理的目标是提高每一欧元带来的运营价值：更有用的充电、更少漏单、更可解释的决策。

## 项目结构

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

## 数据

项目使用 Eindhoven 相关数据集：

- Dataset 1：Mobility Demand Origin-Destination Matrix。
- Dataset 2：Shared Mobility Hubs。
- Dataset 5：Grid Congestion and Constraints。
- Dataset 6：Electricity Load and Zonal Demand。
- Dataset 7：Electricity Prices。
- Dataset 3：Existing EV Charging Points，如果可用。

一个大型 hourly price 原始文件因为超过 GitHub 常规单文件大小限制而被 `.gitignore` 排除。当前可运行项目使用仓库中较小的 price 文件。

## 运行方式

Python 3.9 或以上：

```bash
cd /path/to/Data_Set_副本
python3 -m src.main
```

如果安装了 pytest：

```bash
python3 -m pytest
```

## 使用 Qwen / DashScope

不要把真实 API key 提交到仓库。项目从本地环境变量读取 Qwen key：

```bash
export LLM_PROVIDER=qwen
export DASHSCOPE_API_KEY="your_dashscope_api_key_here"
export QWEN_PROTOCOL=openai_compatible
export QWEN_BASE_URL="https://ws-wlm3jok3dxf4za9f.eu-central-1.maas.aliyuncs.com/compatible-mode/v1"
export QWEN_MODEL="qwen3.5-flash"
python3 -m src.main
```

也可以参考 `.env.example`，但不要提交真实 `.env`。仓库已经忽略 `.env`。

如果 API key 缺失、模型端点不可用，或模型返回非法 JSON，scheduler 会自动 fallback 到确定性规划，完整仿真仍然可以完成。

## 输出文件

运行 `python3 -m src.main` 后会生成：

- `outputs/results/nearest_available_timeseries.csv`
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

最重要的可解释文件是 agent traces。它们记录每一步 observation、候选车辆、LLM 或 mock 的原始 JSON plan、验证结果、拒绝行动、修复记录和最终执行行动。

## 评估指标

`outputs/results/comparison_summary.csv` 包含：

- 总充电成本，
- 总充电量，
- 每 kWh 成本，
- 每 EUR 充电量，
- 相对 baseline 的成本变化，
- 相对 nearest_available 的成本变化，
- 平均车辆可用性，
- 总 unmet demand，
- 相对 baseline / nearest_available 的 unmet demand 降低比例，
- 平均和峰值充电桩利用率，
- 总等待车辆小时数，
- 平均和最低 SOC，
- operational score。

Agentic scheduler 的评价依据是量化运营指标和经过验证的决策轨迹，而不是 LLM 解释听起来是否“聪明”。

## 研究背景

本项目结合两个方向：LLM agent 和 EV 车队充电优化。

参考资料：

- Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", 2022. https://arxiv.org/abs/2210.03629
- Schick et al., "Toolformer: Language Models Can Teach Themselves to Use Tools", 2023. https://arxiv.org/abs/2302.04761
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", 2023. https://arxiv.org/abs/2303.11366
- Huang et al., "Understanding the Planning of LLM Agents: A Survey", 2024. https://arxiv.org/abs/2402.02716
- Masterman et al., "The Landscape of Emerging AI Agent Architectures for Reasoning, Planning, and Tool Calling: A Survey", 2024. https://arxiv.org/abs/2404.11584
- Li, "A Review of Prominent Paradigms for LLM-Based Agents: Tool Use, Planning, and Feedback Learning", 2024. https://arxiv.org/abs/2406.05804
- Tan et al., "Fleet Management and Charging Scheduling for Shared Mobility-on-Demand System: A Systematic Review", IEEE Open Access Journal of Power and Energy, 2022. https://doi.org/10.17023/8v1g-px64
- Elghanam et al., "Optimization Techniques in Electric Vehicle Charging Scheduling, Routing and Spatio-Temporal Demand Coordination: A Systematic Review", IEEE Open Journal of Vehicular Technology, 2024. https://doi.org/10.1109/OJVT.2024.3420244

## 局限性

- 当前 simulator 是课程规模模型，不是生产级 digital twin。
- LLM 输出质量受端点可用性和延迟影响。
- 当前 24 小时电价窗口变化很小，限制了纯价格套利空间。
- 项目优先保证可复现、安全和可解释，而不是追求无限制 LLM 自主性。

## 快速命令

```bash
python3 -m src.main
python3 -m pytest
```
