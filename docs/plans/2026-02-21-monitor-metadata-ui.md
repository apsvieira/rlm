# Monitor Metadata UI Improvements — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. **IMPORTANT: Execute ALL tasks in a single pass without stopping for feedback between batches.** Run all 4 tasks sequentially, committing after each. Only stop if tests fail or you hit a blocker.

**Goal:** Update the monitor TUI to display the new metadata (`status.json`, `run.json`, `error.txt`) that the RLM agent now writes, closing all rendering gaps left after the metadata feature landed.

**Architecture:** All changes are in the Go monitor (`monitor/`). The workspace scanner already parses `status.json` into `Node.StatusJSON` and sets `StateError` — these tasks wire that data through to the view layer. A new `RunManifest` struct is added for `run.json`. Each task touches `workspace.go` (data), `model.go` (rendering), and their test files.

**Tech Stack:** Go, Bubble Tea (`bubbletea`), Lip Gloss (`lipgloss`), existing `monitor/` package.

---

## Gap Summary

| # | Gap | Root Cause |
|---|-----|-----------|
| 1 | `StateError` renders as blank in tree view | No `case StateError:` in `renderTree()` switch |
| 2 | Error count missing from stats bar | `Errors` field exists in `WorkspaceStats` but not displayed |
| 3 | No way to view `error.txt` in detail pane | No `[e]` keybinding |
| 4 | No run-level header (model, goal, total cost) | `run.json` not read by monitor |
| 5 | No per-node cost/tokens shown | `StatusJSON` parsed but cost fields not displayed |
| 6 | No elapsed time shown | `started_at`/`completed_at` parsed but not rendered |
| 7 | Root node shows no goal | Goal comes from parent's `subcalls.json`; root has no parent. `status.json` has the goal but isn't used as fallback |

---

## Task 1: Error state rendering and `[e]` keybinding

**Files:**
- Modify: `monitor/model.go:17-28` (add error style)
- Modify: `monitor/model.go:200-211` (add `StateError` case in `renderTree`)
- Modify: `monitor/model.go:160-166` (show error count in stats bar)
- Modify: `monitor/model.go:106-117` (add `[e]` keybinding)
- Modify: `monitor/model.go:185-186` (add `[e]` to help footer)
- Test: `monitor/workspace_test.go`
- Test: `monitor/smoke_test.go`

**Step 1: Write the failing test**

Add to `monitor/smoke_test.go`, a new test function that creates a workspace with an error node and verifies the rendered output:

```go
func TestSmokeErrorState(t *testing.T) {
	root := t.TempDir()

	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "status.json"), []byte(`{"state":"error","goal":"test goal"}`), 0o644)
	os.WriteFile(filepath.Join(d0c0, "error.txt"), []byte("Agent produced neither answer.txt nor subcalls.json"), 0o644)

	m := initialModel(root)
	m.width = 80
	m.height = 24

	view := m.View()

	// Error state should render with icon and label
	if !strings.Contains(view, "ERROR") {
		t.Error("missing ERROR state label in tree view")
	}

	// Stats bar should show error count
	if !strings.Contains(view, "1 error") {
		t.Errorf("stats bar should show error count, got: %s", view)
	}

	// Detail view should support [e] for error.txt
	m.showDetail = true
	m.loadDetail("error.txt")
	detailView := m.View()
	if !strings.Contains(detailView, "Agent produced neither") {
		t.Error("detail view should show error.txt content")
	}
	if !strings.Contains(detailView, "[e] error") {
		t.Error("detail help should mention [e] error keybinding")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -run TestSmokeErrorState -v`
Expected: FAIL — "ERROR" not found in tree view (renders as blank)

**Step 3: Implement the changes**

In `monitor/model.go`:

1. Add error style (after `synthStyle` on line 24):
```go
	errorStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("196"))  // red
```

2. Add `StateError` case in `renderTree()` (after line 210, the `StateSynthesized` case):
```go
	case StateError:
		stateStr = errorStyle.Render("✗ ERROR")
```

3. Update stats bar (line 161-166) to include error count:
```go
	active := m.stats.Working + m.stats.Decomposed
	done := m.stats.Solved + m.stats.Synthesized
	statsLine := fmt.Sprintf(
		"Nodes: %d total | %d active | %d done | max depth: %d",
		m.stats.TotalNodes, active, done, m.stats.MaxDepth,
	)
	if m.stats.Errors > 0 {
		statsLine += fmt.Sprintf(" | %d error", m.stats.Errors)
		if m.stats.Errors > 1 {
			statsLine += "s"
		}
	}
```

4. Add `[e]` keybinding (after the `"s"` case on line 114-117):
```go
	case "e":
		if m.showDetail && len(m.flat) > 0 {
			m.loadDetail("error.txt")
		}
```

5. Update detail help footer (line 186):
```go
	b.WriteString(helpStyle.Render("[esc] back  [c] context  [a] answer  [s] subcalls  [e] error  [q] quit"))
```

**Step 4: Run tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v`
Expected: PASS (all existing + new tests)

**Step 5: Commit**

```
git add monitor/model.go monitor/smoke_test.go
git commit -m "feat(monitor): render error state with style, stats count, and [e] keybinding"
```

---

## Task 2: Read `run.json` and display run-level header

**Files:**
- Modify: `monitor/workspace.go` (add `RunManifest` struct and `ReadRunManifest` function)
- Modify: `monitor/model.go:38-50` (add `manifest` field to model)
- Modify: `monitor/model.go:58-71` (read manifest in `refresh()`)
- Modify: `monitor/model.go:154-170` (render manifest in header)
- Test: `monitor/workspace_test.go`
- Test: `monitor/smoke_test.go`

**Step 1: Write the failing test**

Add to `monitor/workspace_test.go`:

```go
func TestReadRunManifest(t *testing.T) {
	root := t.TempDir()
	manifestJSON := `{
		"goal": "Summarize the document",
		"model": "claude-sonnet-4-6",
		"max_depth": 3,
		"status": "running",
		"workspace": "/tmp/ws",
		"started_at": "2026-02-21T12:00:00Z"
	}`
	os.WriteFile(filepath.Join(root, "run.json"), []byte(manifestJSON), 0o644)

	manifest := ReadRunManifest(root)
	if manifest == nil {
		t.Fatal("expected manifest, got nil")
	}
	if manifest.Goal != "Summarize the document" {
		t.Errorf("goal=%q, want 'Summarize the document'", manifest.Goal)
	}
	if manifest.Model != "claude-sonnet-4-6" {
		t.Errorf("model=%q, want 'claude-sonnet-4-6'", manifest.Model)
	}
	if manifest.Status != "running" {
		t.Errorf("status=%q, want 'running'", manifest.Status)
	}
	if manifest.MaxDepth != 3 {
		t.Errorf("max_depth=%d, want 3", manifest.MaxDepth)
	}
}

func TestReadRunManifestMissing(t *testing.T) {
	root := t.TempDir()
	manifest := ReadRunManifest(root)
	if manifest != nil {
		t.Error("expected nil for missing run.json")
	}
}

func TestReadRunManifestCompleted(t *testing.T) {
	root := t.TempDir()
	manifestJSON := `{
		"goal": "test",
		"model": "m",
		"max_depth": 1,
		"status": "completed",
		"total_cost_usd": 0.0523,
		"total_calls": 7,
		"started_at": "2026-02-21T12:00:00Z",
		"completed_at": "2026-02-21T12:05:00Z"
	}`
	os.WriteFile(filepath.Join(root, "run.json"), []byte(manifestJSON), 0o644)

	manifest := ReadRunManifest(root)
	if manifest.TotalCostUSD != 0.0523 {
		t.Errorf("total_cost_usd=%f, want 0.0523", manifest.TotalCostUSD)
	}
	if manifest.TotalCalls != 7 {
		t.Errorf("total_calls=%d, want 7", manifest.TotalCalls)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -run TestReadRunManifest -v`
Expected: FAIL — `ReadRunManifest` not defined

**Step 3: Implement `RunManifest` and `ReadRunManifest` in `workspace.go`**

Add after `WorkspaceStats` (after line 209):

```go
// RunManifest holds run-level metadata from run.json.
type RunManifest struct {
	Goal         string  `json:"goal"`
	Model        string  `json:"model"`
	MaxDepth     int     `json:"max_depth"`
	Status       string  `json:"status"`
	Workspace    string  `json:"workspace"`
	StartedAt    string  `json:"started_at"`
	CompletedAt  string  `json:"completed_at,omitempty"`
	TotalCostUSD float64 `json:"total_cost_usd,omitempty"`
	TotalCalls   int     `json:"total_calls,omitempty"`
}

// ReadRunManifest reads and parses run.json from the workspace root.
// Returns nil if the file doesn't exist or can't be parsed.
func ReadRunManifest(root string) *RunManifest {
	data, err := os.ReadFile(filepath.Join(root, "run.json"))
	if err != nil {
		return nil
	}
	var m RunManifest
	if json.Unmarshal(data, &m) != nil {
		return nil
	}
	return &m
}
```

**Step 4: Run workspace tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -run TestReadRunManifest -v`
Expected: PASS

**Step 5: Wire into model and header**

In `monitor/model.go`:

1. Add `manifest` field to model struct (after `err` on line 49):
```go
	manifest  *RunManifest
```

2. Read manifest in `refresh()` (after `m.err = nil` on line 70):
```go
	m.manifest = ReadRunManifest(m.workspacePath)
```

3. Update the header in `View()` to show manifest info. Replace lines 156-168 (the header + stats bar section):
```go
	// Header
	b.WriteString(titleStyle.Render(fmt.Sprintf("RLM Monitor — %s", m.workspacePath)))
	b.WriteString("\n")

	// Run manifest line (if run.json exists)
	if m.manifest != nil {
		modelShort := m.manifest.Model
		// Trim "claude-" prefix for brevity
		modelShort = strings.TrimPrefix(modelShort, "claude-")
		runLine := fmt.Sprintf("model: %s | max-depth: %d | status: %s",
			modelShort, m.manifest.MaxDepth, m.manifest.Status)
		if m.manifest.TotalCostUSD > 0 {
			runLine += fmt.Sprintf(" | cost: $%.4f", m.manifest.TotalCostUSD)
		}
		if m.manifest.TotalCalls > 0 {
			runLine += fmt.Sprintf(" | calls: %d", m.manifest.TotalCalls)
		}
		b.WriteString(dimStyle.Render(runLine))
		b.WriteString("\n")
	}

	// Stats bar
	active := m.stats.Working + m.stats.Decomposed
	done := m.stats.Solved + m.stats.Synthesized
	statsLine := fmt.Sprintf(
		"Nodes: %d total | %d active | %d done | max depth: %d",
		m.stats.TotalNodes, active, done, m.stats.MaxDepth,
	)
```

**Step 6: Write the smoke test for manifest header**

Add to `monitor/smoke_test.go`:

```go
func TestSmokeRunManifestHeader(t *testing.T) {
	root := setupSmokeWorkspace(t)

	// Write run.json
	os.WriteFile(filepath.Join(root, "run.json"), []byte(`{
		"goal": "Summarize the document",
		"model": "claude-sonnet-4-6",
		"max_depth": 3,
		"status": "running",
		"started_at": "2026-02-21T12:00:00Z"
	}`), 0o644)

	m := initialModel(root)
	m.width = 80
	m.height = 24

	view := m.View()
	if !strings.Contains(view, "sonnet-4-6") {
		t.Error("header should show model name")
	}
	if !strings.Contains(view, "max-depth: 3") {
		t.Error("header should show max depth")
	}
	if !strings.Contains(view, "status: running") {
		t.Error("header should show run status")
	}
}
```

**Step 7: Run all tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v`
Expected: PASS

**Step 8: Commit**

```
git add monitor/workspace.go monitor/workspace_test.go monitor/model.go monitor/smoke_test.go
git commit -m "feat(monitor): display run.json manifest in header"
```

---

## Task 3: Show per-node cost and elapsed time from `status.json`

**Files:**
- Modify: `monitor/workspace.go` (add helper to extract typed fields from `StatusJSON`)
- Modify: `monitor/model.go:213-217` (add cost to tree line)
- Modify: `monitor/model.go:247-269` (add cost/tokens/timing to detail view)
- Test: `monitor/workspace_test.go`
- Test: `monitor/smoke_test.go`

**Step 1: Write the failing test**

Add to `monitor/smoke_test.go`:

```go
func TestSmokeCostAndTiming(t *testing.T) {
	root := t.TempDir()

	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "answer.txt"), []byte("answer"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "status.json"), []byte(`{
		"state": "solved",
		"goal": "test goal",
		"cost_usd": 0.0042,
		"input_tokens": 1200,
		"output_tokens": 450,
		"started_at": "2026-02-21T12:00:00Z",
		"completed_at": "2026-02-21T12:00:30Z"
	}`), 0o644)

	m := initialModel(root)
	m.width = 100
	m.height = 24

	// Tree view should show cost
	view := m.View()
	if !strings.Contains(view, "$0.0042") {
		t.Errorf("tree should show cost, got: %s", view)
	}

	// Detail view should show cost, tokens, and timing
	m.showDetail = true
	m.loadDetail("answer.txt")
	detailView := m.View()
	if !strings.Contains(detailView, "$0.0042") {
		t.Error("detail should show cost")
	}
	if !strings.Contains(detailView, "1200") {
		t.Error("detail should show input tokens")
	}
	if !strings.Contains(detailView, "450") {
		t.Error("detail should show output tokens")
	}
	if !strings.Contains(detailView, "30s") {
		t.Error("detail should show elapsed time")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -run TestSmokeCostAndTiming -v`
Expected: FAIL — cost not shown in tree view

**Step 3: Add helpers to extract typed fields from `StatusJSON`**

Add to `monitor/workspace.go` (after `FormatSize` function):

```go
// statusFloat extracts a float64 from StatusJSON, returning 0 if absent.
func statusFloat(s map[string]interface{}, key string) float64 {
	if s == nil {
		return 0
	}
	if v, ok := s[key].(float64); ok {
		return v
	}
	return 0
}

// statusString extracts a string from StatusJSON, returning "" if absent.
func statusString(s map[string]interface{}, key string) string {
	if s == nil {
		return ""
	}
	if v, ok := s[key].(string); ok {
		return v
	}
	return ""
}

// FormatElapsed computes duration between two ISO timestamps and returns
// a human-readable string like "30s", "2m30s", "1h5m". Returns "" if
// either timestamp is missing or unparseable.
func FormatElapsed(startedAt, completedAt string) string {
	if startedAt == "" || completedAt == "" {
		return ""
	}
	start, err := time.Parse(time.RFC3339, startedAt)
	if err != nil {
		return ""
	}
	end, err := time.Parse(time.RFC3339, completedAt)
	if err != nil {
		return ""
	}
	d := end.Sub(start)
	if d < time.Minute {
		return fmt.Sprintf("%ds", int(d.Seconds()))
	}
	if d < time.Hour {
		return fmt.Sprintf("%dm%ds", int(d.Minutes()), int(d.Seconds())%60)
	}
	return fmt.Sprintf("%dh%dm", int(d.Hours()), int(d.Minutes())%60)
}
```

Note: add `"time"` to the imports in `workspace.go`.

**Step 4: Add cost to tree line in `renderTree()`**

In `monitor/model.go`, after the size info block (after line 217 `sizeInfo += ...`), add:

```go
		// Cost from status.json
		costInfo := ""
		if cost := statusFloat(node.StatusJSON, "cost_usd"); cost > 0 {
			costInfo = dimStyle.Render(fmt.Sprintf(" $%.4f", cost))
		}
```

Then update the line format (line 229) to include `costInfo`:
```go
		line := fmt.Sprintf(" %s%s  %s  %s%s%s", prefix, node.Name, stateStr, sizeInfo, costInfo, goalSnip)
```

**Step 5: Add cost/tokens/timing to detail view**

In `monitor/model.go`, in `renderDetail()`, after the Goal block (after line 269 `b.WriteString("\n")`), before the separator line:

```go
	// Cost, tokens, timing from status.json
	if node.StatusJSON != nil {
		var metaParts []string
		if cost := statusFloat(node.StatusJSON, "cost_usd"); cost > 0 {
			metaParts = append(metaParts, fmt.Sprintf("cost: $%.4f", cost))
		}
		inTok := statusFloat(node.StatusJSON, "input_tokens")
		outTok := statusFloat(node.StatusJSON, "output_tokens")
		if inTok > 0 || outTok > 0 {
			metaParts = append(metaParts, fmt.Sprintf("tokens: %d in / %d out", int(inTok), int(outTok)))
		}
		elapsed := FormatElapsed(
			statusString(node.StatusJSON, "started_at"),
			statusString(node.StatusJSON, "completed_at"),
		)
		if elapsed != "" {
			metaParts = append(metaParts, fmt.Sprintf("elapsed: %s", elapsed))
		}
		if len(metaParts) > 0 {
			b.WriteString(dimStyle.Render(strings.Join(metaParts, " | ")))
			b.WriteString("\n")
		}
	}
```

**Step 6: Run all tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v`
Expected: PASS

**Step 7: Commit**

```
git add monitor/workspace.go monitor/model.go monitor/smoke_test.go
git commit -m "feat(monitor): show per-node cost, tokens, and elapsed time"
```

---

## Task 4: Fall back to `status.json` goal for root node

**Files:**
- Modify: `monitor/workspace.go:186-194` (add goal fallback in `buildNode`)
- Test: `monitor/workspace_test.go`

The root node (d0_c0) has no parent, so its `Goal` field is always empty — `subcalls.json`-based goal assignment only works for children. Now that `status.json` contains the goal, we can use it as a fallback.

**Step 1: Write the failing test**

Add to `monitor/workspace_test.go`:

```go
func TestGoalFromStatusJSON(t *testing.T) {
	root := t.TempDir()

	// Root node with no parent — goal should come from status.json
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "status.json"), []byte(`{"state":"working","goal":"Summarize the document"}`), 0o644)

	tree, err := ScanWorkspace(root)
	if err != nil {
		t.Fatalf("ScanWorkspace: %v", err)
	}
	if len(tree) != 1 {
		t.Fatalf("expected 1 node, got %d", len(tree))
	}
	if tree[0].Goal != "Summarize the document" {
		t.Errorf("goal=%q, want 'Summarize the document'", tree[0].Goal)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -run TestGoalFromStatusJSON -v`
Expected: FAIL — `goal=""`, want `"Summarize the document"`

**Step 3: Add goal fallback in `buildNode`**

In `monitor/workspace.go`, in the `buildNode` function, after the status.json parsing block (after line 173, the closing `}`), add:

```go
	// Use status.json goal as fallback when no parent assigns one
	if node.Goal == "" {
		if g := statusString(node.StatusJSON, "goal"); g != "" {
			node.Goal = g
		}
	}
```

Note: The parent-assigned goal (from `subcalls.json`) happens after `buildNode` returns (line 190-194), so this fallback will be overwritten by the parent goal when available. However, for the root node which has no parent, this provides the goal. To ensure the fallback isn't overwritten, we need the parent goal assignment to only set when non-empty, which it already does (it indexes into `SubcallsRaw` by `CallIndex`).

Wait — actually the parent assignment at line 190-194 happens unconditionally if `child.CallIndex < len(node.SubcallsRaw)`. It will overwrite the status.json goal with the subcalls.json goal. For child nodes that's correct (subcalls.json is authoritative). For the root node, no parent exists, so the fallback stands. This is the correct behavior.

**Step 4: Run all tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v`
Expected: PASS

**Step 5: Commit**

```
git add monitor/workspace.go monitor/workspace_test.go
git commit -m "feat(monitor): fall back to status.json goal for root node"
```
