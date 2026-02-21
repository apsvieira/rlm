package main

import (
	"strings"
	"testing"
)

func TestNonExistentWorkspace(t *testing.T) {
	nodes, err := ScanWorkspace("/tmp/this-does-not-exist-at-all")
	if err != nil {
		t.Errorf("expected nil error for non-existent workspace, got: %v", err)
	}
	if nodes != nil {
		t.Errorf("expected nil nodes, got %d", len(nodes))
	}
}

func TestEmptyWorkspace(t *testing.T) {
	root := t.TempDir()
	m := initialModel(root)
	m.width = 80
	m.height = 24

	view := m.View()
	if !strings.Contains(view, "no nodes yet") {
		t.Error("empty workspace should show waiting message")
	}
}
