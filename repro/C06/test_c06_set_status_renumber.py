"""C06 - admin set-status does not renumber the waiting queue.

``queue_set_status`` calls ``store.set_status`` with ``group_ids`` in the
``session_no`` positional slot (main.py:3528-3531, store.py:507-516).
``_renumber_waiting`` then filters with ``row.session_no == [group ids]``,
which matches no row, so the remaining waiting queue is never renumbered.

Observable at the HTTP surface: after the first of two students is marked
"сдал", the second stays at position 2 while the status endpoint reports
queue_size 1 - "position 2 of 1".

Observation test is expected to PASS on the pinned submission (scenario
format).  The regression test states the desired contract and is expected to
FAIL on the pinned submission.
"""

from __future__ import annotations

import c06_fake_sheets as fx


def _register_pair():
    ivanov = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)
    assert fx.queue_register(ivanov, fx.LAB1).status_code == 200
    assert fx.queue_register(petrova, fx.LAB1).status_code == 200
    return ivanov, petrova


def test_observed_set_status_leaves_the_waiting_queue_at_position_2(env):
    """Scenario: admin marks the first student "сдал"; the second keeps position 2."""
    _register_pair()
    admin = fx.admin_client()
    updated = fx.admin_set_status(admin, fx.FIO_IVANOV, "сдал", fx.LAB1)
    assert updated.status_code == 200, updated.text
    assert updated.json() == {"status": "updated", "new_status": "сдал"}

    entries = fx.queue_list(admin, fx.LAB1)["queue"]
    assert [entry["fio"] for entry in entries] == [fx.FIO_IVANOV, fx.FIO_PETROVA]
    assert [entry["status"] for entry in entries] == ["сдал", "ждёт"]
    assert [entry["position"] for entry in entries] == [1, 2]

    # The waiting student is alone in the queue but is reported at position 2.
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)
    status = fx.queue_status(petrova, fx.LAB1)
    assert (status["in_queue"], status["position"], status["queue_size"]) == (True, 2, 1)

    assert [
        (row.position, row.fio, row.status) for row in fx.queue_rows(env.spreadsheet)
    ] == [
        (1, fx.FIO_IVANOV, "сдал"),
        (2, fx.FIO_PETROVA, "ждёт"),
    ]


def test_regression_set_status_renumbers_the_remaining_waiting_queue(env):
    """Desired contract: after a result is recorded the waiting queue is 1..n.

    Expected to FAIL on the pinned submission: the ``session_no`` argument is
    actually the list of group ids, so ``_renumber_waiting`` updates nothing.
    """
    _register_pair()
    admin = fx.admin_client()
    assert fx.admin_set_status(admin, fx.FIO_IVANOV, "сдал", fx.LAB1).status_code == 200

    entries = fx.queue_list(admin, fx.LAB1)["queue"]
    waiting_positions = [
        entry["position"] for entry in entries if entry["status"] == "ждёт"
    ]
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)
    status = fx.queue_status(petrova, fx.LAB1)

    assert waiting_positions == list(range(1, len(waiting_positions) + 1)), (
        "desired: the waiting queue is renumbered to 1..n after set-status; "
        f"actual waiting positions {waiting_positions!r}, status reports "
        f"position {status['position']} of {status['queue_size']}"
    )
    assert status["position"] <= status["queue_size"], (
        f"desired: position <= queue_size; actual {status['position']} of "
        f"{status['queue_size']}"
    )
