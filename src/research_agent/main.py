"""M1 · 最小 ReAct 智能体：问一个问题 → 联网搜索 → 回答（带来源）。

运行方式（在项目根目录）：
    .venv\\Scripts\\python.exe -m research_agent.main "你的问题"
"""

import sys

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from research_agent.models import get_model
from research_agent.tools.search import web_search


def run_research(query: str) -> str:
    """构建一个带联网搜索工具的 ReAct 智能体，执行一轮问答并返回最终回答。"""
    agent = create_agent(get_model("researcher"), tools=[web_search])
    result = agent.invoke({"messages": [HumanMessage(content=query)]})
    return result["messages"][-1].content


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else input("请输入你的研究问题：").strip()
    if not query:
        print("问题不能为空")
        return
    print(f"\n问题：{query}\n")
    print(f"回答：\n{run_research(query)}")


if __name__ == "__main__":
    main()
