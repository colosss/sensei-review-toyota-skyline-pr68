"""C06 - the screenshot chain: own position "2 из 2" while the list shows 2,1,1.

Reproduction of the reported UI state at the real HTTP surface:

  register lab1 (Иванов, github A) -> register lab2 (Иванов, github B, same FIO)
  -> register lab1 (Петрова) -> shift lab1 by 1000

Both "Иванов" rows are per-lab positions 1; the shift moves the lab1 one behind
Петрова, so the *whole day sheet* reads [Иванов 2, Иванов 1, Петрова 1].  The
lab1 page renders that list and reports "position 2 of 2" for Иванов.

The observation test records the actual state and is expected to PASS on the
pinned submission (scenario format).  The regression test states the desired
contract - the lab page list is scoped to the requested group/lab and its
positions form one ordinal sequence - and is expected to FAIL on the pinned
submission because GET .../labs/{lab}/queue returns every row of the day sheet.
"""

from __future__ import annotations

import c06_fake_sheets as fx


def _run_screenshot_chain(env):
    """Drive the chain exactly as the frontend would (status + list after each action)."""
    ivanov_a = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    ivanov_b = fx.student_client(fx.GH_IVANOV_B, fx.FIO_IVANOV)
    petrova = fx.student_client(fx.GH_PETROVA, fx.FIO_PETROVA)

    registered = {}
    registered["ivanov_a_lab1"] = fx.queue_register(ivanov_a, fx.LAB1)
    registered["ivanov_b_lab2"] = fx.queue_register(ivanov_b, fx.LAB2)
    registered["petrova_lab1"] = fx.queue_register(petrova, fx.LAB1)
    for name, response in registered.items():
        assert response.status_code == 200, f"{name}: HTTP {response.status_code} {response.text}"

    status_before = fx.queue_status(ivanov_a, fx.LAB1)
    shift = fx.queue_shift(ivanov_a, 1000, fx.LAB1)
    status_after = fx.queue_status(ivanov_a, fx.LAB1)
    lab1_page = fx.queue_list(ivanov_a, fx.LAB1)
    lab2_page = fx.queue_list(ivanov_b, fx.LAB2)

    return {
        "registered": {name: response.json() for name, response in registered.items()},
        "status_before": status_before,
        "shift": {"http": shift.status_code, "body": shift.json()},
        "status_after": status_after,
        "lab1_page": lab1_page,
        "lab2_page": lab2_page,
        "rows": fx.queue_rows(env.spreadsheet),
    }


def test_observed_screenshot_chain_reproduces_2_1_1_and_2_of_2(env):
    """Scenario: record the actual HTTP/UI state. Expected to pass on pinned code."""
    result = _run_screenshot_chain(env)

    assert result["registered"] == {
        "ivanov_a_lab1": {"position": 1, "queue_size": 1},
        "ivanov_b_lab2": {"position": 1, "queue_size": 1},
        "petrova_lab1": {"position": 2, "queue_size": 2},
    }

    before = result["status_before"]
    assert (before["in_queue"], before["position"], before["queue_size"]) == (True, 1, 2)
    assert result["shift"] == {
        "http": 200,
        "body": {"old_position": 1, "new_position": 2},
    }
    after = result["status_after"]
    assert (after["in_queue"], after["position"], after["queue_size"]) == (True, 2, 2)

    lab1_entries = result["lab1_page"]["queue"]
    assert [entry["position"] for entry in lab1_entries] == [2, 1, 1]
    assert [entry["fio"] for entry in lab1_entries] == [
        fx.FIO_IVANOV,
        fx.FIO_IVANOV,
        fx.FIO_PETROVA,
    ]
    assert [entry["lab"] for entry in lab1_entries] == [
        fx.LAB1_SHORT,
        fx.LAB2_SHORT,
        fx.LAB1_SHORT,
    ]
    assert [entry["group"] for entry in lab1_entries] == [fx.GROUP, fx.GROUP, fx.GROUP]
    assert [entry["status"] for entry in lab1_entries] == ["ждёт", "ждёт", "ждёт"]

    # The lab2 page returns the very same three rows - the list is not scoped.
    assert result["lab2_page"]["queue"] == lab1_entries
    assert result["lab1_page"]["size"] == 3

    # Stored rows, in sheet order, are the source of the rendered chips.
    assert [
        (row.position, row.fio, row.lab, row.status) for row in result["rows"]
    ] == [
        (2, fx.FIO_IVANOV, fx.LAB1_SHORT, "ждёт"),
        (1, fx.FIO_IVANOV, fx.LAB2_SHORT, "ждёт"),
        (1, fx.FIO_PETROVA, fx.LAB1_SHORT, "ждёт"),
    ]


def test_observed_list_mixes_other_groups_too(env):
    """Scenario: the same unscoped list also returns a student of another group."""
    petrova_g2 = fx.student_client(
        fx.GH_PETROVA, fx.FIO_PETROVA, group=fx.OTHER_GROUP
    )
    ivanov_g1 = fx.student_client(fx.GH_IVANOV_A, fx.FIO_IVANOV)
    assert fx.queue_register(petrova_g2, fx.LAB1, fx.OTHER_GROUP).status_code == 200
    assert fx.queue_register(ivanov_g1, fx.LAB1).status_code == 200

    page_g1 = fx.queue_list(ivanov_g1, fx.LAB1)
    assert [
        (entry["group"], entry["fio"], entry["position"]) for entry in page_g1["queue"]
    ] == [
        (fx.OTHER_GROUP, fx.FIO_PETROVA, 1),
        (fx.GROUP, fx.FIO_IVANOV, 1),
    ]
    # Meanwhile the personal status of the B-G1 student counts only B-G1.
    status = fx.queue_status(ivanov_g1, fx.LAB1)
    assert (status["in_queue"], status["position"], status["queue_size"]) == (True, 1, 1)


def test_regression_lab_page_list_is_scoped_to_requested_group_and_lab(env):
    """Desired contract: lab1 page lists lab1's queue with ordinal positions 1..n.

    Expected to FAIL on the pinned submission: GET
    /courses/{c}/groups/{group}/labs/{lab}/queue ignores the group/lab path
    parameters and returns every row of the day sheet, so the page shows
    another lab's student and the positions [2, 1, 1] instead of [1, 2].
    """
    result = _run_screenshot_chain(env)
    entries = result["lab1_page"]["queue"]

    labs = [entry["lab"] for entry in entries]
    positions = [entry["position"] for entry in entries]
    assert labs == [fx.LAB1_SHORT] * len(entries), (
        "desired: the lab1 page must list only lab1 rows; actual labs: "
        f"{labs!r}, positions {positions!r}, status says "
        f"{result['status_after']['position']} of {result['status_after']['queue_size']}"
    )
    assert sorted(positions) == list(range(1, len(entries) + 1)), (
        "desired: displayed positions form one ordinal sequence for the "
        f"requested lab; actual positions: {positions!r} (status reports "
        f"position {result['status_after']['position']} of "
        f"{result['status_after']['queue_size']})"
    )
