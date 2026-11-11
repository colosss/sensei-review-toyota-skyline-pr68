"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R02_registration_must_not_write_grade_cells(harness):
    ws = harness.spreadsheet.worksheet("G1")
    ws.update_cell(3, 4, "?")
    ws.writes.clear()
    result = harness.client.post(BASE + "/1/queue/register")
    print("register:", result.status_code, result.json(), "grade writes:", ws.writes)
    assert ws.writes == [], "queue registration must not write to existing grade cells"

