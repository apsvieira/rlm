# RLM Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a Recursive Language Model (RLM) as a Python CLI using the Claude Agent SDK, with a Claude Code skill for invocation.

**Architecture:** Python orchestrator manages recursion depth and agent lifecycle. Each recursion level runs a two-phase agent pattern: Phase 1 (decompose-or-solve) lets the agent analyze context and either answer directly or write subcall specifications; Phase 2 (synthesize) resumes the agent after subcalls complete so it can read results and produce a final answer. Context is passed between levels as files on disk.

**Critical SDK constraint:** Subagents cannot spawn subagents. Recursion MUST be managed by Python code, not by agents calling Task.

**Tech Stack:** Python 3.10+, claude-agent-sdk, click, pytest, uv

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `rlm/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "rlm"
version = "0.1.0"
description = "Recursive Language Model using Claude Agent SDK"
requires-python = ">=3.10"
dependencies = [
    "claude-agent-sdk",
    "click>=8.0",
]

[project.scripts]
rlm = "rlm.main:cli"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
```

**Step 2: Create rlm/__init__.py**

```python
"""RLM - Recursive Language Model using Claude Agent SDK."""
```

**Step 3: Initialize project and install dependencies**

Run: `cd /home/apsv/source/toy/rlm && uv sync`
Expected: Dependencies installed, venv created

**Step 4: Verify installation**

Run: `cd /home/apsv/source/toy/rlm && uv run python -c "import claude_agent_sdk; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add pyproject.toml rlm/__init__.py uv.lock
git commit -m "feat: scaffold RLM project with dependencies"
```

---

### Task 2: Workspace Manager

**Files:**
- Create: `rlm/workspace.py`
- Create: `tests/test_workspace.py`

**Step 1: Write the failing tests**

```python
# tests/test_workspace.py
import os
import tempfile
from pathlib import Path

from rlm.workspace import Workspace


class TestWorkspaceCreation:
    def test_creates_root_directory(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.path.exists()
        assert (node.path / "vars").is_dir()

    def test_creates_context_file_from_string(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello world")
        assert (node.path / "context.txt").read_text() == "hello world"

    def test_creates_context_file_from_path(self, tmp_path: Path):
        ctx_file = tmp_path / "input.txt"
        ctx_file.write_text("file content")
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context_path=ctx_file)
        assert (node.path / "context.txt").read_text() == "file content"

    def test_node_directory_naming(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=2, call_index=3)
        assert node.path.name == "d2_c3"

    def test_read_answer(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        (node.path / "answer.txt").write_text("the answer")
        assert node.read_answer() == "the answer"

    def test_read_answer_missing_returns_none(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.read_answer() is None

    def test_read_subcalls_empty(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.read_subcalls() == []

    def test_read_subcalls_from_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        import json
        subcalls = [
            {"goal": "summarize section 1", "context_file": "vars/chunk_0.txt"},
            {"goal": "summarize section 2", "context_file": "vars/chunk_1.txt"},
        ]
        (node.path / "subcalls.json").write_text(json.dumps(subcalls))
        result = node.read_subcalls()
        assert len(result) == 2
        assert result[0]["goal"] == "summarize section 1"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rlm.workspace'`

**Step 3: Write workspace.py**

```python
# rlm/workspace.py
"""Workspace directory management for RLM agents."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkspaceNode:
    """A single agent's workspace directory."""

    path: Path

    @property
    def context_path(self) -> Path:
        return self.path / "context.txt"

    @property
    def answer_path(self) -> Path:
        return self.path / "answer.txt"

    @property
    def subcalls_path(self) -> Path:
        return self.path / "subcalls.json"

    @property
    def vars_path(self) -> Path:
        return self.path / "vars"

    def read_answer(self) -> str | None:
        if self.answer_path.exists():
            return self.answer_path.read_text()
        return None

    def read_subcalls(self) -> list[dict[str, Any]]:
        if self.subcalls_path.exists():
            return json.loads(self.subcalls_path.read_text())
        return []


class Workspace:
    """Manages the RLM workspace directory tree."""

    def __init__(self, root: Path):
        self.root = root

    def create_node(
        self,
        depth: int,
        call_index: int,
        context: str | None = None,
        context_path: Path | None = None,
    ) -> WorkspaceNode:
        node_dir = self.root / f"d{depth}_c{call_index}"
        node_dir.mkdir(parents=True, exist_ok=True)
        (node_dir / "vars").mkdir(exist_ok=True)

        if context is not None:
            (node_dir / "context.txt").write_text(context)
        elif context_path is not None:
            shutil.copy2(context_path, node_dir / "context.txt")

        return WorkspaceNode(path=node_dir)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add rlm/workspace.py tests/test_workspace.py
git commit -m "feat: add workspace directory manager with node read/write"
```

---

### Task 3: Prompt Builder

**Files:**
- Create: `rlm/prompts.py`
- Create: `tests/test_prompts.py`

**Step 1: Write the failing tests**

```python
# tests/test_prompts.py
from rlm.prompts import build_decompose_prompt, build_synthesize_prompt


class TestDecomposePrompt:
    def test_includes_workspace_path(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Summarize this",
            current_depth=0,
            max_depth=3,
        )
        assert "/tmp/ws/d0_c0" in prompt

    def test_includes_goal(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Find all bugs",
            current_depth=0,
            max_depth=3,
        )
        assert "Find all bugs" in prompt

    def test_includes_depth_info(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="task",
            current_depth=1,
            max_depth=3,
        )
        assert "depth 1" in prompt
        assert "3" in prompt

    def test_at_max_depth_disables_subcalls(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="task",
            current_depth=3,
            max_depth=3,
        )
        assert "subcalls.json" not in prompt
        assert "answer.txt" in prompt

    def test_below_max_depth_enables_subcalls(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="task",
            current_depth=0,
            max_depth=3,
        )
        assert "subcalls.json" in prompt

    def test_caller_prompt_override(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d1_c0",
            goal="Analyze section 3 for security issues",
            current_depth=1,
            max_depth=3,
            caller_prompt="You are analyzing a security audit report. Focus on CVEs.",
        )
        assert "security audit report" in prompt
        assert "CVEs" in prompt


class TestSynthesizePrompt:
    def test_includes_workspace_path(self):
        prompt = build_synthesize_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Summarize",
            sub_answers={"sub_0": "answer 0", "sub_1": "answer 1"},
        )
        assert "/tmp/ws/d0_c0" in prompt

    def test_includes_sub_answers(self):
        prompt = build_synthesize_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Summarize",
            sub_answers={"section_1": "result A", "section_2": "result B"},
        )
        assert "result A" in prompt
        assert "result B" in prompt

    def test_includes_goal(self):
        prompt = build_synthesize_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Find all bugs",
            sub_answers={"a": "b"},
        )
        assert "Find all bugs" in prompt
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rlm.prompts'`

**Step 3: Write prompts.py**

```python
# rlm/prompts.py
"""System prompt templates for RLM agents."""

from __future__ import annotations


def build_decompose_prompt(
    workspace_path: str,
    goal: str,
    current_depth: int,
    max_depth: int,
    caller_prompt: str | None = None,
) -> str:
    """Build the prompt for the decompose-or-solve phase.

    If at max depth, instructs the agent to solve directly.
    Otherwise, gives the agent the option to decompose via subcalls.json.
    """
    at_max_depth = current_depth >= max_depth

    parts = [
        "You are an RLM (Recursive Language Model) agent.",
        "",
        f"## Workspace",
        f"Your workspace directory is: {workspace_path}",
        "- `context.txt` contains the input you should process",
        "- `vars/` is your scratch space for intermediate files",
        "",
        f"## Depth",
        f"You are at depth {current_depth} of {max_depth}.",
        "",
        "## Instructions",
        "1. Read `context.txt` to understand your input",
        "2. Explore the context as needed (grep, read sections, etc.)",
    ]

    if at_max_depth:
        parts.extend([
            "3. Process the task directly — you cannot delegate further",
            "4. Write your complete answer to `answer.txt` in your workspace",
        ])
    else:
        parts.extend([
            "3. Decide: can you solve this directly, or should you decompose?",
            "",
            "### Option A: Solve directly",
            "Write your complete answer to `answer.txt` in your workspace.",
            "",
            "### Option B: Decompose into sub-tasks",
            "If the task benefits from decomposition:",
            "1. Write each sub-task's context to `vars/sub_N_context.txt`",
            "2. Write a `subcalls.json` file in your workspace with this format:",
            '   ```json',
            '   [',
            '     {"goal": "specific sub-task description", "context_file": "vars/sub_0_context.txt"},',
            '     {"goal": "another sub-task", "context_file": "vars/sub_1_context.txt"}',
            '   ]',
            '   ```',
            "3. Do NOT write `answer.txt` — you will be called again with results.",
            "",
            "Choose Option A unless decomposition clearly improves the result.",
        ])

    if caller_prompt:
        parts.extend([
            "",
            "## Additional context from caller",
            caller_prompt,
        ])

    parts.extend([
        "",
        "## Your task",
        goal,
    ])

    return "\n".join(parts)


def build_synthesize_prompt(
    workspace_path: str,
    goal: str,
    sub_answers: dict[str, str],
) -> str:
    """Build the prompt for the synthesis phase after subcalls complete."""
    parts = [
        "You are an RLM (Recursive Language Model) agent in synthesis mode.",
        "",
        f"## Workspace",
        f"Your workspace directory is: {workspace_path}",
        "",
        "## Context",
        "You previously decomposed a task into sub-tasks.",
        "The sub-tasks have been completed. Here are their results:",
        "",
    ]

    for label, answer in sub_answers.items():
        parts.extend([
            f"### {label}",
            answer,
            "",
        ])

    parts.extend([
        "## Instructions",
        "1. You may also read `context.txt` for the original input",
        "2. Synthesize the sub-task results into a coherent final answer",
        "3. Write your complete answer to `answer.txt` in your workspace",
        "",
        "## Original task",
        goal,
    ])

    return "\n".join(parts)
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_prompts.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add rlm/prompts.py tests/test_prompts.py
git commit -m "feat: add prompt builder for decompose and synthesize phases"
```

---

### Task 4: Agent Runner

**Files:**
- Create: `rlm/agent.py`
- Create: `tests/test_agent.py`

This is the core module. It wraps `claude-agent-sdk` query calls and implements the two-phase recursion pattern.

**Step 1: Write the failing tests**

```python
# tests/test_agent.py
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from rlm.agent import get_tools_for_depth, RLMConfig


class TestToolSelection:
    def test_below_max_depth_includes_write_tools(self):
        tools = get_tools_for_depth(current_depth=0, max_depth=3)
        assert "Read" in tools
        assert "Write" in tools
        assert "Grep" in tools
        assert "Glob" in tools
        assert "Edit" in tools
        assert "Bash" in tools

    def test_at_max_depth_same_tools(self):
        tools = get_tools_for_depth(current_depth=3, max_depth=3)
        assert "Read" in tools
        assert "Write" in tools

    def test_tools_never_include_task(self):
        tools = get_tools_for_depth(current_depth=0, max_depth=3)
        assert "Task" not in tools


class TestRLMConfig:
    def test_defaults(self):
        config = RLMConfig(goal="test")
        assert config.model == "claude-sonnet-4-6"
        assert config.max_depth == 3

    def test_custom_values(self):
        config = RLMConfig(goal="test", model="claude-haiku-4-5-20251001", max_depth=1)
        assert config.model == "claude-haiku-4-5-20251001"
        assert config.max_depth == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rlm.agent'`

**Step 3: Write agent.py**

```python
# rlm/agent.py
"""RLM agent runner — manages the recursive agent loop."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    query,
)

from rlm.prompts import build_decompose_prompt, build_synthesize_prompt
from rlm.workspace import Workspace, WorkspaceNode


AGENT_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


def get_tools_for_depth(current_depth: int, max_depth: int) -> list[str]:
    """Return the tool list for an agent at the given depth.

    Tools are the same at all depths — recursion is managed by Python,
    not by agents spawning sub-agents. Task is never included.
    """
    return list(AGENT_TOOLS)


@dataclass
class RLMConfig:
    """Configuration for an RLM run."""

    goal: str
    model: str = "claude-sonnet-4-6"
    max_depth: int = 3
    permission_mode: str = "bypassPermissions"


@dataclass
class RLMResult:
    """Result from an RLM run."""

    answer: str
    workspace_root: Path
    total_cost_usd: float = 0.0
    total_calls: int = 0


async def run_agent_phase(
    prompt: str,
    cwd: str,
    model: str,
    tools: list[str],
    permission_mode: str,
) -> tuple[str | None, float]:
    """Run a single agent phase (decompose or synthesize).

    Returns (result_text, cost_usd). result_text is the last assistant
    text (for logging), cost comes from ResultMessage.
    """
    last_text: str | None = None
    cost: float = 0.0

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=tools,
            permission_mode=permission_mode,
            model=model,
            cwd=cwd,
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    last_text = block.text
        elif isinstance(message, ResultMessage):
            cost = message.total_cost_usd or 0.0

    return last_text, cost


async def rlm_call(
    workspace: Workspace,
    config: RLMConfig,
    depth: int,
    call_index: int,
    context: str | None = None,
    context_path: Path | None = None,
    caller_prompt: str | None = None,
) -> RLMResult:
    """Execute one level of the RLM recursion.

    1. Create workspace node
    2. Run decompose-or-solve agent
    3. If agent wrote answer.txt → return it
    4. If agent wrote subcalls.json → run each subcall recursively, then synthesize
    """
    node = workspace.create_node(
        depth=depth,
        call_index=call_index,
        context=context,
        context_path=context_path,
    )

    tools = get_tools_for_depth(depth, config.max_depth)
    prompt = build_decompose_prompt(
        workspace_path=str(node.path),
        goal=config.goal if caller_prompt is None else caller_prompt,
        current_depth=depth,
        max_depth=config.max_depth,
        caller_prompt=caller_prompt,
    )

    total_cost = 0.0
    total_calls = 1

    # Phase 1: Decompose or solve
    _, cost = await run_agent_phase(
        prompt=prompt,
        cwd=str(node.path),
        model=config.model,
        tools=tools,
        permission_mode=config.permission_mode,
    )
    total_cost += cost

    # Check: did the agent answer directly?
    answer = node.read_answer()
    if answer is not None:
        return RLMResult(
            answer=answer,
            workspace_root=workspace.root,
            total_cost_usd=total_cost,
            total_calls=total_calls,
        )

    # Check: did the agent request subcalls?
    subcalls = node.read_subcalls()
    if not subcalls:
        return RLMResult(
            answer="[RLM Error: Agent produced neither answer.txt nor subcalls.json]",
            workspace_root=workspace.root,
            total_cost_usd=total_cost,
            total_calls=total_calls,
        )

    # Phase 2: Execute subcalls recursively
    sub_answers: dict[str, str] = {}
    for i, subcall in enumerate(subcalls):
        sub_goal = subcall["goal"]
        sub_context_file = subcall.get("context_file")

        # Resolve context: either from a file the agent wrote, or inline
        sub_context: str | None = None
        sub_context_path: Path | None = None
        if sub_context_file:
            resolved = node.path / sub_context_file
            if resolved.exists():
                sub_context_path = resolved
            else:
                sub_context = f"[Context file not found: {sub_context_file}]"
        else:
            sub_context = subcall.get("context", "")

        sub_result = await rlm_call(
            workspace=workspace,
            config=config,
            depth=depth + 1,
            call_index=i,
            context=sub_context,
            context_path=sub_context_path,
            caller_prompt=sub_goal,
        )
        sub_answers[f"Sub-task {i}: {sub_goal}"] = sub_result.answer
        total_cost += sub_result.total_cost_usd
        total_calls += sub_result.total_calls

    # Phase 3: Synthesize
    synth_prompt = build_synthesize_prompt(
        workspace_path=str(node.path),
        goal=config.goal if caller_prompt is None else caller_prompt,
        sub_answers=sub_answers,
    )

    _, synth_cost = await run_agent_phase(
        prompt=synth_prompt,
        cwd=str(node.path),
        model=config.model,
        tools=tools,
        permission_mode=config.permission_mode,
    )
    total_cost += synth_cost
    total_calls += 1

    answer = node.read_answer()
    if answer is None:
        answer = "[RLM Error: Synthesis agent did not write answer.txt]"

    return RLMResult(
        answer=answer,
        workspace_root=workspace.root,
        total_cost_usd=total_cost,
        total_calls=total_calls,
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_agent.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add rlm/agent.py tests/test_agent.py
git commit -m "feat: add agent runner with two-phase recursive execution"
```

---

### Task 5: CLI Entrypoint

**Files:**
- Create: `rlm/main.py`

**Step 1: Write main.py**

```python
# rlm/main.py
"""CLI entrypoint for the RLM."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import click

from rlm.agent import RLMConfig, rlm_call
from rlm.workspace import Workspace


@click.command()
@click.option("--context", "context_path", type=click.Path(exists=True), help="Path to context file")
@click.option("--context-text", "context_text", type=str, help="Inline context string")
@click.option("--goal", required=True, type=str, help="The task/question to accomplish")
@click.option("--model", default="claude-sonnet-4-6", help="Model to use")
@click.option("--max-depth", default=3, type=int, help="Maximum recursion depth")
@click.option(
    "--workspace",
    "workspace_path",
    type=click.Path(),
    default=None,
    help="Workspace directory (default: rlm_workspace/<timestamp>)",
)
def cli(
    context_path: str | None,
    context_text: str | None,
    goal: str,
    model: str,
    max_depth: int,
    workspace_path: str | None,
):
    """RLM — Recursive Language Model agent."""
    if not context_path and not context_text:
        # Try reading from stdin
        if not sys.stdin.isatty():
            context_text = sys.stdin.read()
        else:
            raise click.UsageError("Provide --context, --context-text, or pipe input via stdin.")

    if workspace_path is None:
        workspace_path = f"rlm_workspace/{int(time.time())}"

    workspace = Workspace(root=Path(workspace_path))
    config = RLMConfig(goal=goal, model=model, max_depth=max_depth)

    result = asyncio.run(
        rlm_call(
            workspace=workspace,
            config=config,
            depth=0,
            call_index=0,
            context=context_text,
            context_path=Path(context_path) if context_path else None,
        )
    )

    click.echo(f"\n{'='*60}")
    click.echo(f"RLM Complete")
    click.echo(f"Workspace: {result.workspace_root}")
    click.echo(f"Total API calls: {result.total_calls}")
    click.echo(f"Total cost: ${result.total_cost_usd:.4f}")
    click.echo(f"{'='*60}\n")
    click.echo(result.answer)


if __name__ == "__main__":
    cli()
```

**Step 2: Verify CLI help works**

Run: `cd /home/apsv/source/toy/rlm && uv run python -m rlm.main --help`
Expected: Shows help text with all options

**Step 3: Commit**

```bash
git add rlm/main.py
git commit -m "feat: add CLI entrypoint with click"
```

---

### Task 6: Integration Test — Single Level (No Recursion)

**Files:**
- Create: `tests/test_integration.py`
- Create: `tests/fixtures/short_text.txt`

**Step 1: Create test fixture**

```text
# tests/fixtures/short_text.txt
The Turing Test, originally called the imitation game by Alan Turing in 1950, is a test
of a machine's ability to exhibit intelligent behaviour equivalent to, or indistinguishable
from, that of a human. Turing proposed that a human evaluator would judge natural language
conversations between a human and a machine designed to generate human-like responses. The
evaluator would be aware that one of the two partners in conversation is a machine, and all
participants would be separated from one another. The conversation would be limited to a
text-only channel. If the evaluator cannot reliably tell the machine from the human, the
machine is said to have passed the test. The test results do not depend on the machine's
ability to give correct answers to questions, only how closely its answers resemble those
a human would give. Since the original test, several variations have been proposed.
```

**Step 2: Write the integration test**

```python
# tests/test_integration.py
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
```

**Step 3: Run the integration test**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_integration.py -v -s`
Expected: PASS (requires ANTHROPIC_API_KEY in env)

**Step 4: Commit**

```bash
git add tests/test_integration.py tests/fixtures/short_text.txt
git commit -m "test: add single-level integration test"
```

---

### Task 7: Integration Test — Recursion

**Files:**
- Create: `tests/fixtures/multi_section.txt`
- Modify: `tests/test_integration.py`

**Step 1: Create multi-section fixture**

Create `tests/fixtures/multi_section.txt` with 3 clearly distinct sections (~500 words each) separated by `---` or section headers. Content should be diverse enough that an agent would reasonably decompose it. Use sections about: (A) the history of the internet, (B) climate change science, (C) the space race. Each section should be self-contained.

**Step 2: Add recursion test**

Append to `tests/test_integration.py`:

```python
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
class TestRecursion:
    @pytest.mark.asyncio
    async def test_decompose_and_synthesize(self, workspace: Workspace):
        """With multi-section input and depth=2, agent should decompose."""
        config = RLMConfig(
            goal="Summarize each section separately, then provide an overall summary that ties them together.",
            model="claude-haiku-4-5-20251001",
            max_depth=2,
        )
        result = await rlm_call(
            workspace=workspace,
            config=config,
            depth=0,
            call_index=0,
            context_path=FIXTURES / "multi_section.txt",
        )
        assert result.answer is not None
        assert len(result.answer) > 50
        # Should have made more than 1 call (decompose + subcalls + synthesize)
        assert result.total_calls > 1

    @pytest.mark.asyncio
    async def test_depth_limit_prevents_recursion(self, workspace: Workspace):
        """With max_depth=0, even complex input should not decompose."""
        config = RLMConfig(
            goal="Summarize each section separately.",
            model="claude-haiku-4-5-20251001",
            max_depth=0,
        )
        result = await rlm_call(
            workspace=workspace,
            config=config,
            depth=0,
            call_index=0,
            context_path=FIXTURES / "multi_section.txt",
        )
        assert result.answer is not None
        assert result.total_calls == 1
        # No subcall directories should exist
        subcall_dirs = list(workspace.root.glob("d1_*"))
        assert len(subcall_dirs) == 0
```

**Step 3: Run tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_integration.py -v -s`
Expected: All integration tests PASS

**Step 4: Commit**

```bash
git add tests/fixtures/multi_section.txt tests/test_integration.py
git commit -m "test: add recursion and depth-limit integration tests"
```

---

### Task 8: Claude Code Skill

**Files:**
- Create: `skill/rlm.md` (in the project, to be symlinked or copied to `~/.claude/skills/`)

**Step 1: Write the skill file**

```markdown
---
name: rlm
description: Use when the user wants to process large contexts recursively, decompose complex tasks, or explicitly asks to use the RLM (Recursive Language Model). Launches a Python-based RLM agent that can recursively break down tasks.
---

# RLM — Recursive Language Model

Invoke the RLM Python entrypoint to recursively process a task using file-based context.

## Usage

Run via Bash:

```bash
uv run python /home/apsv/source/toy/rlm/rlm/main.py \
  --context <path-to-context-file> \
  --goal "<the task description>" \
  [--model claude-sonnet-4-6] \
  [--max-depth 3] \
  [--workspace <path>]
```

Or with inline context:

```bash
uv run python /home/apsv/source/toy/rlm/rlm/main.py \
  --context-text "<inline text>" \
  --goal "<the task>"
```

Or piped:

```bash
cat large_document.txt | uv run python /home/apsv/source/toy/rlm/rlm/main.py \
  --goal "<the task>"
```

## Parameters

- `--context PATH`: Path to context file
- `--context-text TEXT`: Inline context string
- `--goal TEXT`: The task (required)
- `--model MODEL`: Model to use (default: claude-sonnet-4-6)
- `--max-depth N`: Max recursion depth (default: 3). Use 0 for no recursion.
- `--workspace PATH`: Workspace dir (default: rlm_workspace/<timestamp>)

## When to use

- Processing documents too large for a single context window
- Tasks that benefit from divide-and-conquer decomposition
- When the user explicitly asks for RLM or recursive processing
- Multi-section analysis where each section needs independent processing

## How it works

The RLM agent:
1. Reads the context from files (not from the prompt)
2. Decides whether to answer directly or decompose into sub-tasks
3. If decomposing: writes sub-task contexts to files, specifies sub-goals
4. Python orchestrator runs sub-agents recursively
5. Results are synthesized into a final answer

Output goes to stdout. The workspace directory contains all intermediate files for inspection.
```

**Step 2: Symlink to skills directory**

Run: `mkdir -p ~/.claude/skills && ln -sf /home/apsv/source/toy/rlm/skill/rlm.md ~/.claude/skills/rlm.md`

**Step 3: Commit**

```bash
git add skill/rlm.md
git commit -m "feat: add Claude Code skill definition for RLM"
```

---

### Task 9: Run Full Test Suite

**Step 1: Run all unit tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py tests/test_prompts.py tests/test_agent.py -v`
Expected: All unit tests PASS

**Step 2: Run integration tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_integration.py -v -s`
Expected: All integration tests PASS

**Step 3: Run full suite**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest -v`
Expected: All tests PASS

---

### Task 10: Manual E2E Smoke Test

**Step 1: Run the CLI with a simple task**

Run:
```bash
cd /home/apsv/source/toy/rlm && uv run python rlm/main.py \
  --context tests/fixtures/short_text.txt \
  --goal "What is the main idea of this text?" \
  --max-depth 0 \
  --model claude-haiku-4-5-20251001
```
Expected: Prints a coherent answer about the Turing Test

**Step 2: Run with recursion enabled**

Run:
```bash
cd /home/apsv/source/toy/rlm && uv run python rlm/main.py \
  --context tests/fixtures/multi_section.txt \
  --goal "Summarize each section, then provide a combined analysis" \
  --max-depth 2 \
  --model claude-haiku-4-5-20251001
```
Expected: Prints a synthesized summary; workspace directory shows subcall directories

**Step 3: Inspect workspace**

Run: `find rlm_workspace/ -type f | head -20`
Expected: Shows context.txt, answer.txt, and subcalls.json files at various depths
