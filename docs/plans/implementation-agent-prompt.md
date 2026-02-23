# Implementation Agent Prompt

> Use the text below the `---` line as the prompt for the implementation agent.

---

You are implementing the RLM (Recursive Language Model) project. Work through the implementation plan one task at a time, validating each task before moving on.

## Key Documents

All in `/home/apsv/source/toy/rlm/docs/plans/`:

- `2026-02-21-rlm-implementation.md` — The implementation plan. Follow it task-by-task.
- `2026-02-21-rlm-validation.md` — The validation guide. Contains critical issues and per-task checks.
- `validation-agent-prompt.md` — The prompt for the validation agent (everything after the `---` line).

## Your Workflow

For each task (starting from the first incomplete one):

### Step 1: Read the plan and validation guide

Before writing any code for task N, read both:
- The task section in the implementation plan
- The task section in the validation guide, **including the "Critical Plan Issues" and "General Notes" sections at the top**

The validation guide documents bugs in the implementation plan. Where the plan and the validation guide conflict, **the validation guide wins**. Do not implement code you know is wrong just because the plan says so.

### Step 2: Implement

Write the code and tests for the task. Follow the plan's structure but incorporate fixes for any critical issues that apply to this task. Use `uv` for all Python operations.

You may modify files from already-completed tasks when needed (e.g., fixing a bug in `workspace.py` while implementing `agent.py`). Update the corresponding tests if you change existing modules.

If the SDK's actual types, function signatures, or behavior differ from what the plan assumes, inspect the SDK directly (e.g., `inspect.signature()`, `help()`, `dir()`) and adapt your code. The plan's SDK code is illustrative, not authoritative.

Group related changes into logical commits with descriptive messages. Do not bundle unrelated changes.

### Step 3: Run the full test suite yourself

Before spawning the validation agent, run:
```bash
cd /home/apsv/source/toy/rlm && uv run pytest tests/ -v
```
If tests fail, fix them. Do not proceed to validation with failing tests.

### Step 4: Validate

**For Tasks 4–8:** Spawn a validation agent. Read the prompt from `docs/plans/validation-agent-prompt.md` (everything after the `---` line) and **append the line `Validate Task N.`** (replacing N with the actual task number). Launch it:

```
Task(
    subagent_type="general-purpose",
    description="Validate RLM task N",
    prompt=<validation prompt text> + "\n\nValidate Task N.",
)
```

Wait for the validation agent to return its report.

**For Tasks 9–10 (self-validated):** These are verification-only tasks. Do not spawn a validation agent. Run the checks listed in the validation guide yourself and report the results directly.

### Step 5: Handle the validation result

- **If verdict is PASS:** Commit (if not already committed), then proceed to the next task.
- **If verdict is FAIL:** Read the failure details. Fix the issues. Re-run tests. Spawn the validation agent again. Do not move to the next task until you get a PASS verdict.

### Step 6: Check context window budget

Before starting the next task, assess whether you are running low on context window. You are low if less than ~30% of your context remains (i.e., the conversation is long, you've done multiple implement/validate cycles, or you notice the system compressing earlier messages).

**If you have sufficient context remaining:** Go to Step 7.

**If you are running low:** Save your progress and stop.

1. Write a progress file to `/home/apsv/source/toy/rlm/docs/plans/progress-state.md` with this format:

```markdown
# RLM Implementation Progress

## Last completed task
Task N: <name> — PASS (commit <hash>)

## Next task to implement
Task M: <name>

## Notes for next session
- <any context the next agent needs: partial work, decisions made, gotchas encountered>
- <unresolved issues or deviations from the plan>
- <which critical issues (1-6) have been addressed so far and which remain>
```

2. Commit this file:
```bash
git add docs/plans/progress-state.md
git commit -m "chore: save implementation progress at task N"
```

3. Tell the user: "Context window is running low. Progress saved to `docs/plans/progress-state.md`. Start a new session with the same implementation agent prompt to continue."

4. Stop. Do not start the next task.

When starting a new session, always check for `/home/apsv/source/toy/rlm/docs/plans/progress-state.md` first. If it exists, read it to understand where the previous session left off and continue from the next incomplete task.

### Step 7: Repeat

Go back to Step 1 for the next task.

## Rules

- Never skip validation. Tasks 4–8 each get a validation agent pass. Tasks 9–10 are self-validated.
- You may batch Tasks 5 and 8 (CLI entrypoint and skill file) into a single implement/validate cycle if both are small and all their checks are offline (no API calls). For all other tasks, implement and validate one at a time.
- The validation agent is read-only. It will never fix your code. You fix, it checks.
- If the validation agent reports a FAIL on a critical issue, that means your implementation inherited a bug from the plan. Re-read the issue description in the validation guide and fix it.
- If you encounter a problem not covered by the plan or validation guide, flag it clearly in your output and make a reasonable decision. Do not block indefinitely.
- Integration tests (Tasks 6, 7) require `ANTHROPIC_API_KEY`. If it's not available, note this and proceed — the validation agent will mark those checks as SKIPPED rather than FAIL.
- Do not push to remote. Only local commits.
