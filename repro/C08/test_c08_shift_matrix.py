"""C08 - bounded shift matrix and same-lab sequential repeat (scenario tests).

The hypothesis under test: "the shift is strange, maybe because of two
Ivanovs".  This fixture uses three students with distinct FIO, so identity
collision cannot explain the result.  Every test drives the real HTTP
endpoints through TestClient.

Recorded outcomes (all are observations, not automatic defects):

* delta 0, -1, 1.5 -> HTTP 422 from the request schema (no mutation);
* delta 1 -> old 1 / new 2, swap with the next student;
* delta 1000 -> old 1 / new 3, clamped to the last place (no overflow error);
* shift from the last place -> HTTP 400 INVALID_SHIFT ("already at the end"),
  accepted as intentional, not a separate finding;
* sequential repeat in the exact same lab -> HTTP 409 ALREADY_IN_QUEUE, one row;
* the same identity in a different lab -> HTTP 200 and a second row.  No
  requirement prohibiting different labs was found; this is an observation
  and not a bug by itself (C02 scope).

All tests are expected to PASS on the pinned submission (scenario format).
"""

from __future__ import annotations

import pytest

import c08_fixture as fx


def _positions(env):
    return [(row.fio, row.position, row.status) for row in fx.queue_rows(env.spreadsheet)]


@pytest.mark.parametrize(
    "delta,expected_status,expected_body,expected_rows",
    [
        (0, 422, None, [(fx.FIO_A, 1), (fx.FIO_B, 2), (fx.FIO_C, 3)]),
        (-1, 422, None, [(fx.FIO_A, 1), (fx.FIO_B, 2), (fx.FIO_C, 3)]),
        (1.5, 422, None, [(fx.FIO_A, 1), (fx.FIO_B, 2), (fx.FIO_C, 3)]),
        (1, 200, {"old_position": 1, "new_position": 2}, [(fx.FIO_A, 2), (fx.FIO_B, 1), (fx.FIO_C, 3)]),
        (1000, 200, {"old_position": 1, "new_position": 3}, [(fx.FIO_A, 3), (fx.FIO_B, 1), (fx.FIO_C, 2)]),
    ],
)
def test_shift_value_matrix(env, delta, expected_status, expected_body, expected_rows):
    clients = fx.register_three()

    response = fx.queue_shift(clients[0], delta)

    assert response.status_code == expected_status, response.text
    if expected_body is not None:
        assert response.json() == expected_body
    assert [(fio, position) for fio, position, _status in _positions(env)] == expected_rows

    if expected_status == 200:
        status = fx.queue_status(clients[0])
        assert (status["position"], status["queue_size"]) == (expected_body["new_position"], 3)


def test_shift_from_last_place_is_intentional_400(env):
    clients = fx.register_three()

    response = fx.queue_shift(clients[2], 1)

    assert response.status_code == 400
    assert response.json() == {"detail": "INVALID_SHIFT"}
    assert [(fio, position) for fio, position, _status in _positions(env)] == [
        (fx.FIO_A, 1),
        (fx.FIO_B, 2),
        (fx.FIO_C, 3),
    ]


def test_sequential_repeat_same_lab_is_rejected(env):
    student = fx.student_client(fx.GH_A, fx.FIO_A)

    first = fx.queue_register(student, fx.LAB1)
    second = fx.queue_register(student, fx.LAB1)

    assert first.status_code == 200
    assert first.json() == {"position": 1, "queue_size": 1}
    assert second.status_code == 409
    assert second.json() == {"detail": "ALREADY_IN_QUEUE"}
    assert _positions(env) == [(fx.FIO_A, 1, "ждёт")]


def test_same_identity_other_lab_is_allowed_observation(env):
    student = fx.student_client(fx.GH_A, fx.FIO_A)

    first = fx.queue_register(student, fx.LAB1)
    second = fx.queue_register(student, fx.LAB2)

    assert first.status_code == 200
    assert second.status_code == 200
    assert [(fio, position) for fio, position, _status in _positions(env)] == [
        (fx.FIO_A, 1),
        (fx.FIO_A, 1),
    ]
    assert {row.lab for row in fx.queue_rows(env.spreadsheet)} == {
        fx.LAB1_SHORT,
        fx.LAB2_SHORT,
    }
    # Observation only: no requirement forbidding two different labs was found.
