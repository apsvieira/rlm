

from rlm.agent import get_tools_for_depth, RLMConfig


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
