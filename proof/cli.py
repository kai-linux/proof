"""CLI entry point for Proof."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .config import load_run_config
from .reporter import generate_markdown_report, summarize, write_reports
from .runner import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="proof",
        description="Proof — a reliability harness for agentic LLM systems.",
    )
    parser.add_argument("--version", action="version", version=f"proof {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run
    run_parser = subparsers.add_parser("run", help="Run a benchmark")
    run_parser.add_argument("config", help="Path to run config YAML")
    run_parser.add_argument(
        "-o", "--output", default="reports", help="Output directory (default: reports)"
    )
    run_parser.add_argument(
        "--stdout", action="store_true", help="Also print markdown report to stdout"
    )

    # list
    list_parser = subparsers.add_parser("list", help="List available tasks")
    list_parser.add_argument(
        "-d", "--dir", default="tasks", help="Tasks directory (default: tasks)"
    )

    # report
    report_parser = subparsers.add_parser("report", help="Regenerate report from JSON")
    report_parser.add_argument("json_file", help="Path to JSON results file")

    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "list":
        _cmd_list(args)
    elif args.command == "report":
        _cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_run(args: argparse.Namespace) -> None:
    """Execute a benchmark run."""
    run_config = load_run_config(args.config)
    run_config.output_dir = args.output

    print(f"Proof v{__version__}")
    print(f"Run: {run_config.name}")
    print(f"Configs: {', '.join(c.name for c in run_config.configs)}")
    print(f"Tasks dir: {run_config.tasks_dir}")
    print(f"Iterations: {run_config.iterations}")
    print(f"Max retries: {run_config.max_retries}")
    if run_config.fallback_config:
        print(f"Fallback: {run_config.fallback_config}")
    print()

    results = asyncio.run(run_benchmark(run_config))
    summary = summarize(results, name=run_config.name)

    paths = write_reports(summary, results, run_config.output_dir)
    print()
    print("Reports written:")
    for fmt, path in paths.items():
        print(f"  {fmt}: {path}")

    if args.stdout:
        print()
        print(generate_markdown_report(summary, results))

    # Exit with failure if any tasks failed
    if summary.total_failed > 0:
        sys.exit(1)


def _cmd_list(args: argparse.Namespace) -> None:
    """List available tasks."""
    from .task import load_tasks

    tasks = load_tasks(args.dir)
    if not tasks:
        print(f"No tasks found in {args.dir}/")
        return

    print(f"{'ID':30s} {'Category':15s} {'Difficulty':10s} Name")
    print("-" * 80)
    for t in tasks:
        print(f"{t.id:30s} {t.category:15s} {t.difficulty:10s} {t.name}")


def _cmd_report(args: argparse.Namespace) -> None:
    """Regenerate a markdown report from existing JSON results."""
    import json
    from .cost import TokenUsage
    from .runner import TaskResult
    from .scorer import ScoreResult
    from .taxonomy import FailureCategory

    path = Path(args.json_file)
    with open(path) as f:
        data = json.load(f)

    results = []
    for r in data.get("results", []):
        results.append(TaskResult(
            task_id=r["task_id"],
            config_name=r["config_name"],
            iteration=r["iteration"],
            output="",
            score=ScoreResult(
                passed=r["passed"],
                score=r["score"],
                failure_category=FailureCategory(r["failure_category"]),
            ),
            latency_ms=r["latency_ms"],
            tokens=TokenUsage(
                input_tokens=r.get("input_tokens", 0),
                output_tokens=r.get("output_tokens", 0),
            ),
            retries=r.get("retries", 0),
            used_fallback=r.get("used_fallback", False),
            error=r.get("error"),
        ))

    summary = summarize(results, name=data.get("name", ""))
    md = generate_markdown_report(summary, results)
    print(md)


if __name__ == "__main__":
    main()
