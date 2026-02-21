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
