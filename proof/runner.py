"""Task runner — executes tasks against model configurations."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

from .config import ModelConfig, RunConfig
from .cost import TokenUsage
from .scorer import RuleScorer, ScoreResult
from .task import Task, load_tasks
from .taxonomy import FailureCategory


@dataclass
class TaskResult:
    """Result of running a single task against a single config."""

    task_id: str
    config_name: str
    iteration: int
    output: str
    score: ScoreResult
    latency_ms: float
    tokens: TokenUsage
    retries: int = 0
    used_fallback: bool = False
    error: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        model = self.raw_response.get("model", "")
        return self.tokens.estimate_cost(model)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "config_name": self.config_name,
            "iteration": self.iteration,
            "passed": self.score.passed,
            "score": self.score.score,
            "failure_category": self.score.failure_category.value,
            "latency_ms": round(self.latency_ms, 1),
            "input_tokens": self.tokens.input_tokens,
            "output_tokens": self.tokens.output_tokens,
            "total_tokens": self.tokens.total_tokens,
            "cost_usd": self.cost_usd,
            "retries": self.retries,
            "used_fallback": self.used_fallback,
            "error": self.error,
        }


async def call_model(config: ModelConfig, prompt: str, context: dict[str, str]) -> dict[str, Any]:
    """Call an LLM provider. Returns raw response dict.

    This is the integration point. Swap this out for real API calls.
    Currently returns a simulated response for demo/testing.
    """
    provider = config.provider

    if provider == "anthropic":
        return await _call_anthropic(config, prompt, context)
    elif provider == "openai":
        return await _call_openai(config, prompt, context)
    elif provider == "simulate":
        return await _call_simulate(config, prompt, context)
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _call_anthropic(config: ModelConfig, prompt: str, context: dict[str, str]) -> dict[str, Any]:
    """Call the Anthropic API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    client = anthropic.AsyncAnthropic(
        api_key=os.environ.get(config.api_key_env or "ANTHROPIC_API_KEY")
    )

    messages = []
    if context:
        ctx_text = "\n\n".join(f"--- {name} ---\n{content}" for name, content in context.items())
        messages.append({"role": "user", "content": f"Context:\n{ctx_text}\n\nTask:\n{prompt}"})
    else:
        messages.append({"role": "user", "content": prompt})

    response = await client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        system=config.system_prompt or "You are a precise coding assistant.",
        messages=messages,
    )

    output = response.content[0].text if response.content else ""
    return {
        "output": output,
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


async def _call_openai(config: ModelConfig, prompt: str, context: dict[str, str]) -> dict[str, Any]:
    """Call the OpenAI API."""
    try:
        import openai
    except ImportError:
        raise ImportError("Install openai: pip install openai")

    client = openai.AsyncOpenAI(
        api_key=os.environ.get(config.api_key_env or "OPENAI_API_KEY")
    )

    messages = []
    if config.system_prompt:
        messages.append({"role": "system", "content": config.system_prompt})
    if context:
        ctx_text = "\n\n".join(f"--- {name} ---\n{content}" for name, content in context.items())
        messages.append({"role": "user", "content": f"Context:\n{ctx_text}\n\nTask:\n{prompt}"})
    else:
        messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=config.model,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        messages=messages,
    )

    choice = response.choices[0]
    return {
        "output": choice.message.content or "",
        "model": response.model,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


async def _call_simulate(config: ModelConfig, prompt: str, context: dict[str, str]) -> dict[str, Any]:
    """Simulated provider for testing the harness itself."""
    import random

    await asyncio.sleep(random.uniform(0.1, 0.5))

    # Simulate different outcomes based on task content
    output = config.extra.get("simulated_output", f"Simulated response for: {prompt[:80]}")
    return {
        "output": output,
        "model": config.model,
        "input_tokens": random.randint(100, 2000),
        "output_tokens": random.randint(50, 1000),
    }


async def run_task(
    task: Task,
    config: ModelConfig,
    iteration: int,
    timeout: int = 120,
    max_retries: int = 0,
    fallback: ModelConfig | None = None,
) -> TaskResult:
    """Run a single task against a config, with optional retry/fallback."""
    scorer = RuleScorer()
    retries = 0
    used_fallback = False
    current_config = config
    error = None

    while True:
        try:
            start = time.monotonic()
            raw = await asyncio.wait_for(
                call_model(current_config, task.prompt, task.context),
                timeout=timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000

            output = raw.get("output", "")
            tokens = TokenUsage(
                input_tokens=raw.get("input_tokens", 0),
                output_tokens=raw.get("output_tokens", 0),
            )

            score = scorer.score(output, task.expected, task.scoring)

            # If failed and retries remain, retry
            if not score.passed and retries < max_retries:
                retries += 1
                continue

            # If failed and fallback available, try fallback
            if not score.passed and fallback and not used_fallback:
                current_config = fallback
                used_fallback = True
                continue

            # Adjust category for recovery paths
            if score.passed and retries > 0:
                score.failure_category = FailureCategory.RETRY_RECOVERY
            elif score.passed and used_fallback:
                score.failure_category = FailureCategory.FALLBACK_RECOVERY

            return TaskResult(
                task_id=task.id,
                config_name=config.name,
                iteration=iteration,
                output=output,
                score=score,
                latency_ms=latency_ms,
                tokens=tokens,
                retries=retries,
                used_fallback=used_fallback,
                raw_response=raw,
            )

        except asyncio.TimeoutError:
            return TaskResult(
                task_id=task.id,
                config_name=config.name,
                iteration=iteration,
                output="",
                score=ScoreResult(
                    passed=False,
                    score=0.0,
                    failure_category=FailureCategory.TIMEOUT,
                    details=f"Timed out after {timeout}s",
                ),
                latency_ms=timeout * 1000,
                tokens=TokenUsage(),
                retries=retries,
                error=f"Timeout after {timeout}s",
                raw_response={},
            )
        except Exception as e:
            error = str(e)
            if retries < max_retries:
                retries += 1
                continue
            if fallback and not used_fallback:
                current_config = fallback
                used_fallback = True
                continue
            return TaskResult(
                task_id=task.id,
                config_name=config.name,
                iteration=iteration,
                output="",
                score=ScoreResult(
                    passed=False,
                    score=0.0,
                    failure_category=FailureCategory.TOOL_FAILURE,
                    details=error,
                ),
                latency_ms=0,
                tokens=TokenUsage(),
                retries=retries,
                error=error,
                raw_response={},
            )


async def run_benchmark(run_config: RunConfig) -> list[TaskResult]:
    """Execute a full benchmark run. Returns all results."""
    tasks = load_tasks(run_config.tasks_dir, run_config.task_filter or None)
    if not tasks:
        raise ValueError(f"No tasks found in {run_config.tasks_dir}")

    fallback_map: dict[str, ModelConfig] = {}
    config_map: dict[str, ModelConfig] = {c.name: c for c in run_config.configs}
    if run_config.fallback_config and run_config.fallback_config in config_map:
        for c in run_config.configs:
            if c.name != run_config.fallback_config:
                fallback_map[c.name] = config_map[run_config.fallback_config]

    results: list[TaskResult] = []

    for task in tasks:
        for config in run_config.configs:
            for iteration in range(1, run_config.iterations + 1):
                result = await run_task(
                    task=task,
                    config=config,
                    iteration=iteration,
                    timeout=run_config.timeout_seconds,
                    max_retries=run_config.max_retries,
                    fallback=fallback_map.get(config.name),
                )
                results.append(result)
                _print_progress(result)

    return results


def _print_progress(result: TaskResult) -> None:
    """Print a single-line progress indicator."""
    status = "\u2713" if result.score.passed else "\u2717"
    cat = result.score.failure_category.value
    print(
        f"  {status} {result.task_id:30s} | {result.config_name:20s} | "
        f"{result.latency_ms:7.0f}ms | {cat}"
    )
