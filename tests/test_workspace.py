import json
from pathlib import Path

from rlm.workspace import Workspace


class TestWorkspaceCreation:
    def test_creates_root_directory(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.path.exists()
        assert (node.path / "vars").is_dir()

    def test_creates_context_file_from_string(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello world")
        assert (node.path / "context.txt").read_text() == "hello world"

    def test_creates_context_file_from_path(self, tmp_path: Path):
        ctx_file = tmp_path / "input.txt"
        ctx_file.write_text("file content")
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context_path=ctx_file)
        assert (node.path / "context.txt").read_text() == "file content"

    def test_node_directory_naming(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=2, call_index=3)
        assert node.path.name == "d2_c3"

    def test_read_answer(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        (node.path / "answer.txt").write_text("the answer")
        assert node.read_answer() == "the answer"

    def test_read_answer_missing_returns_none(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.read_answer() is None

    def test_read_subcalls_empty(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.read_subcalls() == []

    def test_read_subcalls_from_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        subcalls = [
            {"goal": "summarize section 1", "context_file": "vars/chunk_0.txt"},
            {"goal": "summarize section 2", "context_file": "vars/chunk_1.txt"},
        ]
        (node.path / "subcalls.json").write_text(json.dumps(subcalls))
        result = node.read_subcalls()
        assert len(result) == 2
        assert result[0]["goal"] == "summarize section 1"

    def test_nested_node_avoids_collision(self, tmp_path: Path):
        """Issue 4: Two parents at depth 1 creating depth 2 children must not collide."""
        ws = Workspace(root=tmp_path / "rlm_ws")
        parent_a = ws.create_node(depth=1, call_index=0, context="parent A")
        parent_b = ws.create_node(depth=1, call_index=1, context="parent B")
        child_a = ws.create_node(depth=2, call_index=0, context="child of A", parent=parent_a)
        child_b = ws.create_node(depth=2, call_index=0, context="child of B", parent=parent_b)
        assert child_a.path != child_b.path
        assert (child_a.path / "context.txt").read_text() == "child of A"
        assert (child_b.path / "context.txt").read_text() == "child of B"

    def test_read_subcalls_malformed_json(self, tmp_path: Path):
        """Issue 5: Malformed JSON in subcalls.json should return empty list."""
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        (node.path / "subcalls.json").write_text("not valid json {{{")
        assert node.read_subcalls() == []

    def test_read_subcalls_missing_goal_key(self, tmp_path: Path):
        """Issue 5: Subcall entries without 'goal' key should be filtered out."""
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        subcalls = [
            {"goal": "valid entry", "context_file": "vars/sub_0.txt"},
            {"no_goal_key": "invalid entry"},
        ]
        (node.path / "subcalls.json").write_text(json.dumps(subcalls))
        result = node.read_subcalls()
        assert len(result) == 1
        assert result[0]["goal"] == "valid entry"


class TestNodeStatus:
    def test_write_status_creates_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test goal")
        status = json.loads((node.path / "status.json").read_text())
        assert status["state"] == "working"
        assert status["depth"] == 0
        assert status["call_index"] == 0
        assert status["goal"] == "test goal"
        assert "started_at" in status

    def test_write_status_preserves_existing_fields(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test")
        node.write_status(state="decomposed")
        status = json.loads((node.path / "status.json").read_text())
        assert status["state"] == "decomposed"
        assert status["goal"] == "test"  # preserved from first write

    def test_write_status_with_cost(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(
            state="solved",
            depth=0,
            call_index=0,
            goal="test",
            cost_usd=0.0042,
            input_tokens=1200,
            output_tokens=450,
        )
        status = json.loads((node.path / "status.json").read_text())
        assert status["cost_usd"] == 0.0042
        assert status["input_tokens"] == 1200
        assert status["output_tokens"] == 450

    def test_read_status_missing_returns_empty_dict(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        assert node.read_status() == {}


class TestNodeError:
    def test_write_error_creates_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_error("Agent produced neither answer.txt nor subcalls.json")
        assert (node.path / "error.txt").read_text() == "Agent produced neither answer.txt nor subcalls.json"

    def test_write_error_updates_status(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test")
        node.write_error("something broke")
        status = node.read_status()
        assert status["state"] == "error"
        assert "completed_at" in status


class TestEventLog:
    def test_append_event_creates_file(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.append_event({"type": "tool_use", "name": "Read"})
        assert node.events_path.exists()
        lines = node.events_path.read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["type"] == "tool_use"
        assert event["name"] == "Read"
        assert "ts" in event

    def test_append_event_multiple(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.append_event({"type": "tool_use", "name": "Read"})
        node.append_event({"type": "tool_result", "is_error": False, "content_length": 100})
        node.append_event({"type": "text", "length": 50, "preview": "hello"})
        lines = node.events_path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_append_event_preserves_custom_ts(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.append_event({"type": "text", "ts": "2026-01-01T00:00:00Z"})
        event = json.loads(node.events_path.read_text().strip())
        assert event["ts"] == "2026-01-01T00:00:00Z"

    def test_read_events(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.append_event({"type": "tool_use", "name": "Read"})
        node.append_event({"type": "result", "cost_usd": 0.005})
        events = node.read_events()
        assert len(events) == 2
        assert events[0]["type"] == "tool_use"
        assert events[1]["cost_usd"] == 0.005

    def test_read_events_empty(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        assert node.read_events() == []

    def test_read_events_handles_malformed_lines(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.events_path.write_text('{"type":"tool_use"}\nnot valid json\n{"type":"text"}\n')
        events = node.read_events()
        assert len(events) == 2
        assert events[0]["type"] == "tool_use"
        assert events[1]["type"] == "text"

    def test_append_event_with_phase(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.append_event({"type": "tool_use", "name": "Glob", "phase": "decompose"})
        event = json.loads(node.events_path.read_text().strip())
        assert event["phase"] == "decompose"


class TestRunManifest:
    def test_write_run_manifest(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        ws.write_run_manifest(
            goal="Summarize the document",
            model="claude-sonnet-4-6",
            max_depth=3,
            status="running",
        )
        manifest = json.loads((tmp_path / "rlm_ws" / "run.json").read_text())
        assert manifest["goal"] == "Summarize the document"
        assert manifest["model"] == "claude-sonnet-4-6"
        assert manifest["max_depth"] == 3
        assert manifest["status"] == "running"
        assert "started_at" in manifest
        assert manifest["workspace"] == str(tmp_path / "rlm_ws")

    def test_update_run_manifest(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        ws.write_run_manifest(goal="test", model="m", max_depth=1, status="running")
        ws.update_run_manifest(status="completed", total_cost_usd=0.05, total_calls=3)
        manifest = json.loads((tmp_path / "rlm_ws" / "run.json").read_text())
        assert manifest["status"] == "completed"
        assert manifest["total_cost_usd"] == 0.05
        assert manifest["total_calls"] == 3
        assert "completed_at" in manifest


class TestDiscoverOutputFiles:
    def test_excludes_framework_files(self, tmp_path: Path):
        from rlm.workspace import FRAMEWORK_FILES

        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        # Create framework files
        for name in FRAMEWORK_FILES:
            (node.path / name).write_text("framework")
        # Create output files
        (node.path / "report.md").write_text("analysis")
        (node.path / "data.json").write_text("{}")
        result = node.discover_output_files()
        names = [p.name for p in result]
        assert "report.md" in names
        assert "data.json" in names
        for fw in FRAMEWORK_FILES:
            assert fw not in names

    def test_returns_absolute_paths(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        (node.path / "output.txt").write_text("data")
        result = node.discover_output_files()
        assert len(result) == 1
        assert result[0].is_absolute()

    def test_excludes_directories(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        (node.path / "subdir").mkdir()
        (node.path / "output.txt").write_text("data")
        result = node.discover_output_files()
        names = [p.name for p in result]
        assert "subdir" not in names
        assert "vars" not in names
        assert "output.txt" in names

    def test_empty_workspace(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        node = ws.create_node(depth=0, call_index=0)
        # Only framework files (vars/ dir) exist
        result = node.discover_output_files()
        assert result == []

    def test_collect_all_includes_child_nodes(self, tmp_path: Path):
        ws = Workspace(root=tmp_path / "rlm_ws")
        parent = ws.create_node(depth=0, call_index=0, context="parent")
        child = ws.create_node(depth=1, call_index=0, context="child", parent=parent)
        (parent.path / "parent_report.md").write_text("parent data")
        (child.path / "child_report.md").write_text("child data")
        result = parent.collect_all_output_files()
        names = [p.name for p in result]
        assert "parent_report.md" in names
        assert "child_report.md" in names
