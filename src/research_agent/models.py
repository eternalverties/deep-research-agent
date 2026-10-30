"""与具体厂商解耦的模型工厂。

每个节点都调用 get_model(角色名)，而不是直接 new 某个厂商的类——
这样换模型（DeepSeek → Qwen → OpenAI）只改配置字符串，不改任何业务代码。
"""

from functools import cache

from langchain.chat_models import init_chat_model

from research_agent.config import settings

_SPEC_BY_ROLE = {
    "planner": settings.model_planner,
    "researcher": settings.model_researcher,
    "synthesizer": settings.model_synthesizer,
    "critic": settings.model_critic,
    "judge": settings.model_judge,
}


@cache
def get_model(role: str):
    """按逻辑角色返回一个 chat model；结果缓存，避免重复初始化。"""
    spec = _SPEC_BY_ROLE[role]
    return init_chat_model(spec, temperature=settings.temperature)
