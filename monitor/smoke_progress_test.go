package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSmokeAfterProgress(t *testing.T) {
	root := setupSmokeWorkspace(t)

	// Add answer.txt to both remaining nodes to simulate full completion
	d0c0 := filepath.Join(root, "d0_c0")
	os.WriteFile(filepath.Join(d0c0, "d1_c1", "answer.txt"), []byte("Summary of section 2: it discusses Y"), 0o644)
	os.WriteFile(filepath.Join(d0c0, "answer.txt"), []byte("Combined summary: section 1 covers X, section 2 covers Y"), 0o644)

	m := initialModel(root)
	m.width = 80
	m.height = 24

	// d1_c1 should now be Solved
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
	if d1c1.State != StateSolved {
		t.Errorf("d1_c1 should be Solved after adding answer.txt, got %v", d1c1.State)
	}

	// d0_c0 should now be Synthesized (has subcalls.json + answer.txt)
	var d0c0Node *Node
	for _, n := range m.flat {
		if n.Name == "d0_c0" {
			d0c0Node = n
			break
		}
	}
	if d0c0Node == nil {
		t.Fatal("d0_c0 not found")
	}
	if d0c0Node.State != StateSynthesized {
		t.Errorf("d0_c0 should be Synthesized, got %v", d0c0Node.State)
	}

	// Stats should show all done
	view := m.View()
	if !strings.Contains(view, "SYNTHESIZED") {
		t.Error("should show SYNTHESIZED state")
	}
	if !strings.Contains(view, "0 active") {
		t.Error("should show 0 active nodes")
	}
}
