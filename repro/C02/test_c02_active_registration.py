"""C02: uniqueness of an active (waiting) queue registration.

Invariant under test: for one student identity within one course/group/lab/day
there may be at most one *waiting* queue entry. A second registration must be
rejected with ALREADY_IN_QUEUE instead of appending another row. The check must
also hold for a second request that names another session of the same lab, and
under concurrent requests.

Not asserted as a requirement: whether the same student may wait for two
*different* labs on the same day. The sources express no such prohibition, so
the different-lab case is only observed for over-blocking.

Isolation: in-memory fake gspread Spreadsheet/Worksheet (id
"review-c02-sheet"), function-scoped state, process-local queue lock reset per
test. No network, no real Sheets, no app YAML or runtime writes. Synthetic data
only. Run through scripts/run_review_tests.py.
"""

from __future__ import annotations

import threading
from datetime import date

import pytest

from grading.queue.errors import QueueError
from grading.queue.locks import reset_locks
from grading.queue.store import (
    QUEUE_HEADERS,
    HISTORY_HEADERS,
    STATUS_WAITING,
    queue_sheet_name,
    read_queue_rows,
    register,
)

TODAY = date(2026, 11, 8)
NEXT_DAY = date(2026, 11, 9)
GROUP = "C02-G"
FIO = "c02-student-a"
LAB_A = "ЛР-C02-A"
LAB_B = "ЛР-C02-B"


class FakeWorksheet:
    """Minimal worksheet matching the gspread calls used by grading.queue.store."""

    def __init__(self, title: str, sheet_id: int, rows: list[list[str]], read_delay: float = 0.0):
        self.title = title
        self.id = sheet_id
        self._rows = [list(row) for row in rows]
        self._guard = threading.Lock()
        self._read_delay = read_delay

    def row_values(self, row: int) -> list[str]:
        with self._guard:
            return list(self._rows[row - 1]) if len(self._rows) >= row else []

    def get_all_values(self) -> list[list[str]]:
        with self._guard:
            snapshot = [list(row) for row in self._rows]
        # Widen the read/append window for the concurrency case only; the
        # course lock, not this fake, must serialize the mutation.
        if self._read_delay:
            threading.Event().wait(self._read_delay)
        return snapshot

    def update_cell(self, row: int, col: int, value) -> None:
        with self._guard:
            while len(self._rows) < row:
                self._rows.append([])
            row_values = self._rows[row - 1]
            while len(row_values) < col:
                row_values.append("")
            row_values[col - 1] = str(value)

    def append_row(self, values, **_kwargs) -> None:
        with self._guard:
            self._rows.append([str(value) for value in values])

    def batch_update(self, updates, **_kwargs) -> None:
        for update in updates:
            cell_range = update["range"]
            column = ord(cell_range[0].upper()) - ord("A") + 1
            row = int(cell_range[1:])
            self.update_cell(row, column, update["values"][0][0])


class FakeSpreadsheet:
    """Minimal in-memory spreadsheet with the id used for the process lock."""

    def __init__(self, day: date = TODAY, read_delay: float = 0.0):
        self.id = "review-c02-sheet"
        self._read_delay = read_delay
        self._next_id = 100
        today = FakeWorksheet(queue_sheet_name(day), 1, [QUEUE_HEADERS], read_delay)
        history = FakeWorksheet("История_очереди", 2, [HISTORY_HEADERS])
        self._sheets = {today.title: today, history.title: history}

    def worksheet(self, title: str):
        from gspread.exceptions import WorksheetNotFound

        try:
            return self._sheets[title]
        except KeyError:
            raise WorksheetNotFound(title) from None

    def worksheets(self):
        return list(self._sheets.values())

    def add_worksheet(self, title: str, rows: int, cols: int):
        worksheet = FakeWorksheet(title, self._next_id, [], self._read_delay)
        self._next_id += 1
        self._sheets[title] = worksheet
        return worksheet

    def batch_update(self, body) -> None:
        # The register path only reaches this when creating a new day tab.
        for request in body.get("requests", []):
            if "deleteSheet" in request:
                sheet_id = request["deleteSheet"]["sheetId"]
                for title, worksheet in list(self._sheets.items()):
                    if worksheet.id == sheet_id:
                        del self._sheets[title]


@pytest.fixture(autouse=True)
def _fresh_process_locks():
    reset_locks()
    yield
    reset_locks()


def _waiting_rows(spreadsheet: FakeSpreadsheet, day: date = TODAY):
    return read_queue_rows(spreadsheet.worksheet(queue_sheet_name(day)))


def test_second_registration_same_identity_group_lab_day_is_rejected():
    """Desired contract: one waiting row, second call raises ALREADY_IN_QUEUE."""
    spreadsheet = FakeSpreadsheet()

    assert register(spreadsheet, TODAY, GROUP, FIO, LAB_A) == 1
    with pytest.raises(QueueError) as error:
        register(spreadsheet, TODAY, GROUP, FIO, LAB_A)

    assert error.value.code == "ALREADY_IN_QUEUE"
    rows = _waiting_rows(spreadsheet)
    assert [(row.group, row.fio, row.lab, row.status) for row in rows] == [
        (GROUP, FIO, LAB_A, STATUS_WAITING)
    ]
    assert len(rows) == 1


def test_second_registration_in_other_session_of_same_lab_is_rejected():
    """The duplicate guard intentionally ignores session_no (store.py:413-424)."""
    spreadsheet = FakeSpreadsheet()

    assert register(spreadsheet, TODAY, GROUP, FIO, LAB_A, session_no=1) == 1
    with pytest.raises(QueueError) as error:
        register(spreadsheet, TODAY, GROUP, FIO, LAB_A, session_no=2)

    assert error.value.code == "ALREADY_IN_QUEUE"
    rows = _waiting_rows(spreadsheet)
    assert len(rows) == 1
    assert (rows[0].lab, rows[0].session_no) == (LAB_A, 1)


def test_different_labs_for_same_identity_are_not_blocked():
    """Observation only: no source requires forbidding two different labs."""
    spreadsheet = FakeSpreadsheet()

    assert register(spreadsheet, TODAY, GROUP, FIO, LAB_A) == 1
    assert register(spreadsheet, TODAY, GROUP, FIO, LAB_B) == 1

    rows = _waiting_rows(spreadsheet)
    assert len(rows) == 2
    assert {row.lab for row in rows} == {LAB_A, LAB_B}
    assert {row.position for row in rows} == {1}


def test_same_identity_on_another_day_has_its_own_tab_and_is_allowed():
    """Queue is per day: a next-day registration must not collide with yesterday."""
    spreadsheet = FakeSpreadsheet()

    assert register(spreadsheet, TODAY, GROUP, FIO, LAB_A) == 1
    assert register(spreadsheet, NEXT_DAY, GROUP, FIO, LAB_A) == 1

    assert len(_waiting_rows(spreadsheet, TODAY)) == 1
    assert len(_waiting_rows(spreadsheet, NEXT_DAY)) == 1


def test_concurrent_duplicate_registrations_leave_exactly_one_waiting_row():
    """Two simultaneous calls: one appends, the other gets ALREADY_IN_QUEUE."""
    spreadsheet = FakeSpreadsheet(read_delay=0.05)
    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, object]] = []
    outcomes_guard = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=5)
        try:
            position = register(spreadsheet, TODAY, GROUP, FIO, LAB_A)
            result: tuple[str, object] = ("ok", position)
        except QueueError as error:
            result = ("error", error.code)
        with outcomes_guard:
            outcomes.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(kind for kind, _ in outcomes) == ["error", "ok"]
    assert ("error", "ALREADY_IN_QUEUE") in outcomes
    assert ("ok", 1) in outcomes

    rows = _waiting_rows(spreadsheet)
    assert len(rows) == 1
    assert (rows[0].group, rows[0].fio, rows[0].lab, rows[0].status) == (
        GROUP,
        FIO,
        LAB_A,
        STATUS_WAITING,
    )
