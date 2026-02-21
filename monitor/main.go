package main

import (
	"fmt"
	"os"
	"path/filepath"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	workspace, err := resolveWorkspace()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	p := tea.NewProgram(initialModel(workspace), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

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
