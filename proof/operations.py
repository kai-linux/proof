"""Evidence-based operational metrics, separate from simulated benchmarks.

The input is a versioned, privacy-filtered observation export. Unknown costs and
missing acceptance evidence are never converted to zero cost or success.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ValueError("Timestamps must be finite")
        return float(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()


def _money(value):
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("Costs must be nonnegative finite numbers or null")
    return float(value)


def summarize_operations(data):
    if data.get("schema") != "proof.observations.v1":
        raise ValueError(
            "Expected proof.observations.v1; benchmark results are not live observations"
        )
    now = timestamp(data["observed_at"])
    goals = data.get("goals", [])
    attempts = data.get("attempts", [])
    evidence = data.get("evidence", [])
    by_id = {g["id"]: g for g in goals}
    if len(by_id) != len(goals):
        raise ValueError("Goal identities must be unique")
    children = defaultdict(list)
    for g in goals:
        parent = by_id.get(g.get("parent_id"))
        if parent and g.get("parent_revision", 1) == parent["revision"]:
            children[parent["id"]].append(g["id"])
    dependencies = defaultdict(list)
    for d in data.get("dependencies", []):
        dependencies[d["goal_id"]].append(d["requires_id"])
    passed = defaultdict(set)
    for e in evidence:
        if e.get("passed") is True or e.get("passed") == 1:
            passed[(e["goal_id"], e["revision"])].add(e["check_id"])
    verified = {}

    def verifies(ident, visiting=None):
        if ident in verified:
            return verified[ident]
        visiting = set(visiting or ())
        if ident not in by_id or ident in visiting:
            return False
        visiting.add(ident)
        goal = by_id[ident]
        expected = set(goal.get("required_checks") or ["human_acceptance"])
        value = goal["state"] == "succeeded" and expected.issubset(
            passed[(ident, goal["revision"])]
        )
        value = value and all(verifies(k, visiting) for k in children[ident] + dependencies[ident])
        verified[ident] = value
        return value

    for g in goals:
        verifies(g["id"])

    def authorized(goal):
        seen = set()
        while goal and goal["id"] not in seen:
            seen.add(goal["id"])
            if goal["state"] in {
                "paused",
                "waiting",
                "backlog",
                "cancelled",
                "failed",
                "succeeded",
            }:
                return False
            parent_id = goal.get("parent_id")
            if parent_id and parent_id not in by_id:
                return False
            goal = by_id.get(parent_id)
        return goal is None

    alerts = []
    for component in data.get("health", []):
        if component.get("state", "ok") != "ok":
            alerts.append(
                {
                    "code": "component_unhealthy",
                    "severity": "warning",
                    "goal_id": None,
                    "message": str(component.get("component", "unknown"))
                    + ": "
                    + str(component["state"]),
                }
            )
    coordinator = next(
        (h for h in data.get("health", []) if h.get("component") == "delivery_coordinator"), None
    )
    if goals and (coordinator is None or now - timestamp(coordinator["observed_at"]) > 300):
        alerts.append(
            {
                "code": "coordinator_stale",
                "severity": "critical",
                "goal_id": None,
                "message": "The delivery coordinator has no heartbeat in the last five minutes. "
                "Dashboard refresh is not worker health.",
            }
        )
    for g in goals:
        if g["state"] == "succeeded" and not verified[g["id"]]:
            alerts.append(
                {
                    "code": "unproven_completion",
                    "severity": "critical",
                    "goal_id": g["id"],
                    "message": "Completion lacks current acceptance evidence "
                    "or a prerequisite outcome.",
                }
            )
    active = []
    durations = []
    actual_costs = []
    unknown_costs = 0
    reservations = 0.0
    failures = Counter()
    per_worker = defaultdict(
        lambda: {
            "attempts": 0,
            "finished": 0,
            "reported_complete": 0,
            "known_cost_usd": 0.0,
            "unknown_costs": 0,
        }
    )
    for a in attempts:
        cost = _money(a.get("cost_usd"))
        reservation = _money(a.get("reserved_usd", 0))
        if cost is None:
            unknown_costs += 1
            reservations += reservation or 0
        else:
            actual_costs.append(cost)
        worker = per_worker[a.get("worker", "unknown")]
        worker["attempts"] += 1
        worker["known_cost_usd"] += cost or 0
        worker["unknown_costs"] += cost is None
        worker["reported_complete"] += a.get("result_status") == "complete"
        if a.get("finished_at") is not None:
            worker["finished"] += 1
            durations.append(max(0, timestamp(a["finished_at"]) - timestamp(a["started_at"])))
        if a.get("blocker_code") not in (None, "", "none"):
            failures[a["blocker_code"]] += 1
        if a["state"] == "running":
            g = by_id.get(a["goal_id"])
            valid = (
                g
                and authorized(g)
                and g["state"] == "running"
                and a["revision"] == g["revision"]
                and timestamp(a["lease_until"]) > now
            )
            if valid:
                active.append(a)
            else:
                alerts.append(
                    {
                        "code": "stale_worker",
                        "severity": "critical",
                        "goal_id": a["goal_id"],
                        "message": "Worker has an expired lease or no current execution authority.",
                    }
                )
    leaves = [
        g
        for g in goals
        if g["kind"] == "task"
        and not children[g["id"]]
        and g["state"] != "cancelled"
        and not g.get("historical_import")
    ]
    delivered = sum(verified[g["id"]] for g in leaves)
    delivery_durations = sorted(
        timestamp(g["updated_at"]) - timestamp(g["created_at"]) for g in leaves if verified[g["id"]]
    )
    due_deliveries = [g for g in leaves if verified[g["id"]] and g.get("deadline") is not None]
    on_time = sum(timestamp(g["updated_at"]) <= timestamp(g["deadline"]) for g in due_deliveries)
    attempts_per_goal = Counter(a["goal_id"] for a in attempts)
    rows = []
    for g in goals:
        deadline = timestamp(g.get("deadline"))
        if (
            deadline is not None
            and deadline < now
            and g["state"] not in {"succeeded", "cancelled", "failed"}
        ):
            alerts.append(
                {
                    "code": "overdue",
                    "severity": "warning",
                    "goal_id": g["id"],
                    "message": "Delivery commitment is overdue.",
                }
            )
        rows.append(
            {
                **g,
                "verified": verified[g["id"]],
                "children_total": len(children[g["id"]]),
                "children_verified": sum(verified[k] for k in children[g["id"]]),
                "attempt_count": attempts_per_goal[g["id"]],
                "age_seconds": max(0, now - timestamp(g["created_at"])),
            }
        )
    notifications = data.get("notifications", {})
    oldest = timestamp(notifications.get("oldest_pending_at"))
    if oldest is not None and now - oldest > 300:
        alerts.append(
            {
                "code": "notification_delay",
                "severity": "warning",
                "goal_id": None,
                "message": "A persisted status update has been undelivered "
                "for more than five minutes.",
            }
        )
    if data.get("uncertain_actions", 0):
        alerts.append(
            {
                "code": "uncertain_effect",
                "severity": "critical",
                "goal_id": None,
                "message": "External effects require reconciliation before retrying.",
            }
        )
    if unknown_costs:
        alerts.append(
            {
                "code": "cost_coverage",
                "severity": "warning",
                "goal_id": None,
                "message": f"Actual provider cost is unknown for {unknown_costs} attempts; "
                "reservations are not invoices.",
            }
        )
    durations.sort()
    latency = durations[max(0, math.ceil(len(durations) * 0.95) - 1)] if durations else None
    buckets = defaultdict(lambda: {"started": 0, "verified": 0})
    for a in attempts:
        day = datetime.fromtimestamp(timestamp(a["started_at"]), timezone.utc).date().isoformat()
        buckets[day]["started"] += 1
    for event in data.get("events", []):
        if (
            event.get("state") == "succeeded"
            and verified.get(event.get("goal_id"), False)
            and event.get("revision", by_id[event["goal_id"]]["revision"])
            == by_id[event["goal_id"]]["revision"]
        ):
            day = datetime.fromtimestamp(timestamp(event["at"]), timezone.utc).date().isoformat()
            buckets[day]["verified"] += 1
    return {
        "schema": "proof.operations.v1",
        "observed_at": now,
        "last_event_at": max((timestamp(e["at"]) for e in data.get("events", [])), default=None),
        "metrics": {
            "verified_delivery": {
                "value": delivered / len(leaves) if leaves else None,
                "numerator": delivered,
                "denominator": len(leaves),
                "definition": "Verified task outcomes / accepted task goals, excluding cancelled "
                "tasks and historical imports. Open tasks remain in the denominator.",
            },
            "active_workers": len(active),
            "waiting": sum(g["state"] == "waiting" for g in goals),
            "pending_verification": sum(g["state"] == "verifying" for g in goals),
            "programs": sum(g["kind"] == "program" for g in goals),
            "projects": sum(g["kind"] == "project" for g in goals),
            "attempts": len(attempts),
            "historical_imports": sum(bool(g.get("historical_import")) for g in goals),
            "retries": sum(max(0, n - 1) for n in attempts_per_goal.values()),
            "p95_attempt_seconds": latency,
            "latency_samples": len(durations),
            "p95_delivery_seconds": delivery_durations[
                math.ceil(len(delivery_durations) * 0.95) - 1
            ]
            if delivery_durations
            else None,
            "delivery_latency_samples": len(delivery_durations),
            "on_time_delivery": {
                "value": on_time / len(due_deliveries) if due_deliveries else None,
                "numerator": on_time,
                "denominator": len(due_deliveries),
            },
            "known_cost_usd": sum(actual_costs),
            "unknown_cost_attempts": unknown_costs,
            "reserved_unpriced_usd": reservations,
            "cost_coverage": len(actual_costs) / len(attempts) if attempts else None,
            "cost_per_verified_task_usd": sum(actual_costs) / delivered
            if delivered
            and not unknown_costs
            and all(attempts_per_goal[g["id"]] for g in leaves if verified[g["id"]])
            else None,
            "pending_notifications": notifications.get("pending", 0),
        },
        "goals": rows,
        "active_attempts": active,
        "alerts": alerts,
        "workers": [{"name": k, **v} for k, v in sorted(per_worker.items())],
        "failure_taxonomy": dict(failures),
        "timeline": [{"date": k, **v} for k, v in sorted(buckets.items())][-30:],
        "legacy": data.get("legacy", {}),
        "risks": data.get("risks", []),
        "health": data.get("health", []),
    }


def render_operations_dashboard(snapshot=None, *, data_url="/api/delivery"):
    if not data_url.startswith("/") or data_url.startswith("//"):
        raise ValueError("Live data must use a same-origin absolute path")
    template = files("proof").joinpath("static/operations.html").read_text(encoding="utf-8")
    initial = (
        json.dumps(snapshot, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return template.replace(
        "__DATA_URL__", json.dumps(data_url).replace("<", "\\u003c"), 1
    ).replace("__INITIAL_DATA__", initial, 1)


def write_operations_report(observations, output):
    snapshot = summarize_operations(observations)
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "operations.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    (destination / "index.html").write_text(
        render_operations_dashboard(snapshot, data_url="/operations.json"), encoding="utf-8"
    )
    return snapshot
