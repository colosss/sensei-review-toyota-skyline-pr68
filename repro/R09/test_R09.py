"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R09_list_order_matches_shifted_positions(harness):
    ss = harness.spreadsheet
    store.register(ss, date.fromisoformat(DAY), "G1", "Alice Synthetic", "L1", 2)
    store.register(ss, date.fromisoformat(DAY), "G1", "Bob Synthetic", "L1", 2)
    assert harness.client.post(BASE + "/1/queue/shift", json={"delta": 1}).status_code == 200
    data = harness.client.get(BASE + "/1/queue").json()
    print("API after shift:", [(r["fio"], r["position"]) for r in data["queue"]])
    assert [r["fio"] for r in data["queue"]] == ["Bob Synthetic", "Alice Synthetic"]

