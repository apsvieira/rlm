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
        "## Tools",
        "You have access to: Read, Write, Edit, Bash, Glob, Grep.",
        "Use them freely to explore files, search codebases, and run commands.",
        "",
        "## Workspace",
        f"Your workspace directory is: {workspace_path}",
        "- `context.txt` is your **briefing** — it contains the goal, pointers to relevant files/directories, and any context the caller already discovered",
        "- `vars/` is your scratch space for intermediate files",
        "",
        "## Depth",
        f"You are at depth {current_depth} of {max_depth}.",
        "",
        "## Instructions",
        "1. If `context.txt` exists in your workspace, read it — it contains pointers to relevant files/directories and any context the caller already discovered",
        "2. Explore files and directories to understand the task — use Glob, Grep, Read, and Bash to discover what you need",
        "3. The briefing (if present) points you at source material; it is not the complete data",
    ]

    if at_max_depth:
        parts.extend([
            "4. Process the task directly — you cannot delegate further",
            "5. Write your answer to `answer.txt` in your workspace",
        ])
    else:
        parts.extend([
            "4. Decide: can you solve this directly, or should you decompose?",
            "",
            "### Option A: Solve directly",
            "Write your answer to `answer.txt` in your workspace.",
            "",
            "### Option B: Decompose into sub-tasks",
            "If the task benefits from decomposition:",
            "1. Write each sub-task's briefing to `vars/sub_N_context.txt` — include file pointers and relevant discovered context, not massive inlined content",
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

    parts.extend([
        "",
        "## Answer format",
        "When writing `answer.txt`, include:",
        "- What you found (key findings, data, analysis)",
        "- What actions you took (files modified, commands run), if any",
        "- Current state (what changed, what the caller should know)",
        "",
        "### Output files",
        "If you created any files (reports, parsed data, scripts, etc.), list them at the end of your answer under an `## Output files` heading:",
        "- Use the **full absolute path** for each file",
        "- Briefly describe what each file contains",
        "- Note when the caller should read it (e.g., \"read for full analysis\", \"run to regenerate data\")",
        "",
        "Example:",
        "```",
        "## Output files",
        f"- `{workspace_path}/vars/parsed_data.json` — structured extraction of all records; read for programmatic access",
        f"- `{workspace_path}/vars/summary_report.md` — human-readable analysis; read for full findings",
        "```",
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
        "## Tools",
        "You have access to: Read, Write, Edit, Bash, Glob, Grep.",
        "You can re-read any source files referenced in your original briefing — you are not limited to the sub-answers below.",
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
        "1. Review the sub-task results above",
        "2. You may also read `context.txt` for the original briefing and re-read any source files it references",
        "3. Synthesize a coherent final answer covering: findings, actions taken, and current state",
        "4. If sub-tasks list output files, aggregate them into a consolidated `## Output files` section in your answer — preserve the absolute paths from sub-tasks",
        "5. Write your complete answer to `answer.txt` in your workspace",
        "",
        "## Original task",
        goal,
    ])

    return "\n".join(parts)
