"""Scoring engine for evaluating task results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .taxonomy import FailureCategory


@dataclass
class ScoreResult:
    """Result of scoring a single task execution."""

    passed: bool
    score: float  # 0.0 to 1.0
    failure_category: FailureCategory
    details: str = ""
    checks: dict[str, bool] | None = None


class RuleScorer:
    """Rule-based scorer using configurable checks."""

    def score(self, output: str, expected: dict[str, Any], scoring: dict[str, Any]) -> ScoreResult:
        """Score output against expected results using rule-based checks."""
        checks: dict[str, bool] = {}
        mode = scoring.get("mode", "contains")

        if mode == "exact":
            checks["exact_match"] = output.strip() == expected.get("output", "").strip()

        elif mode == "contains":
            for i, substring in enumerate(expected.get("contains", [])):
                checks[f"contains_{i}"] = substring in output

        elif mode == "regex":
            pattern = expected.get("pattern", "")
            checks["regex_match"] = bool(re.search(pattern, output, re.DOTALL))

        elif mode == "json_schema":
            checks.update(self._check_json_schema(output, expected))

        elif mode == "multi":
            # Combine multiple check types
            for check in scoring.get("checks", []):
                sub_result = self.score(output, check.get("expected", {}), check)
                checks.update(sub_result.checks or {})

        if not checks:
            return ScoreResult(
                passed=False,
                score=0.0,
                failure_category=FailureCategory.UNKNOWN_ERROR,
                details="No scoring rules matched",
            )

        passed_count = sum(1 for v in checks.values() if v)
        total = len(checks)
        score = passed_count / total if total > 0 else 0.0
        all_passed = passed_count == total

        if all_passed:
            category = FailureCategory.SUCCESS
        elif score >= 0.5:
            category = FailureCategory.PARTIAL_COMPLETION
        else:
            category = self._classify_failure(output, expected, scoring)

        return ScoreResult(
            passed=all_passed,
            score=score,
            failure_category=category,
            checks=checks,
        )

    def _check_json_schema(self, output: str, expected: dict[str, Any]) -> dict[str, bool]:
        """Check if output is valid JSON with required keys."""
        checks = {}
        try:
            parsed = json.loads(output)
            checks["valid_json"] = True
            for key in expected.get("required_keys", []):
                checks[f"has_key_{key}"] = key in parsed
        except json.JSONDecodeError:
            checks["valid_json"] = False
        return checks

    def _classify_failure(
        self, output: str, expected: dict[str, Any], scoring: dict[str, Any]
    ) -> FailureCategory:
        """Attempt to classify why a task failed."""
        if not output or not output.strip():
            return FailureCategory.TIMEOUT

        # Check for common failure patterns
        lower = output.lower()
        if any(kw in lower for kw in ["error", "traceback", "exception"]):
            return FailureCategory.TOOL_FAILURE
        if any(kw in lower for kw in ["rate limit", "429", "quota"]):
            return FailureCategory.RATE_LIMIT
        if any(kw in lower for kw in ["unauthorized", "403", "auth"]):
            return FailureCategory.AUTH_ERROR
        if any(kw in lower for kw in ["context length", "token limit", "too long"]):
            return FailureCategory.CONTEXT_OVERFLOW

        # Check for JSON formatting issues
        if scoring.get("mode") == "json_schema":
            try:
                json.loads(output)
            except json.JSONDecodeError:
                return FailureCategory.FORMATTING_FAILURE

        # If output exists but is wrong, it might be hallucinated success
        if any(kw in lower for kw in ["done", "completed", "success", "finished"]):
            return FailureCategory.HALLUCINATED_SUCCESS

        return FailureCategory.UNKNOWN_ERROR
