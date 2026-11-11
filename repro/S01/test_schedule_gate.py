"""S01: schedule gate for the daily defense queue.

Invariant checked in the regression test: a schedule correction that cancels
one lab inside a slot (``remove_slots[].labs``) must close the queue for that
lab, as documented in ``source/docs/schedule-config.md`` ("Если дополнительно
указан список ``labs``, отменяются только эти лабораторные в слоте").

The documented and shipped default is a slot with no ``labs`` key: GUAP-imported
slots omit it and ``schedules/dev-course.yaml`` has no ``labs`` and no
``queue_settings``.  ``grading/schedule/manual.py::_resolve_day`` can only
subtract labs from such a slot if ``queue_settings.all_lab_ids`` is declared;
otherwise it silently keeps ``allowed_lab_ids = None`` ("all labs").

Isolation (per assignment "review-gates-B"):
  * one temporary schedule directory per test (``tmp_path``), one fake
    in-memory spreadsheet with synthetic students, unique course id;
  * managed clock: ``active_session_for`` is the real gate, called with an
    explicit ``now`` and ``schedules_dir``; system time is not changed;
  * the real ``main.queue_register`` is exercised through ``TestClient``;
  * CI is out of scope here and is stubbed as passed, so only the schedule
    gate decides admission;
  * no real Sheets/GitHub/GUAP/network, no writes outside ``tmp_path``/memory.
"""

import itertools
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from gspread.exceptions import WorksheetNotFound

import main as main_module
from grading.queue.cache import reset_queue_cache
from grading.queue.schedule_window import active_session_for, reset_schedule_cache
from grading.queue.session import build_student_session
from grading.queue.store import (
    HISTORY_HEADERS,
    QUEUE_HEADERS,
    STATUS_WAITING,
    read_queue_rows,
)

GROUP = "4431"
TODAY = "2026-11-09"          # Monday, ISO week 46
FAKE_NOW = datetime(2026, 11, 9, 12, 0)
SLOT_START = "10:40:00"
SLOT_END = "12:10:00"
FIO = "Студент Дельта"
GITHUB = "s01-student-a"

_COURSE_SEQ = itertools.count(1)


# ---------------------------------------------------------------------------
# Fake Google Sheets (surface used by the queue endpoints)
# ---------------------------------------------------------------------------
class FakeCell:
    def __init__(self, value):
        self.value = value


class FakeWorksheet:
    def __init__(self, title, rows=None, sheet_id=1):
        self.title = title
        self.id = sheet_id
        self.values = [list(row) for row in (rows or [])]

    def _pad(self, row, col):
        while len(self.values) < row:
            self.values.append([])
        while len(self.values[row - 1]) < col:
            self.values[row - 1].append("")

    def row_values(self, row):
        return list(self.values[row - 1]) if len(self.values) >= row else []

    def get_all_values(self):
        return [list(row) for row in self.values]

    def col_values(self, col):
        return [row[col - 1] if len(row) >= col else "" for row in self.values]

    def cell(self, row, col):
        self._pad(row, col)
        return FakeCell(self.values[row - 1][col - 1])

    def update_cell(self, row, col, value):
        self._pad(row, col)
        self.values[row - 1][col - 1] = str(value)

    def append_row(self, values, **_kw):
        self.values.append([str(v) for v in values])

    def batch_update(self, updates, **_kw):
        for update in updates:
            cell_range = update["range"]
            col = ord(cell_range[0].upper()) - ord("A") + 1
            row = int(cell_range[1:])
            self.update_cell(row, col, update["values"][0][0])


class FakeSpreadsheet:
    def __init__(self, spreadsheet_id):
        self.id = spreadsheet_id
        self._sheets = {}
        self._next_id = 100
        self._sheets[GROUP] = FakeWorksheet(GROUP, _group_grid(), sheet_id=1)
        self._sheets["Очередь-" + TODAY] = FakeWorksheet(
            "Очередь-" + TODAY, [QUEUE_HEADERS], sheet_id=2
        )
        self._sheets["История_очереди"] = FakeWorksheet(
            "История_очереди", [HISTORY_HEADERS], sheet_id=3
        )

    def worksheet(self, title):
        if title not in self._sheets:
            raise WorksheetNotFound(title)
        return self._sheets[title]

    def worksheets(self):
        return list(self._sheets.values())

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title, [["" for _ in range(cols)]], self._next_id)
        self._next_id += 1
        self._sheets[title] = worksheet
        return worksheet

    def fetch_sheet_metadata(self):
        return {"properties": {"locale": "en_US"}}

    def batch_update(self, body):
        for request in body.get("requests", []):
            if "deleteSheet" in request:
                for title, worksheet in list(self._sheets.items()):
                    if worksheet.id == request["deleteSheet"]["sheetId"]:
                        del self._sheets[title]
            elif "appendCells" in request:
                target = next(
                    worksheet
                    for worksheet in self._sheets.values()
                    if worksheet.id == request["appendCells"]["sheetId"]
                )
                for row in request["appendCells"]["rows"]:
                    target.append_row(
                        [cell["userEnteredValue"]["stringValue"] for cell in row["values"]]
                    )


def _group_grid():
    return [
        ["ФИО", "GitHub", "ЛР1", "ЛР3"],
        ["", "", "ЛР1", "ЛР3"],
        [FIO, GITHUB, "", ""],
    ]


# ---------------------------------------------------------------------------
# Schedule fixtures (written to tmp_path, never to source/schedules)
# ---------------------------------------------------------------------------
def schedule_yaml(course_id, labs_line="", corrections=""):
    return f"""course-id: {course_id}
source: manual
timezone: UTC+3
auto_open_minutes_before: 30
auto_close_minutes_after: 30
manual-groups:
  - "{GROUP}"
groups:
  "{GROUP}":
    group_id: "{GROUP}"
    slots:
      - id: guap-mon-2
        recurrence:
          day: monday
          week: all
        start: '{SLOT_START}'
        end: '{SLOT_END}'
        subject: Операционные системы
{labs_line}{corrections}"""


ALL_LABS_YAML = schedule_yaml(
    course_id="{course}",
    corrections="""    corrections:
      - id: cancel-lab3-mon-2
        date: '2026-11-09'
        remove_slots:
          - slot_id: guap-mon-2
            labs: ['3']
""",
)

EXPLICIT_LABS_YAML = schedule_yaml(
    course_id="{course}",
    labs_line="        labs: ['1', '3']\n",
    corrections="""    corrections:
      - id: cancel-lab3-mon-2
        date: '2026-11-09'
        remove_slots:
          - slot_id: guap-mon-2
            labs: ['3']
""",
)

NO_CORRECTION_YAML = schedule_yaml(course_id="{course}")


def _course_info(course_id):
    return {
        "name": "Review S01 course",
        "timezone": "UTC+3",
        "github": {"organization": "review-s01-org", "teachers": []},
        "google": {
            "spreadsheet": f"review-s01-sheet-{course_id}",
            "student-name-column": 0,
        },
        "labs": {
            "1": {"short-name": "ЛР1", "github-prefix": "s01lab1", "files": []},
            "3": {"short-name": "ЛР3", "github-prefix": "s01lab3", "files": []},
        },
        "_meta": {
            "filename": f"{course_id}.yaml",
            "status": "active",
            "priority": 0,
            "logo": None,
            "featured": False,
        },
    }


@pytest.fixture
def make_env(monkeypatch, tmp_path):
    """builder(yaml_template, now=FAKE_NOW) -> (client, spreadsheet, course_id)."""

    def build(yaml_template, now=FAKE_NOW):
        reset_schedule_cache()
        reset_queue_cache()
        course_id = f"review-s01-{next(_COURSE_SEQ)}"
        (tmp_path / f"{course_id}.yaml").write_text(
            yaml_template.format(course=course_id), encoding="utf-8"
        )
        spreadsheet = FakeSpreadsheet(f"review-s01-sheet-{course_id}")

        monkeypatch.setattr(
            main_module, "get_course_by_id", lambda cid: _course_info(course_id)
        )
        monkeypatch.setattr(
            main_module,
            "sheets_client",
            lambda: SimpleNamespace(open_by_key=lambda spreadsheet_id: spreadsheet),
        )
        monkeypatch.setattr(
            main_module,
            "_queue_active_session",
            lambda cid, gid, lab_key: active_session_for(
                cid, gid, lab_key, now=now, schedules_dir=tmp_path
            ),
        )
        monkeypatch.setattr(main_module, "_queue_next_session", lambda *a, **kw: None)
        monkeypatch.setattr(main_module, "_queue_today_str", lambda course_info: TODAY)
        monkeypatch.setattr(main_module, "_schedule_group_ids", lambda cid: [GROUP])
        # CI is a different packet (C03); stub it as passed so that only the
        # schedule gate decides admission here.
        monkeypatch.setattr(main_module, "ensure_ci_passed", lambda **kw: None)
        monkeypatch.setattr(main_module.limiter, "enabled", False)

        client = TestClient(main_module.app)
        cookie = build_student_session(
            main_module.signer, GITHUB, FIO, course_id, GROUP
        )
        client.cookies.set("student_session", cookie)
        return client, spreadsheet, course_id

    return build


def _register(client, course_id, lab):
    return client.post(f"/courses/{course_id}/groups/{GROUP}/labs/{lab}/queue/register")


def _waiting_rows(spreadsheet, lab_short_name):
    worksheet = spreadsheet.worksheet("Очередь-" + TODAY)
    return [
        row for row in read_queue_rows(worksheet)
        if row.group == GROUP and row.lab == lab_short_name and row.status == STATUS_WAITING
    ]


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
def test_control_no_correction_allows_any_lab(make_env):
    client, spreadsheet, course_id = make_env(NO_CORRECTION_YAML)
    response = _register(client, course_id, "3")

    assert response.status_code == 200, response.text
    assert len(_waiting_rows(spreadsheet, "ЛР3")) == 1


def test_control_time_window_closes_after_auto_close(make_env):
    client, _spreadsheet, course_id = make_env(
        NO_CORRECTION_YAML, now=datetime(2026, 11, 9, 12, 40, 1)
    )
    response = _register(client, course_id, "1")

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "QUEUE_CLOSED"


def test_control_correction_works_for_explicit_lab_list(make_env):
    """With an explicit ``labs`` list the same correction is applied."""
    client, _spreadsheet, course_id = make_env(EXPLICIT_LABS_YAML)
    allowed = _register(client, course_id, "1")
    cancelled = _register(client, course_id, "3")

    assert allowed.status_code == 200, allowed.text
    assert cancelled.status_code == 403, cancelled.text
    assert cancelled.json()["detail"] == "QUEUE_CLOSED"


# ---------------------------------------------------------------------------
# Regression assertion (expected to fail on the pinned code)
# ---------------------------------------------------------------------------
def test_cancelled_lab_must_be_closed_for_all_labs_slot(make_env):
    """The shipped/documented slot shape (no ``labs`` key) with a lab cancels."""
    client, spreadsheet, course_id = make_env(ALL_LABS_YAML)

    allowed = _register(client, course_id, "1")
    assert allowed.status_code == 200, (
        f"control failed: the queue window must be open at {FAKE_NOW}: "
        f"HTTP {allowed.status_code} {allowed.text}"
    )

    cancelled = _register(client, course_id, "3")
    states = [(row.fio, row.lab, row.status) for row in _waiting_rows(spreadsheet, "ЛР3")]
    assert cancelled.status_code == 403 and states == [], (
        "desired contract: schedule-config.md says remove_slots[].labs cancels "
        "only those labs in the slot, so lab 3 must be closed; actual: "
        f"register HTTP {cancelled.status_code} ({cancelled.text}), "
        f"queue rows for ЛР3 {states!r}"
    )
