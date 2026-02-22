package main

import (
	"os"
	"path/filepath"
	"strings"
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

func TestStatusJSONOverridesInference(t *testing.T) {
	root := t.TempDir()

	// Create a node that looks "working" by file presence (only context.txt)
	// but has status.json saying "error"
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "status.json"), []byte(`{"state":"error","goal":"test"}`), 0o644)

	tree, err := ScanWorkspace(root)
	if err != nil {
		t.Fatalf("ScanWorkspace: %v", err)
	}
	if len(tree) != 1 {
		t.Fatalf("expected 1 node, got %d", len(tree))
	}
	if tree[0].State != StateError {
		t.Errorf("state=%v, want Error", tree[0].State)
	}
	if tree[0].StatusJSON == nil {
		t.Fatal("StatusJSON should not be nil")
	}
	if tree[0].StatusJSON["goal"] != "test" {
		t.Errorf("goal=%v, want 'test'", tree[0].StatusJSON["goal"])
	}
}

func TestStatusJSONSolvedState(t *testing.T) {
	root := t.TempDir()

	// Node with no answer.txt but status.json says "solved"
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "status.json"), []byte(`{"state":"solved"}`), 0o644)

	tree, err := ScanWorkspace(root)
	if err != nil {
		t.Fatalf("ScanWorkspace: %v", err)
	}
	if tree[0].State != StateSolved {
		t.Errorf("state=%v, want Solved", tree[0].State)
	}
}

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

func TestEventsJSONLParsing(t *testing.T) {
	root := t.TempDir()

	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)

	events := `{"ts":"2026-02-21T12:03:45Z","type":"tool_use","phase":"decompose","name":"Read","input":{"file_path":"context.txt"}}
{"ts":"2026-02-21T12:03:46Z","type":"tool_result","phase":"decompose","is_error":false,"content_length":1234}
{"ts":"2026-02-21T12:03:47Z","type":"text","phase":"decompose","length":450,"preview":"The authentication module..."}
{"ts":"2026-02-21T12:03:48Z","type":"result","phase":"decompose","cost_usd":0.0042,"input_tokens":1200,"output_tokens":450}
{"ts":"2026-02-21T12:03:49Z","type":"system","phase":"decompose","subtype":"init"}
`
	os.WriteFile(filepath.Join(d0c0, "events.jsonl"), []byte(events), 0o644)

	tree, err := ScanWorkspace(root)
	if err != nil {
		t.Fatalf("ScanWorkspace: %v", err)
	}
	if len(tree) != 1 {
		t.Fatalf("expected 1 node, got %d", len(tree))
	}

	node := tree[0]
	if len(node.Events) != 5 {
		t.Fatalf("expected 5 events, got %d", len(node.Events))
	}

	// Check tool_use event
	ev0 := node.Events[0]
	if ev0.Type != "tool_use" {
		t.Errorf("event[0] type=%q, want 'tool_use'", ev0.Type)
	}
	if ev0.Name != "Read" {
		t.Errorf("event[0] name=%q, want 'Read'", ev0.Name)
	}
	if ev0.Phase != "decompose" {
		t.Errorf("event[0] phase=%q, want 'decompose'", ev0.Phase)
	}

	// Check tool_result event
	ev1 := node.Events[1]
	if ev1.Type != "tool_result" {
		t.Errorf("event[1] type=%q, want 'tool_result'", ev1.Type)
	}
	if ev1.IsError == nil || *ev1.IsError != false {
		t.Errorf("event[1] is_error should be false")
	}
	if ev1.ContentLength != 1234 {
		t.Errorf("event[1] content_length=%d, want 1234", ev1.ContentLength)
	}

	// Check result event
	ev3 := node.Events[3]
	if ev3.CostUSD != 0.0042 {
		t.Errorf("event[3] cost_usd=%f, want 0.0042", ev3.CostUSD)
	}
	if ev3.InputTokens != 1200 {
		t.Errorf("event[3] input_tokens=%d, want 1200", ev3.InputTokens)
	}
}

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

func TestToolUseCount(t *testing.T) {
	node := &Node{
		Events: []EventEntry{
			{Type: "tool_use", Name: "Read"},
			{Type: "tool_result"},
			{Type: "tool_use", Name: "Glob"},
			{Type: "text"},
			{Type: "tool_use", Name: "Write"},
		},
	}
	if count := ToolUseCount(node); count != 3 {
		t.Errorf("ToolUseCount=%d, want 3", count)
	}
}

func TestToolUseCountEmpty(t *testing.T) {
	node := &Node{}
	if count := ToolUseCount(node); count != 0 {
		t.Errorf("ToolUseCount=%d, want 0", count)
	}
}

func TestEventsJSONLMalformed(t *testing.T) {
	root := t.TempDir()

	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("ctx"), 0o644)

	// Mix of valid and invalid lines
	events := `{"ts":"2026-02-21T12:00:00Z","type":"tool_use","name":"Read"}
not valid json
{"ts":"2026-02-21T12:00:01Z","type":"text","length":10}
`
	os.WriteFile(filepath.Join(d0c0, "events.jsonl"), []byte(events), 0o644)

	tree, err := ScanWorkspace(root)
	if err != nil {
		t.Fatalf("ScanWorkspace: %v", err)
	}
	// Should skip malformed lines
	if len(tree[0].Events) != 2 {
		t.Errorf("expected 2 events, got %d", len(tree[0].Events))
	}
}

func TestFormatEventLog(t *testing.T) {
	isErr := false
	events := []EventEntry{
		{Ts: "2026-02-21T12:03:45Z", Type: "tool_use", Phase: "decompose", Name: "Read", Input: map[string]interface{}{"file_path": "context.txt"}},
		{Ts: "2026-02-21T12:03:46Z", Type: "tool_result", Phase: "decompose", IsError: &isErr, ContentLength: 1234},
		{Ts: "2026-02-21T12:03:47Z", Type: "text", Phase: "decompose", Length: 450, Preview: "The auth module..."},
	}
	output := FormatEventLog(events)
	if output == "" {
		t.Error("expected non-empty output")
	}
	// Check that timestamps are formatted
	if !strings.Contains(output, "12:03:45") {
		t.Error("expected timestamp in output")
	}
	if !strings.Contains(output, "tool_use: Read") {
		t.Error("expected tool_use Read in output")
	}
	if !strings.Contains(output, "tool_result: ok") {
		t.Error("expected tool_result ok in output")
	}
}

func TestNodeState(t *testing.T) {
	tests := []struct {
		name          string
		hasContext    bool
		hasAnswer    bool
		hasSubcalls  bool
		expectedState NodeState
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
