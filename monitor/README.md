# rlm-monitor

A terminal UI for watching [RLM](../README.md) agent runs in real time.

`rlm-monitor` polls the RLM workspace directory once per second and renders a live tree of every agent node, its state, token usage, cost, and output files. You can drill into any node to read its context, answer, event log, or error.

```
RLM Monitor — rlm_workspace/1740000000
model: sonnet-4-6 | max-depth: 3 | status: running | cost: $0.0182 | calls: 5
Nodes: 5 total | 3 active | 2 done | max depth: 2
────────────────────────────────────────────────────────────────
 d0_c0  ◆ DECOMPOSED  ctx:842B  $0.0021 320↑40↓ tools:4 "Summarise the codebase"
 ├─ d1_c0  ✓ SOLVED     ctx:210B ans:1.2k $0.0062 "Analyse src/auth/"
 ├─ d1_c1  ● WORKING    ctx:195B         $0.0041 "Analyse src/api/"
 └─ d1_c2  ● WORKING    ctx:203B                 "Analyse tests/"

[j/k] navigate  [enter] detail  [r] refresh  [q] quit
```

---

## Table of Contents

- [Build and Install](#build-and-install)
- [Usage](#usage)
- [Keyboard Controls](#keyboard-controls)
- [Display Layout](#display-layout)
  - [Header](#header)
  - [Stats bar](#stats-bar)
  - [Tree view](#tree-view)
  - [Detail pane](#detail-pane)
- [Workspace Format](#workspace-format)
- [Development](#development)

---

## Build and Install

Requires Go ≥ 1.25.

```bash
cd monitor

# Build the binary
make build
# produces: ./rlm-monitor

# Or build directly with go
go build -o rlm-monitor .
```

To install system-wide, copy the binary to your `PATH`:

```bash
cp rlm-monitor ~/.local/bin/
```

**Dependencies** (managed by `go.mod`):

| Module | Purpose |
|--------|---------|
| `github.com/charmbracelet/bubbletea` | Elm-architecture TUI framework |
| `github.com/charmbracelet/bubbles` | Scrollable viewport widget |
| `github.com/charmbracelet/lipgloss` | Terminal styling and colour |

---

## Usage

```bash
# Auto-detect the latest workspace in ./rlm_workspace/
rlm-monitor

# Point at a specific workspace
rlm-monitor rlm_workspace/1740000000

# Watch from another directory
rlm-monitor /abs/path/to/workspace
```

The monitor works with both running and completed workspaces. It starts cleanly even if the workspace directory does not exist yet — it will appear once RLM creates it.

**Tip:** open a second terminal *before* or immediately after launching `rlm`, then run `rlm-monitor` with the workspace path printed in the RLM output.

---

## Keyboard Controls

### Tree view (default)

| Key | Action |
|-----|--------|
| `j` / `↓` | Move cursor down |
| `k` / `↑` | Move cursor up |
| `enter` | Open detail pane for the selected node |
| `r` | Force refresh (workspace is re-scanned immediately) |
| `q` / `ctrl+c` | Quit |

### Detail pane

| Key | Action |
|-----|--------|
| `↑` / `↓` | Scroll content up / down |
| `pgup` / `pgdown` | Scroll one page up / down |
| `home` / `end` | Jump to top / bottom |
| `a` | Show `answer.txt` |
| `c` | Show `context.txt` |
| `s` | Show `subcalls.json` |
| `e` | Show `error.txt` |
| `l` | Show formatted event log (`events.jsonl`) |
| `f` | Show output files list |
| `esc` | Return to tree view |
| `q` / `ctrl+c` | Quit |

---

## Display Layout

### Header

```
RLM Monitor — rlm_workspace/1740000000
model: sonnet-4-6 | max-depth: 3 | status: running | cost: $0.0523 | calls: 7
```

The first line shows the workspace path. The second line comes from `run.json` and updates as the run progresses. Cost and call count appear only once they are non-zero.

### Stats bar

```
Nodes: 7 total | 3 active | 4 done | max depth: 2
```

- **active** = nodes in `working` or `decomposed` state
- **done** = nodes in `solved` or `synthesized` state
- Errors are shown separately: `| 1 error`

### Tree view

Each node occupies one line:

```
 [indent][prefix][name]  [state]  [ctx:<size>] [ans:<size>] [$cost] [↑in↓out] [tools:<n>] [files:<n>] ["goal snippet"]
```

| Column | Description |
|--------|-------------|
| Indent + prefix | Box-drawing tree (`├─`, `└─`) showing parent/child relationships |
| Name | Directory name, e.g. `d0_c0`, `d1_c2` |
| State | Coloured icon + label (see below) |
| `ctx:` | Size of `context.txt` |
| `ans:` | Size of `answer.txt` (shown only if present) |
| `$cost` | Aggregated cost from `events.jsonl` (live) or `status.json` |
| `↑in↓out` | Live input/output token counts from event log |
| `tools:N` | Number of tool calls (from `events.jsonl`) |
| `files:N` | Number of agent output files (non-framework files in the node directory) |
| `"goal…"` | First 40 characters of the node's goal (from `subcalls.json` or `status.json`) |

The selected node is highlighted. Token counts (`↑`/`↓`) are shown only when live event data is available; otherwise only cost from `status.json` is shown.

#### Node states

| Icon | Label | Colour | Meaning |
|------|-------|--------|---------|
| `●` | `WORKING` | Orange | Agent is running (no answer or subcalls yet) |
| `◆` | `DECOMPOSED` | Blue | Agent wrote `subcalls.json`; children are running |
| `✓` | `SOLVED` | Green | Agent wrote `answer.txt` directly (no decomposition) |
| `✦` | `SYNTHESIZED` | Purple | All children done; parent wrote final `answer.txt` |
| `✗` | `ERROR` | Red | `error.txt` present or `status.json` state is `"error"` |

### Detail pane

Opened by pressing `enter` on a node. Shows:

1. **Node header** — name, depth, call index, state
2. **Files summary** — which framework files are present and their sizes; `vars/` file count
3. **Output files** — non-framework files created by the agent
4. **Goal** — full goal text
5. **Cost / tokens / elapsed** — from `status.json`
6. **Scrollable content** — the selected file (`answer.txt` by default)
7. **Scroll percentage** — shown at the bottom

Long lines are word-wrapped to fit the terminal width.

---

## Workspace Format

The monitor reads the standard RLM workspace layout (shared with the Python orchestrator):

```
<workspace-root>/
├── run.json                 ← Run-level manifest
└── d0_c0/                   ← Root node
    ├── context.txt          ← Agent briefing (input)
    ├── answer.txt           ← Agent answer (output, if solved)
    ├── subcalls.json        ← Sub-task list (output, if decomposed)
    ├── status.json          ← Live state metadata
    ├── events.jsonl         ← Append-only event stream
    ├── error.txt            ← Error message (if failed)
    ├── vars/                ← Agent scratch files
    └── d1_c0/               ← Child node (same structure)
        └── ...
```

Node directories match `d<depth>_c<callindex>` (with optional `_<counter>` suffix for collision avoidance). The monitor recursively scans all matching subdirectories to build the tree.

### State inference

The monitor determines a node's state from two sources, with `status.json` taking priority:

1. **File presence** (fallback):
   - Only `context.txt` → `Working`
   - `context.txt` + `subcalls.json` → `Decomposed`
   - `context.txt` + `answer.txt` → `Solved`
   - `context.txt` + `subcalls.json` + `answer.txt` → `Synthesized`

2. **`status.json` `state` field** (authoritative): `working`, `decomposed`, `solved`, `synthesized`, `error`

### run.json

```json
{
  "goal":          "Summarize the document",
  "model":         "claude-sonnet-4-6",
  "max_depth":     3,
  "status":        "running",
  "workspace":     "rlm_workspace/1740000000",
  "started_at":    "2026-02-21T12:00:00Z",
  "completed_at":  "2026-02-21T12:05:00Z",
  "total_cost_usd": 0.0523,
  "total_calls":   7
}
```

### events.jsonl

One JSON object per line. The monitor reads this to compute live token counts and cost before `status.json` is finalized:

```jsonl
{"ts":"...","phase":"decompose","type":"system","subtype":"init"}
{"ts":"...","phase":"decompose","type":"tool_use","name":"Read","input":{"file_path":"context.txt"}}
{"ts":"...","phase":"decompose","type":"tool_result","is_error":false,"content_length":842}
{"ts":"...","phase":"decompose","type":"text","length":210,"preview":"I'll analyse..."}
{"ts":"...","phase":"decompose","type":"result","cost_usd":0.0042,"input_tokens":1200,"output_tokens":450,"duration_ms":8340,"num_turns":4}
```

The formatted event log view (key `l` in detail pane) renders this as a human-readable activity feed with timestamps, phases, and summaries.

---

## Development

### Running tests

```bash
cd monitor
make test
# or
go test ./...
```

The test suite covers:

| File | Coverage |
|------|----------|
| `workspace_test.go` | `ScanWorkspace`, state inference, `events.jsonl` parsing, `run.json` reading, output file discovery, live token aggregation |
| `smoke_test.go` | Full render cycle: tree view, detail pane, error state, run manifest header, cost/timing display |
| `smoke_progress_test.go` | Live state transitions as files appear on disk |
| `edge_test.go` | Edge cases: empty workspace, missing files, malformed JSON |

### All make targets

```bash
make all     # fmt + vet + lint + test + build
make build   # go build -o rlm-monitor .
make fmt     # go fmt ./...
make vet     # go vet ./...
make lint    # golangci-lint run ./...
make test    # go test ./...
make clean   # rm -f rlm-monitor
```

### Architecture

The monitor follows the [Bubbletea](https://github.com/charmbracelet/bubbletea) Elm architecture:

| File | Responsibility |
|------|---------------|
| `main.go` | Entry point; resolves workspace path (argument or auto-detect latest); starts the Bubbletea program |
| `model.go` | `model` struct, `Init` / `Update` / `View`; keyboard handling; tree and detail rendering; viewport management |
| `workspace.go` | `ScanWorkspace` — recursive directory walk; `Node` / `NodeState` types; stats computation; helper functions (`LiveTokens`, `ToolUseCount`, `FormatEventLog`, `TreePrefix`, `FormatSize`, `FormatElapsed`) |

The model polls the workspace every **1 second** via a `tickMsg`. Pressing `r` triggers an immediate refresh on top of the tick schedule.

The detail pane uses the `bubbles/viewport` widget for scrollable content. Long lines are hard-wrapped by `wrapText` before being set as viewport content, so every line fits within the detected terminal width.
