# RLM Implementation Review

**Date:** 2026-02-21
**Project:** `/home/apsv/source/toy/rlm`
**Branch:** `main`

## Status: Complete

All 10 tasks implemented, validated, and committed.

## Commits

| Hash | Message |
|------|---------|
| `3fd05c3` | feat: scaffold RLM project with dependencies |
| `ee9e34e` | feat: add workspace directory manager with node read/write |
| `d19a730` | feat: add prompt builder for decompose and synthesize phases |
| `6fb0080` | feat: add agent runner with two-phase recursive execution |
| `1f1524d` | feat: add CLI entrypoint with click |
| `0c43b2a` | test: add single-level integration test |
| `a7c038e` | test: add recursion and depth-limit integration tests |
| `a952826` | feat: add Claude Code skill definition for RLM |

## Files Created

**Source:**
- `pyproject.toml` — Project config with hatchling build system
- `rlm/__init__.py` — Package marker
- `rlm/workspace.py` — Workspace directory manager (WorkspaceNode, Workspace)
- `rlm/prompts.py` — System prompt builder (decompose + synthesize phases)
- `rlm/agent.py` — Core agent runner with recursive two-phase execution
- `rlm/main.py` — Click CLI entrypoint

**Tests:**
- `tests/test_workspace.py` — 11 tests (incl. collision + malformed JSON)
- `tests/test_prompts.py` — 9 tests
- `tests/test_agent.py` — 5 tests
- `tests/test_integration.py` — 3 tests (require ANTHROPIC_API_KEY)
- `tests/fixtures/short_text.txt` — Turing Test paragraph
- `tests/fixtures/multi_section.txt` — 3-section document (~1000 words)

**Skill:**
- `skill/rlm.md` — Claude Code skill (symlinked to `~/.claude/skills/rlm.md`)

## Test Results

- **25 unit tests** — all pass in <1s
- **3 integration tests** — all pass (~2min, require API key)
- **28 total** — zero failures

## Critical Plan Issues Addressed

The implementation plan had 6 documented bugs. All were fixed:

1. **`allowed_tools` vs `tools`** — Used `tools=` in ClaudeAgentOptions (controls availability, not just auto-approval)
2. **`system_prompt` vs `prompt`** — Meta-instructions go into `system_prompt`, goal goes into `prompt`
3. **`goal`/`caller_prompt` duplication** — Separate `goal` parameter per recursion level; no duplication
4. **Node naming collision** — Nested directories under parent + collision counter fallback
5. **Malformed `subcalls.json`** — `read_subcalls()` validates JSON, checks for list type, filters entries missing `goal` key
6. **Skill frontmatter** — Proper `---` delimiters (opening and closing)

## Additional Fix: CLAUDECODE Environment Variable

The SDK subprocess fails when launched inside a Claude Code session due to the `CLAUDECODE` env var. Fixed in `run_agent_phase()` by temporarily unsetting it with a try/finally restore.

## Architecture

```
User -> CLI (main.py) -> rlm_call() -> run_agent_phase() -> claude-agent-sdk query()
                             | (if subcalls.json written)
                         rlm_call() recursively for each subcall
                             | (after all subcalls complete)
                         run_agent_phase() for synthesis -> answer.txt
```

- Python orchestrator manages recursion (agents cannot spawn subagents)
- Two-phase pattern: decompose-or-solve -> synthesize
- File-based context passing via workspace directories
- Nested workspace directories prevent naming collisions
