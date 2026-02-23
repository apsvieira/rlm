---
name: rlm
description: Use when the user wants to process large contexts recursively, decompose complex tasks, or explicitly asks to use the RLM (Recursive Language Model). Launches a Python-based RLM agent that can recursively break down tasks.
---

# RLM — Recursive Language Model

Launch a recursive agent that explores, decomposes, and solves tasks autonomously.

## Key principle

RLM agents have full file exploration tools (Read, Glob, Grep, Bash, Write, Edit). They discover and navigate files themselves. **Do not pre-explore the codebase** — pass the goal and any known pointers directly. The RLM agent (or its sub-agents) will do the exploration.

## Usage

```bash
# Goal only — agent explores from scratch
uv run --project /home/apsv/source/toy/rlm rlm \
  --goal "<the task description>"

# With a brief context file of pointers (not a data dump)
uv run --project /home/apsv/source/toy/rlm rlm \
  --context <path-to-context-file> \
  --goal "<the task description>"

# With inline context
uv run --project /home/apsv/source/toy/rlm rlm \
  --context-text "<inline pointers and constraints>" \
  --goal "<the task>"

# Piped input
cat document.txt | uv run --project /home/apsv/source/toy/rlm rlm \
  --goal "<the task>"
```

## Parameters

| Option | Default | Description |
|--------|---------|-------------|
| `--goal TEXT` | *(required)* | The task for the agent to accomplish |
| `--context PATH` | — | Path to a context file (optional) |
| `--context-text TEXT` | — | Inline context string (optional) |
| `--model MODEL` | `claude-sonnet-4-6` | Model to use |
| `--max-depth N` | `3` | Max recursion depth (0 = no decomposition) |
| `--workspace PATH` | `rlm_workspace/<timestamp>` | Workspace directory |

Context is optional. When omitted, the agent starts with just the goal and explores from there.

## When to use

- Processing documents too large for a single context window
- Tasks that benefit from divide-and-conquer decomposition
- When the user explicitly asks for RLM or recursive processing
- Multi-section analysis where each section needs independent processing
- Codebase exploration tasks where the agent should discover and navigate files itself

## How to call it

1. **Put the task in `--goal`.** This is the primary instruction to the agent.

2. **Optionally provide context** — but only what you already know. Do not explore first to build context. Good context includes:
   - Specific file paths or directories the user mentioned
   - Error messages or stack traces from the conversation
   - Constraints (e.g., "don't modify X", "must be backwards-compatible")

3. **Choose `--max-depth`** based on task complexity:

   | Task complexity | `--max-depth` | Example |
   |----------------|---------------|---------|
   | Simple / focused | `0` | "Summarize this file" |
   | Multi-part | `1` | "Write docs for these 3 modules" |
   | Cross-cutting | `2` | "Analyse this codebase's architecture" |
   | Large-scale | `3` | "Review and refactor the entire test suite" |

4. **Run and let the agent work.** It will explore, decide whether to decompose, and produce results.

### Context file format (when used)

A short briefing — pointers, not a data dump:

```text
=== RELEVANT FILES AND DIRECTORIES ===
- src/auth/ — authentication module
- tests/test_auth.py — existing tests
- config/settings.py:45-60 — relevant config

=== WHAT I ALREADY KNOW ===
The login endpoint returns 403 for valid tokens since commit abc123.

=== CONSTRAINTS ===
Don't modify the token format. Must remain backwards-compatible.
```

## How it works

1. Agent reads its briefing (if any) and explores referenced files
2. Decides: solve directly (write `answer.txt`) or decompose (write `subcalls.json`)
3. If decomposing: orchestrator runs child agents recursively
4. After children finish: parent synthesizes results into final `answer.txt`
5. Recursion bounded by `--max-depth`; at max depth, agent must solve directly

## Monitoring

Before launching the RLM run, print to the user:

```
TIP: Run `rlm-monitor <workspace-path>` in another terminal to watch progress in real time.
```

Use the actual workspace path that will be used for the run (either the user-specified `--workspace` or the default `rlm_workspace/<timestamp>`).
