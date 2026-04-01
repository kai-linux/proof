"""Task definition and loading."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Task:
    """A single benchmark task."""

    id: str
    name: str
    description: str
    category: str  # e.g. "code_edit", "refactor", "generation", "analysis"
    prompt: str
    context: dict[str, str] = field(default_factory=dict)  # filename -> content
    expected: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    difficulty: str = "medium"  # easy, medium, hard

    @classmethod
    def from_yaml(cls, path: str | Path) -> Task:
        """Load a task from a YAML file."""
        path = Path(path)
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls(
            id=raw.get("id", path.stem),
            name=raw["name"],
            description=raw.get("description", ""),
            category=raw.get("category", "general"),
            prompt=raw["prompt"],
            context=raw.get("context", {}),
            expected=raw.get("expected", {}),
            scoring=raw.get("scoring", {}),
            tags=raw.get("tags", []),
            difficulty=raw.get("difficulty", "medium"),
        )


def load_tasks(
    tasks_dir: str | Path, filter_ids: list[str] | None = None
) -> list[Task]:
    """Load all tasks from a directory, optionally filtering by ID."""
    tasks_dir = Path(tasks_dir)
    tasks = []
    for path in sorted(tasks_dir.glob("*.yaml")):
        task = Task.from_yaml(path)
        if filter_ids and task.id not in filter_ids:
            continue
        tasks.append(task)
    return tasks
