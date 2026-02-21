# RLM (Recursive Language Model) Implementation Design

## Overview

Implementation of the [RLM paper](https://arxiv.org/abs/2512.24601) as a Claude Code skill backed by a Python entrypoint using the Claude Agent SDK. The system allows Claude to recursively decompose tasks by spawning sub-agents that operate on file-based context variables.

## Architecture

Three layers:

### 1. Claude Code Skill (`~/.claude/skills/rlm.md`)

A skill file that teaches Claude how to invoke the RLM Python entrypoint. When the user asks for recursive processing, Claude runs the script via Bash with appropriate arguments.

### 2. Python Entrypoint (`rlm/main.py`)

CLI script that orchestrates the RLM agent loop.

**Arguments:**
- `--context PATH` — Path to context file (or `-` for stdin)
- `--goal TEXT` — The task/question to accomplish
- `--model MODEL` — Model to use (default: `claude-sonnet-4-6`)
- `--max-depth N` — Maximum recursion depth (default: 3)
- `--workspace PATH` — Workspace directory (default: `rlm_workspace/{timestamp}`)

**Responsibilities:**
- Parse arguments, create workspace directory structure
- Write initial context to `depth_0/context.txt`
- Construct the RLM meta system prompt
- Launch the root agent via `claude-agent-sdk`'s `query()`
- Stream agent output, collect final answer from `answer.txt`
- Print final result to stdout

### 3. RLM Agent (root + sub-agents)

Both root and sub-agents share the same paradigm but differ in depth and caller-crafted instructions.

## Context Variable System

Context lives in files, not in prompts. Each agent operates within a workspace directory.

```
rlm_workspace/{session}/
├── depth_0/
│   ├── context.txt          # Original input
│   ├── vars/                # Agent-created intermediate files
│   │   ├── chunk_0.txt
│   │   ├── chunk_1.txt
│   │   └── summary.txt
│   └── answer.txt           # Final answer from root
├── depth_1_call_0/
│   ├── context.txt          # Context written by parent
│   ├── vars/
│   └── answer.txt           # Sub-agent's answer
└── depth_1_call_1/
    ├── context.txt
    ├── vars/
    └── answer.txt
```

**Conventions:**
- `context.txt` — The input the agent should process
- `vars/` — Scratch space for intermediate results
- `answer.txt` — The agent writes its final output here

## Agent-Driven Recursion

Recursion is **not mechanical** — each agent autonomously decides whether to recurse.

### Flow:

1. Agent receives: goal, workspace path, depth metadata
2. Agent explores context (reads, greps, slices `context.txt`)
3. Agent reasons about whether the task needs decomposition
4. If yes:
   a. Creates a new workspace directory for the sub-agent
   b. Writes relevant context to the sub-agent's `context.txt`
   c. **Crafts a specific prompt** for the sub-agent with a narrowed goal
   d. Spawns sub-agent via the `rlm-sub` subagent definition
5. Reads sub-agent's `answer.txt`
6. Synthesizes results and writes own `answer.txt`

### What the parent controls:
- The goal/instructions (free-form, crafted per sub-task)
- What context to provide (writes the files)
- How many sub-agents to spawn

### What the system controls:
- Depth enforcement (removes `Task` tool at max depth)
- Workspace conventions (via meta-prompt)
- The meta-prompt teaching the RLM paradigm

### Sub-agent definition:

The `rlm-sub` subagent is defined with:
- **Tools**: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`, `Task` (Task removed at max depth)
- **Meta-prompt prefix**: "You are an RLM sub-agent at depth {N}/{max_depth}. [conventions about files, answer.txt, optional further recursion]"
- **Caller's prompt**: Appended after the meta-prompt — this is the specific task from the parent

## System Prompt Structure

### Meta-prompt (prepended to all agents):

```
You are an RLM (Recursive Language Model) agent.

## Your workspace
Your workspace directory is: {workspace_path}
- `context.txt` contains the input you should process
- `vars/` is your scratch space — create files here for intermediate results
- Write your final answer to `answer.txt`

## Current depth
You are at depth {current_depth} of {max_depth}.

## How to work
1. Read `context.txt` to understand your input
2. Explore the context — grep, slice, examine as needed
3. Decide if you need to decompose the task
4. If decomposing: create sub-workspaces, write context files, spawn sub-agents
5. Synthesize results and write `answer.txt`

## Spawning sub-agents
To delegate a sub-task:
1. Create a directory: {workspace_parent}/depth_{next}_call_{n}/
2. Write the sub-task's context to that directory's `context.txt`
3. Use the Task tool to spawn an `rlm-sub` agent with your crafted prompt
4. The sub-agent will write its result to `answer.txt` in its workspace
5. Read that file to get the result

{depth_limit_notice}
```

Where `{depth_limit_notice}` is either empty or "You are at maximum depth. Process this task directly without spawning sub-agents."

### Root agent prompt:
```
{meta_prompt}

## Your task
{user_goal}
```

## File Structure

```
rlm/
├── pyproject.toml
├── rlm/
│   ├── __init__.py
│   ├── main.py              # CLI entrypoint
│   ├── agent.py             # Agent construction and query logic
│   ├── workspace.py         # Workspace directory management
│   └── prompts.py           # System prompt templates
├── tests/
│   ├── conftest.py
│   ├── test_workspace.py    # Unit tests for workspace setup
│   ├── test_prompts.py      # Unit tests for prompt construction
│   ├── test_single_level.py # Integration: no recursion
│   ├── test_recursion.py    # Integration: with recursion
│   └── test_depth_limit.py  # Integration: depth enforcement
└── docs/
    └── plans/
        └── 2026-02-21-rlm-design.md
```

## Skill Definition

`~/.claude/skills/rlm.md`:

```markdown
name: rlm
description: Use when the user wants to process large contexts, decompose complex tasks recursively, or asks to use the RLM. Launches a Recursive Language Model agent.
---
# RLM — Recursive Language Model

Launch the RLM Python entrypoint to recursively process a task.

## Usage
Run via Bash:
  uv run python /path/to/rlm/main.py \
    --context <path-to-context-file> \
    --goal "<the task>" \
    [--model claude-sonnet-4-6] \
    [--max-depth 3]

## When to use
- Processing documents that exceed comfortable context sizes
- Complex tasks that benefit from recursive decomposition
- Any task where the user explicitly asks for RLM processing
```

## Testing Plan

### Test 1: Unit — Workspace Setup
- Verify workspace directory creation with correct structure
- Verify context file writing from file path and stdin
- Verify CLI argument parsing

### Test 2: Unit — Prompt Construction
- Verify meta-prompt includes correct depth/path information
- Verify depth limit notice appears at max depth
- Verify Task tool is excluded from tools list at max depth

### Test 3: Integration — Single Level (max_depth=1)
- Short text (~500 words), simple goal ("Summarize this text")
- Verify: answer.txt created, contains reasonable response

### Test 4: Integration — Recursion (max_depth=2)
- Longer text (~5000 words, multiple distinct sections)
- Goal: "Summarize each section separately, then provide an overall summary"
- Verify: sub-agent workspaces created, each has context.txt and answer.txt
- Verify: final answer synthesizes sub-answers

### Test 5: Depth Limit Enforcement
- max_depth=1 with complex task
- Verify: no sub-agent directories created
- Verify: agent handles task directly

### Test 6: End-to-End — Real Document
- Real long document, open-ended goal
- max_depth=3
- Verify: coherent result, depth not exceeded

## Dependencies

- `claude-agent-sdk` — Agent loop and tool execution
- `click` — CLI argument parsing
- `pytest` — Testing

## Open Questions

- Should we support async parallel sub-agent calls? (Deferred — start sequential)
- Should we add cost/token tracking across recursive calls? (Nice-to-have for v2)
- Should workspace cleanup be automatic or manual? (Start manual, add --cleanup flag later)
