"""Tests for task loading."""

from pathlib import Path

from proof.task import Task, load_tasks

TASKS_DIR = Path(__file__).parent.parent / "tasks"


def test_load_single_task():
    task = Task.from_yaml(TASKS_DIR / "config_edit.yaml")
    assert task.id == "config_edit"
    assert task.category == "code_edit"
    assert "host" in task.prompt.lower()


def test_load_all_tasks():
    tasks = load_tasks(TASKS_DIR)
    assert len(tasks) >= 3
    ids = {t.id for t in tasks}
    assert "config_edit" in ids
    assert "fix_failing_test" in ids
    assert "structured_output" in ids


def test_load_tasks_with_filter():
    tasks = load_tasks(TASKS_DIR, filter_ids=["config_edit"])
    assert len(tasks) == 1
    assert tasks[0].id == "config_edit"
