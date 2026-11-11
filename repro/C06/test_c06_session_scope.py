"""C06 - position numbering key vs read/renumber key (session scope).

``store.register`` computes the new position from ``list_waiting(...,
session_no)`` - only rows of the currently active class slot.  Every read and
renumber path reachable from the API calls the same helpers *without* a
session filter: ``queue_status``/``queue_list`` (``main.py``), ``withdraw``,
``shift_down`` and ``set_status`` pass ``session_no=None``.

The queue sheet lives for the whole day, so rows registered during pair 1 stay
"ждёт" when pair 2 starts.  A registration in pair 2 then gets position 1
again while the UI/API display both rows as one queue.

The observation test records [1, 1] within one lab and is expected to PASS on
the pinned submission.  The regression test states the desired contract -
positions shown for one group/lab/day are unique and form 1..n - and is
expected to FAIL on the pinned submission.
"""

from __future__ import annotations

import c06_fake_sheets as fx


def _run_two_sessions(env):
    ivanov_a = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)

    env.clock.set("guap-mon-1")  # pair 1
    first = fx.queue_register(ivanov_a, fx.LAB1)
    env.clock.set("guap-mon-2")  # pair 2, same day, same lab
    second = fx.queue_register(petrova, fx.LAB1)

    return {
        "first": {"http": first.status_code, "body": first.json()},
        "second": {"http": second.status_code, "body": second.json()},
        "status": fx.queue_status(petrova, fx.LAB1),
        "lab1_page": fx.queue_list(ivanov_a, fx.LAB1),
        "rows": fx.queue_rows(env.spreadsheet),
    }


def test_observed_two_pairs_in_one_day_give_duplicate_positions(env):
    """Scenario: record the actual state. Expected to pass on pinned code."""
    result = _run_two_sessions(env)

    assert result["first"] == {"http": 200, "body": {"position": 1, "queue_size": 1}}
    assert result["second"] == {"http": 200, "body": {"position": 1, "queue_size": 1}}

    status = result["status"]
    assert (status["in_queue"], status["position"], status["queue_size"]) == (True, 1, 2)

    entries = result["lab1_page"]["queue"]
    assert [entry["lab"] for entry in entries] == [fx.LAB1_SHORT, fx.LAB1_SHORT]
    assert [entry["position"] for entry in entries] == [1, 1]
    assert [entry["fio"] for entry in entries] == [fx.FIO_IVANOV, fx.FIO_PETROVA]

    assert [
        (row.position, row.fio, row.lab, row.session_no, row.status)
        for row in result["rows"]
    ] == [
        (1, fx.FIO_IVANOV, fx.LAB1_SHORT, 1, "ждёт"),
        (1, fx.FIO_PETROVA, fx.LAB1_SHORT, 2, "ждёт"),
    ]


def test_regression_position_is_unique_for_one_group_lab_day(env):
    """Desired contract: one group+lab queue has one ordinal sequence 1..n.

    Expected to FAIL on the pinned submission: register counts only the active
    session while status/list/withdraw/shift/set-status operate on all sessions
    of the day, so both students are displayed at position 1.
    """
    result = _run_two_sessions(env)
    positions = [entry["position"] for entry in result["lab1_page"]["queue"]]

    assert len(set(positions)) == len(positions), (
        "desired: positions shown for one group/lab/day are unique; actual "
        f"positions {positions!r} for rows of sessions "
        f"{[row.session_no for row in result['rows']]}, while status reports "
        f"position {result['status']['position']} of {result['status']['queue_size']}"
    )
    assert sorted(positions) == list(range(1, len(positions) + 1)), (
        "desired: positions form 1..n; actual "
        f"{positions!r}"
    )
