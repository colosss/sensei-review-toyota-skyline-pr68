"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


@pytest.mark.parametrize("view", ["status", "list"])
def test_R05_waiting_entry_remains_visible_after_class(harness, view):
    assert harness.client.post(BASE + "/1/queue/register").status_code == 200
    harness.clock["now"] = datetime(2026, 11, 9, 12, 11)
    assert harness.client.post(BASE + "/1/queue/register").status_code == 403
    assert len(store.read_queue_rows(harness.spreadsheet.worksheet("Очередь-" + DAY))) == 1
    endpoint = BASE + "/1/queue" + ("/status" if view == "status" else "")
    result = harness.client.get(endpoint)
    print("after class:", view, result.status_code, result.json())
    assert result.status_code == 200
    if view == "status":
        assert result.json()["in_queue"] is True
    else:
        assert result.json()["size"] == 1

