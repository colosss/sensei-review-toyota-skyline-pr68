"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R03_only_one_active_entry_across_labs(harness):
    first = harness.client.post(BASE + "/1/queue/register")
    second = harness.client.post(BASE + "/2/queue/register")
    print("two lab registrations:", first.status_code, first.json(), second.status_code, second.json())
    assert first.status_code == 200
    assert second.status_code == 409, "one student cannot wait for two labs simultaneously"

