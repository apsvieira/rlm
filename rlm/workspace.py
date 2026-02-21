"""Workspace directory management for RLM agents."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkspaceNode:
    """A single agent's workspace directory."""

    path: Path

    @property
    def context_path(self) -> Path:
        return self.path / "context.txt"

    @property
    def answer_path(self) -> Path:
        return self.path / "answer.txt"

    @property
    def subcalls_path(self) -> Path:
        return self.path / "subcalls.json"

    @property
    def vars_path(self) -> Path:
        return self.path / "vars"

    def read_answer(self) -> str | None:
        if self.answer_path.exists():
            return self.answer_path.read_text()
        return None

    def read_subcalls(self) -> list[dict[str, Any]]:
        if self.subcalls_path.exists():
            return json.loads(self.subcalls_path.read_text())
        return []


class Workspace:
    """Manages the RLM workspace directory tree."""

    def __init__(self, root: Path):
        self.root = root

    def create_node(
        self,
        depth: int,
        call_index: int,
        context: str | None = None,
        context_path: Path | None = None,
    ) -> WorkspaceNode:
        node_dir = self.root / f"d{depth}_c{call_index}"
        node_dir.mkdir(parents=True, exist_ok=True)
        (node_dir / "vars").mkdir(exist_ok=True)

        if context is not None:
            (node_dir / "context.txt").write_text(context)
        elif context_path is not None:
            shutil.copy2(context_path, node_dir / "context.txt")

        return WorkspaceNode(path=node_dir)
