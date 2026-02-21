from rlm.prompts import build_decompose_prompt, build_synthesize_prompt


class TestDecomposePrompt:
    def test_includes_workspace_path(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Summarize this",
            current_depth=0,
            max_depth=3,
        )
        assert "/tmp/ws/d0_c0" in prompt

    def test_includes_goal(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Find all bugs",
            current_depth=0,
            max_depth=3,
        )
        assert "Find all bugs" in prompt

    def test_includes_depth_info(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="task",
            current_depth=1,
            max_depth=3,
        )
        assert "depth 1" in prompt
        assert "3" in prompt

    def test_at_max_depth_disables_subcalls(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="task",
            current_depth=3,
            max_depth=3,
        )
        assert "subcalls.json" not in prompt
        assert "answer.txt" in prompt

    def test_below_max_depth_enables_subcalls(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="task",
            current_depth=0,
            max_depth=3,
        )
        assert "subcalls.json" in prompt

    def test_caller_prompt_override(self):
        prompt = build_decompose_prompt(
            workspace_path="/tmp/ws/d1_c0",
            goal="Analyze section 3 for security issues",
            current_depth=1,
            max_depth=3,
            caller_prompt="You are analyzing a security audit report. Focus on CVEs.",
        )
        assert "security audit report" in prompt
        assert "CVEs" in prompt


class TestSynthesizePrompt:
    def test_includes_workspace_path(self):
        prompt = build_synthesize_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Summarize",
            sub_answers={"sub_0": "answer 0", "sub_1": "answer 1"},
        )
        assert "/tmp/ws/d0_c0" in prompt

    def test_includes_sub_answers(self):
        prompt = build_synthesize_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Summarize",
            sub_answers={"section_1": "result A", "section_2": "result B"},
        )
        assert "result A" in prompt
        assert "result B" in prompt

    def test_includes_goal(self):
        prompt = build_synthesize_prompt(
            workspace_path="/tmp/ws/d0_c0",
            goal="Find all bugs",
            sub_answers={"a": "b"},
        )
        assert "Find all bugs" in prompt
