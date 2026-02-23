package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

const pollInterval = 1 * time.Second

// Styles
var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("99"))
	statsStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("241"))
	selectedStyle = lipgloss.NewStyle().Background(lipgloss.Color("236")).Bold(true)
	workingStyle  = lipgloss.NewStyle().Foreground(lipgloss.Color("214")) // orange
	decomStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("111")) // blue
	solvedStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("114")) // green
	synthStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("177")) // purple
	errorStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("196")) // red
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
	manifest      *RunManifest
	viewport      viewport.Model
	viewportReady bool
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
	m.manifest = ReadRunManifest(m.workspacePath)
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
				m.viewport, _ = m.viewport.Update(msg)
				break
			}
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.showDetail {
				m.viewport, _ = m.viewport.Update(msg)
				break
			}
			if m.cursor < len(m.flat)-1 {
				m.cursor++
			}
		case "pgup", "pgdown", "home", "end":
			if m.showDetail {
				m.viewport, _ = m.viewport.Update(msg)
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
		case "e":
			if m.showDetail && len(m.flat) > 0 {
				m.loadDetail("error.txt")
			}
		case "l":
			if m.showDetail && len(m.flat) > 0 {
				m.loadEventLog()
			}
		case "f":
			if m.showDetail && len(m.flat) > 0 {
				m.loadOutputFiles()
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
		headerHeight := 8
		footerHeight := 2
		viewportHeight := max(m.height-headerHeight-footerHeight, 5)
		w := m.contentWidth()
		if !m.viewportReady {
			m.viewport = viewport.New(w, viewportHeight)
			m.viewportReady = true
		} else {
			m.viewport.Width = w
			m.viewport.Height = viewportHeight
		}
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
	m.syncViewport()
}

func (m *model) loadEventLog() {
	if m.cursor >= len(m.flat) {
		return
	}
	node := m.flat[m.cursor]
	if len(node.Events) == 0 {
		m.detailContent = "(no events)"
	} else {
		m.detailContent = FormatEventLog(node.Events)
	}
	m.detailFile = "events.jsonl"
	m.syncViewport()
}

func (m *model) loadOutputFiles() {
	if m.cursor >= len(m.flat) {
		return
	}
	node := m.flat[m.cursor]
	if len(node.OutputFiles) == 0 {
		m.detailContent = "(no output files)"
	} else {
		var b strings.Builder
		fmt.Fprintf(&b, "Output files (%d):\n\n", len(node.OutputFiles))
		for _, of := range node.OutputFiles {
			fmt.Fprintf(&b, "  %s  (%s)\n", of.Path, FormatSize(of.Size))
		}
		m.detailContent = b.String()
	}
	m.detailFile = "output files"
	m.syncViewport()
}

func (m model) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error: %v\nPress q to quit.", m.err)
	}

	var b strings.Builder

	// Header
	b.WriteString(titleStyle.Render(fmt.Sprintf("RLM Monitor — %s", m.workspacePath)))
	b.WriteString("\n")

	// Run manifest line (if run.json exists)
	if m.manifest != nil {
		modelShort := strings.TrimPrefix(m.manifest.Model, "claude-")
		runLine := fmt.Sprintf("model: %s | max-depth: %d | status: %s",
			modelShort, m.manifest.MaxDepth, m.manifest.Status)
		if m.manifest.TotalCostUSD > 0 {
			runLine += fmt.Sprintf(" | cost: $%.4f", m.manifest.TotalCostUSD)
		}
		if m.manifest.TotalCalls > 0 {
			runLine += fmt.Sprintf(" | calls: %d", m.manifest.TotalCalls)
		}
		b.WriteString(dimStyle.Render(runLine))
		b.WriteString("\n")
	}

	// Stats bar
	active := m.stats.Working + m.stats.Decomposed
	done := m.stats.Solved + m.stats.Synthesized
	statsLine := fmt.Sprintf(
		"Nodes: %d total | %d active | %d done | max depth: %d",
		m.stats.TotalNodes, active, done, m.stats.MaxDepth,
	)
	if m.stats.Errors > 0 {
		statsLine += fmt.Sprintf(" | %d error", m.stats.Errors)
		if m.stats.Errors > 1 {
			statsLine += "s"
		}
	}
	b.WriteString(statsStyle.Render(statsLine))
	b.WriteString("\n")
	b.WriteString(strings.Repeat("─", m.contentWidth()))
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
		b.WriteString(helpStyle.Render("[↑/↓] scroll  [esc] back  [c] context  [a] answer  [s] subcalls  [e] error  [l] log  [f] files  [q] quit"))
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
		case StateError:
			stateStr = errorStyle.Render("✗ ERROR")
		}

		// Size info
		sizeInfo := dimStyle.Render(fmt.Sprintf("ctx:%s", FormatSize(node.ContextLen)))
		if node.AnswerLen > 0 {
			sizeInfo += dimStyle.Render(fmt.Sprintf(" ans:%s", FormatSize(node.AnswerLen)))
		}

		// Cost + tokens: prefer live events data, fall back to status.json
		costInfo := ""
		tokenInfo := ""
		inTok, outTok, liveCost := LiveTokens(node)
		if inTok > 0 || outTok > 0 {
			costInfo = dimStyle.Render(fmt.Sprintf(" $%.4f", liveCost))
			tokenInfo = dimStyle.Render(fmt.Sprintf(" %s↑%s↓", FormatSize(inTok), FormatSize(outTok)))
		} else if cost := statusFloat(node.StatusJSON, "cost_usd"); cost > 0 {
			costInfo = dimStyle.Render(fmt.Sprintf(" $%.4f", cost))
		}

		// Tool use count from events
		toolInfo := ""
		if tc := ToolUseCount(node); tc > 0 {
			toolInfo = dimStyle.Render(fmt.Sprintf(" tools:%d", tc))
		}

		// Output files count
		filesInfo := ""
		if len(node.OutputFiles) > 0 {
			filesInfo = dimStyle.Render(fmt.Sprintf(" files:%d", len(node.OutputFiles)))
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

		line := fmt.Sprintf(" %s%s  %s  %s%s%s%s%s%s", prefix, node.Name, stateStr, sizeInfo, costInfo, tokenInfo, toolInfo, filesInfo, goalSnip)

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

	if len(node.OutputFiles) > 0 {
		b.WriteString(dimStyle.Render(fmt.Sprintf("Output files (%d):", len(node.OutputFiles))))
		b.WriteString("\n")
		for _, of := range node.OutputFiles {
			b.WriteString(dimStyle.Render(fmt.Sprintf("  %s  (%s)", of.Path, FormatSize(of.Size))))
			b.WriteString("\n")
		}
	}

	if node.Goal != "" {
		b.WriteString(dimStyle.Render(fmt.Sprintf("Goal: %s", node.Goal)))
		b.WriteString("\n")
	}

	// Cost, tokens, timing from status.json
	if node.StatusJSON != nil {
		var metaParts []string
		if cost := statusFloat(node.StatusJSON, "cost_usd"); cost > 0 {
			metaParts = append(metaParts, fmt.Sprintf("cost: $%.4f", cost))
		}
		inTok := statusFloat(node.StatusJSON, "input_tokens")
		outTok := statusFloat(node.StatusJSON, "output_tokens")
		if inTok > 0 || outTok > 0 {
			metaParts = append(metaParts, fmt.Sprintf("tokens: %d in / %d out", int(inTok), int(outTok)))
		}
		elapsed := FormatElapsed(
			statusString(node.StatusJSON, "started_at"),
			statusString(node.StatusJSON, "completed_at"),
		)
		if elapsed != "" {
			metaParts = append(metaParts, fmt.Sprintf("elapsed: %s", elapsed))
		}
		if len(metaParts) > 0 {
			b.WriteString(dimStyle.Render(strings.Join(metaParts, " | ")))
			b.WriteString("\n")
		}
	}

	b.WriteString(strings.Repeat("─", m.contentWidth()))
	b.WriteString("\n")
	b.WriteString(detailLabel.Render(fmt.Sprintf("── %s ──", m.detailFile)))
	b.WriteString("\n")

	b.WriteString(m.viewport.View())
	b.WriteString("\n")
	pct := m.viewport.ScrollPercent()
	scrollInfo := fmt.Sprintf(" %d%% ", int(pct*100))
	b.WriteString(dimStyle.Render(scrollInfo))
	b.WriteString("\n")

	return b.String()
}

// wrapText hard-wraps text to fit within the given width.
func wrapText(text string, width int) string {
	if width <= 0 {
		return text
	}
	var result strings.Builder
	for _, line := range strings.Split(text, "\n") {
		for len(line) > width {
			result.WriteString(line[:width])
			result.WriteByte('\n')
			line = line[width:]
		}
		result.WriteString(line)
		result.WriteByte('\n')
	}
	s := result.String()
	if len(s) > 0 && s[len(s)-1] == '\n' {
		s = s[:len(s)-1]
	}
	return s
}

// contentWidth returns the usable content width, using the detected
// terminal width or falling back to 80 if not yet known.
func (m model) contentWidth() int {
	if m.width > 0 {
		return m.width
	}
	return 80
}

func (m *model) syncViewport() {
	headerHeight := 8
	footerHeight := 2
	viewportHeight := max(m.height-headerHeight-footerHeight, 5)
	w := m.contentWidth()
	if !m.viewportReady {
		m.viewport = viewport.New(w, viewportHeight)
		m.viewportReady = true
	} else {
		m.viewport.Width = w
		m.viewport.Height = viewportHeight
	}
	wrapped := wrapText(m.detailContent, w)
	m.viewport.SetContent(wrapped)
	m.viewport.GotoTop()
}
