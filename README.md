# deep-research-agent

一个基于 LangGraph 的多智能体「深度研究 Agent」：给定一个研究问题，系统自动完成
「输入护栏 → 任务拆解 → （可选人工审批）→ 并行联网研究 → 覆盖度反思 → 生成带真实引用的报告
→ 输出护栏校验」的完整闭环。

## 架构

```
START → 输入护栏 → Planner → HITL 审批 →（Send × N）→ 并行研究员
                          ↑                                │
                          └──────── Critic 覆盖不足 ────────┘
                                                           ↓
                                      Synthesizer → 输出护栏 → END
```

几个关键设计：共享状态用 TypedDict，`findings` 与 `llm_calls` 用 reducer 支持并行累加；
SQLite checkpoint 以 `thread_id` 持久化每个超步，支撑断点续跑与人工审批；
FastAPI 采用 202 提交 + 轮询，避免长任务阻塞 HTTP 连接。

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

### 5. 运行完整流程（M3–M5）

```bash
.venv\Scripts\python.exe -m research_agent.graph "你的研究问题"
```

注意：引号里的「你的研究问题」是占位文字，请替换成真实问题。占位文字或过短输入
会被输入护栏直接拒绝，不会调用模型。

Planner 先拆解子任务，再用 `Send` 为每个子任务并行派发一个研究员，最后汇总发现、
来源 URL、子任务数与模型调用数。Critic 会评估覆盖度，不足时带着缺口回流 Planner
补研。最多 2 轮，模型调用预算兜底；并发上限为 3，节点带指数退避重试。

Synthesizer 输出 `summary + sections + citations` 的结构化报告。输出护栏会逐条校验
引用是否来自检索结果，并扫描 PII 与提示词泄漏；不合格时带着修复要求重写一次，
仍不合格则带标记放行。

### 6. 持久化与人工审批（M6）

开启人工审批：

```bash
.venv\Scripts\python.exe -m research_agent.graph "你的研究问题" --hitl
```

Planner 生成计划后图会暂停，展示子任务并等待你选择 approve / edit / reject / abort。
每次运行都会打印 `thread_id`，状态保存在 `checkpoints.db`（已 gitignore）。
进程中断后可按线程恢复：

```bash
.venv\Scripts\python.exe -m research_agent.graph --thread run-xxxxxxxx
```

无人值守演示可加 `--decision approve` 自动批准。

### 7. HTTP 服务（M7）

启动服务：

```bash
.venv\Scripts\python.exe -m uvicorn research_agent.api:api --host 0.0.0.0 --port 8000
```

提交任务（返回 202 + thread_id）：

```bash
curl -X POST http://127.0.0.1:8000/research -H "Content-Type: application/json" -d "{\"query\":\"你的研究问题\"}"
```

轮询结果：

```bash
curl http://127.0.0.1:8000/research/<thread_id>
```

开启 HITL 时，状态会变为 `interrupted`，可用 `/research/{thread_id}/resume` 提交
`{"action":"approve"}` 等决定。健康检查为 `GET /health`。

Docker 构建与运行：

```bash
docker build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t deep-research-agent .
docker run --env-file .env -p 8000:8000 deep-research-agent
```

可观测：设置 `LANGSMITH_TRACING=true` 与 `LANGSMITH_API_KEY` 后，每次运行会带上
`run_name` 与角色模型元数据，可在 LangSmith 查看完整调用树。

### 8. 评测与 CI（M8）

默认测试只跑离线单元测试：

```bash
.venv\Scripts\python.exe -m pytest -q
```

端到端质量评测（会真实调用模型）：

```bash
.venv\Scripts\python.exe -m pytest -m eval -q
.venv\Scripts\python.exe -m evals.run_evals --max-cases 1
```

评测包含三项指标：LLM-as-judge 的忠实度与覆盖度，以及程序化引用准确率。门槛由
`EVAL_MIN_*` 环境变量控制。最近一次真实样例结果：忠实度 0.9、覆盖度 0.83、
引用准确率 1.0，全部通过。

CI 工作流在 `.github/workflows/`：`ci.yml` 每次 push/PR 跑 lint 与离线测试；
`evals.yml` 在 PR 上跑质量评测，需要在仓库 Secrets 中配置 `DEEPSEEK_API_KEY`
与 `TAVILY_API_KEY`（未配置时自动跳过并给出警告）。

## 进度

- [x] M0 项目骨架与依赖环境
- [x] M1 最小 ReAct 智能体（DeepSeek + Tavily，带来源回答）
- [x] M2 图建模 + Planner（拆解子任务）
- [x] M3 并行 fan-out（多研究员）
- [x] M4 反思闭环 + 成本护栏
- [x] M5 结构化引用报告 + 输出护栏
- [x] M6 持久化 + 人在回路
- [x] M7 服务化 + 可观测 + 打包
- [x] M8 评测 + CI

## 简历要点

- 基于 LangGraph 从零实现多智能体深度研究系统：Planner 动态拆解、`Send` 并行 fan-out、
  Critic 有界反思、Synthesizer 输出结构化引用报告。
- 设计 SQLite checkpoint + `thread_id` 的持久化执行与 HITL 审批闸门，支持进程崩溃后
  断点续跑，并用迭代次数与模型调用预算双重封顶控制成本。
- 实现引用真实性护栏（覆盖率校验、PII/提示词扫描、有界修复）与评测体系
  （LLM-as-judge + 程序化指标 + CI 质量门槛）。
- 使用 FastAPI 提交-轮询 API 与 Docker 封装长任务服务，支持异步研究任务与人工审批。

## 参考实现

本项目在设计与实现上参考了以下开源项目（本地克隆在 `references/`，不纳入版本控制）：

- `libattistella/deep-research-agent`（主蓝本）
- `langchain-ai/deep-agents-from-scratch`
- `langchain-ai/deepagents-quickstarts`
- `langchain-ai/langgraph-101`
- `assafelovic/gpt-researcher`
- `bytedance/deer-flow`
