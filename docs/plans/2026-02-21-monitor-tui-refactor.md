# Monitor TUI Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix line wrapping, add scrollable detail pane, fix truncation message bug, and show live token counts from events.

**Architecture:** Replace the manual string-truncation detail pane with `charmbracelet/bubbles/viewport` for scrolling. Wrap long lines before setting viewport content. Aggregate token counts from `events.jsonl` result entries for live display in the tree view. The viewport handles up/down/pgup/pgdown natively; we just feed it wrapped content.

**Tech Stack:** Go, Bubble Tea, Lip Gloss, `charmbracelet/bubbles` (viewport component)

---

### Task 1: Fix the "0 more lines" truncation bug

The current code on `model.go:360-365` slices `lines` before computing the remainder count, so it always shows 0:

```go
// BUG: len(lines) is maxLines after slicing, so difference is always 0
lines = lines[:maxLines]
lines = append(lines, fmt.Sprintf("... (%d more lines)", len(lines)-maxLines))
```

**Files:**
- Modify: `monitor/model.go:359-365`
- Test: `monitor/smoke_test.go`

**Step 1: Write the failing test**

Add to `smoke_test.go`:

```go
func TestTruncationMessageShowsCorrectCount(t *testing.T) {
	root := t.TempDir()

	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte(strings.Repeat("line\n", 100)), 0o644)

	m := initialModel(root)
	m.width = 80
	m.height = 24 // maxLines = max(24-12, 5) = 12
	m.showDetail = true
	m.loadDetail("context.txt")

	view := m.View()
	// Should show 88 more lines (100 - 12), NOT "0 more lines"
	if strings.Contains(view, "(0 more lines)") {
		t.Error("truncation message should not show 0 more lines")
	}
	if !strings.Contains(view, "more lines)") {
		t.Error("should show truncation message for long content")
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd monitor && go test -run TestTruncationMessageShowsCorrectCount -v`
Expected: FAIL — view contains "(0 more lines)"

**Step 3: Fix the bug**

In `model.go`, replace lines 359-365:

```go
	// Truncate content to fit screen
	lines := strings.Split(m.detailContent, "\n")
	maxLines := max(m.height-12, 5)
	if len(lines) > maxLines {
		total := len(lines)
		lines = lines[:maxLines]
		lines = append(lines, dimStyle.Render(fmt.Sprintf("... (%d more lines)", total-maxLines)))
	}
```

**Step 4: Run test to verify it passes**

Run: `cd monitor && go test -run TestTruncationMessageShowsCorrectCount -v`
Expected: PASS

**Step 5: Commit**

```bash
git add monitor/model.go monitor/smoke_test.go
git commit -m "fix(monitor): correct truncation message line count"
```

---

### Task 2: Add `charmbracelet/bubbles` dependency

**Files:**
- Modify: `monitor/go.mod`

**Step 1: Add the dependency**

Run: `cd monitor && go get github.com/charmbracelet/bubbles`

**Step 2: Verify the dependency resolves**

Run: `cd monitor && go mod tidy`

**Step 3: Commit**

```bash
git add monitor/go.mod monitor/go.sum
git commit -m "chore(monitor): add charmbracelet/bubbles dependency"
```

---

### Task 3: Replace detail pane with viewport + line wrapping

Replace the manual truncation in `renderDetail()` with a `viewport.Model` that supports scrolling. Wrap lines to terminal width before setting viewport content.

**Files:**
- Modify: `monitor/model.go`
- Test: `monitor/smoke_test.go`

**Step 1: Write failing tests for scrolling and wrapping**

Add to `smoke_test.go`:

```go
func TestDetailViewScrollDown(t *testing.T) {
	root := t.TempDir()
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	// Create content with numbered lines for easy verification
	var lines []string
	for i := 1; i <= 100; i++ {
		lines = append(lines, fmt.Sprintf("line %d content", i))
	}
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte(strings.Join(lines, "\n")), 0o644)

	m := initialModel(root)
	m.width = 80
	m.height = 24
	m.showDetail = true
	m.loadDetail("context.txt")

	// Initial view should show line 1
	view := m.View()
	if !strings.Contains(view, "line 1 content") {
		t.Error("initial detail view should show first line")
	}

	// Simulate scrolling down
	updated, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = updated.(model)
	// After scrolling, view should still be renderable (no panic)
	view = m.View()
	if view == "" {
		t.Error("view should not be empty after scrolling")
	}
}

func TestDetailViewWrapsLongLines(t *testing.T) {
	root := t.TempDir()
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	// Create a single very long line (200 chars)
	longLine := strings.Repeat("word ", 40) // 200 chars
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte(longLine), 0o644)

	m := initialModel(root)
	m.width = 60
	m.height = 24
	m.showDetail = true
	m.loadDetail("context.txt")

	view := m.View()
	// The view should contain the content (it was previously clipped)
	if !strings.Contains(view, "word") {
		t.Error("wrapped content should contain the text")
	}
	// No single rendered line should exceed terminal width
	// (This is approximate since ANSI codes add invisible chars)
}
```

**Step 2: Run tests to verify they fail**

Run: `cd monitor && go test -run "TestDetailViewScroll|TestDetailViewWraps" -v`
Expected: FAIL (scrolling not implemented, or panics)

**Step 3: Implement viewport + wrapping**

Update `model.go`:

1. Add imports:
```go
import (
	"github.com/charmbracelet/bubbles/viewport"
)
```

2. Add viewport field and scroll state to `model`:
```go
type model struct {
	// ... existing fields ...
	viewport      viewport.Model
	viewportReady bool
}
```

3. Add a `wrapText` helper function:
```go
// wrapText hard-wraps text to fit within the given width.
func wrapText(text string, width int) string {
	if width <= 0 {
		return text
	}
	var result strings.Builder
	for _, line := range strings.Split(text, "\n") {
		for len(line) > width {
			result.WriteString(line[:width])
			result.WriteByte('\n')
			line = line[width:]
		}
		result.WriteString(line)
		result.WriteByte('\n')
	}
	// Remove trailing newline added by loop
	s := result.String()
	if len(s) > 0 && s[len(s)-1] == '\n' {
		s = s[:len(s)-1]
	}
	return s
}
```

4. Update `loadDetail` and `loadEventLog` to set viewport content:
```go
func (m *model) loadDetail(filename string) {
	if m.cursor >= len(m.flat) {
		return
	}
	node := m.flat[m.cursor]
	path := filepath.Join(node.Path, filename)
	data, err := os.ReadFile(path)
	if err != nil {
		m.detailContent = fmt.Sprintf("(no %s)", filename)
	} else {
		m.detailContent = string(data)
	}
	m.detailFile = filename
	m.syncViewport()
}

func (m *model) loadEventLog() {
	if m.cursor >= len(m.flat) {
		return
	}
	node := m.flat[m.cursor]
	if len(node.Events) == 0 {
		m.detailContent = "(no events)"
	} else {
		m.detailContent = FormatEventLog(node.Events)
	}
	m.detailFile = "events.jsonl"
	m.syncViewport()
}

func (m *model) syncViewport() {
	contentWidth := min(m.width, 72)
	wrapped := wrapText(m.detailContent, contentWidth)
	m.viewport.SetContent(wrapped)
	m.viewport.GotoTop()
}
```

5. Update `Update()` to forward keys to viewport in detail mode and initialize viewport on WindowSizeMsg:
```go
case tea.WindowSizeMsg:
	m.width = msg.Width
	m.height = msg.Height
	headerHeight := 8 // header + stats + separator + detail header lines
	footerHeight := 2 // help line + blank
	viewportHeight := max(m.height-headerHeight-footerHeight, 5)
	if !m.viewportReady {
		m.viewport = viewport.New(min(m.width, 72), viewportHeight)
		m.viewportReady = true
	} else {
		m.viewport.Width = min(m.width, 72)
		m.viewport.Height = viewportHeight
	}
```

For key handling in detail mode, replace the `break` statements for up/down in showDetail:
```go
case "up", "k":
	if m.showDetail {
		m.viewport, _ = m.viewport.Update(msg)
		break
	}
	// ... existing tree nav
case "down", "j":
	if m.showDetail {
		m.viewport, _ = m.viewport.Update(msg)
		break
	}
	// ... existing tree nav
```

Also forward page up/page down/home/end to viewport:
```go
case "pgup", "pgdown", "home", "end":
	if m.showDetail {
		m.viewport, _ = m.viewport.Update(msg)
	}
```

6. Update `renderDetail()` to use viewport instead of manual truncation:

Replace the truncation block (lines 359-367) with:
```go
	// Scrollable content via viewport
	b.WriteString(m.viewport.View())
	b.WriteString("\n")

	// Scroll position indicator
	pct := m.viewport.ScrollPercent()
	scrollInfo := fmt.Sprintf(" %d%% ", int(pct*100))
	b.WriteString(dimStyle.Render(scrollInfo))
	b.WriteString("\n")
```

**Step 4: Run tests to verify they pass**

Run: `cd monitor && go test -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add monitor/model.go monitor/smoke_test.go
git commit -m "feat(monitor): add viewport scrolling and line wrapping to detail pane"
```

---

### Task 4: Update help footer to show scroll keybindings

**Files:**
- Modify: `monitor/model.go`

**Step 1: Update the detail help text**

Change the detail footer in `View()` from:
```go
b.WriteString(helpStyle.Render("[esc] back  [c] context  [a] answer  [s] subcalls  [e] error  [l] log  [q] quit"))
```
to:
```go
b.WriteString(helpStyle.Render("[↑/↓] scroll  [esc] back  [c] context  [a] answer  [s] subcalls  [e] error  [l] log  [q] quit"))
```

**Step 2: Update the existing test assertion**

In `smoke_test.go`, `TestSmokeRender` checks for `[esc] back` which still holds. No test changes needed unless the existing test breaks.

**Step 3: Run tests**

Run: `cd monitor && go test -v`
Expected: PASS

**Step 4: Commit**

```bash
git add monitor/model.go
git commit -m "feat(monitor): show scroll keybindings in detail help footer"
```

---

### Task 5: Add live token count from events in tree view

Currently the tree shows cost from `status.json`. But `status.json` is only updated at the end of a phase. For working nodes, we should show a live running total from `events.jsonl` result entries.

**Files:**
- Modify: `monitor/workspace.go` — add `LiveTokens` helper
- Modify: `monitor/model.go` — display live tokens in tree
- Test: `monitor/workspace_test.go` — test the aggregation

**Step 1: Write failing test for LiveTokens**

Add to `workspace_test.go`:

```go
func TestLiveTokens(t *testing.T) {
	node := &Node{
		Events: []EventEntry{
			{Type: "result", InputTokens: 500, OutputTokens: 100, CostUSD: 0.001},
			{Type: "tool_use", Name: "Read"},
			{Type: "result", InputTokens: 800, OutputTokens: 200, CostUSD: 0.002},
		},
	}
	inTok, outTok, cost := LiveTokens(node)
	if inTok != 1300 {
		t.Errorf("input_tokens=%d, want 1300", inTok)
	}
	if outTok != 300 {
		t.Errorf("output_tokens=%d, want 300", outTok)
	}
	if cost < 0.002 || cost > 0.004 {
		t.Errorf("cost=%f, want ~0.003", cost)
	}
}

func TestLiveTokensEmpty(t *testing.T) {
	node := &Node{}
	inTok, outTok, cost := LiveTokens(node)
	if inTok != 0 || outTok != 0 || cost != 0 {
		t.Errorf("expected all zeros for empty node, got %d/%d/%.4f", inTok, outTok, cost)
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd monitor && go test -run TestLiveTokens -v`
Expected: FAIL — `LiveTokens` undefined

**Step 3: Implement `LiveTokens` in workspace.go**

```go
// LiveTokens aggregates token counts and cost from all result events.
// This provides a live running total even before status.json is finalized.
func LiveTokens(node *Node) (inputTokens, outputTokens int, costUSD float64) {
	for _, ev := range node.Events {
		if ev.Type == "result" {
			inputTokens += ev.InputTokens
			outputTokens += ev.OutputTokens
			costUSD += ev.CostUSD
		}
	}
	return
}
```

**Step 4: Run test to verify it passes**

Run: `cd monitor && go test -run TestLiveTokens -v`
Expected: PASS

**Step 5: Display live tokens in tree view**

In `model.go` `renderTree()`, update the token display logic. Replace the costInfo block:

```go
		// Cost + tokens: prefer live events data, fall back to status.json
		costInfo := ""
		tokenInfo := ""
		inTok, outTok, liveCost := LiveTokens(node)
		if inTok > 0 || outTok > 0 {
			costInfo = dimStyle.Render(fmt.Sprintf(" $%.4f", liveCost))
			tokenInfo = dimStyle.Render(fmt.Sprintf(" %s↑%s↓", FormatSize(inTok), FormatSize(outTok)))
		} else if cost := statusFloat(node.StatusJSON, "cost_usd"); cost > 0 {
			costInfo = dimStyle.Render(fmt.Sprintf(" $%.4f", cost))
		}
```

Update the line format to include `tokenInfo`:
```go
		line := fmt.Sprintf(" %s%s  %s  %s%s%s%s%s", prefix, node.Name, stateStr, sizeInfo, costInfo, tokenInfo, toolInfo, goalSnip)
```

**Step 6: Write a smoke test for live tokens in tree**

Add to `smoke_test.go`:

```go
func TestSmokeTreeShowsLiveTokens(t *testing.T) {
	root := t.TempDir()

	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)
	// Write events with result entries (simulating live API calls)
	events := `{"ts":"2026-02-21T12:00:00Z","type":"result","phase":"decompose","cost_usd":0.0010,"input_tokens":500,"output_tokens":100}
{"ts":"2026-02-21T12:00:01Z","type":"result","phase":"decompose","cost_usd":0.0020,"input_tokens":800,"output_tokens":200}
`
	os.WriteFile(filepath.Join(d0c0, "events.jsonl"), []byte(events), 0o644)

	m := initialModel(root)
	m.width = 120
	m.height = 24

	view := m.View()
	// Should show aggregated cost from events
	if !strings.Contains(view, "$0.0030") {
		t.Errorf("tree should show aggregated live cost, got: %s", view)
	}
	// Should show token arrows
	if !strings.Contains(view, "↑") || !strings.Contains(view, "↓") {
		t.Errorf("tree should show token arrows, got: %s", view)
	}
}
```

**Step 7: Run full test suite**

Run: `cd monitor && go test -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add monitor/workspace.go monitor/model.go monitor/workspace_test.go monitor/smoke_test.go
git commit -m "feat(monitor): show live token counts from events in tree view"
```

---

### Task 6: Final integration test and cleanup

**Step 1: Run full test suite**

Run: `cd monitor && go test -v`
Expected: All PASS

**Step 2: Manual verification**

If an RLM workspace exists, run the monitor to visually verify:
- Long lines wrap to terminal width
- Arrow keys scroll in detail view
- Scroll percentage indicator shows at bottom
- Live tokens display in tree for active nodes
- Truncation message (if viewport is disabled for some reason) shows correct count

**Step 3: Remove the truncation test from Task 1**

The truncation test from Task 1 (`TestTruncationMessageShowsCorrectCount`) may no longer be relevant since we replaced truncation with viewport scrolling. Remove it if it no longer applies, or keep it if there's a fallback path.

**Step 4: Run tests one final time**

Run: `cd monitor && go test -v`
Expected: All PASS

**Step 5: Commit any cleanup**

```bash
git add monitor/
git commit -m "chore(monitor): clean up tests after viewport refactor"
```
