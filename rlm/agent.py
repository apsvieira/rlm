"""RLM agent runner — manages the recursive agent loop."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
    system_prompt: str,
    prompt: str,
    cwd: str,
    model: str,
    tools: list[str],
    permission_mode: str,
) -> tuple[str | None, float]:
    """Run a single agent phase (decompose or synthesize).

    Uses system_prompt for meta-instructions and prompt for the task-specific
    user message. The tools parameter controls which tools are available
    (Issue 1: uses 'tools' not 'allowed_tools').

    Returns (result_text, cost_usd).
    """
    last_text: str | None = None
    cost: float = 0.0

    # Unset CLAUDECODE to allow SDK subprocess to launch when running
    # inside a Claude Code session (e.g., during integration tests).
    saved_claudecode = os.environ.pop("CLAUDECODE", None)
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                system_prompt=system_prompt,
                tools=tools,
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
    finally:
        if saved_claudecode is not None:
            os.environ["CLAUDECODE"] = saved_claudecode

    return last_text, cost


async def rlm_call(
    workspace: Workspace,
    config: RLMConfig,
    depth: int,
    call_index: int,
    goal: str | None = None,
    context: str | None = None,
    context_path: Path | None = None,
    parent: WorkspaceNode | None = None,
) -> RLMResult:
    """Execute one level of the RLM recursion.

    1. Create workspace node (nested under parent to avoid collisions — Issue 4)
    2. Run decompose-or-solve agent
    3. If agent wrote answer.txt → return it
    4. If agent wrote subcalls.json → run each subcall recursively, then synthesize

    Issue 3 fix: `goal` parameter is the task-specific goal for this level.
    At depth 0 it defaults to config.goal. Subcalls pass their own goal.
    """
    effective_goal = goal if goal is not None else config.goal

    node = workspace.create_node(
        depth=depth,
        call_index=call_index,
        context=context,
        context_path=context_path,
        parent=parent,
    )

    tools = get_tools_for_depth(depth, config.max_depth)

    # Issue 2: Use system_prompt for meta-instructions, prompt for the goal
    system_prompt = build_decompose_prompt(
        workspace_path=str(node.path),
        goal=effective_goal,
        current_depth=depth,
        max_depth=config.max_depth,
    )

    total_cost = 0.0
    total_calls = 1

    # Phase 1: Decompose or solve
    _, cost = await run_agent_phase(
        system_prompt=system_prompt,
        prompt=effective_goal,
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

    # Check: did the agent request subcalls? (Issue 5: validated by read_subcalls)
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
            goal=sub_goal,
            context=sub_context,
            context_path=sub_context_path,
            parent=node,
        )
        sub_answers[f"Sub-task {i}: {sub_goal}"] = sub_result.answer
        total_cost += sub_result.total_cost_usd
        total_calls += sub_result.total_calls

    # Phase 3: Synthesize
    synth_system_prompt = build_synthesize_prompt(
        workspace_path=str(node.path),
        goal=effective_goal,
        sub_answers=sub_answers,
    )

    _, synth_cost = await run_agent_phase(
        system_prompt=synth_system_prompt,
        prompt=f"Synthesize the sub-task results and write your answer to answer.txt. Original task: {effective_goal}",
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
