"""C04: identity authority of queue register / withdraw / shift.

The invariant checked here is the one from the queue ADR (students act on
their own queue record) combined with the signed, scoped session contract
in ``grading/queue/session.py``: a session that is not proven to belong to a
student must not be able to change another student's waiting record.

Fixture isolation, per assignment:
  * one fresh in-memory fake spreadsheet per test, id ``review-c04-sheet``;
  * real app endpoint functions called through ``TestClient`` against
    ``main.app``, with separate cookie jars for A, B, C and an anonymous
    client (no cookies at all);
  * course/group/lab and clock are injected through the app's own seams
    (``get_course_by_id``, ``_queue_active_session``, ``_queue_today_str``);
  * the only external call made by public registration is the GitHub
    "user exists" check, replaced by a contract-compliant fake response;
  * no real Sheets, no real GitHub, no real network, no file writes.

The regression assertions state the desired behaviour (the foreign record
must stay intact and the call must be rejected). They are expected to fail
on the pinned code if the identity contract is violated.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from gspread.exceptions import WorksheetNotFound

import main as main_module
from grading.queue.store import (
    HISTORY_HEADERS,
    QUEUE_HEADERS,
    STATUS_WAITING,
    read_queue_rows,
)

COURSE = "review-c04"
GROUP = "C04-G"
LAB = "1"
TODAY = "2026-11-08"
SPREADSHEET_ID = "review-c04-sheet"

FIO_A, GH_A = "Студент Альфа", "c04-student-a"
FIO_B, GH_B = "Студент Бета", "c04-student-b"
FIO_C, GH_C = "Студент Гамма", "c04-student-c"


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
        return [
            row[col - 1] if len(row) >= col else ""
            for row in self.values
        ]

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
    def __init__(self):
        self.id = SPREADSHEET_ID
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
        worksheet = FakeWorksheet(title, [[ "" for _ in range(cols)]], self._next_id)
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
    # Row 1: headers (FIO / GitHub / lab), row 2: lab header row, rows 3+:
    # students.  ``student-name-column: 0`` means column A in both the
    # registration endpoint and grading.queue.sheets_context.
    return [
        ["ФИО", "GitHub", "ЛР1"],
        ["", "", "ЛР1"],
        [FIO_A, GH_A, "v"],
        [FIO_B, GH_B, "v"],
        [FIO_C, GH_C, "v"],
    ]


def _course_info():
    return {
        "name": "Review C04 course",
        "timezone": "UTC+3",
        "github": {"organization": "review-c04-org", "teachers": []},
        "google": {
            "spreadsheet": SPREADSHEET_ID,
            "student-name-column": 0,
        },
        "labs": {
            "1": {
                "short-name": "ЛР1",
                "github-prefix": "lab1",
                "template-repo": "review-c04-org/lab1-template",
                "repo-provisioning": "generate",
                "files": ["main.py"],
                "ci": ["workflows"],
            }
        },
        "_meta": {
            "filename": "review-c04.yaml",
            "status": "active",
            "priority": 0,
            "logo": None,
            "featured": False,
        },
    }


def _fake_session():
    return SimpleNamespace(
        slot_id="guap-mon-2",
        subject="Review C04",
        starts_at=datetime(2026, 11, 8, 10, 40),
        ends_at=datetime(2026, 11, 8, 12, 10),
        room="101",
    )


@pytest.fixture
def env(monkeypatch):
    """Fresh fake Sheets store + patched app seams, per test."""
    spreadsheet = FakeSpreadsheet()

    monkeypatch.setattr(main_module, "get_course_by_id", lambda course_id: _course_info())
    monkeypatch.setattr(
        main_module,
        "sheets_client",
        lambda: SimpleNamespace(open_by_key=lambda spreadsheet_id: spreadsheet),
    )
    monkeypatch.setattr(main_module, "_queue_active_session", lambda *a, **kw: _fake_session())
    monkeypatch.setattr(main_module, "_queue_today_str", lambda course_info: TODAY)
    monkeypatch.setattr(main_module, "_schedule_group_ids", lambda course_id: [GROUP])
    # CI check is not part of this packet; assume passed CI (contract-compliant)
    # and assert nothing about it here.
    monkeypatch.setattr(main_module, "ensure_ci_passed", lambda **kw: None)
    # Public registration calls GET api.github.com/users/<login>; the fake
    # answers exactly as GitHub would for an existing account.
    monkeypatch.setattr(
        main_module.requests,
        "get",
        lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {}),
    )
    # Rate limiting is out of scope in this packet.
    monkeypatch.setattr(main_module.limiter, "enabled", False)

    yield SimpleNamespace(spreadsheet=spreadsheet)


def _client():
    return TestClient(main_module.app)


def _register(client, fio, github):
    surname, name = fio.split(" ", 1)
    return client.post(
        f"/courses/{COURSE}/groups/{GROUP}/register",
        json={
            "surname": surname,
            "name": name,
            "patronymic": "",
            "github": github,
        },
    )


def _queue_register(client):
    return client.post(
        f"/courses/{COURSE}/groups/{GROUP}/labs/{LAB}/queue/register"
    )


def _queue_withdraw(client):
    return client.post(
        f"/courses/{COURSE}/groups/{GROUP}/labs/{LAB}/queue/withdraw"
    )


def _queue_shift(client, delta=1):
    return client.post(
        f"/courses/{COURSE}/groups/{GROUP}/labs/{LAB}/queue/shift",
        json={"delta": delta},
    )


def _queue_row(spreadsheet, fio):
    worksheet = spreadsheet.worksheet("Очередь-" + TODAY)
    rows = [row for row in read_queue_rows(worksheet) if row.fio == fio]
    assert len(rows) == 1, f"expected exactly one queue row for {fio!r}, found {len(rows)}"
    return rows[0]


def _queue_student(client):
    response = _queue_register(client)
    assert response.status_code == 200, (
        f"queue registration setup failed: HTTP {response.status_code}"
    )


def test_unauthenticated_and_peer_sessions_cannot_withdraw_b(env):
    """Control: no cookie -> 401; a genuine peer session only sees itself."""
    client_b = _client()
    anon = _client()
    client_a = _client()

    assert _register(client_b, FIO_B, GH_B).status_code == 200
    _queue_student(client_b)
    assert _queue_row(env.spreadsheet, FIO_B).status == STATUS_WAITING

    no_cookie = _queue_withdraw(anon)
    assert no_cookie.status_code == 401, (
        f"anonymous withdraw without any session must be rejected, "
        f"got HTTP {no_cookie.status_code}"
    )

    assert _register(client_a, FIO_A, GH_A).status_code == 200
    peer = _queue_withdraw(client_a)
    assert peer.status_code == 404, (
        f"session A must not resolve student B's entry; got HTTP {peer.status_code}"
    )
    assert _queue_row(env.spreadsheet, FIO_B).status == STATUS_WAITING, (
        "student B's waiting record changed after a peer/session-A withdraw"
    )


def test_public_registration_of_another_identity_cannot_withdraw_b(env):
    """An unauthenticated visitor claims B (public FIO + public GitHub login)."""
    client_b = _client()
    anon = _client()

    assert _register(client_b, FIO_B, GH_B).status_code == 200
    _queue_student(client_b)

    # Public, unauthenticated registration: no OAuth, no proof of GitHub
    # ownership; the only check is that the login exists.
    _register(anon, FIO_B, GH_B)

    response = _queue_withdraw(anon)
    observed_status = _queue_row(env.spreadsheet, FIO_B).status
    assert response.status_code in (401, 403) and observed_status == STATUS_WAITING, (
        "desired contract: an unproven identity must not change another "
        "student's waiting record; actual: "
        f"withdraw HTTP {response.status_code}, entry status {observed_status!r}"
    )


def test_public_registration_of_another_identity_cannot_shift_b(env):
    """Same escalation, exercised through shift while B is ahead of C."""
    client_b = _client()
    client_c = _client()
    anon = _client()

    assert _register(client_b, FIO_B, GH_B).status_code == 200
    assert _register(client_c, FIO_C, GH_C).status_code == 200
    _queue_student(client_b)
    _queue_student(client_c)
    before = _queue_row(env.spreadsheet, FIO_B).position

    _register(anon, FIO_B, GH_B)

    response = _queue_shift(anon, delta=1)
    after = _queue_row(env.spreadsheet, FIO_B).position
    assert response.status_code in (401, 403) and after == before, (
        "desired contract: an unproven identity must not reorder another "
        "student's waiting record; actual: "
        f"shift HTTP {response.status_code}, position {before} -> {after}"
    )
