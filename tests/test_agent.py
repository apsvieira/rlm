



from rlm.agent import RLMConfig, get_tools_for_depth


class TestToolSelection:
    def test_below_max_depth_includes_write_tools(self):
        tools = get_tools_for_depth(current_depth=0, max_depth=3)
        assert "Read" in tools
        assert "Write" in tools
        assert "Grep" in tools
        assert "Glob" in tools
        assert "Edit" in tools
        assert "Bash" in tools

    def test_at_max_depth_same_tools(self):
        tools = get_tools_for_depth(current_depth=3, max_depth=3)
        assert "Read" in tools
        assert "Write" in tools

    def test_tools_never_include_task(self):
        tools = get_tools_for_depth(current_depth=0, max_depth=3)
        assert "Task" not in tools


class TestRLMConfig:
    def test_defaults(self):
        config = RLMConfig(goal="test")
        assert config.model == "claude-sonnet-4-6"
        assert config.max_depth == 3

    def test_custom_values(self):
        config = RLMConfig(goal="test", model="claude-haiku-4-5-20251001", max_depth=1)
        assert config.model == "claude-haiku-4-5-20251001"
        assert config.max_depth == 1


class TestStatusWriting:
    """Test that rlm_call writes status.json at key points.

    These are workspace-level tests that verify status file contents
    after simulating what rlm_call would write. We don't call rlm_call
    directly (that requires a running agent) — we test the write_status
    integration with the workspace.
    """

    def test_initial_status_on_node_creation(self, tmp_path):
        from rlm.workspace import Workspace

        ws = Workspace(root=tmp_path / "ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        node.write_status(state="working", depth=0, call_index=0, goal="test goal")
        status = node.read_status()
        assert status["state"] == "working"
        assert "started_at" in status

    def test_status_transitions(self, tmp_path):
        from rlm.workspace import Workspace

        ws = Workspace(root=tmp_path / "ws")
        node = ws.create_node(depth=0, call_index=0, context="hello")
        # working -> decomposed -> synthesized
        node.write_status(state="working", depth=0, call_index=0, goal="test")
        node.write_status(state="decomposed")
        assert node.read_status()["state"] == "decomposed"
        node.write_status(state="synthesized", completed_at="2026-02-21T00:00:00Z")
        status = node.read_status()
        assert status["state"] == "synthesized"
        assert status["completed_at"] == "2026-02-21T00:00:00Z"


class TestRunAgentPhaseSignature:
    """Test that run_agent_phase accepts node and phase_label parameters."""

    def test_accepts_node_and_phase_label_params(self):
        import inspect

        from rlm.agent import run_agent_phase

        sig = inspect.signature(run_agent_phase)
        params = list(sig.parameters.keys())
        assert "node" in params
        assert "phase_label" in params

    def test_node_defaults_to_none(self):
        import inspect

        from rlm.agent import run_agent_phase

        sig = inspect.signature(run_agent_phase)
        assert sig.parameters["node"].default is None

    def test_phase_label_defaults_to_none(self):
        import inspect

        from rlm.agent import run_agent_phase

        sig = inspect.signature(run_agent_phase)
        assert sig.parameters["phase_label"].default is None


class TestRLMResultOutputFiles:
    def test_output_files_default_empty(self):
        from pathlib import Path

        from rlm.agent import RLMResult

        result = RLMResult(answer="test", workspace_root=Path("/tmp"))
        assert result.output_files == []

    def test_output_files_with_values(self):
        from pathlib import Path

        from rlm.agent import RLMResult

        files = [Path("/tmp/report.md"), Path("/tmp/data.json")]
        result = RLMResult(answer="test", workspace_root=Path("/tmp"), output_files=files)
        assert len(result.output_files) == 2
        assert result.output_files[0] == Path("/tmp/report.md")
