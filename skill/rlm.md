---
name: rlm
description: Use when the user wants to process large contexts recursively, decompose complex tasks, or explicitly asks to use the RLM (Recursive Language Model). Launches a Python-based RLM agent that can recursively break down tasks.
---

# RLM — Recursive Language Model

Invoke the RLM Python entrypoint to recursively process a task using file-based context.

## Usage

Run via Bash (works from any directory):

```bash
uv run --project /home/apsv/source/toy/rlm rlm \
  --context <path-to-context-file> \
  --goal "<the task description>" \
  [--model claude-sonnet-4-6] \
  [--max-depth 3] \
  [--workspace <path>]
```

Or with inline context:

```bash
uv run --project /home/apsv/source/toy/rlm rlm \
  --context-text "<inline text>" \
  --goal "<the task>"
```

Or piped:

```bash
cat large_document.txt | uv run --project /home/apsv/source/toy/rlm rlm \
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
- Codebase exploration tasks where the agent should discover and navigate files itself

## Preparing the context file

The context file is a **briefing document** that tells the RLM agent what to accomplish and where to look. The agent has full file exploration tools (Read, Glob, Grep, Bash, Write, Edit) and can read any file on the filesystem — so the context file should **point the agent at source material**, not try to inline everything.

### What the context file should contain

The context file is a **briefing**, not a data dump. It tells the agent what to do and where to look:

- **Goal**: What the caller wants accomplished
- **Pointers**: Paths to relevant files, directories, and line ranges the agent should explore
- **Discovered context**: Anything the caller already knows — error messages, stack traces, prior findings — that saves the agent from rediscovering it
- **Constraints**: Boundaries like "don't modify X" or "must be backwards-compatible"

When it's useful, you can still inline small amounts of content (a config snippet, an error trace, a key function). Use your judgment: inline what saves the agent time, point at everything else.

### Briefing format

```text
=== GOAL ===
[What the caller wants accomplished]

=== RELEVANT FILES AND DIRECTORIES ===
- src/auth/ — authentication module, likely where the bug lives
- tests/test_auth.py — existing tests for auth
- config/settings.py:45-60 — relevant configuration section

=== WHAT I ALREADY KNOW ===
[Caller's discovered context: error messages, stack traces, prior findings]

=== CONSTRAINTS ===
[Any boundaries: don't modify X, must be backwards-compatible, etc.]
```

### What NOT to put in the context file

- Instructions to the agent (those go in `--goal`)
- Prompts or questions (those go in `--goal`)
- Massive inlined file dumps when a path reference would suffice
- Raw `find` output without explanation of what's relevant

### Task complexity guidelines

| Task complexity | Recommended `--max-depth` | Strategy |
|----------------|--------------------------|----------|
| Simple, focused | 0 (no recursion) | Agent explores and solves directly |
| Multi-part task | 1 | One level of decomposition into independent sub-tasks |
| Cross-cutting analysis | 2 | Two levels; point at distinct directories or subsystems |
| Large-scale exploration | 3 | Full recursion; each sub-task gets its own file pointers |

### How the RLM decides to recurse

Internally, each RLM agent autonomously decides whether to:
- **Solve directly** (Option A): Write `answer.txt` immediately — chosen when the task is simple enough to handle in one pass
- **Decompose** (Option B): Write sub-task contexts to `vars/sub_N_context.txt` and a `subcalls.json` specifying sub-goals — chosen when the task has distinct independent subtasks

The agent is biased toward direct solving: "Choose Option A unless decomposition clearly improves the result." At max depth, decomposition is disabled entirely — the agent must solve directly.

After sub-tasks complete, the parent agent enters **synthesis mode**: it receives all sub-answers and combines them into a coherent final answer, optionally re-reading the original `context.txt` and any referenced source files.

### Decomposition strategies (from the RLM literature)

The RLM paradigm (Zhang, Kraska & Khattab, 2025) documents four emergent strategies that agents use:

1. **Peeking**: Inspect the first N characters/lines to understand structure before deciding how to proceed
2. **Grepping**: Pattern/regex-based filtering to narrow the search space before recursive calls
3. **Partition + Map**: Chunk context into segments, launch recursive calls on each, then aggregate — ideal for semantic mapping tasks (e.g., "analyze each component")
4. **Summarization**: Extract and condense information subsets for the outer agent's decision-making

You don't need to tell the agent which strategy to use — it decides autonomously. But structuring your briefing with clear file pointers and section boundaries makes Partition + Map particularly effective.

## How it works

The RLM agent:
1. Reads the briefing from `context.txt` in its workspace
2. Explores referenced files and directories using its tools (Read, Glob, Grep, Bash)
3. Decides whether to answer directly or decompose into sub-tasks
4. If decomposing: writes sub-task briefings to files, specifies sub-goals
5. Python orchestrator runs sub-agents recursively
6. Results are synthesized into a final answer

Output goes to stdout. The workspace directory contains all intermediate files for inspection.

## Monitoring

Before launching the RLM run, print to the user:

```
TIP: Run `rlm-monitor <workspace-path>` in another terminal to watch progress in real time.
```

Use the actual workspace path that will be used for the run (either the user-specified `--workspace` or the default `rlm_workspace/<timestamp>`).
