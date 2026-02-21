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
	StateDecomposed                   // context.txt + subcalls.json
	StateSolved                       // context.txt + answer.txt (no subcalls)
	StateSynthesized                  // context.txt + subcalls.json + answer.txt
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
	Name        string         // directory name, e.g. "d0_c0"
	Path        string         // absolute path
	Depth       int
	CallIndex   int
	State       NodeState
	Goal        string         // from parent's subcalls.json, if available
	AnswerLen   int            // length of answer.txt in bytes, 0 if absent
	ContextLen  int            // length of context.txt in bytes
	VarsFiles   []string       // filenames in vars/
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

// WorkspaceStats holds summary stats for the whole workspace.
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
