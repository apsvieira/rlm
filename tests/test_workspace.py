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
