# RLM Metadata Feature Requests — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured metadata files (`status.json`, `run.json`, `error.txt`) to the RLM workspace so that external tools (like the monitor TUI) can observe run state, costs, timestamps, and errors without guessing from file presence alone.

**Architecture:** Each feature request adds a small amount of JSON-writing logic at key phase transitions in `rlm/agent.py` and `rlm/main.py`. The workspace module gains helper methods for writing status. All changes are additive — existing behavior is preserved, the agent loop just writes extra files alongside the existing `context.txt`, `subcalls.json`, and `answer.txt`.

**Tech Stack:** Python, existing `rlm` package, `claude_agent_sdk` (provides `ResultMessage` with `usage` dict and `total_cost_usd`).

---

## Feature Request Evaluation

| FR | Title | Verdict | Rationale |
|----|-------|---------|-----------|
| FR-1 | `status.json` per node | **Implement** | Core observability primitive. 4 write-points in `rlm_call()`. |
| FR-2 | `run.json` manifest | **Implement** | Small change in `main.py`. Gives monitors run-level metadata without tree traversal. |
| FR-3 | Timestamps on phases | **Implement** | Folds into FR-1's `status.json` — add `started_at`/`completed_at` fields. |
| FR-4 | Per-node cost/token tracking | **Implement** | `ResultMessage.usage` provides `input_tokens`/`output_tokens`; `total_cost_usd` already extracted. Fold into `status.json`. |
| FR-5 | Error recording | **Implement** | Write `error.txt` at the two error branches in `rlm_call()`. Trivial. |
| FR-6 | Pending subcalls signal | **Skip** | Would require either (a) pre-creating child directories before dispatching, which conflicts with the collision-avoidance counter in `Workspace.create_node()` (`workspace.py:75-77`), or (b) writing a separate `pending_subcalls.json` that the monitor must reconcile with actual child directories. Both add complexity for marginal benefit — the monitor already handles missing directories gracefully by showing only what exists. The sequential dispatch loop means at most one child is "in flight" at a time, so the monitor can infer "N of M complete" from `subcalls.json` entry count vs. child directory count. |

---

## Task 1: Add `write_status` helper to `WorkspaceNode`

**Files:**
- Modify: `rlm/workspace.py:12-53`
- Test: `tests/test_workspace.py`

**Step 1: Write the failing test**

Add to `tests/test_workspace.py`:

```python
class TestNodeStatus:
    def test_write_status_creates_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test goal")
        status = json.loads((node.path / "status.json").read_text())
        assert status["state"] == "working"
        assert status["depth"] == 0
        assert status["call_index"] == 0
        assert status["goal"] == "test goal"
        assert "started_at" in status

    def test_write_status_preserves_existing_fields(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test")
        node.write_status(state="decomposed")
        status = json.loads((node.path / "status.json").read_text())
        assert status["state"] == "decomposed"
        assert status["goal"] == "test"  # preserved from first write

    def test_write_status_with_cost(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(
            state="solved",
            depth=0,
            call_index=0,
            goal="test",
            cost_usd=0.0042,
            input_tokens=1200,
            output_tokens=450,
        )
        status = json.loads((node.path / "status.json").read_text())
        assert status["cost_usd"] == 0.0042
        assert status["input_tokens"] == 1200
        assert status["output_tokens"] == 450

    def test_read_status_missing_returns_empty_dict(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.read_status() == {}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py::TestNodeStatus -v`
Expected: FAIL — `write_status` not defined on `WorkspaceNode`

**Step 3: Implement `write_status` and `read_status` on `WorkspaceNode`**

In `rlm/workspace.py`, add to `WorkspaceNode` (after line 32):

```python
    @property
    def status_path(self) -> Path:
        return self.path / "status.json"

    def read_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {}
        try:
            return json.loads(self.status_path.read_text())
        except json.JSONDecodeError:
            return {}

    def write_status(self, **fields: Any) -> None:
        """Merge fields into status.json (creates if missing).

        Common fields: state, depth, call_index, goal, started_at,
        completed_at, cost_usd, input_tokens, output_tokens, error.
        """
        from datetime import datetime, timezone

        existing = self.read_status()
        # Auto-set started_at on first write
        if not existing and "started_at" not in fields:
            fields["started_at"] = datetime.now(timezone.utc).isoformat()
        existing.update(fields)
        self.status_path.write_text(json.dumps(existing, indent=2))
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py -v`
Expected: PASS (all existing + new tests)

**Step 5: Commit**

```
git add rlm/workspace.py tests/test_workspace.py
git commit -m "feat(workspace): add write_status/read_status to WorkspaceNode"
```

---

## Task 2: Write `status.json` at phase transitions in `rlm_call()`

**Files:**
- Modify: `rlm/agent.py:53-96` (change `run_agent_phase` return type)
- Modify: `rlm/agent.py:99-232` (add status writes in `rlm_call`)
- Test: `tests/test_agent.py`

This is the core change. We modify `run_agent_phase` to also return usage info, then write `status.json` at each phase transition in `rlm_call()`.

**Step 1: Write the failing test**

Add to `tests/test_agent.py`:

```python
import json
from pathlib import Path
from rlm.workspace import Workspace


class TestStatusWriting:
    """Test that rlm_call writes status.json at key points.

    These are workspace-level tests that verify status file contents
    after simulating what rlm_call would write. We don't call rlm_call
    directly (that requires a running agent) — we test the write_status
    integration with the workspace.
    """

    def test_initial_status_on_node_creation(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test goal")
        status = node.read_status()
        assert status["state"] == "working"
        assert "started_at" in status

    def test_status_transitions(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        # working -> decomposed -> synthesized
        node.write_status(state="working", depth=0, call_index=0, goal="test")
        node.write_status(state="decomposed")
        assert node.read_status()["state"] == "decomposed"
        node.write_status(state="synthesized", completed_at="2026-02-21T00:00:00Z")
        status = node.read_status()
        assert status["state"] == "synthesized"
        assert status["completed_at"] == "2026-02-21T00:00:00Z"
```

**Step 2: Run test to verify it passes (uses Task 1's implementation)**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_agent.py::TestStatusWriting -v`
Expected: PASS (this validates the write_status contract)

**Step 3: Change `run_agent_phase` to return usage info**

In `rlm/agent.py`, change the return type and capture usage:

Replace `run_agent_phase` (lines 53-96) — change signature to return a dataclass instead of tuple:

```python
@dataclass
class PhaseResult:
    """Result from a single agent phase."""
    text: str | None
    cost_usd: float
    input_tokens: int
    output_tokens: int
```

Then update `run_agent_phase` to return `PhaseResult`:
- Capture `message.usage` from `ResultMessage` (the `usage` dict has `input_tokens` and `output_tokens` keys)
- Return `PhaseResult(text=last_text, cost_usd=cost, input_tokens=..., output_tokens=...)`

**Step 4: Add status writes to `rlm_call()`**

The 5 write-points in `rlm_call()` (lines 99-232):

1. **After node creation** (after line 127): Write initial status
   ```python
   node.write_status(state="working", depth=depth, call_index=call_index, goal=effective_goal)
   ```

2. **After decompose phase** (after line 151): Update with cost + state
   ```python
   node.write_status(
       cost_usd=phase.cost_usd,
       input_tokens=phase.input_tokens,
       output_tokens=phase.output_tokens,
   )
   ```

3. **On direct solve** (before the return at line 156): Mark solved
   ```python
   node.write_status(state="solved", completed_at=datetime.now(timezone.utc).isoformat())
   ```

4. **On decompose** (after reading subcalls at line 164): Mark decomposed
   ```python
   if subcalls:
       node.write_status(state="decomposed")
   ```

5. **After synthesis** (after line 221): Mark synthesized or error
   ```python
   if answer is not None:
       node.write_status(
           state="synthesized",
           completed_at=datetime.now(timezone.utc).isoformat(),
           cost_usd=node.read_status().get("cost_usd", 0) + synth_phase.cost_usd,
           input_tokens=node.read_status().get("input_tokens", 0) + synth_phase.input_tokens,
           output_tokens=node.read_status().get("output_tokens", 0) + synth_phase.output_tokens,
       )
   ```

**Step 5: Update all callers of `run_agent_phase` to use `PhaseResult`**

In `rlm_call()`, replace:
- `_, cost = await run_agent_phase(...)` → `phase = await run_agent_phase(...)`
- `total_cost += cost` → `total_cost += phase.cost_usd`
- Same for the synthesis call

**Step 6: Run all tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest -v`
Expected: PASS

**Step 7: Commit**

```
git add rlm/agent.py tests/test_agent.py
git commit -m "feat(agent): write status.json at phase transitions with cost/token tracking"
```

---

## Task 3: Write `error.txt` on error branches (FR-5)

**Files:**
- Modify: `rlm/agent.py:165-171, 224-225`
- Modify: `rlm/workspace.py` (add `write_error` helper)
- Test: `tests/test_workspace.py`

**Step 1: Write the failing test**

Add to `tests/test_workspace.py`:

```python
class TestNodeError:
    def test_write_error_creates_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_error("Agent produced neither answer.txt nor subcalls.json")
        assert (node.path / "error.txt").read_text() == "Agent produced neither answer.txt nor subcalls.json"

    def test_write_error_updates_status(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test")
        node.write_error("something broke")
        status = node.read_status()
        assert status["state"] == "error"
        assert "completed_at" in status
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py::TestNodeError -v`
Expected: FAIL — `write_error` not defined

**Step 3: Implement `write_error` on `WorkspaceNode`**

In `rlm/workspace.py`, add to `WorkspaceNode`:

```python
    @property
    def error_path(self) -> Path:
        return self.path / "error.txt"

    def write_error(self, message: str) -> None:
        """Write error.txt and update status.json to error state."""
        from datetime import datetime, timezone

        self.error_path.write_text(message)
        self.write_status(state="error", completed_at=datetime.now(timezone.utc).isoformat())
```

**Step 4: Run tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py -v`
Expected: PASS

**Step 5: Add error writes to `rlm_call()` error branches**

In `rlm/agent.py`, at the two error branches:

1. Line 165-171 (no answer, no subcalls):
   ```python
   if not subcalls:
       error_msg = "Agent produced neither answer.txt nor subcalls.json"
       node.write_error(error_msg)
       return RLMResult(
           answer=f"[RLM Error: {error_msg}]",
           ...
       )
   ```

2. Line 224-225 (synthesis didn't write answer):
   ```python
   if answer is None:
       error_msg = "Synthesis agent did not write answer.txt"
       node.write_error(error_msg)
       answer = f"[RLM Error: {error_msg}]"
   ```

**Step 6: Run all tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest -v`
Expected: PASS

**Step 7: Commit**

```
git add rlm/workspace.py rlm/agent.py tests/test_workspace.py
git commit -m "feat(agent): write error.txt on failure branches"
```

---

## Task 4: Write `run.json` manifest at workspace root (FR-2)

**Files:**
- Modify: `rlm/main.py:45-68`
- Modify: `rlm/workspace.py` (add `write_run_manifest` to `Workspace`)
- Test: `tests/test_workspace.py`

**Step 1: Write the failing test**

Add to `tests/test_workspace.py`:

```python
class TestRunManifest:
    def test_write_run_manifest(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        ws.write_run_manifest(
            goal="Summarize the document",
            model="claude-sonnet-4-6",
            max_depth=3,
            status="running",
        )
        manifest = json.loads((tmp_path / "rlm_ws" / "run.json").read_text())
        assert manifest["goal"] == "Summarize the document"
        assert manifest["model"] == "claude-sonnet-4-6"
        assert manifest["max_depth"] == 3
        assert manifest["status"] == "running"
        assert "started_at" in manifest
        assert manifest["workspace"] == str(tmp_path / "rlm_ws")

    def test_update_run_manifest(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        ws.write_run_manifest(goal="test", model="m", max_depth=1, status="running")
        ws.update_run_manifest(status="completed", total_cost_usd=0.05, total_calls=3)
        manifest = json.loads((tmp_path / "rlm_ws" / "run.json").read_text())
        assert manifest["status"] == "completed"
        assert manifest["total_cost_usd"] == 0.05
        assert manifest["total_calls"] == 3
        assert "completed_at" in manifest
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py::TestRunManifest -v`
Expected: FAIL — `write_run_manifest` not defined

**Step 3: Implement on `Workspace`**

In `rlm/workspace.py`, add to `Workspace` class:

```python
    def write_run_manifest(self, goal: str, model: str, max_depth: int, status: str) -> None:
        """Write run.json at workspace root."""
        from datetime import datetime, timezone

        self.root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "goal": goal,
            "model": model,
            "max_depth": max_depth,
            "status": status,
            "workspace": str(self.root),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.root / "run.json").write_text(json.dumps(manifest, indent=2))

    def update_run_manifest(self, **fields: Any) -> None:
        """Merge fields into existing run.json."""
        from datetime import datetime, timezone

        manifest_path = self.root / "run.json"
        existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        if "status" in fields and fields["status"] in ("completed", "error"):
            fields.setdefault("completed_at", datetime.now(timezone.utc).isoformat())
        existing.update(fields)
        manifest_path.write_text(json.dumps(existing, indent=2))
```

**Step 4: Run tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest tests/test_workspace.py -v`
Expected: PASS

**Step 5: Wire into `main.py`**

In `rlm/main.py`, add two calls:

1. After workspace creation (after line 48):
   ```python
   workspace.write_run_manifest(
       goal=goal, model=model, max_depth=max_depth, status="running",
   )
   ```

2. After `rlm_call` returns (after line 60, before printing):
   ```python
   workspace.update_run_manifest(
       status="completed",
       total_cost_usd=result.total_cost_usd,
       total_calls=result.total_calls,
   )
   ```

**Step 6: Run all tests**

Run: `cd /home/apsv/source/toy/rlm && uv run pytest -v`
Expected: PASS

**Step 7: Commit**

```
git add rlm/workspace.py rlm/main.py tests/test_workspace.py
git commit -m "feat(main): write run.json manifest at workspace root"
```

---

## Task 5: Update monitor TUI to read new metadata files

**Files:**
- Modify: `monitor/workspace.go`
- Modify: `monitor/workspace_test.go`

This is optional follow-up work for the Go monitor. The monitor currently infers state from file presence. After FR-1 ships, it can prefer `status.json` when present and fall back to file-presence inference.

**Step 1: Add `StatusJSON` field to `Node` struct and parse it in `buildNode`**

In `monitor/workspace.go`, add to `Node`:
```go
StatusJSON map[string]interface{} // parsed status.json, nil if absent
```

In `buildNode`, after scanning vars, try to read `status.json`:
```go
if data, err := os.ReadFile(filepath.Join(path, "status.json")); err == nil {
    var status map[string]interface{}
    if json.Unmarshal(data, &status) == nil {
        node.StatusJSON = status
        // Prefer status.json state over file-presence inference
        if stateStr, ok := status["state"].(string); ok {
            switch stateStr {
            case "working":
                node.State = StateWorking
            case "decomposed":
                node.State = StateDecomposed
            case "solved":
                node.State = StateSolved
            case "synthesized":
                node.State = StateSynthesized
            case "error":
                node.State = StateError // new state constant
            }
        }
    }
}
```

**Step 2: Add `StateError` constant**

```go
const (
    StateWorking     NodeState = iota
    StateDecomposed
    StateSolved
    StateSynthesized
    StateError
)
```

Update `String()` method to handle `StateError` → `"Error"`.

**Step 3: Add test for status.json parsing**

**Step 4: Run tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v`
Expected: PASS

**Step 5: Commit**

```
git add monitor/
git commit -m "feat(monitor): read status.json for richer node state"
```
