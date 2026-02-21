package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// setupSmokeWorkspace creates a self-contained workspace with mixed states.
func setupSmokeWorkspace(t *testing.T) string {
	t.Helper()
	root := t.TempDir()

	// d0_c0: decomposed (has subcalls.json, no answer.txt)
	d0c0 := filepath.Join(root, "d0_c0")
	os.MkdirAll(filepath.Join(d0c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d0c0, "context.txt"), []byte("root context content here"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "subcalls.json"), []byte(`[{"goal":"summarize section 1","context_file":"vars/sub_0_context.txt"},{"goal":"summarize section 2","context_file":"vars/sub_1_context.txt"}]`), 0o644)
	os.WriteFile(filepath.Join(d0c0, "vars", "sub_0_context.txt"), []byte("section 1 text"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "vars", "sub_1_context.txt"), []byte("section 2 text"), 0o644)

	// d1_c0: solved
	d1c0 := filepath.Join(d0c0, "d1_c0")
	os.MkdirAll(filepath.Join(d1c0, "vars"), 0o755)
	os.WriteFile(filepath.Join(d1c0, "context.txt"), []byte("section 1 text"), 0o644)
	os.WriteFile(filepath.Join(d1c0, "answer.txt"), []byte("Summary of section 1: it talks about X"), 0o644)

	// d1_c1: working (no answer.txt)
	d1c1 := filepath.Join(d0c0, "d1_c1")
	os.MkdirAll(filepath.Join(d1c1, "vars"), 0o755)
	os.WriteFile(filepath.Join(d1c1, "context.txt"), []byte("section 2 text"), 0o644)

	return root
}

func TestSmokeRender(t *testing.T) {
	root := setupSmokeWorkspace(t)
	m := initialModel(root)
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

func TestSmokeProgressUpdate(t *testing.T) {
	root := setupSmokeWorkspace(t)
	m := initialModel(root)

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

	// Simulate adding answer.txt
	os.WriteFile(filepath.Join(d1c1.Path, "answer.txt"), []byte("Summary of section 2"), 0o644)
	m.refresh()

	// Find d1_c1 again after refresh
	for _, n := range m.flat {
		if n.Name == "d1_c1" {
			if n.State != StateSolved {
				t.Errorf("d1_c1 should be Solved after adding answer.txt, got %v", n.State)
			}
			return
		}
	}
	t.Fatal("d1_c1 not found after refresh")
}
