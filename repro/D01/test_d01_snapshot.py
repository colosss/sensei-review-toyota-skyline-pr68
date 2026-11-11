"""D01: closing a past day must not lose rows written after the read.

Contract (pinned PR's own documentation):

* ``source/docs/SETUP.md:97-105`` — «Как скрипт и backend не мешают друг
  другу. Обе стороны выполняют одну и ту же идемпотентную операцию…»:
  step 4 «проверить, что все строки очереди есть в истории», step 5
  «удалить лист очереди, только если он не менялся с момента чтения».
* ``source/docs/SETUP.md:129-130`` — «Лист изменился во время закрытия. В лист
  прошлой даты кто-то писал во время копирования. Лист не удалён, следующий
  запуск добавит недостающие строки и закроет его.»
* ``source/docs/hackathon/ADR-queue-storage.md:108-113`` — the teacher works in
  the sheet directly (manual edits are a stated feature), so a past-day sheet
  can be modified outside the backend.

``grading/queue/store.py::snapshot_sheet`` reads the tab, builds the append
list, then sends ``appendCells`` + ``deleteSheet`` in one ``batch_update``.
It never re-reads the tab before deleting it (unlike
``queue-apps-script/Code.gs:156-169``, which does exactly that), so a row or a
status change that lands after the read is deleted without being archived.

Isolation: in-memory workbook only (id ``review-persistence-B``), one fresh
object per test, no network, no real Sheets, no file writes, no browser.
The fake ``batch_update`` mirrors the Google Sheets request shape the code
sends (``appendCells`` with ``userEnteredValue.stringValue`` rows and
``deleteSheet`` by ``sheetId``) and can simulate an external write between the
read and the batch, plus a partial failure (append applied, delete failed).
"""

from datetime import date

import pytest
from gspread.exceptions import WorksheetNotFound

from grading.queue.store import (
    HISTORY_HEADERS,
    QUEUE_HEADERS,
    STATUS_PASSED,
    maybe_snapshot_past_days,
    snapshot_sheet,
)

SPREADSHEET_ID = "review-persistence-B"
QUEUE_SHEET = "Очередь-2026-11-07"
TODAY_SHEET = "Очередь-2026-11-08"
FUTURE_SHEET = "Очередь-2026-11-09"
HISTORY = "История_очереди"
TODAY = date(2026, 11, 8)

ROWS = [
    [1, "4431", "Иванов Иван", "ЛР1", 2, "ждёт"],
    [2, "4431", "Петрова Анна", "ЛР1", 2, "сдал"],
    [1, "4432", "Сидоров Пётр", "ЛР2", 1, "отозван"],
]


class FakeWorksheet:
    def __init__(self, title, rows=None, sheet_id=1):
        self.title = title
        self.id = sheet_id
        self.values = [list(row) for row in (rows if rows is not None else [])]

    def _pad(self, row, col):
        while len(self.values) < row:
            self.values.append([])
        while len(self.values[row - 1]) < col:
            self.values[row - 1].append("")

    def row_values(self, row):
        # Real gspread returns strings for every cell of get_all_values/row_values.
        return (
            [str(value) for value in self.values[row - 1]]
            if len(self.values) >= row
            else []
        )

    def get_all_values(self):
        return [[str(value) for value in row] for row in self.values]

    def update_cell(self, row, col, value):
        self._pad(row, col)
        self.values[row - 1][col - 1] = str(value)

    def append_row(self, values, **_kwargs):
        self.values.append([str(value) for value in values])


class FakeSpreadsheet:
    """In-memory workbook with a hook for the supported "sheet changed" case."""

    def __init__(self, rows=None):
        self.id = SPREADSHEET_ID
        self._next_id = 100
        self._sheets = {
            QUEUE_SHEET: FakeWorksheet(
                QUEUE_SHEET, [list(QUEUE_HEADERS)] + [list(r) for r in (rows or ROWS)],
                sheet_id=1,
            ),
            HISTORY: FakeWorksheet(HISTORY, [list(HISTORY_HEADERS)], sheet_id=2),
        }
        # "before": raise before applying any request.
        # "before_delete": append history rows, then raise instead of deleting.
        self.fail_mode = None
        # Called inside batch_update, i.e. after snapshot_sheet has read the tab
        # and before its append/delete requests are applied: simulates a teacher
        # or Apps Script writing to the tab during the close.
        self.on_batch_update = None

    def worksheet(self, title):
        try:
            return self._sheets[title]
        except KeyError:
            raise WorksheetNotFound(title) from None

    def worksheets(self):
        return list(self._sheets.values())

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title, [["" for _ in range(cols)]], self._next_id)
        self._next_id += 1
        self._sheets[title] = worksheet
        return worksheet

    def fetch_sheet_metadata(self):
        return {"properties": {"locale": "en_US"}}

    def _append_cells(self, request):
        target = next(
            worksheet
            for worksheet in self._sheets.values()
            if worksheet.id == request["appendCells"]["sheetId"]
        )
        for row in request["appendCells"]["rows"]:
            target.append_row(
                [cell["userEnteredValue"]["stringValue"] for cell in row["values"]]
            )

    def _delete_sheet(self, request):
        sheet_id = request["deleteSheet"]["sheetId"]
        for title, worksheet in list(self._sheets.items()):
            if worksheet.id == sheet_id:
                del self._sheets[title]
                return
        raise KeyError(f"sheetId {sheet_id} not found")

    def batch_update(self, body):
        requests = body.get("requests", [])
        if self.fail_mode == "before":
            raise RuntimeError("simulated Sheets batch failure")
        if self.on_batch_update is not None:
            self.on_batch_update(self)
        for request in requests:
            if "appendCells" in request:
                self._append_cells(request)
            elif "deleteSheet" in request:
                if self.fail_mode == "before_delete":
                    raise RuntimeError("simulated deleteSheet failure")
                self._delete_sheet(request)
            else:
                raise AssertionError(f"unexpected request in fake: {request}")


def _history_rows(spreadsheet):
    return spreadsheet.worksheet(HISTORY).get_all_values()[1:]


def _has_sheet(spreadsheet, title):
    return any(worksheet.title == title for worksheet in spreadsheet.worksheets())


def _archive_statuses(spreadsheet):
    return {row[3]: row[6] for row in _history_rows(spreadsheet)}


# ---------------------------------------------------------------------------
# Controls: archive/retry behaviour that the pinned code does get right
# ---------------------------------------------------------------------------
def test_observed_snapshot_archives_rows_and_maps_waiting_to_not_reached():
    spreadsheet = FakeSpreadsheet()

    copied = snapshot_sheet(spreadsheet, QUEUE_SHEET)

    assert copied == 3
    assert _history_rows(spreadsheet) == [
        ["2026-11-07", "1", "4431", "Иванов Иван", "ЛР1", "2", "не_дошло"],
        ["2026-11-07", "2", "4431", "Петрова Анна", "ЛР1", "2", "сдал"],
        ["2026-11-07", "1", "4432", "Сидоров Пётр", "ЛР2", "1", "отозван"],
    ]
    assert not _has_sheet(spreadsheet, QUEUE_SHEET)


def test_control_retry_after_partial_append_has_no_loss_and_no_duplicates():
    """Append applied, deleteSheet failed: the retry must not duplicate or drop."""
    spreadsheet = FakeSpreadsheet()
    spreadsheet.fail_mode = "before_delete"

    with pytest.raises(RuntimeError, match="deleteSheet"):
        maybe_snapshot_past_days(spreadsheet, TODAY)

    assert _has_sheet(spreadsheet, QUEUE_SHEET), "a failed close must keep the tab"
    assert len(_history_rows(spreadsheet)) == 3, "rows copied before the failure stay"

    spreadsheet.fail_mode = None
    copied = maybe_snapshot_past_days(spreadsheet, TODAY)

    assert copied == 0
    assert not _has_sheet(spreadsheet, QUEUE_SHEET)
    assert sorted(row[3] for row in _history_rows(spreadsheet)) == [
        "Иванов Иван",
        "Петрова Анна",
        "Сидоров Пётр",
    ]


def test_control_retry_after_full_append_failure_copies_once():
    spreadsheet = FakeSpreadsheet()
    spreadsheet.fail_mode = "before"

    with pytest.raises(RuntimeError, match="batch failure"):
        maybe_snapshot_past_days(spreadsheet, TODAY)

    assert _has_sheet(spreadsheet, QUEUE_SHEET)
    assert _history_rows(spreadsheet) == []

    spreadsheet.fail_mode = None
    assert maybe_snapshot_past_days(spreadsheet, TODAY) == 3
    assert not _has_sheet(spreadsheet, QUEUE_SHEET)
    assert len(_history_rows(spreadsheet)) == 3


def test_control_second_run_is_idempotent_and_future_tabs_are_kept():
    spreadsheet = FakeSpreadsheet()
    spreadsheet._sheets[TODAY_SHEET] = FakeWorksheet(
        TODAY_SHEET, [list(QUEUE_HEADERS)], sheet_id=3
    )
    spreadsheet._sheets[FUTURE_SHEET] = FakeWorksheet(
        FUTURE_SHEET, [list(QUEUE_HEADERS)], sheet_id=4
    )

    assert maybe_snapshot_past_days(spreadsheet, TODAY) == 3
    assert maybe_snapshot_past_days(spreadsheet, TODAY) == 0

    assert not _has_sheet(spreadsheet, QUEUE_SHEET)
    assert _has_sheet(spreadsheet, TODAY_SHEET)
    assert _has_sheet(spreadsheet, FUTURE_SHEET)
    assert len(_history_rows(spreadsheet)) == 3


# ---------------------------------------------------------------------------
# Regression assertions (expected to fail on the pinned code)
# ---------------------------------------------------------------------------
def test_regression_close_must_not_drop_row_added_after_read():
    """SETUP.md:129-130: a tab that changed during copying must not be deleted."""
    spreadsheet = FakeSpreadsheet()

    def late_row(_spreadsheet):
        spreadsheet.worksheet(QUEUE_SHEET).append_row(
            [3, "4431", "Новиков Олег", "ЛР1", 2, "ждёт"]
        )

    spreadsheet.on_batch_update = late_row

    snapshot_sheet(spreadsheet, QUEUE_SHEET)

    archived = [row[3] for row in _history_rows(spreadsheet)]
    still_open = _has_sheet(spreadsheet, QUEUE_SHEET)
    assert still_open or "Новиков Олег" in archived, (
        "desired contract (SETUP.md:104-105,129-130): a row written to the past-day "
        "tab after the backend read it must either be archived or keep the tab for "
        "the next run; actual: history FIOs "
        f"{archived!r}, tab still present={still_open}"
    )


def test_regression_late_status_change_must_not_be_archived_stale():
    """The same close must not archive a status the teacher changed before delete."""
    spreadsheet = FakeSpreadsheet()

    def mark_passed(_spreadsheet):
        worksheet = spreadsheet.worksheet(QUEUE_SHEET)
        for row in worksheet.values[1:]:
            if row[2] == "Иванов Иван":
                row[5] = "сдал"

    spreadsheet.on_batch_update = mark_passed

    snapshot_sheet(spreadsheet, QUEUE_SHEET)

    archived = _archive_statuses(spreadsheet)
    still_open = _has_sheet(spreadsheet, QUEUE_SHEET)
    assert still_open or archived.get("Иванов Иван") == STATUS_PASSED, (
        "desired contract (SETUP.md:104-105,129-130): the close must observe the "
        "tab as it was at deletion time; actual: archived status for Иванов Иван "
        f"is {archived.get('Иванов Иван')!r}, all statuses {archived!r}, "
        f"tab still present={still_open}"
    )
