"""Q03 - same FIO, different GitHub login: B mutates A's queue row.

Roster rows (both real, distinct students):

* ``Иванов Иван`` / ``c06-ivanov-a`` (A)
* ``Иванов Иван`` / ``c06-ivanov-b`` (B)

B's ``student_session`` is built with the application signer and B's own
GitHub username via ``build_student_session`` - a completed, reliable OAuth
login.  The test never calls the public registration form and never claims
A's login; there is no impersonation of A's GitHub account.  The real
``_load_queue_sheet_context`` resolves each username to its own roster row,
but both rows carry the same FIO, and ``store`` keys mutate operations on
``fio`` only.

Desired contract: an authenticated student acts on their own row; the app
must distinguish the two real persons.  A distinct-FIO control shows that the
FIO key protects unrelated students, so the failure is specific to the
same-FIO collision.

Observation tests record the actual state and are expected to PASS on the
pinned submission.  Regression tests state the desired contract and are
expected to FAIL on the pinned submission.  This cause is separate from C04:
B is properly authenticated as B; no public re-registration and no A login.
"""

from __future__ import annotations

import c06_fake_sheets as fx


def _clients():
    ivanov_a = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    ivanov_b = fx.student_client(fx.GH_IVANOV_B, fx.FIO_IVANOV)
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)
    return ivanov_a, ivanov_b, petrova


def _rows(env):
    return [
        (row.position, row.fio, row.status) for row in fx.queue_rows(env.spreadsheet)
    ]


def test_observed_b_withdraw_changes_a_row(env):
    """Scenario: B (own valid session, same FIO) withdraws and removes A."""
    ivanov_a, ivanov_b, _petrova = _clients()
    assert fx.queue_register(ivanov_a, fx.LAB1).json() == {
        "position": 1,
        "queue_size": 1,
    }

    withdrawn = fx.queue_withdraw(ivanov_b, fx.LAB1)
    assert withdrawn.status_code == 200
    assert withdrawn.json() == {"status": "withdrawn"}

    # A never asked to leave; A's row is gone from the waiting queue.
    assert _rows(env) == [(1, fx.FIO_IVANOV, "отозван")]
    assert fx.queue_status(ivanov_a, fx.LAB1)["in_queue"] is False


def test_observed_b_shift_reorders_a_row(env):
    """Scenario: B shifts by 1 and A moves behind Петрова."""
    ivanov_a, ivanov_b, petrova = _clients()
    assert fx.queue_register(ivanov_a, fx.LAB1).status_code == 200
    assert fx.queue_register(petrova, fx.LAB1).status_code == 200

    shifted = fx.queue_shift(ivanov_b, 1, fx.LAB1)
    assert shifted.status_code == 200
    assert shifted.json() == {"old_position": 1, "new_position": 2}

    assert _rows(env) == [
        (2, fx.FIO_IVANOV, "ждёт"),
        (1, fx.FIO_PETROVA, "ждёт"),
    ]


def test_control_distinct_fio_withdraw_changes_only_own_row(env):
    """Control: a different FIO cannot reach A's row; only its own row changes."""
    ivanov_a, _ivanov_b, petrova = _clients()
    assert fx.queue_register(ivanov_a, fx.LAB1).status_code == 200
    assert fx.queue_register(petrova, fx.LAB1).status_code == 200

    withdrawn = fx.queue_withdraw(petrova, fx.LAB1)
    assert withdrawn.status_code == 200

    assert _rows(env) == [
        (1, fx.FIO_IVANOV, "ждёт"),
        (2, fx.FIO_PETROVA, "отозван"),
    ]


def test_regression_b_withdraw_must_not_change_a_row(env):
    """Desired: B's withdraw is rejected and A's waiting row stays intact.

    Expected to FAIL on the pinned submission: store matches by FIO, so B's
    properly authenticated request removes A's row (HTTP 200, "отозван").
    """
    ivanov_a, ivanov_b, _petrova = _clients()
    assert fx.queue_register(ivanov_a, fx.LAB1).status_code == 200

    response = fx.queue_withdraw(ivanov_b, fx.LAB1)
    rows = _rows(env)
    assert not 200 <= response.status_code < 300 and rows == [
        (1, fx.FIO_IVANOV, "ждёт")
    ], (
        "desired: B's own session must not change A's row; actual "
        f"withdraw HTTP {response.status_code} {response.text!r}, rows {rows!r}"
    )


def test_regression_b_shift_must_not_reorder_a_row(env):
    """Desired: B's shift is rejected and A keeps position 1.

    Expected to FAIL on the pinned submission: store matches by FIO, so B's
    shift moves A behind Петрова (old 1 -> new 2).
    """
    ivanov_a, ivanov_b, petrova = _clients()
    assert fx.queue_register(ivanov_a, fx.LAB1).status_code == 200
    assert fx.queue_register(petrova, fx.LAB1).status_code == 200

    response = fx.queue_shift(ivanov_b, 1, fx.LAB1)
    rows = _rows(env)
    assert not 200 <= response.status_code < 300 and rows == [
        (1, fx.FIO_IVANOV, "ждёт"),
        (2, fx.FIO_PETROVA, "ждёт"),
    ], (
        "desired: B's own session must not move A; actual shift HTTP "
        f"{response.status_code} {response.text!r}, rows {rows!r}"
    )
