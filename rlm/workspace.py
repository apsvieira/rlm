"""Workspace directory management for RLM agents."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FRAMEWORK_FILES = {"answer.txt", "context.txt", "subcalls.json", "status.json", "events.jsonl", "error.txt"}


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

    @property
    def events_path(self) -> Path:
        return self.path / "events.jsonl"

    def append_event(self, event: dict[str, Any]) -> None:
        """Append a timestamped event to events.jsonl."""
        from datetime import datetime, timezone

        event.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with self.events_path.open("a") as f:
            f.write(json.dumps(event) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        """Read all events from events.jsonl."""
        if not self.events_path.exists():
            return []
        events = []
        for line in self.events_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    @property
    def error_path(self) -> Path:
        return self.path / "error.txt"

    def write_error(self, message: str) -> None:
        """Write error.txt and update status.json to error state."""
        from datetime import datetime, timezone

        self.error_path.write_text(message)
        self.write_status(state="error", completed_at=datetime.now(timezone.utc).isoformat())

    def discover_output_files(self) -> list[Path]:
        """Return sorted list of non-framework files in this node's directory.

        Skips directories and known framework files. Non-recursive.
        """
        if not self.path.exists():
            return []
        files = []
        for entry in self.path.iterdir():
            if entry.is_dir():
                continue
            if entry.name in FRAMEWORK_FILES:
                continue
            files.append(entry.resolve())
        return sorted(files)

    def collect_all_output_files(self) -> list[Path]:
        """Collect output files from this node and all child nodes recursively."""
        files = self.discover_output_files()
        for child_dir in sorted(self.path.glob("d*_c*")):
            if child_dir.is_dir():
                child_node = WorkspaceNode(path=child_dir)
                files.extend(child_node.collect_all_output_files())
        return files

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

    def write_run_manifest(self, goal: str, model: str, max_depth: int, status: str) -> None:
        """Write run.json at workspace root."""
        from datetime import datetime, timezone

        self.root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "goal": goal,
            "model": model,
            "max_depth": max_depth,
            "status": status,
            "workspace": str(self.root),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.root / "run.json").write_text(json.dumps(manifest, indent=2))

    def update_run_manifest(self, **fields: Any) -> None:
        """Merge fields into existing run.json."""
        from datetime import datetime, timezone

        manifest_path = self.root / "run.json"
        existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        if "status" in fields and fields["status"] in ("completed", "error"):
            fields.setdefault("completed_at", datetime.now(timezone.utc).isoformat())
        existing.update(fields)
        manifest_path.write_text(json.dumps(existing, indent=2))
