"""Tests for the failure taxonomy."""

from proof.taxonomy import CATEGORY_DESCRIPTIONS, FailureCategory


def test_success_categories():
    assert FailureCategory.SUCCESS.is_success
    assert FailureCategory.RETRY_RECOVERY.is_success
    assert FailureCategory.FALLBACK_RECOVERY.is_success


def test_partial_categories():
    assert FailureCategory.PARTIAL_COMPLETION.is_partial
    assert FailureCategory.FORMATTING_FAILURE.is_partial
    assert FailureCategory.SCHEMA_VIOLATION.is_partial


def test_hard_failure_categories():
    assert FailureCategory.TIMEOUT.is_hard_failure
    assert FailureCategory.TOOL_FAILURE.is_hard_failure
    assert FailureCategory.HALLUCINATED_SUCCESS.is_hard_failure
    assert FailureCategory.WRONG_FILE_MODIFIED.is_hard_failure


def test_severity_ordering():
    assert FailureCategory.SUCCESS.severity == 0
    assert FailureCategory.RETRY_RECOVERY.severity == 1
    assert FailureCategory.PARTIAL_COMPLETION.severity == 2
    assert FailureCategory.TIMEOUT.severity == 3


def test_all_categories_have_descriptions():
    for cat in FailureCategory:
        assert cat in CATEGORY_DESCRIPTIONS, f"Missing description for {cat}"
