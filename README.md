# deep-research-agent

一个基于 LangGraph 的多智能体「深度研究 Agent」：给定一个研究问题，系统自动完成
「输入护栏 → 任务拆解 → （可选人工审批）→ 并行联网研究 → 覆盖度反思 → 生成带真实引用的报告
→ 输出护栏校验」的完整闭环。

> 施工中。已跑通 M0（环境）与 M1（最小 ReAct 智能体），后续里程碑按计划推进。

## 快速开始

### 1. 环境

- Python 3.11+（本项目使用 3.12）
- 推荐用 [uv](https://docs.astral.sh/uv/) 管理环境，也可用 `venv + pip`

### 2. 安装依赖

```bash
uv sync
```

或使用标准虚拟环境：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e . pytest ruff
```

### 3. 配置密钥

把 `.env.example` 复制为 `.env`，填入：

- `DEEPSEEK_API_KEY`：DeepSeek 模型密钥（https://platform.deepseek.com）
- `TAVILY_API_KEY`：Tavily 联网搜索密钥（https://tavily.com，有免费额度）

### 4. 运行 M1：最小 ReAct 智能体

```bash
.venv\Scripts\python.exe -m research_agent.main "你的研究问题"
```

智能体会先联网检索，再基于检索结果作答，并在末尾列出使用过的来源 URL。

### 5. 运行 M3/M4：并行多研究员 + 反思闭环

```bash
.venv\Scripts\python.exe -m research_agent.graph "你的研究问题"
```

Planner 先拆解子任务，再用 `Send` 为每个子任务并行派发一个研究员，最后汇总发现、
来源 URL、子任务数与模型调用数。Critic 会评估覆盖度，不足时带着缺口回流 Planner
补研。最多 2 轮，模型调用预算兜底；并发上限为 3，节点带指数退避重试。

## 进度

- [x] M0 项目骨架与依赖环境
- [x] M1 最小 ReAct 智能体（DeepSeek + Tavily，带来源回答）
- [x] M2 图建模 + Planner（拆解子任务）
- [x] M3 并行 fan-out（多研究员）
- [x] M4 反思闭环 + 成本护栏
- [ ] M5 结构化引用报告 + 输出护栏
- [ ] M6 持久化 + 人在回路
- [ ] M7 服务化 + 可观测 + 打包
- [ ] M8 评测 + CI

## 参考实现

本项目在设计与实现上参考了以下开源项目（本地克隆在 `references/`，不纳入版本控制）：

- `libattistella/deep-research-agent`（主蓝本）
- `langchain-ai/deep-agents-from-scratch`
- `langchain-ai/deepagents-quickstarts`
- `langchain-ai/langgraph-101`
- `assafelovic/gpt-researcher`
- `bytedance/deer-flow`
