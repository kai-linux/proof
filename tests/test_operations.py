import json
from copy import deepcopy

import pytest

from proof.operations import (
    render_operations_dashboard,
    summarize_operations,
    write_operations_report,
)


def observations():
    return {
        "schema": "proof.observations.v1",
        "observed_at": 1000,
        "goals": [
            {
                "id": "g1",
                "parent_id": None,
                "kind": "task",
                "title": "Deliver",
                "revision": 1,
                "state": "succeeded",
                "created_at": 100,
                "updated_at": 900,
                "required_checks": ["artifact"],
            }
        ],
        "attempts": [
            {
                "id": "a1",
                "goal_id": "g1",
                "revision": 1,
                "worker": "codex",
                "state": "finished",
                "started_at": 100,
                "finished_at": 200,
                "lease_until": 250,
                "cost_usd": None,
                "reserved_usd": 1,
                "result_status": "complete",
            }
        ],
        "evidence": [{"goal_id": "g1", "revision": 1, "check_id": "artifact", "passed": True}],
        "events": [{"goal_id": "g1", "at": 900, "state": "succeeded"}],
    }


def test_verified_outcome_is_distinct_from_worker_claim():
    data = observations()
    data["evidence"] = []
    report = summarize_operations(data)
    assert report["metrics"]["verified_delivery"]["value"] == 0
    assert report["workers"][0]["reported_complete"] == 1
    assert any(a["code"] == "unproven_completion" for a in report["alerts"])
    assert not any(day["verified"] for day in report["timeline"])


def test_parent_pause_invalidates_a_live_child_worker():
    data = observations()
    data["goals"][0].update(parent_id="program", state="running")
    data["goals"].append(
        {
            **data["goals"][0],
            "id": "program",
            "parent_id": None,
            "kind": "program",
            "state": "paused",
        }
    )
    data["attempts"][0].update(state="running", finished_at=None, lease_until=2000)
    result = summarize_operations(data)
    assert result["metrics"]["active_workers"] == 0
    assert any(a["code"] == "stale_worker" for a in result["alerts"])


def test_delivery_time_includes_waits_and_deadline_has_own_denominator():
    data = observations()
    data["goals"][0]["deadline"] = 950
    metrics = summarize_operations(data)["metrics"]
    assert metrics["p95_delivery_seconds"] == 800
    assert metrics["p95_attempt_seconds"] == 100
    assert metrics["on_time_delivery"] == {"value": 1, "numerator": 1, "denominator": 1}


def test_coordinator_health_is_not_dashboard_refresh():
    data = observations()
    assert any(a["code"] == "coordinator_stale" for a in summarize_operations(data)["alerts"])
    data["health"] = [{"component": "delivery_coordinator", "observed_at": 950, "state": "ok"}]
    assert not any(a["code"] == "coordinator_stale" for a in summarize_operations(data)["alerts"])


def test_unknown_cost_does_not_become_zero_total():
    report = summarize_operations(observations())
    assert report["metrics"]["unknown_cost_attempts"] == 1
    assert report["metrics"]["cost_per_verified_task_usd"] is None
    assert report["metrics"]["reserved_unpriced_usd"] == 1
    assert report["metrics"]["cost_coverage"] == 0


def test_adopted_verified_outcome_without_attempt_cost_is_not_free():
    data = observations()
    data["attempts"] = []
    report = summarize_operations(data)
    assert report["metrics"]["verified_delivery"]["numerator"] == 1
    assert report["metrics"]["cost_per_verified_task_usd"] is None


def test_historical_reconciliation_does_not_invent_fast_current_delivery():
    data = observations()
    data["goals"][0]["historical_import"] = True
    data["attempts"] = []
    metrics = summarize_operations(data)["metrics"]
    assert metrics["verified_delivery"]["denominator"] == 0
    assert metrics["p95_delivery_seconds"] is None
    assert metrics["historical_imports"] == 1


def test_failed_source_reconciliation_is_visible_even_with_fresh_heartbeat():
    data = observations()
    data["health"] = [
        {"component": "source_reconciliation", "observed_at": 990, "state": "1 source reads failed"}
    ]
    assert any(a["code"] == "component_unhealthy" for a in summarize_operations(data)["alerts"])


def test_current_revision_is_required_for_acceptance():
    data = observations()
    data["goals"][0]["revision"] = 2
    assert summarize_operations(data)["metrics"]["verified_delivery"]["numerator"] == 0


def test_parent_does_not_hide_failed_integration():
    data = observations()
    parent = deepcopy(data["goals"][0])
    parent.update(id="parent", kind="program")
    data["goals"][0]["parent_id"] = "parent"
    data["goals"].append(parent)
    report = summarize_operations(data)
    assert report["metrics"]["verified_delivery"]["numerator"] == 1
    assert next(g for g in report["goals"] if g["id"] == "parent")["verified"] is False


def test_expired_worker_is_not_active():
    data = observations()
    data["goals"][0]["state"] = "running"
    data["attempts"][0]["state"] = "running"
    report = summarize_operations(data)
    assert report["metrics"]["active_workers"] == 0
    assert any(a["code"] == "stale_worker" for a in report["alerts"])


def test_open_work_stays_in_explicit_denominator():
    data = observations()
    pending = {**data["goals"][0], "id": "waiting", "state": "waiting"}
    data["goals"].append(pending)
    metric = summarize_operations(data)["metrics"]["verified_delivery"]
    assert metric["numerator"] == 1
    assert metric["denominator"] == 2
    assert metric["value"] == 0.5


def test_empty_data_is_unknown_not_perfect():
    result = summarize_operations({"schema": "proof.observations.v1", "observed_at": 1})
    assert result["metrics"]["verified_delivery"]["value"] is None
    assert result["metrics"]["p95_attempt_seconds"] is None
    assert result["metrics"]["cost_coverage"] is None


def test_benchmark_output_cannot_masquerade_as_operations():
    with pytest.raises(ValueError, match="benchmark"):
        summarize_operations({"name": "simulated benchmark", "results": []})


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_invalid_costs_rejected(value):
    data = observations()
    data["attempts"][0]["cost_usd"] = value
    with pytest.raises(ValueError):
        summarize_operations(data)


def test_report_escapes_embedded_script_and_uses_safe_dom(tmp_path):
    data = observations()
    data["goals"][0]["title"] = '</script><script>alert("secret")</script>'
    report = write_operations_report(data, tmp_path)
    page = (tmp_path / "index.html").read_text()
    assert data["goals"][0]["title"] not in page
    assert "innerHTML" not in page
    assert "textContent" in page
    assert json.loads((tmp_path / "operations.json").read_text())["schema"] == report["schema"]


def test_dashboard_refuses_third_party_data_endpoint():
    with pytest.raises(ValueError, match="same-origin"):
        render_operations_dashboard(data_url="https://external.example/data")
    with pytest.raises(ValueError):
        render_operations_dashboard(data_url="//external.example/data")
