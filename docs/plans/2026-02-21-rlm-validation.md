# RLM Implementation Validation Guide

> **For the implementing agent:** After completing each task, run the validation checks below **before** committing. Report results as PASS/FAIL with actual output. Do not proceed to the next task if any check fails — fix first.

## Critical Plan Issues Found During Review

These issues exist in the implementation plan and MUST be addressed during implementation. Do not blindly follow the plan where it contradicts these findings.

### Issue 1: `allowed_tools` vs `tools` in SDK

The plan uses `allowed_tools` in `ClaudeAgentOptions`. The SDK has **both** `tools` (controls which tools are available) and `allowed_tools` (auto-approves tools without permission prompts). For restricting the agent's toolset, use `tools`. The `allowed_tools` field only controls auto-approval. **Action:** In `run_agent_phase`, use `tools=tools` not `allowed_tools=tools`.

### Design Note: `query()` uses `prompt` as a user message, not system prompt

The plan passes the decompose/synthesize prompt as the `prompt` arg to `query()`. This is a user-turn message, not a system prompt. The system prompt can be set via `ClaudeAgentOptions(system_prompt=...)`. Using `prompt` for everything works — it is a valid pattern and not a bug. However, if the agent wants to split meta-instructions into `system_prompt` and the goal into `prompt`, that is also acceptable. Either approach is fine; this is not a blocking issue.

### Issue 3: `goal` vs `caller_prompt` confusion in `rlm_call`

In the plan's `rlm_call`, the decompose prompt is built with:
```python
goal=config.goal if caller_prompt is None else caller_prompt,
```
This means at depth > 0, the **original user goal is lost** from the prompt's "Your task" section and replaced with the subcall goal. But `caller_prompt` is *also* passed to `build_decompose_prompt` as the `caller_prompt` parameter, which adds it under "Additional context from caller." So the subcall goal appears **twice** in the prompt (once as "Your task", once as "Additional context from caller"), and the original goal is gone.

**Recommended fix:** At each depth, the sub-agent's goal is the subcall-specific goal — pass it as `goal`. Remove the `caller_prompt` parameter from `build_decompose_prompt` entirely. Sub-agents don't need the original user goal; they need their specific sub-task description. This is the simpler design: each agent gets exactly one goal, the one relevant to its scope.

### Issue 4: Node naming collision at different depths

`Workspace.create_node` creates directories as `d{depth}_c{call_index}` at the workspace root level. At depth 1 with 3 subcalls, you get `d1_c0`, `d1_c1`, `d1_c2`. But if depth 1 call 0 itself decomposes into 2 subcalls, those create `d2_c0` and `d2_c1`. If depth 1 call 1 *also* decomposes, it creates `d2_c0` and `d2_c1` again — **collision**. The `call_index` resets per parent but directories are flat. **Action:** Either make `call_index` globally unique per depth (counter across all parents), or nest directories under parents. This is a **correctness bug** that will surface in Task 7's recursion test.

### Issue 5: No error handling for malformed `subcalls.json`

If the agent writes invalid JSON to `subcalls.json`, or a valid JSON with unexpected structure (missing "goal" key), the code will crash with an unhandled exception. **Action:** Add basic validation in `read_subcalls()` or in `rlm_call` where subcalls are consumed.

### Issue 6: Skill file frontmatter is malformed

The plan shows the skill `rlm.md` with `---` only at the top (not closing the frontmatter block). Claude Code skills require the frontmatter to be wrapped in `---` delimiters (opening and closing). **Action:** Ensure the skill file has proper YAML frontmatter: `---\nname: rlm\ndescription: ...\n---`.

---

## General Notes

- **Modifying already-completed modules is permitted.** Some fixes (especially Issue 4) require changes to `workspace.py` or `prompts.py`, which were committed in earlier tasks. This is expected — update the code, update the tests, and note the change in the commit message.
- **SDK behavior may differ from the plan.** If `claude-agent-sdk` types or function signatures don't match what the plan assumes, inspect the SDK directly (e.g., `inspect.signature()`, `help()`, `dir()`) and adapt. The plan's SDK code is illustrative, not authoritative.

---

## Completed Tasks (Already Validated)

### Task 1: Project Scaffolding — DONE (commit 3fd05c3)
### Task 2: Workspace Manager — DONE (commit ee9e34e)
### Task 3: Prompt Builder — DONE (commit d19a730)

---

## Task 4: Agent Runner (`rlm/agent.py`)

### Pre-implementation checklist
- [ ] Read Issue 1, 3, 4, 5 above — they all affect this task
- [ ] Decide on the `call_index` collision fix (Issue 4) before writing code

### Validation Checks

**Check 4.1: Module imports cleanly**
```bash
uv run python -c "from rlm.agent import get_tools_for_depth, RLMConfig, RLMResult, rlm_call, run_agent_phase; print('OK')"
```
- Expected: `OK`
- Fail means: missing imports, typos in function names, or SDK import errors

**Check 4.2: Unit tests pass**
```bash
uv run pytest tests/test_agent.py -v
```
- Expected: All tests in `TestToolSelection` and `TestRLMConfig` pass (5 tests)
- Fail means: tool list logic or config defaults are wrong

**Check 4.3: `tools` parameter, not `allowed_tools` (Issue 1)**
```bash
grep -n "allowed_tools" rlm/agent.py
```
- Expected: No matches (or only in comments explaining the decision)
- Fail means: Issue 1 was not addressed

**Check 4.4: `Task` tool is excluded**
```bash
uv run python -c "
from rlm.agent import get_tools_for_depth
for d in range(4):
    tools = get_tools_for_depth(d, 3)
    assert 'Task' not in tools, f'Task found at depth {d}'
print('OK: Task excluded at all depths')
"
```
- Expected: `OK: Task excluded at all depths`

**Check 4.5: Node collision is handled (Issue 4)**

The fix may live in `workspace.py` (naming scheme prevents collision) or in `agent.py` (caller ensures unique arguments). Verify by checking how the code handles the scenario where two parents at depth 1 both create children at depth 2:

- **Option A — fixed in Workspace:** The `create_node` API itself prevents collisions (e.g., names include parent identity, or directories are nested).
- **Option B — fixed in agent.py:** The `rlm_call` function ensures `call_index` is globally unique per depth (e.g., via a counter on the Workspace object), so `create_node` is never called with conflicting arguments.

To validate, read the source code for the fix and verify that the following scenario cannot produce two nodes writing to the same directory:
1. Root (d0_c0) decomposes into 2 subcalls → creates d1_c0 and d1_c1
2. d1_c0 decomposes into 2 subcalls → creates children at depth 2
3. d1_c1 also decomposes into 2 subcalls → creates children at depth 2
4. The depth-2 children from step 2 and step 3 must have distinct directories.

If the fix is Option A, run:
```bash
uv run python -c "
from rlm.workspace import Workspace
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory() as td:
    ws = Workspace(root=Path(td) / 'ws')
    n1 = ws.create_node(depth=2, call_index=0, context='from parent 0')
    n2 = ws.create_node(depth=2, call_index=0, context='from parent 1')
    if n1.path == n2.path:
        print('FAIL: Node collision — same path for both nodes')
    else:
        print('OK: No collision')
"
```

If the fix is Option B, verify by reading `agent.py` and confirming the call_index values passed to `create_node` are guaranteed unique per depth. Write a brief explanation in the notes column.

- Expected: Collision is prevented by one of the two approaches
- Fail means: Two sibling parents can still create children with overlapping directory names

**Check 4.6: Existing tests still pass**
```bash
uv run pytest tests/ -v
```
- Expected: All existing tests (workspace + prompts) still pass alongside new agent tests

### Acceptance Criteria
- `rlm/agent.py` exists with `RLMConfig`, `RLMResult`, `get_tools_for_depth`, `run_agent_phase`, `rlm_call`
- All unit tests pass (including updated workspace tests if workspace.py was modified)
- No `allowed_tools` misuse (Issue 1)
- Node collision addressed (Issue 4) — at either the Workspace or agent level
- `goal`/`caller_prompt` duplication removed (Issue 3) — each agent gets one goal, its own

---

## Task 5: CLI Entrypoint (`rlm/main.py`)

### Validation Checks

**Check 5.1: Module imports cleanly**
```bash
uv run python -c "from rlm.main import cli; print('OK')"
```
- Expected: `OK`

**Check 5.2: CLI help text renders**
```bash
uv run python -m rlm.main --help
```
- Expected: Shows usage with `--context`, `--context-text`, `--goal`, `--model`, `--max-depth`, `--workspace`

**Check 5.3: Missing arguments produce clear errors**
```bash
uv run python -m rlm.main 2>&1; echo "exit: $?"
```
- Expected: Error message mentioning `--goal` is required, non-zero exit code

**Check 5.4: Stdin detection works**
```bash
echo "test input" | uv run python -m rlm.main --goal "test" --max-depth 0 --help 2>&1 | head -5
```
- Expected: Does not crash on stdin detection logic (help flag short-circuits before API call)

**Check 5.5: All tests still pass**
```bash
uv run pytest tests/ -v
```
- Expected: All tests pass

### Acceptance Criteria
- `rlm/main.py` exists with a `cli()` Click command
- CLI accepts all documented flags
- Proper error on missing `--goal`
- Stdin piping is supported
- No API calls made during validation (we defer live testing to Tasks 6-7)

---

## Task 6: Integration Test — Single Level

### Pre-implementation checklist
- [ ] Verify `ANTHROPIC_API_KEY` is set in environment
- [ ] Fixture file `tests/fixtures/short_text.txt` exists and is non-empty

### Validation Checks

**Check 6.1: Fixture file exists**
```bash
test -f tests/fixtures/short_text.txt && wc -c tests/fixtures/short_text.txt
```
- Expected: File exists, ~500-700 bytes

**Check 6.2: Integration test runs (requires API key)**
```bash
uv run pytest tests/test_integration.py::TestSingleLevel -v -s --timeout=120
```
- Expected: `test_direct_answer` PASSES
- Watch for:
  - `answer.txt` written in `d0_c0/`
  - `result.total_calls == 1` (no recursion)
  - Answer is non-empty and coherent (length > 10 chars)
  - No `subcalls.json` in `d0_c0/` (direct answer, no decomposition)
- Fail likely means: SDK call failed, agent didn't write `answer.txt`, or workspace path is wrong

**Check 6.3: All unit tests still pass**
```bash
uv run pytest tests/test_workspace.py tests/test_prompts.py tests/test_agent.py -v
```
- Expected: All unit tests pass (integration test doesn't break anything)

### Acceptance Criteria
- `tests/fixtures/short_text.txt` exists
- `tests/test_integration.py` has `TestSingleLevel` class
- Test passes with live API (skipped without key)
- Agent writes `answer.txt` directly without decomposing

---

## Task 7: Integration Test — Recursion

### Pre-implementation checklist
- [ ] Task 6 passed — single-level works
- [ ] Node collision fix from Issue 4 is in place
- [ ] `ANTHROPIC_API_KEY` is set

### Validation Checks

**Check 7.1: Multi-section fixture exists**
```bash
test -f tests/fixtures/multi_section.txt && wc -w tests/fixtures/multi_section.txt
```
- Expected: File exists, ~1000-1500 words (3 sections, ~500 each)

**Check 7.2: Fixture has distinct sections**
```bash
grep -c "^#\|^---" tests/fixtures/multi_section.txt
```
- Expected: 2-3+ section separators

**Check 7.3: Recursion test runs**
```bash
uv run pytest tests/test_integration.py::TestRecursion::test_decompose_and_synthesize -v -s --timeout=300
```
- Expected: PASSES
- Watch for:
  - `result.total_calls > 1` (recursion happened)
  - `d1_c*` directories exist (sub-agents were spawned)
  - Each sub-agent directory has `context.txt` and `answer.txt`
  - Root `d0_c0` has `subcalls.json` AND `answer.txt` (after synthesis)
  - No node collisions (Issue 4)
- Fail likely means: agent chose to solve directly (prompt not compelling enough), or workspace collision, or SDK error

**Check 7.4: Depth limit test runs**
```bash
uv run pytest tests/test_integration.py::TestRecursion::test_depth_limit_prevents_recursion -v -s --timeout=120
```
- Expected: PASSES
- Watch for:
  - `result.total_calls == 1`
  - No `d1_*` directories exist
  - Agent solved directly despite complex input

**Check 7.5: All tests pass together**
```bash
uv run pytest tests/ -v --timeout=300
```
- Expected: All unit + integration tests pass

### Key Risk
The recursion test (`test_decompose_and_synthesize`) is **non-deterministic**. The agent may choose to solve directly instead of decomposing. If this happens:
- Verify the prompt correctly encourages decomposition for multi-section input
- Consider making the goal more explicit: "You MUST decompose this into one sub-task per section"
- Or accept that the test may need a retry

### Acceptance Criteria
- `tests/fixtures/multi_section.txt` exists with 3 distinct sections
- `TestRecursion` has `test_decompose_and_synthesize` and `test_depth_limit_prevents_recursion`
- Recursion test produces `total_calls > 1` and creates sub-agent directories
- Depth limit test produces `total_calls == 1` with no sub-directories
- No workspace collisions

---

## Task 8: Claude Code Skill

### Validation Checks

**Check 8.1: Skill file exists with valid frontmatter (Issue 6)**
```bash
head -4 skill/rlm.md
```
- Expected: First line is `---`, contains `name: rlm` and `description:`, ends with `---`

**Check 8.2: Skill references correct paths**
```bash
grep "/home/apsv/source/toy/rlm" skill/rlm.md
```
- Expected: Path to `rlm/main.py` is correct and matches actual file location

**Check 8.3: Skill usage examples are syntactically valid**
Manually verify:
- `--context`, `--context-text`, `--goal` flags match `rlm/main.py` Click definitions
- Model default matches `RLMConfig` default
- `--max-depth` flag name matches CLI

**Check 8.4: Symlink created**
```bash
ls -la ~/.claude/skills/rlm.md
```
- Expected: Symlink pointing to `/home/apsv/source/toy/rlm/skill/rlm.md`

### Acceptance Criteria
- `skill/rlm.md` exists with valid YAML frontmatter
- All CLI flags in the skill match the actual CLI implementation
- Symlink in `~/.claude/skills/` works

---

## Task 9: Full Test Suite (self-validated)

> **No validation agent needed.** The implementation agent runs these checks directly and reports the output.

### Checks (run yourself)

**Check 9.1: All unit tests pass**
```bash
uv run pytest tests/test_workspace.py tests/test_prompts.py tests/test_agent.py -v
```
- Expected: All unit tests pass (17+ tests)

**Check 9.2: All integration tests pass**
```bash
uv run pytest tests/test_integration.py -v -s --timeout=300
```
- Expected: All integration tests pass (3 tests, requires API key)

**Check 9.3: Full suite in one run**
```bash
uv run pytest -v --timeout=300
```
- Expected: All tests pass, zero failures

**Check 9.4: No import warnings or deprecation notices**
```bash
uv run pytest -v --timeout=300 2>&1 | grep -i "warning\|deprecat"
```
- Expected: No relevant warnings (pytest collection warnings are OK)

### Acceptance Criteria
- Zero test failures across the entire suite
- Unit tests run fast (< 5 seconds)
- Integration tests complete within timeout

---

## Task 10: Manual E2E Smoke Test (self-validated)

> **No validation agent needed.** The implementation agent runs these checks directly and reports the output.

### Checks (run yourself)

**Check 10.1: Simple no-recursion run**
```bash
uv run python rlm/main.py \
  --context tests/fixtures/short_text.txt \
  --goal "What is the main idea of this text?" \
  --max-depth 0 \
  --model claude-haiku-4-5-20251001
```
- Expected output contains:
  - `RLM Complete` banner
  - `Total API calls: 1`
  - A coherent answer about the Turing Test
  - `Workspace:` path shown

**Check 10.2: Recursion-enabled run**
```bash
uv run python rlm/main.py \
  --context tests/fixtures/multi_section.txt \
  --goal "Summarize each section, then provide a combined analysis" \
  --max-depth 2 \
  --model claude-haiku-4-5-20251001
```
- Expected:
  - `Total API calls` > 1
  - Answer references content from multiple sections
  - Workspace directory has `d0_c0`, `d1_c*` directories

**Check 10.3: Workspace inspection**
```bash
find rlm_workspace/ -name "*.txt" -o -name "*.json" | sort
```
- Expected: Shows `context.txt`, `answer.txt` at multiple depths, `subcalls.json` at root

**Check 10.4: Stdin piping works**
```bash
echo "The quick brown fox jumps over the lazy dog." | \
  uv run python rlm/main.py --goal "What animal is mentioned?" --max-depth 0 --model claude-haiku-4-5-20251001
```
- Expected: Answer mentions a fox (and/or dog), `Total API calls: 1`

**Check 10.5: Cleanup workspace**
```bash
rm -rf rlm_workspace/
```

### Acceptance Criteria
- CLI produces output for all input methods (file, inline, stdin)
- Recursion creates multi-depth workspace structure
- No crashes or unhandled exceptions
- Output is coherent and task-relevant
