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
