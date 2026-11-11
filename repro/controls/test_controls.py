"""Passing controls distinguish application failures from harness failures."""
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from grading.queue import store
from grading.queue.errors import QueueError
from grading.queue.schedule_window import sessions_for_date
from conftest import BASE, DAY


def test_normal_join_status_and_withdraw(harness):
    client = harness.client
    assert client.post(BASE + "/1/queue/register").json() == {"position": 1, "queue_size": 1}
    status = client.get(BASE + "/1/queue/status").json()
    assert status["in_queue"] is True and status["position"] == 1
    assert client.post(BASE + "/1/queue/withdraw").status_code == 200
    assert client.get(BASE + "/1/queue/status").json()["in_queue"] is False
    assert harness.spreadsheet.worksheet("G1").writes == []


def test_real_ci_evaluator_reports_failure(harness):
    from grading.grader import LabGrader
    harness.github.conclusion = "failure"
    result = LabGrader(harness.github)._evaluate_ci_internal("org", "repo", {"ci": {"workflows": ["test"]}})
    assert result.ci_passed is False
    assert result.grade_result.result == "x"
    assert result.grade_result.passed == "0/1 тестов пройдено"


def test_student_session_cannot_be_used_for_other_group(harness):
    result = harness.client.post(BASE.replace("G1", "G2") + "/1/queue/withdraw")
    assert result.status_code == 401


def test_admin_api_requires_admin_cookie(harness):
    harness.client.cookies.clear()
    result = harness.client.post("/admin" + BASE + "/1/queue/set-status",
                                  json={"identifier": "Alice Synthetic", "status": "сдал"})
    assert result.status_code == 401


def test_rejoin_after_absent_is_at_the_end(harness):
    ss = harness.spreadsheet
    day = date.fromisoformat(DAY)
    store.register(ss, day, "G1", "Alice Synthetic", "L1", 2)
    store.register(ss, day, "G1", "Bob Synthetic", "L1", 2)
    store.set_status(ss, day, "G1", "Alice Synthetic", "L1", store.STATUS_ABSENT)
    assert store.register(ss, day, "G1", "Alice Synthetic", "L1", 2) == 2


def test_snapshot_retains_each_attempt_and_is_idempotent(harness):
    ss = harness.spreadsheet
    day = date(2026, 11, 8)
    store.register(ss, day, "G1", "Alice Synthetic", "L1", 2)
    store.set_status(ss, day, "G1", "Alice Synthetic", "L1", store.STATUS_ABSENT)
    store.register(ss, day, "G1", "Alice Synthetic", "L1", 2)
    assert store.maybe_snapshot_past_days(ss, date.fromisoformat(DAY)) == 2
    assert store.maybe_snapshot_past_days(ss, date.fromisoformat(DAY)) == 0
    rows = ss.worksheet(store.HISTORY_SHEET).get_all_values()[1:]
    assert [r[-1] for r in rows] == [store.STATUS_ABSENT, store.STATUS_NOT_REACHED]


@pytest.mark.parametrize("source", ["manual", "guap"])
def test_corrections_apply_to_stored_slots(harness, source):
    data = harness.path.read_text().replace("source: manual", "source: " + source)
    harness.path.write_text(data + """    corrections:
      - id: cancel-and-add
        date: '2026-11-09'
        remove_slots:
          - slot_id: mon-2
        add_slots:
          - id: extra-4
            start: '15:00'
            end: '16:30'
""")
    sessions = sessions_for_date("review", "G1", date.fromisoformat(DAY), harness.path.parent)
    assert [(s.slot_id, s.starts_at.hour) for s in sessions] == [("extra-4", 15)]


def test_same_lab_duplicate_is_serialized_in_supported_single_process(harness):
    barrier = Barrier(2)
    def attempt():
        barrier.wait(timeout=3)
        try:
            return store.register(harness.spreadsheet, date.fromisoformat(DAY), "G1", "Alice Synthetic", "L1", 2)
        except QueueError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(map(str, results)) == ["1", "ALREADY_IN_QUEUE"]
