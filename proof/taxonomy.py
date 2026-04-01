"""Failure taxonomy for classifying LLM task outcomes."""

from __future__ import annotations

from enum import Enum


class FailureCategory(str, Enum):
    """Categories of failure in agentic LLM tasks.

    These categories are ordered roughly by severity, from least
    to most concerning in a production context.
    """

    # Success states
    SUCCESS = "success"
    RETRY_RECOVERY = "retry_recovery"
    FALLBACK_RECOVERY = "fallback_recovery"

    # Partial failures
    PARTIAL_COMPLETION = "partial_completion"
    FORMATTING_FAILURE = "formatting_failure"
    SCHEMA_VIOLATION = "schema_violation"

    # Hard failures
    WRONG_FILE_MODIFIED = "wrong_file_modified"
    HALLUCINATED_SUCCESS = "hallucinated_success"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    CONTEXT_OVERFLOW = "context_overflow"
    UNKNOWN_ERROR = "unknown_error"

    @property
    def is_success(self) -> bool:
        return self in {
            FailureCategory.SUCCESS,
            FailureCategory.RETRY_RECOVERY,
            FailureCategory.FALLBACK_RECOVERY,
        }

    @property
    def is_partial(self) -> bool:
        return self in {
            FailureCategory.PARTIAL_COMPLETION,
            FailureCategory.FORMATTING_FAILURE,
            FailureCategory.SCHEMA_VIOLATION,
        }

    @property
    def is_hard_failure(self) -> bool:
        return not self.is_success and not self.is_partial

    @property
    def severity(self) -> int:
        """0 = success, 1 = recovered, 2 = partial, 3 = hard failure."""
        if self == FailureCategory.SUCCESS:
            return 0
        if self.is_success:
            return 1
        if self.is_partial:
            return 2
        return 3


# Human-readable descriptions for reports
CATEGORY_DESCRIPTIONS: dict[FailureCategory, str] = {
    FailureCategory.SUCCESS: "Task completed correctly on first attempt",
    FailureCategory.RETRY_RECOVERY: "Failed initially but succeeded after retry",
    FailureCategory.FALLBACK_RECOVERY: "Primary model failed, fallback model succeeded",
    FailureCategory.PARTIAL_COMPLETION: "Task partially completed, missing required elements",
    FailureCategory.FORMATTING_FAILURE: "Output exists but doesn't match expected format",
    FailureCategory.SCHEMA_VIOLATION: "Output violates the expected schema or structure",
    FailureCategory.WRONG_FILE_MODIFIED: "Modified incorrect file or resource",
    FailureCategory.HALLUCINATED_SUCCESS: "Claimed success but output is incorrect",
    FailureCategory.TOOL_FAILURE: "Tool call failed or returned unexpected error",
    FailureCategory.TIMEOUT: "Task exceeded time limit",
    FailureCategory.AUTH_ERROR: "Authentication or authorization failure",
    FailureCategory.RATE_LIMIT: "Rate limited by provider",
    FailureCategory.CONTEXT_OVERFLOW: "Input exceeded model context window",
    FailureCategory.UNKNOWN_ERROR: "Unclassified failure",
}
