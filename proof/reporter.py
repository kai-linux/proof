"""Report generation — markdown, JSON, and HTML summaries."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runner import TaskResult
from .taxonomy import CATEGORY_DESCRIPTIONS, FailureCategory


@dataclass
class RunSummary:
    """Aggregated summary of a benchmark run."""

    name: str
    timestamp: str
    total_tasks: int
    total_passed: int
    total_failed: int
    success_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    by_config: dict[str, dict[str, Any]]
    by_category: dict[str, int]
    by_task: dict[str, dict[str, Any]]


def summarize(results: list[TaskResult], name: str = "") -> RunSummary:
    """Build a RunSummary from a list of TaskResults."""
    total = len(results)
    passed = sum(1 for r in results if r.score.passed)
    latencies = sorted(r.latency_ms for r in results)

    # By config
    by_config: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        by_config[r.config_name].append(r)

    config_summaries = {}
    for cfg_name, cfg_results in by_config.items():
        cfg_passed = sum(1 for r in cfg_results if r.score.passed)
        cfg_latencies = sorted(r.latency_ms for r in cfg_results)
        config_summaries[cfg_name] = {
            "total": len(cfg_results),
            "passed": cfg_passed,
            "failed": len(cfg_results) - cfg_passed,
            "success_rate": cfg_passed / len(cfg_results) if cfg_results else 0,
            "avg_latency_ms": sum(cfg_latencies) / len(cfg_latencies) if cfg_latencies else 0,
            "p95_latency_ms": _percentile(cfg_latencies, 0.95),
            "total_cost_usd": sum(r.cost_usd for r in cfg_results),
            "retries": sum(r.retries for r in cfg_results),
            "fallbacks": sum(1 for r in cfg_results if r.used_fallback),
        }

    # By failure category
    by_category: dict[str, int] = defaultdict(int)
    for r in results:
        by_category[r.score.failure_category.value] += 1

    # By task
    by_task: dict[str, dict[str, Any]] = {}
    task_groups: dict[str, list[TaskResult]] = defaultdict(list)
    for r in results:
        task_groups[r.task_id].append(r)
    for task_id, task_results in task_groups.items():
        t_passed = sum(1 for r in task_results if r.score.passed)
        by_task[task_id] = {
            "total": len(task_results),
            "passed": t_passed,
            "success_rate": t_passed / len(task_results) if task_results else 0,
        }

    return RunSummary(
        name=name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_tasks=total,
        total_passed=passed,
        total_failed=total - passed,
        success_rate=passed / total if total else 0,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0,
        p95_latency_ms=_percentile(latencies, 0.95),
        total_cost_usd=sum(r.cost_usd for r in results),
        total_input_tokens=sum(r.tokens.input_tokens for r in results),
        total_output_tokens=sum(r.tokens.output_tokens for r in results),
        by_config=config_summaries,
        by_category=dict(by_category),
        by_task=by_task,
    )


def generate_markdown_report(summary: RunSummary, results: list[TaskResult]) -> str:
    """Generate a markdown report."""
    lines = [
        f"# Proof Benchmark Report: {summary.name}",
        f"",
        f"**Run:** {summary.timestamp}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total tasks | {summary.total_tasks} |",
        f"| Passed | {summary.total_passed} |",
        f"| Failed | {summary.total_failed} |",
        f"| Success rate | {summary.success_rate:.1%} |",
        f"| Avg latency | {summary.avg_latency_ms:.0f}ms |",
        f"| P95 latency | {summary.p95_latency_ms:.0f}ms |",
        f"| Total cost | ${summary.total_cost_usd:.4f} |",
        f"| Total tokens | {summary.total_input_tokens + summary.total_output_tokens:,} |",
        f"",
        f"## By Configuration",
        f"",
        f"| Config | Pass | Fail | Rate | Avg Latency | Cost | Retries | Fallbacks |",
        f"|--------|------|------|------|-------------|------|---------|-----------|",
    ]

    for cfg_name, cfg in summary.by_config.items():
        lines.append(
            f"| {cfg_name} | {cfg['passed']} | {cfg['failed']} | "
            f"{cfg['success_rate']:.1%} | {cfg['avg_latency_ms']:.0f}ms | "
            f"${cfg['total_cost_usd']:.4f} | {cfg['retries']} | {cfg['fallbacks']} |"
        )

    lines.extend([
        f"",
        f"## Failure Taxonomy",
        f"",
        f"| Category | Count | Description |",
        f"|----------|-------|-------------|",
    ])

    for cat_val, count in sorted(summary.by_category.items(), key=lambda x: -x[1]):
        cat = FailureCategory(cat_val)
        desc = CATEGORY_DESCRIPTIONS.get(cat, "")
        lines.append(f"| {cat_val} | {count} | {desc} |")

    lines.extend([
        f"",
        f"## By Task",
        f"",
        f"| Task | Pass | Total | Rate |",
        f"|------|------|-------|------|",
    ])

    for task_id, t in sorted(summary.by_task.items()):
        lines.append(f"| {task_id} | {t['passed']} | {t['total']} | {t['success_rate']:.1%} |")

    lines.extend([
        f"",
        f"## Detailed Results",
        f"",
    ])

    for r in results:
        status = "PASS" if r.score.passed else "FAIL"
        lines.append(
            f"- **[{status}]** `{r.task_id}` / `{r.config_name}` (iter {r.iteration}) "
            f"— {r.score.failure_category.value}, {r.latency_ms:.0f}ms, "
            f"{r.tokens.total_tokens} tokens, ${r.cost_usd:.6f}"
        )
        if r.error:
            lines.append(f"  - Error: {r.error}")

    lines.append("")
    return "\n".join(lines)


def generate_json_report(summary: RunSummary, results: list[TaskResult]) -> str:
    """Generate a JSON report."""
    data = {
        "name": summary.name,
        "timestamp": summary.timestamp,
        "summary": {
            "total_tasks": summary.total_tasks,
            "passed": summary.total_passed,
            "failed": summary.total_failed,
            "success_rate": summary.success_rate,
            "avg_latency_ms": round(summary.avg_latency_ms, 1),
            "p95_latency_ms": round(summary.p95_latency_ms, 1),
            "total_cost_usd": summary.total_cost_usd,
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
        },
        "by_config": summary.by_config,
        "by_category": summary.by_category,
        "by_task": summary.by_task,
        "results": [r.to_dict() for r in results],
    }
    return json.dumps(data, indent=2)


def write_reports(
    summary: RunSummary,
    results: list[TaskResult],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write all report formats to disk. Returns paths to generated files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prefix = f"{summary.name}_{ts}" if summary.name else ts

    paths = {}

    md_path = output_dir / f"{prefix}.md"
    md_path.write_text(generate_markdown_report(summary, results))
    paths["markdown"] = md_path

    json_path = output_dir / f"{prefix}.json"
    json_path.write_text(generate_json_report(summary, results))
    paths["json"] = json_path

    return paths


def _percentile(sorted_values: list[float], p: float) -> float:
    """Calculate percentile from a sorted list."""
    if not sorted_values:
        return 0.0
    idx = int(len(sorted_values) * p)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]
