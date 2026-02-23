"""RLM agent runner — manages the recursive agent loop."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
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
class PhaseResult:
    """Result from a single agent phase."""

    text: str | None
    cost_usd: float
    input_tokens: int
    output_tokens: int


@dataclass
class RLMResult:
    """Result from an RLM run."""

    answer: str
    workspace_root: Path
    total_cost_usd: float = 0.0
    total_calls: int = 0
    output_files: list[Path] = field(default_factory=list)


def _truncate_input(input_val: dict | str | None, max_len: int = 200) -> dict | str | None:
    """Truncate tool input values over max_len chars for logging."""
    if isinstance(input_val, dict):
        result = {}
        for k, v in input_val.items():
            sv = str(v)
            if len(sv) > max_len:
                result[k] = sv[:max_len] + "..."
            else:
                result[k] = v
        return result
    if isinstance(input_val, str) and len(input_val) > max_len:
        return input_val[:max_len] + "..."
    return input_val


def _log_event(node: WorkspaceNode | None, phase_label: str | None, event: dict) -> None:
    """Log an event to the node's events.jsonl if node is provided."""
    if node is None:
        return
    if phase_label:
        event["phase"] = phase_label
    node.append_event(event)


async def run_agent_phase(
    system_prompt: str,
    prompt: str,
    cwd: str,
    model: str,
    tools: list[str],
    permission_mode: str,
    node: WorkspaceNode | None = None,
    phase_label: str | None = None,
) -> PhaseResult:
    """Run a single agent phase (decompose or synthesize).

    Uses system_prompt for meta-instructions and prompt for the task-specific
    user message. The tools parameter controls which tools are available
    (Issue 1: uses 'tools' not 'allowed_tools').

    Returns PhaseResult with text, cost, and token usage.
    """
    last_text: str | None = None
    cost: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

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
                    if isinstance(block, ToolUseBlock):
                        _log_event(node, phase_label, {
                            "type": "tool_use",
                            "name": block.name,
                            "input": _truncate_input(block.input),
                        })
                    elif isinstance(block, ToolResultBlock):
                        _log_event(node, phase_label, {
                            "type": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "is_error": block.is_error,
                            "content_length": len(str(block.content)),
                        })
                    elif isinstance(block, TextBlock):
                        last_text = block.text
                        _log_event(node, phase_label, {
                            "type": "text",
                            "length": len(block.text),
                            "preview": block.text[:200],
                        })
            elif isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0.0
                usage = message.usage or {}
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                _log_event(node, phase_label, {
                    "type": "result",
                    "cost_usd": cost,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "duration_ms": getattr(message, "duration_ms", None),
                    "num_turns": getattr(message, "num_turns", None),
                })
            elif isinstance(message, SystemMessage):
                _log_event(node, phase_label, {
                    "type": "system",
                    "subtype": message.subtype,
                })
    finally:
        if saved_claudecode is not None:
            os.environ["CLAUDECODE"] = saved_claudecode

    return PhaseResult(
        text=last_text,
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


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

    from datetime import datetime, timezone

    total_cost = 0.0
    total_calls = 1

    # Write initial status
    node.write_status(state="working", depth=depth, call_index=call_index, goal=effective_goal)

    # Phase 1: Decompose or solve
    phase = await run_agent_phase(
        system_prompt=system_prompt,
        prompt=effective_goal,
        cwd=str(node.path),
        model=config.model,
        tools=tools,
        permission_mode=config.permission_mode,
        node=node,
        phase_label="decompose",
    )
    total_cost += phase.cost_usd

    # Update status with decompose phase cost
    node.write_status(
        cost_usd=phase.cost_usd,
        input_tokens=phase.input_tokens,
        output_tokens=phase.output_tokens,
    )

    # Check: did the agent answer directly?
    answer = node.read_answer()
    if answer is not None:
        node.write_status(state="solved", completed_at=datetime.now(timezone.utc).isoformat())
        return RLMResult(
            answer=answer,
            workspace_root=workspace.root,
            total_cost_usd=total_cost,
            total_calls=total_calls,
            output_files=node.discover_output_files(),
        )

    # Check: did the agent request subcalls? (Issue 5: validated by read_subcalls)
    subcalls = node.read_subcalls()
    if not subcalls:
        error_msg = "Agent produced neither answer.txt nor subcalls.json"
        node.write_error(error_msg)
        return RLMResult(
            answer=f"[RLM Error: {error_msg}]",
            workspace_root=workspace.root,
            total_cost_usd=total_cost,
            total_calls=total_calls,
        )

    # Mark as decomposed
    node.write_status(state="decomposed")

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

    synth_phase = await run_agent_phase(
        system_prompt=synth_system_prompt,
        prompt=f"Synthesize the sub-task results and write your answer to answer.txt. Original task: {effective_goal}",
        cwd=str(node.path),
        model=config.model,
        tools=tools,
        permission_mode=config.permission_mode,
        node=node,
        phase_label="synthesize",
    )
    total_cost += synth_phase.cost_usd
    total_calls += 1

    answer = node.read_answer()
    if answer is not None:
        cur_status = node.read_status()
        node.write_status(
            state="synthesized",
            completed_at=datetime.now(timezone.utc).isoformat(),
            cost_usd=cur_status.get("cost_usd", 0) + synth_phase.cost_usd,
            input_tokens=cur_status.get("input_tokens", 0) + synth_phase.input_tokens,
            output_tokens=cur_status.get("output_tokens", 0) + synth_phase.output_tokens,
        )
    if answer is None:
        error_msg = "Synthesis agent did not write answer.txt"
        node.write_error(error_msg)
        answer = f"[RLM Error: {error_msg}]"

    return RLMResult(
        answer=answer,
        workspace_root=workspace.root,
        total_cost_usd=total_cost,
        total_calls=total_calls,
        output_files=node.collect_all_output_files(),
    )
