"""端到端质量门槛：只在 `pytest -m eval` 下运行，会真实调用模型。"""

from pathlib import Path

import pytest

from research_agent.config import settings
from research_agent.evaluation import evaluate, load_dataset
from research_agent.graph import build_graph


@pytest.mark.eval
def test_agent_quality_gate() -> None:
    settings.hitl_approval_enabled = False
    dataset = load_dataset(Path(__file__).parents[1] / "evals" / "dataset.json")
    max_cases = settings.eval_max_cases or 1
    result = evaluate(build_graph(), dataset, max_cases=max_cases)
    assert result["passed"], result
