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
    def status_path(self) -> Path:
        return self.path / "status.json"

    @property
    def vars_path(self) -> Path:
        return self.path / "vars"

    def read_answer(self) -> str | None:
        if self.answer_path.exists():
            return self.answer_path.read_text()
        return None

    def read_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {}
        try:
            return json.loads(self.status_path.read_text())
        except json.JSONDecodeError:
            return {}

    def write_status(self, **fields: Any) -> None:
        """Merge fields into status.json (creates if missing)."""
        from datetime import datetime, timezone

        existing = self.read_status()
        # Auto-set started_at on first write
        if not existing and "started_at" not in fields:
            fields["started_at"] = datetime.now(timezone.utc).isoformat()
        existing.update(fields)
        self.status_path.write_text(json.dumps(existing, indent=2))

    def read_subcalls(self) -> list[dict[str, Any]]:
        if not self.subcalls_path.exists():
            return []
        try:
            data = json.loads(self.subcalls_path.read_text())
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        # Validate each subcall has the required "goal" key
        valid = []
        for item in data:
            if isinstance(item, dict) and "goal" in item:
                valid.append(item)
        return valid


class Workspace:
    """Manages the RLM workspace directory tree."""

    def __init__(self, root: Path):
        self.root = root
        self._node_counter = 0

    def create_node(
        self,
        depth: int,
        call_index: int,
        context: str | None = None,
        context_path: Path | None = None,
        parent: WorkspaceNode | None = None,
    ) -> WorkspaceNode:
        base = parent.path if parent else self.root
        node_dir = base / f"d{depth}_c{call_index}"
        # Issue 4: Avoid collision — if directory already exists at this base,
        # use the workspace-wide counter to generate a unique name.
        if node_dir.exists():
            self._node_counter += 1
            node_dir = base / f"d{depth}_c{call_index}_{self._node_counter}"
        node_dir.mkdir(parents=True, exist_ok=True)
        (node_dir / "vars").mkdir(exist_ok=True)

        if context is not None:
            (node_dir / "context.txt").write_text(context)
        elif context_path is not None:
            shutil.copy2(context_path, node_dir / "context.txt")

        return WorkspaceNode(path=node_dir)
