"""C06 side observation - identity is FIO, not GitHub (same-name students).

The roster used here declares two distinct students with the same full name
"Иванов Иван" and different GitHub logins (a normal real-world collision).
The queue, however, keys every student operation on ``fio`` resolved from the
roster row:

* ``store.register`` rejects the second student with ALREADY_IN_QUEUE;
* ``queue_status`` resolves the second student's cookie FIO to the first
  student's waiting row and reports ``in_queue=true`` and that position.

This is NOT the numbering defect analysed by C06.  It is recorded as an
observation for the C02/C04 packets: the green store-level C02 tests use a
single identity, so they do not cover two different GitHub logins with equal
FIO.  No desired-contract regression is asserted here because the
requirements do not explicitly state how a same-name collision must be
resolved; the candidate suggestion is kept separate in the C06 discovery JSON.
"""

from __future__ import annotations

import c06_fake_sheets as fx


def test_observed_same_fio_different_github_shares_one_queue_slot(env):
    ivanov_a = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    ivanov_b = fx.student_client(fx.GH_IVANOV_B, fx.FIO_IVANOV)

    first = fx.queue_register(ivanov_a, fx.LAB1)
    assert first.status_code == 200
    assert first.json() == {"position": 1, "queue_size": 1}

    # The second student has not registered, but the status resolves to the
    # first student's row because both have the same FIO.
    status_b = fx.queue_status(ivanov_b, fx.LAB1)
    assert (status_b["in_queue"], status_b["position"], status_b["queue_size"]) == (
        True,
        1,
        1,
    )

    # And the second student cannot register for the same lab.
    second = fx.queue_register(ivanov_b, fx.LAB1)
    assert second.status_code == 409, second.text
    assert second.json() == {"detail": "ALREADY_IN_QUEUE"}

    rows = fx.queue_rows(env.spreadsheet)
    assert [(row.fio, row.lab, row.position, row.status) for row in rows] == [
        (fx.FIO_IVANOV, fx.LAB1_SHORT, 1, "ждёт")
    ]
