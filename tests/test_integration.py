"""Integration tests for RLM — requires ANTHROPIC_API_KEY."""

import os
import pytest
from pathlib import Path

from rlm.agent import RLMConfig, rlm_call
from rlm.workspace import Workspace

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(root=tmp_path / "rlm_ws")


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
class TestSingleLevel:
    @pytest.mark.asyncio
    async def test_direct_answer(self, workspace: Workspace):
        """With max_depth=0, agent must answer directly."""
        config = RLMConfig(
            goal="Summarize this text in exactly one sentence.",
            model="claude-haiku-4-5-20251001",
            max_depth=0,
        )
        result = await rlm_call(
            workspace=workspace,
            config=config,
            depth=0,
            call_index=0,
            context_path=FIXTURES / "short_text.txt",
        )
        assert result.answer is not None
        assert len(result.answer) > 10
        assert result.total_calls == 1
        # Verify answer.txt was written
        node_dir = workspace.root / "d0_c0"
        assert (node_dir / "answer.txt").exists()
