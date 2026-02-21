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
        "## Workspace",
        f"Your workspace directory is: {workspace_path}",
        "- `context.txt` contains the input you should process",
        "- `vars/` is your scratch space for intermediate files",
        "",
        "## Depth",
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
        "## Workspace",
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
