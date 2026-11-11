"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R01_failed_ci_must_not_allow_registration(harness):
    harness.spreadsheet.worksheet("G1").update_cell(3, 4, "x")
    harness.github.conclusion = "failure"
    result = harness.client.post(BASE + "/1/queue/register")
    print("failed CI, stored x:", result.status_code, result.json())
    assert result.status_code == 400, "0/1 passed is a nonempty string, not a successful verdict"

