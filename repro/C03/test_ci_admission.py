"""C03: queue admission must refuse a CI that completed but did not pass.

Contract under test (all from the pinned source, SHA 20bea22):

* ``grading/queue/ci.py`` ``ensure_ci_passed`` says the verdict comes from
  ``outcome.passed`` and that it "Raises QueueError with a stable code on any
  non-passing outcome"; the non-passing code is ``CI_NOT_PASSED``.
* The same module's own unit test
  ``source/tests/test_ci.py::test_ensure_ci_passed_writes_failed_grade_like_grade_endpoint``
  asserts ``CI_NOT_PASSED`` for ``StudentOutcome(status="updated",
  cell_value="x", passed=False)``.
* The queue status endpoint only advertises ``can_register`` for a queue that
  is open; the register endpoint is the enforcement point for CI.

The real producer of ``StudentOutcome.passed`` is ``grading/bulk.py``
``evaluate_student`` via ``grading/grader.py``: for a *completed* CI it stores
the formatted ratio string ``"N/M тестов пройдено"`` (``GradeResult.passed``
is declared ``str | None``), not a boolean.  The regression assertions below
state the desired behaviour (reject and do not queue) and are expected to fail
on the pinned code when CI is red.

Isolation (per assignment "review-gates-B"):
  * one fresh in-memory fake spreadsheet per test, ids ``review-c03-*``;
  * real ``main.queue_register`` -> real ``ensure_ci_passed`` ->
    real ``evaluate_student`` -> real ``LabGrader``/``GitHubClient``;
  * only the GitHub HTTP transport is replaced, with payloads shaped like the
    documented REST responses the client actually parses;
  * schedule gate, course config and the current date are injected through
    the app's own seams; no real Sheets/GitHub/network, no file writes.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from gspread.exceptions import WorksheetNotFound

import grading.github_client as github_client_module
import main as main_module
from grading.queue.cache import reset_queue_cache
from grading.queue.session import build_student_session
from grading.queue.store import (
    HISTORY_HEADERS,
    QUEUE_HEADERS,
    STATUS_WAITING,
    read_queue_rows,
)

COURSE = "review-c03"
GROUP = "C03-G"
LAB = "1"
TODAY = "2026-11-08"
ORG = "review-c03-org"
SHA = "c03" + "0" * 37
FIO = "Студент Гамма"
GITHUB = "c03-student-a"
REPO = f"c03lab-{GITHUB}"


# ---------------------------------------------------------------------------
# Fake Google Sheets (same surface used by the queue endpoints)
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
    def __init__(self, grade_cell):
        self.id = "review-c03-sheet"
        self._sheets = {}
        self._next_id = 100
        self._sheets[GROUP] = FakeWorksheet(GROUP, _group_grid(grade_cell), sheet_id=1)
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


def _group_grid(grade_cell):
    # Row 1: headers; row 2: lab header row; row 3: the single student.
    # student-name-column: 0 -> column A in sheets_context.
    return [
        ["ФИО", "GitHub", "ЛР1"],
        ["", "", "ЛР1"],
        [FIO, GITHUB, grade_cell],
    ]


# ---------------------------------------------------------------------------
# Fake GitHub REST transport (payloads follow the shapes GitHubClient parses)
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        return self._payload


class FakeGitHubTransport:
    """Contract-shaped responses for the endpoints GitHubClient calls."""

    def __init__(self, conclusion, completed_at="2026-11-08T09:00:00Z"):
        self.conclusion = conclusion
        self.completed_at = completed_at
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        prefix = f"{github_client_module.GitHubClient.BASE_URL}/repos/{ORG}/{REPO}"
        if url == f"{prefix}":
            return FakeResponse(200, {"name": REPO, "full_name": f"{ORG}/{REPO}"})
        if url == f"{prefix}/contents/.github/workflows":
            return FakeResponse(200, {"type": "dir", "path": ".github/workflows"})
        if url == f"{prefix}/commits":
            return FakeResponse(200, [{"sha": SHA}])
        if url == f"{prefix}/commits/{SHA}":
            return FakeResponse(200, {"sha": SHA, "files": []})
        if url == f"{prefix}/commits/{SHA}/check-runs":
            return FakeResponse(200, {
                "total_count": 1,
                "check_runs": [{
                    "id": 42,
                    "name": "test",
                    "conclusion": self.conclusion,
                    "status": "completed" if self.conclusion else "in_progress",
                    "html_url": f"https://github.com/{ORG}/{REPO}/runs/42/job/42",
                    "completed_at": self.completed_at,
                }],
            })
        return FakeResponse(404, {"message": "Not Found"})


# ---------------------------------------------------------------------------
# App seams
# ---------------------------------------------------------------------------
def _course_info():
    return {
        "name": "Review C03 course",
        "timezone": "UTC+3",
        "github": {"organization": ORG, "teachers": []},
        "google": {"spreadsheet": "review-c03-sheet", "student-name-column": 0},
        "labs": {
            LAB: {
                "short-name": "ЛР1",
                "github-prefix": "c03lab",
                "files": [],
                "ci": {"jobs": ["test"]},
            }
        },
        "_meta": {
            "filename": "review-c03.yaml",
            "status": "active",
            "priority": 0,
            "logo": None,
            "featured": False,
        },
    }


def _fake_session():
    return SimpleNamespace(
        slot_id="guap-mon-2",
        subject="Review C03",
        starts_at=datetime(2026, 11, 8, 10, 40),
        ends_at=datetime(2026, 11, 8, 12, 10),
        room="101",
    )


@pytest.fixture
def make_env(monkeypatch):
    """Return a builder: (conclusion, grade_cell) -> (client, spreadsheet, transport)."""

    def build(conclusion, grade_cell=""):
        reset_queue_cache()
        spreadsheet = FakeSpreadsheet(grade_cell)
        transport = FakeGitHubTransport(conclusion)
        monkeypatch.setattr(github_client_module.requests, "get", transport.get)
        monkeypatch.setattr(main_module, "get_course_by_id", lambda course_id: _course_info())
        monkeypatch.setattr(
            main_module,
            "sheets_client",
            lambda: SimpleNamespace(open_by_key=lambda spreadsheet_id: spreadsheet),
        )
        monkeypatch.setattr(main_module, "_queue_active_session", lambda *a, **kw: _fake_session())
        monkeypatch.setattr(main_module, "_queue_today_str", lambda course_info: TODAY)
        monkeypatch.setattr(main_module, "_schedule_group_ids", lambda course_id: [GROUP])
        monkeypatch.setattr(main_module.limiter, "enabled", False)

        client = TestClient(main_module.app)
        cookie = build_student_session(
            main_module.signer, GITHUB, FIO, COURSE, GROUP
        )
        client.cookies.set("student_session", cookie)
        return client, spreadsheet, transport

    return build


def _queue_register(client):
    return client.post(
        f"/courses/{COURSE}/groups/{GROUP}/labs/{LAB}/queue/register"
    )


def _waiting_rows(spreadsheet):
    worksheet = spreadsheet.worksheet("Очередь-" + TODAY)
    return [
        row for row in read_queue_rows(worksheet)
        if row.group == GROUP and row.lab == "ЛР1" and row.status == STATUS_WAITING
    ]


def _grade_cell(spreadsheet):
    return spreadsheet.worksheet(GROUP).get_all_values()[2][2]


# ---------------------------------------------------------------------------
# Controls: the fake transport drives the real CI evaluator end to end
# ---------------------------------------------------------------------------
def test_control_passing_ci_admits_and_records_grade(make_env):
    client, spreadsheet, transport = make_env("success")
    response = _queue_register(client)

    assert response.status_code == 200, response.text
    assert len(_waiting_rows(spreadsheet)) == 1
    # A completed passing CI is synced into the grade cell ("v") by design.
    assert _grade_cell(spreadsheet).startswith("v")
    # The CI verdict is requested for exactly the commit returned as latest.
    assert [url for url in transport.calls if url.endswith("/check-runs")] == [
        f"{github_client_module.GitHubClient.BASE_URL}/repos/{ORG}/{REPO}"
        f"/commits/{SHA}/check-runs"
    ]


def test_control_pending_ci_is_rejected(make_env):
    client, spreadsheet, _transport = make_env(None)
    response = _queue_register(client)

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "CI_PENDING"
    assert _waiting_rows(spreadsheet) == []


# ---------------------------------------------------------------------------
# Regression assertions (expected to fail on the pinned code)
# ---------------------------------------------------------------------------
def test_failing_ci_must_not_admit(make_env):
    """A completed CI with a failing job is a non-passing outcome."""
    client, spreadsheet, _transport = make_env("failure")
    response = _queue_register(client)

    states = [(row.fio, row.status) for row in _waiting_rows(spreadsheet)]
    assert response.status_code == 400 and states == [], (
        "desired contract: a student whose current HEAD CI did not pass must "
        "not enter the defense queue (CI_NOT_PASSED); actual: "
        f"register HTTP {response.status_code} "
        f"({response.text}), waiting rows {states!r}, "
        f"grade cell after the call {_grade_cell(spreadsheet)!r}"
    )


def test_protected_passing_cell_with_failing_current_ci_must_not_admit(make_env):
    """``ci.py`` allows a protected cell only when current HEAD CI is green."""
    client, spreadsheet, _transport = make_env("failure", grade_cell="v")
    response = _queue_register(client)

    states = [(row.fio, row.status) for row in _waiting_rows(spreadsheet)]
    assert response.status_code == 400 and states == [], (
        "desired contract: an earlier passing run kept in a protected cell "
        "does not replace CI on the current HEAD; actual: "
        f"register HTTP {response.status_code} ({response.text}), "
        f"waiting rows {states!r}, grade cell {_grade_cell(spreadsheet)!r}"
    )
