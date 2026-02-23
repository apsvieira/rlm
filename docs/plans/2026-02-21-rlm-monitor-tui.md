# RLM Monitor TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a terminal UI that monitors an in-progress RLM run by watching its workspace directory, showing the recursion tree, agent states, and file activity in real-time.

**Architecture:** A Go program using Bubble Tea (Charm) for the TUI framework. It polls the workspace directory on a timer, reconstructs the agent tree from the `d{depth}_c{index}` directory naming convention, infers each node's state from file presence (`context.txt`, `subcalls.json`, `answer.txt`), and renders a navigable tree view. A detail pane shows file contents for the selected node.

**Tech Stack:** Go, Bubble Tea (TUI framework), Lip Gloss (styling), Bubble (tree/list components), `fsnotify` or polling for filesystem watching.

---

## Part 1: RLM Metadata Deficiencies (Feature Requests for `rlm`)

Before building the monitor, we should document what the RLM *doesn't* write today that would make monitoring significantly better. These are feature requests for the Python `rlm` package, not blockers for the TUI (we can work around all of them).

### FR-1: No `status.json` per node

**Problem:** The only way to know a node's state is to check which files exist (`context.txt` alone = working, `answer.txt` = done, etc.). There is no way to distinguish "agent is actively running" from "agent crashed and left an incomplete workspace". There is also no way to know which *phase* an agent is in (decompose vs. synthesis).

**Proposed fix:** Write a `status.json` to each node directory at phase transitions:

```json
{
  "state": "decompose" | "synthesize" | "solved" | "error",
  "phase_started_at": "2026-02-21T14:30:00Z",
  "depth": 0,
  "call_index": 0,
  "goal": "Summarize the document",
  "parent": null
}
```

Updated at: node creation, decompose start, subcall dispatch, synthesis start, completion.

**Where to add:** `rlm/agent.py:121-127` (after `workspace.create_node`) and at each phase transition in `rlm_call()`.

### FR-2: No run-level manifest

**Problem:** There is no single file describing the entire run. A monitor must traverse the full directory tree to discover all nodes. There's no record of `goal`, `model`, `max_depth`, or start time at the workspace root.

**Proposed fix:** Write `run.json` at the workspace root:

```json
{
  "goal": "Summarize this document",
  "model": "claude-sonnet-4-6",
  "max_depth": 3,
  "started_at": "2026-02-21T14:30:00Z",
  "workspace": "rlm_workspace/1740100000",
  "status": "running" | "completed" | "error"
}
```

Updated at run start (`rlm/main.py:48`) and at run completion (`rlm/main.py:62`).

### FR-3: No timestamps on files

**Problem:** Filesystem `mtime` is the only temporal signal. There is no structured record of when each phase started or finished. This makes it impossible to show durations or identify stalled agents.

**Proposed fix:** Include timestamps in `status.json` (see FR-1). Additionally, record phase durations after each `run_agent_phase()` call at `rlm/agent.py:143-151` and `rlm/agent.py:212-220`.

### FR-4: No cost/token tracking per node

**Problem:** `total_cost_usd` and `total_calls` are aggregated in-memory by `rlm_call()` return values (`rlm/agent.py:139-140, 202-203, 220-221`) but never written to disk. A monitor can only see the final totals printed to stdout.

**Proposed fix:** Write per-node cost to `status.json` after each phase completes:

```json
{
  "cost_usd": 0.0042,
  "input_tokens": 1200,
  "output_tokens": 450
}
```

### FR-5: No error recording

**Problem:** When an agent produces neither `answer.txt` nor `subcalls.json`, the error message is only in the returned `RLMResult` string (`rlm/agent.py:167`). No file records the failure. A monitor sees a node stuck in "working" state forever.

**Proposed fix:** Write an `error.txt` (or add `"error"` field to `status.json`) when `rlm_call()` hits error branches at lines 165-171 and 224-225.

### FR-6: Subcalls executed sequentially — no parallelism signal

**Problem:** Subcalls are dispatched sequentially in a `for` loop (`rlm/agent.py:175`). A monitor can't know which subcall is "next" vs "not started yet" because their directories don't exist until Python creates them.

**Proposed fix (informational):** After reading `subcalls.json`, write a `pending_subcalls.json` to the parent node listing all planned subcalls with their indices. This lets the monitor show "2 of 4 subcalls complete" before all directories exist. Alternatively, create all child directories up-front with just a `pending` status.

---

## Part 2: TUI Implementation

The monitor works with the RLM *as it exists today* — all FR items above are nice-to-haves.

### Task 1: Initialize Go module and dependencies

**Files:**
- Create: `monitor/go.mod`
- Create: `monitor/main.go`

**Step 1: Create module and install dependencies**

```bash
cd /home/apsv/source/toy/rlm && mkdir -p monitor
cd monitor
go mod init github.com/apsv/rlm-monitor
go get github.com/charmbracelet/bubbletea@latest
go get github.com/charmbracelet/lipgloss@latest
go get github.com/charmbracelet/bubbles@latest
```

**Step 2: Write minimal main.go that starts Bubble Tea**

```go
package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: rlm-monitor <workspace-path>")
		os.Exit(1)
	}
	p := tea.NewProgram(initialModel(os.Args[1]), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
```

**Step 3: Verify it compiles**

Run: `cd /home/apsv/source/toy/rlm/monitor && go build ./...`
Expected: compiles (will fail at missing `initialModel` — that's Task 2)

**Step 4: Commit**

```
git add monitor/
git commit -m "feat(monitor): initialize Go module with bubbletea deps"
```

---

### Task 2: Workspace scanner — parse directory tree into node structs

**Files:**
- Create: `monitor/workspace.go`
- Create: `monitor/workspace_test.go`

This is the core data model. It walks the workspace directory and builds a tree of nodes with inferred states.

**Step 1: Write the failing test**

```go
// monitor/workspace_test.go
package main

import (
	"os"
	"path/filepath"
	"testing"
)

func setupTestWorkspace(t *testing.T) string {
	t.Helper()
	root := t.TempDir()

	// d0_c0: decomposed (has subcalls.json + answer.txt = synthesized)
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("root context"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "subcalls.json"), []byte(`[{"goal":"sub1"},{"goal":"sub2"}]`), 0o644)
	os.WriteFile(filepath.Join(d0c0, "answer.txt"), []byte("synthesized answer"), 0o644)

	// d0_c0/d1_c0: solved directly
	d1c0 := filepath.Join(d0c0, "d1_c0")
	os.MkdirAll(filepath.Join(d1c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d1c0, "context.txt"), []byte("child 0 context"), 0o644)
	os.WriteFile(filepath.Join(d1c0, "answer.txt"), []byte("child 0 answer"), 0o644)

	// d0_c0/d1_c1: still working (only context.txt)
	d1c1 := filepath.Join(d0c0, "d1_c1")
	os.MkdirAll(filepath.Join(d1c1, "vars"), 0o755)
	os.WriteFile(filepath.Join(d1c1, "context.txt"), []byte("child 1 context"), 0o644)

	return root
}

func TestScanWorkspace(t *testing.T) {
	root := setupTestWorkspace(t)
	tree, err := ScanWorkspace(root)
	if err != nil {
		t.Fatalf("ScanWorkspace: %v", err)
	}

	// Root should have 1 top-level node
	if len(tree) != 1 {
		t.Fatalf("expected 1 root node, got %d", len(tree))
	}

	d0c0 := tree[0]
	if d0c0.Depth != 0 || d0c0.CallIndex != 0 {
		t.Errorf("root node: depth=%d call=%d, want 0,0", d0c0.Depth, d0c0.CallIndex)
	}
	if d0c0.State != StateSynthesized {
		t.Errorf("root state=%v, want Synthesized", d0c0.State)
	}
	if len(d0c0.Children) != 2 {
		t.Fatalf("root children=%d, want 2", len(d0c0.Children))
	}

	child0 := d0c0.Children[0]
	if child0.State != StateSolved {
		t.Errorf("child0 state=%v, want Solved", child0.State)
	}

	child1 := d0c0.Children[1]
	if child1.State != StateWorking {
		t.Errorf("child1 state=%v, want Working", child1.State)
	}
}

func TestNodeState(t *testing.T) {
	tests := []struct {
		name           string
		hasContext      bool
		hasAnswer      bool
		hasSubcalls    bool
		expectedState  NodeState
	}{
		{"working", true, false, false, StateWorking},
		{"solved", true, true, false, StateSolved},
		{"decomposed", true, false, true, StateDecomposed},
		{"synthesized", true, true, true, StateSynthesized},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := inferState(tt.hasContext, tt.hasAnswer, tt.hasSubcalls)
			if got != tt.expectedState {
				t.Errorf("got %v, want %v", got, tt.expectedState)
			}
		})
	}
}
```

**Step 2: Run test to verify it fails**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v -run TestScanWorkspace`
Expected: FAIL — `ScanWorkspace` undefined

**Step 3: Implement workspace scanner**

```go
// monitor/workspace.go
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

type NodeState int

const (
	StateWorking     NodeState = iota // context.txt only
	StateDecomposed                    // context.txt + subcalls.json
	StateSolved                        // context.txt + answer.txt (no subcalls)
	StateSynthesized                   // context.txt + subcalls.json + answer.txt
)

func (s NodeState) String() string {
	switch s {
	case StateWorking:
		return "Working"
	case StateDecomposed:
		return "Decomposed"
	case StateSolved:
		return "Solved"
	case StateSynthesized:
		return "Synthesized"
	default:
		return "Unknown"
	}
}

type Node struct {
	Name        string     // directory name, e.g. "d0_c0"
	Path        string     // absolute path
	Depth       int
	CallIndex   int
	State       NodeState
	Goal        string     // from parent's subcalls.json, if available
	AnswerLen   int        // length of answer.txt in bytes, 0 if absent
	ContextLen  int        // length of context.txt in bytes
	VarsFiles   []string   // filenames in vars/
	Children    []*Node
	SubcallsRaw []SubcallEntry // parsed subcalls.json
}

type SubcallEntry struct {
	Goal        string `json:"goal"`
	ContextFile string `json:"context_file,omitempty"`
}

// Regex matches d<depth>_c<index> with optional _<counter> suffix.
var nodePattern = regexp.MustCompile(`^d(\d+)_c(\d+)(?:_\d+)?$`)

func inferState(hasContext, hasAnswer, hasSubcalls bool) NodeState {
	switch {
	case hasSubcalls && hasAnswer:
		return StateSynthesized
	case hasSubcalls:
		return StateDecomposed
	case hasAnswer:
		return StateSolved
	default:
		return StateWorking
	}
}

// ScanWorkspace walks the workspace root and returns top-level nodes (typically one: d0_c0).
func ScanWorkspace(root string) ([]*Node, error) {
	return scanDir(root)
}

func scanDir(dir string) ([]*Node, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("reading %s: %w", dir, err)
	}

	var nodes []*Node
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		matches := nodePattern.FindStringSubmatch(e.Name())
		if matches == nil {
			continue
		}
		var depth, callIdx int
		fmt.Sscanf(matches[1], "%d", &depth)
		fmt.Sscanf(matches[2], "%d", &callIdx)

		nodePath := filepath.Join(dir, e.Name())
		node, err := buildNode(nodePath, e.Name(), depth, callIdx)
		if err != nil {
			continue // skip broken nodes
		}
		nodes = append(nodes, node)
	}

	sort.Slice(nodes, func(i, j int) bool {
		if nodes[i].Depth != nodes[j].Depth {
			return nodes[i].Depth < nodes[j].Depth
		}
		return nodes[i].CallIndex < nodes[j].CallIndex
	})

	return nodes, nil
}

func buildNode(path, name string, depth, callIndex int) (*Node, error) {
	node := &Node{
		Name:      name,
		Path:      path,
		Depth:     depth,
		CallIndex: callIndex,
	}

	hasContext := false
	if info, err := os.Stat(filepath.Join(path, "context.txt")); err == nil {
		hasContext = true
		node.ContextLen = int(info.Size())
	}

	hasAnswer := false
	if info, err := os.Stat(filepath.Join(path, "answer.txt")); err == nil {
		hasAnswer = true
		node.AnswerLen = int(info.Size())
	}

	hasSubcalls := false
	subcallsPath := filepath.Join(path, "subcalls.json")
	if data, err := os.ReadFile(subcallsPath); err == nil {
		hasSubcalls = true
		var entries []SubcallEntry
		if json.Unmarshal(data, &entries) == nil {
			node.SubcallsRaw = entries
		}
	}

	node.State = inferState(hasContext, hasAnswer, hasSubcalls)

	// Scan vars/
	varsPath := filepath.Join(path, "vars")
	if entries, err := os.ReadDir(varsPath); err == nil {
		for _, e := range entries {
			if !e.IsDir() {
				node.VarsFiles = append(node.VarsFiles, e.Name())
			}
		}
	}

	// Recurse into child node directories
	children, err := scanDir(path)
	if err == nil {
		node.Children = children
		// Assign goals from subcalls.json to matching children
		for _, child := range children {
			if child.CallIndex < len(node.SubcallsRaw) {
				child.Goal = node.SubcallsRaw[child.CallIndex].Goal
			}
		}
	}

	return node, nil
}

// Summary stats for the whole workspace.
type WorkspaceStats struct {
	TotalNodes  int
	Working     int
	Decomposed  int
	Solved      int
	Synthesized int
	MaxDepth    int
}

func ComputeStats(nodes []*Node) WorkspaceStats {
	var s WorkspaceStats
	var walk func([]*Node)
	walk = func(ns []*Node) {
		for _, n := range ns {
			s.TotalNodes++
			switch n.State {
			case StateWorking:
				s.Working++
			case StateDecomposed:
				s.Decomposed++
			case StateSolved:
				s.Solved++
			case StateSynthesized:
				s.Synthesized++
			}
			if n.Depth > s.MaxDepth {
				s.MaxDepth = n.Depth
			}
			walk(n.Children)
		}
	}
	walk(nodes)
	return s
}

// Flatten returns all nodes in pre-order (for list rendering).
func Flatten(nodes []*Node) []*Node {
	var result []*Node
	var walk func([]*Node)
	walk = func(ns []*Node) {
		for _, n := range ns {
			result = append(result, n)
			walk(n.Children)
		}
	}
	walk(nodes)
	return result
}

// FormatSize returns a human-readable size string.
func FormatSize(bytes int) string {
	if bytes < 1024 {
		return fmt.Sprintf("%dB", bytes)
	}
	return fmt.Sprintf("%.1fk", float64(bytes)/1024)
}

// TreePrefix returns the box-drawing prefix for a node in a flat list display.
func TreePrefix(node *Node, nodes []*Node, index int) string {
	if node.Depth == 0 {
		return ""
	}
	indent := strings.Repeat("  ", node.Depth-1)
	// Check if this is the last child at its depth under the same parent
	isLast := true
	for i := index + 1; i < len(nodes); i++ {
		if nodes[i].Depth < node.Depth {
			break
		}
		if nodes[i].Depth == node.Depth {
			isLast = false
			break
		}
	}
	if isLast {
		return indent + "└─ "
	}
	return indent + "├─ "
}
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v -run "TestScanWorkspace|TestNodeState"`
Expected: PASS

**Step 5: Commit**

```
git add monitor/workspace.go monitor/workspace_test.go
git commit -m "feat(monitor): workspace scanner with tree parsing and state inference"
```

---

### Task 3: Bubble Tea model — tree view with tick-based refresh

**Files:**
- Create: `monitor/model.go`

This is the Bubble Tea model that ties the scanner to a TUI with periodic refresh.

**Step 1: Implement the model**

```go
// monitor/model.go
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

const pollInterval = 1 * time.Second

// Styles
var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
	statsStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
	selectedStyle = lipgloss.NewStyle().Background(lipgloss.Color("236")).Bold(true)
	workingStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("214"))  // orange
	decomStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("111"))  // blue
	solvedStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("114"))  // green
	synthStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("177"))  // purple
	dimStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
	detailLabel   = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
	helpStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
)

type tickMsg time.Time

func tickCmd() tea.Cmd {
	return tea.Tick(pollInterval, func(t time.Time) tea.Msg {
		return tickMsg(t)
	})
}

type model struct {
	workspacePath string
	nodes         []*Node
	flat          []*Node // pre-order flattened for cursor navigation
	stats         WorkspaceStats
	cursor        int
	showDetail    bool // true = detail pane for selected node
	detailContent string
	detailFile    string
	width         int
	height        int
	err           error
}

func initialModel(workspacePath string) model {
	m := model{workspacePath: workspacePath}
	m.refresh()
	return m
}

func (m *model) refresh() {
	nodes, err := ScanWorkspace(m.workspacePath)
	if err != nil {
		m.err = err
		return
	}
	m.nodes = nodes
	m.flat = Flatten(nodes)
	m.stats = ComputeStats(nodes)
	if m.cursor >= len(m.flat) {
		m.cursor = max(0, len(m.flat)-1)
	}
	m.err = nil
}

func (m model) Init() tea.Cmd {
	return tickCmd()
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "up", "k":
			if m.showDetail {
				break
			}
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.showDetail {
				break
			}
			if m.cursor < len(m.flat)-1 {
				m.cursor++
			}
		case "enter":
			if len(m.flat) > 0 {
				m.showDetail = !m.showDetail
				if m.showDetail {
					m.loadDetail("answer.txt")
				}
			}
		case "esc":
			m.showDetail = false
		case "c":
			if m.showDetail && len(m.flat) > 0 {
				m.loadDetail("context.txt")
			}
		case "a":
			if m.showDetail && len(m.flat) > 0 {
				m.loadDetail("answer.txt")
			}
		case "s":
			if m.showDetail && len(m.flat) > 0 {
				m.loadDetail("subcalls.json")
			}
		case "r":
			m.refresh()
		}

	case tickMsg:
		m.refresh()
		return m, tickCmd()

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	}

	return m, nil
}

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
}

func (m model) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error: %v\nPress q to quit.", m.err)
	}

	var b strings.Builder

	// Header
	b.WriteString(titleStyle.Render(fmt.Sprintf("RLM Monitor — %s", m.workspacePath)))
	b.WriteString("\n")

	// Stats bar
	active := m.stats.Working + m.stats.Decomposed
	done := m.stats.Solved + m.stats.Synthesized
	statsLine := fmt.Sprintf(
		"Nodes: %d total | %d active | %d done | max depth: %d",
		m.stats.TotalNodes, active, done, m.stats.MaxDepth,
	)
	b.WriteString(statsStyle.Render(statsLine))
	b.WriteString("\n")
	b.WriteString(strings.Repeat("─", min(m.width, 72)))
	b.WriteString("\n")

	if len(m.flat) == 0 {
		b.WriteString(dimStyle.Render("  (no nodes yet — waiting for RLM to start...)"))
		b.WriteString("\n")
	}

	if m.showDetail {
		b.WriteString(m.renderDetail())
	} else {
		b.WriteString(m.renderTree())
	}

	// Help footer
	b.WriteString("\n")
	if m.showDetail {
		b.WriteString(helpStyle.Render("[esc] back  [c] context  [a] answer  [s] subcalls  [q] quit"))
	} else {
		b.WriteString(helpStyle.Render("[j/k] navigate  [enter] detail  [r] refresh  [q] quit"))
	}

	return b.String()
}

func (m model) renderTree() string {
	var b strings.Builder

	for i, node := range m.flat {
		prefix := TreePrefix(node, m.flat, i)

		// State icon + style
		var stateStr string
		switch node.State {
		case StateWorking:
			stateStr = workingStyle.Render("● WORKING")
		case StateDecomposed:
			stateStr = decomStyle.Render("◆ DECOMPOSED")
		case StateSolved:
			stateStr = solvedStyle.Render("✓ SOLVED")
		case StateSynthesized:
			stateStr = synthStyle.Render("✦ SYNTHESIZED")
		}

		// Size info
		sizeInfo := dimStyle.Render(fmt.Sprintf("ctx:%s", FormatSize(node.ContextLen)))
		if node.AnswerLen > 0 {
			sizeInfo += dimStyle.Render(fmt.Sprintf(" ans:%s", FormatSize(node.AnswerLen)))
		}

		// Goal snippet (truncated)
		goalSnip := ""
		if node.Goal != "" {
			g := node.Goal
			if len(g) > 40 {
				g = g[:37] + "..."
			}
			goalSnip = dimStyle.Render(fmt.Sprintf(" \"%s\"", g))
		}

		line := fmt.Sprintf(" %s%s  %s  %s%s", prefix, node.Name, stateStr, sizeInfo, goalSnip)

		if i == m.cursor {
			line = selectedStyle.Render(line)
		}
		b.WriteString(line)
		b.WriteString("\n")
	}

	return b.String()
}

func (m model) renderDetail() string {
	if m.cursor >= len(m.flat) {
		return ""
	}
	node := m.flat[m.cursor]

	var b strings.Builder
	b.WriteString(detailLabel.Render(fmt.Sprintf("Node: %s  depth:%d  call:%d  state:%s",
		node.Name, node.Depth, node.CallIndex, node.State)))
	b.WriteString("\n")

	// Files present
	files := []string{"context.txt"}
	if node.AnswerLen > 0 {
		files = append(files, fmt.Sprintf("answer.txt (%s)", FormatSize(node.AnswerLen)))
	}
	if len(node.SubcallsRaw) > 0 {
		files = append(files, fmt.Sprintf("subcalls.json (%d entries)", len(node.SubcallsRaw)))
	}
	if len(node.VarsFiles) > 0 {
		files = append(files, fmt.Sprintf("vars/ (%d files)", len(node.VarsFiles)))
	}
	b.WriteString(dimStyle.Render("Files: " + strings.Join(files, ", ")))
	b.WriteString("\n")

	if node.Goal != "" {
		b.WriteString(dimStyle.Render(fmt.Sprintf("Goal: %s", node.Goal)))
		b.WriteString("\n")
	}

	b.WriteString(strings.Repeat("─", min(m.width, 72)))
	b.WriteString("\n")
	b.WriteString(detailLabel.Render(fmt.Sprintf("── %s ──", m.detailFile)))
	b.WriteString("\n")

	// Truncate content to fit screen
	lines := strings.Split(m.detailContent, "\n")
	maxLines := max(m.height-12, 5)
	if len(lines) > maxLines {
		lines = lines[:maxLines]
		lines = append(lines, dimStyle.Render(fmt.Sprintf("... (%d more lines)", len(lines)-maxLines)))
	}
	b.WriteString(strings.Join(lines, "\n"))
	b.WriteString("\n")

	return b.String()
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
```

**Step 2: Verify it compiles and runs**

Run: `cd /home/apsv/source/toy/rlm/monitor && go build -o rlm-monitor .`
Expected: compiles successfully

**Step 3: Commit**

```
git add monitor/model.go monitor/main.go
git commit -m "feat(monitor): bubble tea TUI with tree view and detail pane"
```

---

### Task 4: Manual smoke test with a real or mock workspace

**Step 1: Create a mock workspace for testing**

```bash
mkdir -p /tmp/rlm-test/d0_c0/vars
echo "root context content here" > /tmp/rlm-test/d0_c0/context.txt
echo '[{"goal":"summarize section 1","context_file":"vars/sub_0_context.txt"},{"goal":"summarize section 2","context_file":"vars/sub_1_context.txt"}]' > /tmp/rlm-test/d0_c0/subcalls.json
echo "section 1 text" > /tmp/rlm-test/d0_c0/vars/sub_0_context.txt
echo "section 2 text" > /tmp/rlm-test/d0_c0/vars/sub_1_context.txt

mkdir -p /tmp/rlm-test/d0_c0/d1_c0/vars
echo "section 1 text" > /tmp/rlm-test/d0_c0/d1_c0/context.txt
echo "Summary of section 1: it talks about X" > /tmp/rlm-test/d0_c0/d1_c0/answer.txt

mkdir -p /tmp/rlm-test/d0_c0/d1_c1/vars
echo "section 2 text" > /tmp/rlm-test/d0_c0/d1_c1/context.txt
```

**Step 2: Run the monitor against the mock workspace**

Run: `cd /home/apsv/source/toy/rlm/monitor && go run . /tmp/rlm-test`

Expected: TUI shows tree with d0_c0 (DECOMPOSED), d1_c0 (SOLVED), d1_c1 (WORKING). Navigation with j/k works. Enter shows detail pane with file contents. q quits.

**Step 3: Simulate progress — add answer.txt to the working node**

In a separate terminal while the monitor runs:
```bash
echo "Summary of section 2: it discusses Y" > /tmp/rlm-test/d0_c0/d1_c1/answer.txt
```

Expected: Within 1 second, the monitor updates d1_c1 from WORKING to SOLVED.

**Step 4: Simulate synthesis — add answer.txt to root**

```bash
echo "Combined summary: section 1 covers X, section 2 covers Y" > /tmp/rlm-test/d0_c0/answer.txt
```

Expected: d0_c0 changes from DECOMPOSED to SYNTHESIZED.

---

### Task 5: Polish — handle edge cases and empty workspaces

**Files:**
- Modify: `monitor/workspace.go`
- Modify: `monitor/model.go`

**Step 1: Handle workspace directory not existing yet**

The RLM creates the workspace on startup. The monitor should handle the case where the directory doesn't exist yet by showing a waiting message and retrying on tick.

In `workspace.go`, modify `ScanWorkspace`:
```go
func ScanWorkspace(root string) ([]*Node, error) {
	if _, err := os.Stat(root); os.IsNotExist(err) {
		return nil, nil // Not an error — workspace not created yet
	}
	return scanDir(root)
}
```

In `model.go`, the "no nodes yet" message already handles this case.

**Step 2: Run tests**

Run: `cd /home/apsv/source/toy/rlm/monitor && go test -v`
Expected: PASS

**Step 3: Commit**

```
git add monitor/
git commit -m "fix(monitor): handle workspace directory not existing yet"
```

---

### Task 6: Add `--workspace` flag and auto-detect latest workspace

**Files:**
- Modify: `monitor/main.go`

**Step 1: Implement auto-detect**

When no workspace path is given, scan `rlm_workspace/` in the current directory for the most recently modified subdirectory (highest timestamp).

```go
// In main.go, replace the arg parsing:
func resolveWorkspace() (string, error) {
	if len(os.Args) >= 2 {
		return os.Args[1], nil
	}
	// Auto-detect: find latest rlm_workspace/<timestamp> directory
	entries, err := os.ReadDir("rlm_workspace")
	if err != nil {
		return "", fmt.Errorf("no workspace argument and no rlm_workspace/ directory found")
	}
	var latest string
	for _, e := range entries {
		if e.IsDir() && e.Name() > latest {
			latest = e.Name()
		}
	}
	if latest == "" {
		return "", fmt.Errorf("no workspaces found in rlm_workspace/")
	}
	return filepath.Join("rlm_workspace", latest), nil
}
```

**Step 2: Commit**

```
git add monitor/main.go
git commit -m "feat(monitor): auto-detect latest workspace when no arg given"
```
