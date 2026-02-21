package main

import (
	"strings"
	"testing"
)

func TestSmokeAfterProgress(t *testing.T) {
	// After adding answer.txt to d1_c1 and d0_c0, re-scan
	m := initialModel("/tmp/rlm-test")

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
	var d0c0 *Node
	for _, n := range m.flat {
		if n.Name == "d0_c0" {
			d0c0 = n
			break
		}
	}
	if d0c0 == nil {
		t.Fatal("d0_c0 not found")
	}
	if d0c0.State != StateSynthesized {
		t.Errorf("d0_c0 should be Synthesized, got %v", d0c0.State)
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
