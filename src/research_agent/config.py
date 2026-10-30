"""全局配置：模型规格、温度、预算与护栏开关。

用 pydantic-settings 从环境变量 / .env 文件读取配置；每个字段都有代码级默认值，
所以不填 .env 也能跑（只是会用默认的 DeepSeek 模型）。
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 每个逻辑角色对应一个 "provider:model" 字符串，通过 init_chat_model 解析。
    # 默认全部用 DeepSeek（国内直连、便宜）；换 OpenAI/Qwen/GLM 只需改这里或 .env。
    model_planner: str = "deepseek:deepseek-chat"
    model_researcher: str = "deepseek:deepseek-chat"
    model_synthesizer: str = "deepseek:deepseek-chat"
    model_critic: str = "deepseek:deepseek-chat"
    model_judge: str = "deepseek:deepseek-chat"
    model_verifier: str = "deepseek:deepseek-chat"

    # 搜索服务的密钥。显式放进 Settings，避免各个工具模块隐式依赖 .env 已被加载。
    tavily_api_key: str = ""
    search_provider: str = "auto"  # auto / tavily / bing
    search_max_results: int = 6
    search_timeout_seconds: int = 10

    temperature: float = 0.0

    # 输出护栏：引用覆盖率阈值与最多修复次数。
    guardrail_output_enabled: bool = True
    min_citation_coverage: float = 0.8
    max_output_repairs: int = 1

    # 评测门槛：CI 上均值低于这些分数即判失败。
    eval_min_faithfulness: float = 0.7
    eval_min_coverage: float = 0.6
    eval_min_citation_accuracy: float = 0.8
    eval_max_cases: int = 0  # 0 表示跑完整数据集

    # 研究循环与预算上限（M4 用到）：迭代次数 + LLM 调用次数双重封顶。
    max_research_iterations: int = 2
    # 5 个研究员一轮通常要 20+ 次调用，40 留出一次反思补研的余量，同时仍能兜底。
    max_llm_calls_per_run: int = 60
    budget_reserve_for_synthesis: int = 6

    # Claim-Evidence 事实核验
    enable_verifier: bool = True
    verifier_max_claims: int = 8
    verifier_max_evidence: int = 5

    # 重试策略（M4 用到）：遇 429/5xx/超时按指数退避重试。
    retry_max_attempts: int = 4
    retry_initial_interval: float = 1.0
    retry_backoff_factor: float = 2.0

    # 持久化与人在回路（M6 用到）。
    checkpoint_db_path: str = "checkpoints.db"
    hitl_approval_enabled: bool = False


settings = Settings()
