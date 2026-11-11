"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R06_without_schedule_queue_lives_for_the_day(harness):
    harness.path.unlink()
    status = harness.client.get(BASE + "/1/queue/status")
    result = harness.client.post(BASE + "/1/queue/register")
    print("without schedule:", status.json(), result.status_code, result.json())
    assert result.status_code == 200

