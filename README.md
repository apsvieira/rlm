# RLM — Recursive Language Model

RLM is a Python framework that runs [Claude](https://www.anthropic.com/claude) as a recursive agent. Given a goal and a context, an RLM agent either solves the task directly or decomposes it into sub-tasks, each handled by a child agent. Sub-results are gathered and synthesized into a final answer. The recursion is managed by the Python orchestrator; agents themselves only write files.

```
Goal + Context
     │
     ▼
 ┌────────────┐   answers directly?  ──► answer.txt
 │  Agent d0  │
 └────────────┘   decomposes?        ──► subcalls.json
         │
    ┌────┴────┐
    ▼         ▼
 Agent d1   Agent d1      (children run in sequence)
    │         │
  answer    answer
    └────┬────┘
         ▼
   Synthesize → answer.txt
```

---

## Table of Contents

- [Architecture](#architecture)
- [Installation](#installation)
- [CLI Usage](#cli-usage)
- [How Agents Work](#how-agents-work)
- [Workspace Format](#workspace-format)
- [Monitoring](#monitoring)
- [Testing](#testing)
- [Project Structure](#project-structure)

---

## Architecture

### Core components

| File | Role |
|------|------|
| `rlm/main.py` | Click CLI — parses arguments, creates workspace, calls `rlm_call`, prints summary |
| `rlm/agent.py` | `rlm_call()` — the recursive agent loop; runs decompose and synthesize phases |
| `rlm/workspace.py` | `Workspace` and `WorkspaceNode` — directory creation, file I/O, event logging |
| `rlm/prompts.py` | System prompt templates for decompose and synthesize phases |

### Execution flow

1. **Decompose phase** — an agent is given a goal and context. It may use any of its tools (`Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`) to explore files and data, then either:
   - Write `answer.txt` → the node is **solved** and returns immediately.
   - Write `subcalls.json` → the orchestrator spawns child agents for each entry.

2. **Child agents** — each sub-task runs as a new `rlm_call` at `depth + 1`, nested under the parent's workspace node. Children run sequentially.

3. **Synthesize phase** — after all children finish, the parent agent receives every sub-answer and synthesizes them into a final `answer.txt`.

Recursion is bounded by `--max-depth`. At max depth, agents cannot decompose and must solve directly.

### Agent tools

Every agent at every depth has the same tool set:

```
Read   Write   Edit   Bash   Glob   Grep
```

### Key design choices

- **File-based protocol** — the only contract between orchestrator and agent is the presence of `answer.txt` or `subcalls.json`. Agents are otherwise unconstrained.
- **System prompt for meta-instructions** — the orchestrator role and workspace layout are in the system prompt; the user message is just the goal text.
- **Depth-aware prompts** — at max depth the prompt removes the decompose option and instructs the agent to solve directly.
- **Node collision avoidance** — if a directory `d<N>_c<M>` already exists, the workspace appends a counter suffix (`d<N>_c<M>_1`, etc.).

---

## Installation

RLM requires Python ≥ 3.10 and [`uv`](https://github.com/astral-sh/uv).

```bash
# Install the package in editable mode (from the repo root)
uv pip install -e .

# Or run directly without installing, using uv --project:
uv run --project /path/to/rlm rlm --goal "..."
```

**Dependencies** (from `pyproject.toml`):

- [`claude-agent-sdk`](https://github.com/anthropics/claude-agent-sdk) — the Anthropic SDK that drives the agent loop
- [`click`](https://click.palletsprojects.com/) ≥ 8.0 — CLI parsing

Dev dependencies (for testing): `pytest ≥ 8.0`, `pytest-asyncio ≥ 0.23`.

---

## CLI Usage

```
rlm [OPTIONS]
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--goal TEXT` | *(required)* | The task or question for the agent to accomplish |
| `--context PATH` | — | Path to a context file (briefing document) |
| `--context-text TEXT` | — | Inline context string |
| `--model MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `--max-depth N` | `3` | Maximum recursion depth (0 = no decomposition) |
| `--workspace PATH` | `rlm_workspace/<timestamp>` | Workspace directory |

At least one of `--context`, `--context-text`, or stdin must be provided.

### Examples

```bash
# With a context file
rlm --context briefing.txt --goal "Summarize the key findings"

# Inline context
rlm --context-text "See /src/auth/ for the auth module" \
    --goal "Find all places where session tokens are generated"

# Piped input
cat large_document.txt | rlm --goal "Extract all action items"

# No decomposition (single-pass)
rlm --context briefing.txt --goal "Count the number of TODO comments" --max-depth 0

# Custom workspace for easy monitoring
rlm --context briefing.txt --goal "Analyse the codebase" \
    --workspace rlm_workspace/my_run
```

### Output

After the run completes, RLM prints a summary to stdout:

```
============================================================
RLM Complete
Workspace: rlm_workspace/1740000000
Total API calls: 7
Total cost: $0.0523

Output files (2):
  /abs/path/report.md  (14.2KB)
  /abs/path/data.json  (3.1KB)
============================================================

<final answer text>
```

---

## How Agents Work

Each agent receives a system prompt that describes its role, workspace, available tools, and recursion depth. The user message is just the goal text.

### Decompose or solve

The agent reads `context.txt` (its briefing), explores any referenced files, and decides:

**Option A — solve directly:** write `answer.txt` with findings, actions taken, and current state. Include an `## Output files` section listing any created files by absolute path.

**Option B — decompose:** if the task has distinct independent sub-tasks:
1. Write sub-task briefings to `vars/sub_N_context.txt`.
2. Write `subcalls.json`:
   ```json
   [
     {"goal": "sub-task description", "context_file": "vars/sub_0_context.txt"},
     {"goal": "another sub-task",     "context_file": "vars/sub_1_context.txt"}
   ]
   ```
3. Do *not* write `answer.txt` — the orchestrator will call again after children finish.

The agent prompt instructs: *"Choose Option A unless decomposition clearly improves the result."*

### Synthesis phase

After all children complete, the parent agent enters synthesis mode. It receives all sub-answers and must write a unified `answer.txt`. It can also re-read the original `context.txt` and any source files referenced in it.

### Emergent strategies

Agents autonomously choose among several strategies (from the RLM literature):

| Strategy | Description |
|----------|-------------|
| **Peeking** | Inspect the first N lines to understand structure before deciding |
| **Grepping** | Filter with patterns to narrow the search space |
| **Partition + Map** | Chunk input into segments, recurse on each, then aggregate |
| **Summarization** | Extract and condense subsets for the outer agent |

### Context file format

The context file is a *briefing* — it points the agent at source material rather than inlining it. Recommended format:

```
=== GOAL ===
What the caller wants accomplished.

=== RELEVANT FILES AND DIRECTORIES ===
- src/auth/         — authentication module
- tests/test_auth.py — existing auth tests
- config/settings.py:45-60 — key configuration

=== WHAT I ALREADY KNOW ===
Caller's prior findings, error messages, stack traces.

=== CONSTRAINTS ===
Don't modify X. Must remain backwards-compatible.
```

### Depth guidelines

| Task complexity | `--max-depth` | Strategy |
|----------------|---------------|----------|
| Simple / focused | `0` | Single agent solves directly |
| Multi-part | `1` | One round of decomposition |
| Cross-cutting analysis | `2` | Two levels; target distinct subsystems |
| Large-scale exploration | `3` | Full recursion with independent file pointers |

---

## Workspace Format

RLM uses a file-based protocol. All state is on disk, making it inspectable and resumable.

### Directory layout

```
rlm_workspace/
└── <timestamp>/                 ← workspace root
    ├── run.json                 ← run-level manifest
    └── d0_c0/                   ← root agent node (depth 0, call 0)
        ├── context.txt          ← briefing (input)
        ├── status.json          ← live state (working/decomposed/solved/synthesized/error)
        ├── events.jsonl         ← append-only event log
        ├── answer.txt           ← final answer (output, if solved)
        ├── subcalls.json        ← decomposition request (output, if decomposed)
        ├── error.txt            ← error message (if failed)
        ├── vars/                ← agent scratch space
        │   ├── sub_0_context.txt
        │   └── sub_1_context.txt
        └── d1_c0/               ← child node (depth 1, call 0)
            ├── context.txt
            ├── answer.txt
            └── vars/
```

Node directories are named `d<depth>_c<callindex>` and nested inside their parent.

### run.json

Created at the start of each run:

```json
{
  "goal": "Summarize the document",
  "model": "claude-sonnet-4-6",
  "max_depth": 3,
  "status": "running",
  "workspace": "rlm_workspace/1740000000",
  "started_at": "2026-02-21T12:00:00Z",
  "completed_at": "2026-02-21T12:05:00Z",
  "total_cost_usd": 0.0523,
  "total_calls": 7
}
```

### status.json

Each node maintains a `status.json` updated throughout the run:

```json
{
  "state": "synthesized",
  "depth": 0,
  "call_index": 0,
  "goal": "Summarize the document",
  "started_at": "2026-02-21T12:00:01Z",
  "completed_at": "2026-02-21T12:04:58Z",
  "cost_usd": 0.0523,
  "input_tokens": 18400,
  "output_tokens": 3200
}
```

States: `working` → `decomposed` or `solved` → `synthesized` (or `error`).

### events.jsonl

Append-only JSONL log of agent activity. One JSON object per line:

```jsonl
{"ts":"2026-02-21T12:00:01Z","phase":"decompose","type":"system","subtype":"init"}
{"ts":"2026-02-21T12:00:02Z","phase":"decompose","type":"tool_use","name":"Read","input":{"file_path":"context.txt"}}
{"ts":"2026-02-21T12:00:03Z","phase":"decompose","type":"tool_result","tool_use_id":"...","is_error":false,"content_length":842}
{"ts":"2026-02-21T12:00:10Z","phase":"decompose","type":"text","length":320,"preview":"I'll decompose this into..."}
{"ts":"2026-02-21T12:00:10Z","phase":"decompose","type":"result","cost_usd":0.0021,"input_tokens":4200,"output_tokens":380,"duration_ms":8340,"num_turns":4}
```

Event types: `system`, `tool_use`, `tool_result`, `text`, `result`.

---

## Monitoring

Use the companion TUI monitor to watch a run in real time:

```bash
# In a second terminal — auto-detects the latest workspace:
rlm-monitor

# Or point at a specific workspace:
rlm-monitor rlm_workspace/1740000000
```

See [`monitor/README.md`](monitor/README.md) for installation and full documentation.

When launching an RLM run, print the workspace path so users know where to point the monitor:

```
TIP: Run `rlm-monitor rlm_workspace/1740000000` in another terminal to watch progress.
```

---

## Testing

### Python tests

```bash
# Run all tests
make test
# or
uv run pytest

# Unit tests only (skip integration)
make test-unit

# Integration tests only (requires API key)
make test-integration

# Lint
make lint
```

Test files:

| File | Coverage |
|------|----------|
| `tests/test_workspace.py` | Workspace/node creation, status, events, subcalls, output files |
| `tests/test_prompts.py` | System prompt template generation |
| `tests/test_agent.py` | Agent phase logic |
| `tests/test_integration.py` | End-to-end RLM runs (requires API key) |

### Go monitor tests

```bash
cd monitor
make test
# or
go test ./...
```

---

## Project Structure

```
rlm/
├── Makefile                 # Python lint + test targets
├── pyproject.toml           # Package metadata and dependencies
│
├── rlm/                     # Python source
│   ├── __init__.py
│   ├── agent.py             # rlm_call() — recursive agent loop and phase runner
│   ├── main.py              # CLI entrypoint (click)
│   ├── prompts.py           # build_decompose_prompt(), build_synthesize_prompt()
│   └── workspace.py         # Workspace, WorkspaceNode — all file I/O
│
├── tests/                   # Python test suite
│   ├── fixtures/            # Test fixture files
│   ├── test_workspace.py
│   ├── test_prompts.py
│   ├── test_agent.py
│   └── test_integration.py
│
├── monitor/                 # Go TUI monitor (see monitor/README.md)
│   ├── Makefile
│   ├── go.mod
│   ├── main.go              # Entry point, workspace auto-detection
│   ├── model.go             # Bubbletea model, key handling, rendering
│   ├── workspace.go         # Workspace scanner, node types, stats
│   ├── workspace_test.go    # Unit tests for workspace scanning
│   ├── smoke_test.go        # Smoke tests for the TUI
│   ├── smoke_progress_test.go
│   └── edge_test.go
│
├── skill/
│   └── rlm.md               # Claude Code skill definition
│
└── docs/                    # Design documents and implementation notes
    ├── implementation-review.md
    └── plans/
```

---

## Reference

- [`claude-agent-sdk`](https://github.com/anthropics/claude-agent-sdk) — underlying agent SDK
- [Bubbletea](https://github.com/charmbracelet/bubbletea) — Go TUI framework used by the monitor
- RLM paradigm: Zhang, Kraska & Khattab, 2025 — *Recursive Language Models*
