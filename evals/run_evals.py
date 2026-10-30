"""命令行评测入口：

    python -m evals.run_evals --max-cases 2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_agent.config import settings
from research_agent.evaluation import evaluate, load_dataset
from research_agent.graph import build_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Agent 质量评测")
    parser.add_argument("--max-cases", type=int, default=None, help="只跑前 N 条")
    args = parser.parse_args()

    # 评测必须全自动，不能停在 HITL 审批闸门。
    settings.hitl_approval_enabled = False
    dataset = load_dataset(Path(__file__).parent / "dataset.json")
    max_cases = args.max_cases if args.max_cases is not None else settings.eval_max_cases
    result = evaluate(build_graph(), dataset, max_cases=max_cases)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
