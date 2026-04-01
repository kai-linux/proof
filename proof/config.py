"""Configuration loading for Proof runs."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelConfig:
    """Configuration for a single model/prompt variant."""

    name: str
    provider: str  # "anthropic", "openai", "local"
    model: str  # e.g. "claude-sonnet-4-20250514", "gpt-4o"
    api_key_env: str = ""  # env var name for API key
    temperature: float = 0.0
    max_tokens: int = 4096
    system_prompt: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunConfig:
    """Configuration for a benchmark run."""

    name: str
    description: str = ""
    tasks_dir: str = "tasks"
    task_filter: list[str] = field(default_factory=list)  # empty = all
    configs: list[ModelConfig] = field(default_factory=list)
    iterations: int = 1
    timeout_seconds: int = 120
    output_dir: str = "reports"
    parallel: bool = False
    max_retries: int = 0
    fallback_config: str | None = None  # name of fallback ModelConfig


def load_run_config(path: str | Path) -> RunConfig:
    """Load a run configuration from a YAML file."""
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    configs = []
    for c in raw.get("configs", []):
        configs.append(ModelConfig(**c))

    return RunConfig(
        name=raw["name"],
        description=raw.get("description", ""),
        tasks_dir=raw.get("tasks_dir", "tasks"),
        task_filter=raw.get("task_filter", []),
        configs=configs,
        iterations=raw.get("iterations", 1),
        timeout_seconds=raw.get("timeout_seconds", 120),
        output_dir=raw.get("output_dir", "reports"),
        parallel=raw.get("parallel", False),
        max_retries=raw.get("max_retries", 0),
        fallback_config=raw.get("fallback_config"),
    )
