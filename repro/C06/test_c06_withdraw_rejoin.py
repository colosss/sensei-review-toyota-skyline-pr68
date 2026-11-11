"""C06 - stale positions of withdrawn rows shown in the same list.

``store.withdraw`` only renumbers rows whose status is "ждёт"
(``_renumber_waiting``); the withdrawn row keeps its old position.
``GET .../queue`` returns *all* rows of the day sheet, waiting and not, in
sheet order.  The UI renders every row with its stored position chip, so after
a withdraw + rejoin the same person appears twice and the two rows share
position 1 with the student who moved up.

This is independent of the group/lab scoping defect and of the session-scope
defect: it reproduces inside a single group/lab/day and would remain after
those are fixed.

Observation test is expected to PASS on the pinned submission (scenario
format).  The regression test states the displayed positions must be unique
and is expected to FAIL on the pinned submission.
"""

from __future__ import annotations

import c06_fake_sheets as fx


def _register_pair():
    ivanov = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)
    assert fx.queue_register(ivanov, fx.LAB1).status_code == 200
    assert fx.queue_register(petrova, fx.LAB1).status_code == 200
    return ivanov, petrova


def _run_withdraw_rejoin(env):
    ivanov, petrova = _register_pair()
    withdraw = fx.queue_withdraw(ivanov, fx.LAB1)
    rejoin = fx.queue_register(ivanov, fx.LAB1)
    return {
        "withdraw": {"http": withdraw.status_code, "body": withdraw.json()},
        "rejoin": {"http": rejoin.status_code, "body": rejoin.json()},
        "status": fx.queue_status(ivanov, fx.LAB1),
        "lab1_page": fx.queue_list(petrova, fx.LAB1),
        "rows": fx.queue_rows(env.spreadsheet),
    }


def test_observed_withdraw_and_rejoin_show_the_same_person_twice(env):
    """Scenario: one student, withdraw + rejoin, list shows two Иванов rows."""
    result = _run_withdraw_rejoin(env)

    assert result["withdraw"] == {"http": 200, "body": {"status": "withdrawn"}}
    assert result["rejoin"] == {"http": 200, "body": {"position": 2, "queue_size": 2}}
    assert (result["status"]["position"], result["status"]["queue_size"]) == (2, 2)

    entries = result["lab1_page"]["queue"]
    assert [entry["fio"] for entry in entries] == [
        fx.FIO_IVANOV,
        fx.FIO_PETROVA,
        fx.FIO_IVANOV,
    ]
    assert [entry["status"] for entry in entries] == ["отозван", "ждёт", "ждёт"]
    assert [entry["position"] for entry in entries] == [1, 1, 2]

    assert [
        (row.position, row.fio, row.status) for row in result["rows"]
    ] == [
        (1, fx.FIO_IVANOV, "отозван"),
        (1, fx.FIO_PETROVA, "ждёт"),
        (2, fx.FIO_IVANOV, "ждёт"),
    ]


def test_regression_displayed_positions_are_unique_after_withdraw_and_rejoin(env):
    """Desired contract: rows displayed in one group/lab list have unique positions.

    Expected to FAIL on the pinned submission: the withdrawn row keeps
    position 1 while the waiting student is renumbered to 1, and both are
    returned by the list endpoint and rendered by QueueSection.
    """
    result = _run_withdraw_rejoin(env)
    entries = result["lab1_page"]["queue"]
    positions = [entry["position"] for entry in entries]

    assert len(set(positions)) == len(positions), (
        "desired: no two rows of the lab1 list share a position; actual "
        f"positions {positions!r} with statuses "
        f"{[entry['status'] for entry in entries]!r}"
    )
