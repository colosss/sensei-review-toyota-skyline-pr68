"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R04_finishing_first_student_renumbers_remaining_queue(harness):
    ss = harness.spreadsheet
    store.register(ss, date.fromisoformat(DAY), "G1", "Alice Synthetic", "L1", 2)
    store.register(ss, date.fromisoformat(DAY), "G1", "Bob Synthetic", "L1", 2)
    result = harness.client.post("/admin" + BASE + "/1/queue/set-status",
                                 json={"identifier": "Alice Synthetic", "status": "сдал"})
    assert result.status_code == 200
    harness.login("carol", "Carol Synthetic")
    assert harness.client.post(BASE + "/1/queue/register").status_code == 200
    waiting = store.list_waiting(store.read_queue_rows(ss.worksheet("Очередь-" + DAY)), "G1", "L1")
    print("after completion:", [(r.fio, r.position) for r in waiting])
    assert [r.position for r in waiting] == [1, 2], "positions must not both be 2"

