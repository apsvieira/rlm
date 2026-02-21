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
        import json
        subcalls = [
            {"goal": "summarize section 1", "context_file": "vars/chunk_0.txt"},
            {"goal": "summarize section 2", "context_file": "vars/chunk_1.txt"},
        ]
        (node.path / "subcalls.json").write_text(json.dumps(subcalls))
        result = node.read_subcalls()
        assert len(result) == 2
        assert result[0]["goal"] == "summarize section 1"
