"""Assertions express the requested behavior and intentionally fail on PR 68."""
from datetime import date, datetime
import pytest
from grading.queue import store
from grading.schedule import parse_course_schedule
from grading.schedule.base import ScheduleSource
from grading.schedule.registry import register_source
from conftest import BASE, DAY


def test_R07_registered_schedule_module_is_used(harness):
    calls = []
    class ReviewUniversity(ScheduleSource):
        def __init__(self, *args, **kwargs):
            calls.append("construct")
        def list_sessions(self, group_id, since, until):
            calls.append("list_sessions")
            return []
    from grading.schedule import registry
    registry._REGISTRY.pop("review_university", None)
    register_source("review_university")(ReviewUniversity)
    harness.path.write_text("""course-id: review
source: review_university
groups:
  G1:
    group_id: G1
    slots: []
""")
    try:
        sources = parse_course_schedule("review", harness.path.parent)
        list(sources["G1"].list_sessions("G1", datetime(2026, 11, 9), datetime(2026, 11, 10)))
        print("source selected:", type(sources["G1"]).__name__, "module calls:", calls)
        assert isinstance(sources["G1"], ReviewUniversity)
    finally:
        registry._REGISTRY.pop("review_university", None)

