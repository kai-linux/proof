"""Tests for token counting and cost estimation."""

from proof.cost import TokenUsage


def test_total_tokens():
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    assert usage.total_tokens == 150


def test_cost_estimation_claude():
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = usage.estimate_cost("claude-sonnet-4-20250514")
    assert cost == 18.0  # $3 input + $15 output


def test_cost_estimation_unknown_model():
    usage = TokenUsage(input_tokens=1000, output_tokens=500)
    cost = usage.estimate_cost("unknown-model")
    assert cost == 0.0


def test_addition():
    a = TokenUsage(input_tokens=100, output_tokens=50)
    b = TokenUsage(input_tokens=200, output_tokens=75)
    total = a + b
    assert total.input_tokens == 300
    assert total.output_tokens == 125
