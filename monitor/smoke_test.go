package main

import (
	"strings"
	"testing"
)

func TestSmokeRender(t *testing.T) {
	m := initialModel("/tmp/rlm-test")
	m.width = 80
	m.height = 24

	view := m.View()

	// Verify header
	if !strings.Contains(view, "RLM Monitor") {
		t.Error("missing header")
	}

	// Verify stats
	if !strings.Contains(view, "3 total") {
		t.Errorf("expected 3 total nodes in stats, got: %s", view)
	}

	// Verify tree nodes are rendered
	if !strings.Contains(view, "d0_c0") {
		t.Error("missing d0_c0 in tree")
	}
	if !strings.Contains(view, "d1_c0") {
		t.Error("missing d1_c0 in tree")
	}
	if !strings.Contains(view, "d1_c1") {
		t.Error("missing d1_c1 in tree")
	}

	// Verify states
	if !strings.Contains(view, "DECOMPOSED") {
		t.Error("missing DECOMPOSED state for d0_c0")
	}
	if !strings.Contains(view, "SOLVED") {
		t.Error("missing SOLVED state for d1_c0")
	}
	if !strings.Contains(view, "WORKING") {
		t.Error("missing WORKING state for d1_c1")
	}

	// Verify goals from subcalls.json
	if !strings.Contains(view, "summarize section 1") {
		t.Error("missing goal for d1_c0")
	}

	// Verify help footer
	if !strings.Contains(view, "[j/k] navigate") {
		t.Error("missing help footer")
	}

	// Test detail view
	m.showDetail = true
	m.loadDetail("answer.txt")
	detailView := m.View()
	if !strings.Contains(detailView, "answer.txt") {
		t.Error("detail view should mention answer.txt")
	}
	if !strings.Contains(detailView, "[esc] back") {
		t.Error("detail view should show detail help")
	}
}

func TestSmokeProgressUpdate(t *testing.T) {
	// Simulate adding answer.txt to working node
	m := initialModel("/tmp/rlm-test")

	// Find d1_c1 and verify it's working
	var d1c1 *Node
	for _, n := range m.flat {
		if n.Name == "d1_c1" {
			d1c1 = n
			break
		}
	}
	if d1c1 == nil {
		t.Fatal("d1_c1 not found")
	}
	if d1c1.State != StateWorking {
		t.Errorf("d1_c1 should be Working, got %v", d1c1.State)
	}
}
