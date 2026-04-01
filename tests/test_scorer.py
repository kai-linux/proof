"""Tests for the scoring engine."""

from proof.scorer import RuleScorer
from proof.taxonomy import FailureCategory


def test_contains_all_pass():
    scorer = RuleScorer()
    result = scorer.score(
        output="host: db.prod.internal\nport: 5432\nssl_enabled: true",
        expected={"contains": ["host: db.prod.internal", "port: 5432", "ssl_enabled: true"]},
        scoring={"mode": "contains"},
    )
    assert result.passed is True
    assert result.score == 1.0
    assert result.failure_category == FailureCategory.SUCCESS


def test_contains_partial():
    scorer = RuleScorer()
    result = scorer.score(
        output="host: db.prod.internal\nport: 3306",
        expected={"contains": ["host: db.prod.internal", "port: 5432"]},
        scoring={"mode": "contains"},
    )
    assert result.passed is False
    assert result.score == 0.5
    assert result.failure_category == FailureCategory.PARTIAL_COMPLETION


def test_contains_all_fail():
    scorer = RuleScorer()
    result = scorer.score(
        output="completely wrong output",
        expected={"contains": ["host: db.prod.internal", "port: 5432"]},
        scoring={"mode": "contains"},
    )
    assert result.passed is False
    assert result.score == 0.0


def test_exact_match():
    scorer = RuleScorer()
    result = scorer.score(
        output="hello world",
        expected={"output": "hello world"},
        scoring={"mode": "exact"},
    )
    assert result.passed is True
    assert result.failure_category == FailureCategory.SUCCESS


def test_exact_mismatch():
    scorer = RuleScorer()
    result = scorer.score(
        output="hello world!",
        expected={"output": "hello world"},
        scoring={"mode": "exact"},
    )
    assert result.passed is False


def test_regex_match():
    scorer = RuleScorer()
    result = scorer.score(
        output='{"key": "value", "count": 42}',
        expected={"pattern": r'"count":\s*\d+'},
        scoring={"mode": "regex"},
    )
    assert result.passed is True


def test_json_schema_valid():
    scorer = RuleScorer()
    result = scorer.score(
        output='{"files_changed": [], "summary": "test", "breaking_change": false}',
        expected={"required_keys": ["files_changed", "summary", "breaking_change"]},
        scoring={"mode": "json_schema"},
    )
    assert result.passed is True
    assert result.checks["valid_json"] is True


def test_json_schema_missing_key():
    scorer = RuleScorer()
    result = scorer.score(
        output='{"files_changed": []}',
        expected={"required_keys": ["files_changed", "summary"]},
        scoring={"mode": "json_schema"},
    )
    assert result.passed is False
    assert result.checks["has_key_summary"] is False


def test_json_schema_invalid_json():
    scorer = RuleScorer()
    result = scorer.score(
        output="not json at all",
        expected={"required_keys": ["key"]},
        scoring={"mode": "json_schema"},
    )
    assert result.passed is False
    assert result.checks["valid_json"] is False


def test_empty_output_classified_as_timeout():
    scorer = RuleScorer()
    result = scorer.score(
        output="",
        expected={"contains": ["something"]},
        scoring={"mode": "contains"},
    )
    assert result.passed is False
    assert result.failure_category == FailureCategory.TIMEOUT


def test_error_output_classified_as_tool_failure():
    scorer = RuleScorer()
    result = scorer.score(
        output="Traceback (most recent call last):\n  File ...\nError: something broke",
        expected={"contains": ["correct output"]},
        scoring={"mode": "contains"},
    )
    assert result.passed is False
    assert result.failure_category == FailureCategory.TOOL_FAILURE
