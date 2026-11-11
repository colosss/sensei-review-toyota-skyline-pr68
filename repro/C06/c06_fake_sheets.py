"""C06 synthetic fixture: in-memory Sheets, roster and queue session clock.

This module is not a test.  It provides the disposable state used by the C06
tests, which drive the real FastAPI app through ``TestClient`` (the same HTTP
surface the frontend uses: ``/queue``, ``/queue/status``, ``/queue/register``,
``/queue/withdraw``, ``/queue/shift`` and the admin ``set-status`` route).

Isolation contract (see ``scratch/pipeline/C06/assignment.md``):

* one fresh in-memory workbook per test, spreadsheet id ``review-c06-sheet``;
* synthetic roster only: two students share the FIO "Иванов Иван" but have
  different GitHub logins, plus a third student "Петрова Анна";
* two labs (``ЛР1``/``ЛР2``) in one group (``B-G1``), a second empty group
  (``B-G2``) and one fixed course day (2026-11-08);
* GitHub, CI and the course config are replaced by the app's own seams;
  the student/FIO lookup (``_load_queue_sheet_context``) stays real and reads
  the fake group worksheet, so identity resolution is not bypassed;
* no network, no real Sheets, no file writes, no app YAML changes.

The queue-session clock models the schedule window: a test may switch the
active slot (pair number) between requests with ``env.clock.set(...)``.  This
is deterministic - no sleeps and no wall-clock dependence.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from gspread.exceptions import WorksheetNotFound

import main as main_module
from grading.queue.cache import reset_queue_cache
from grading.queue.locks import reset_locks
from grading.queue.session import build_student_session
from grading.queue.store import (
    HISTORY_HEADERS,
    QUEUE_HEADERS,
    queue_sheet_name,
)

COURSE = "review-c06"
GROUP = "B-G1"
OTHER_GROUP = "B-G2"
LAB1 = "1"
LAB2 = "2"
LAB1_SHORT = "ЛР1"
LAB2_SHORT = "ЛР2"

TODAY = date(2026, 11, 8)
TODAY_STR = TODAY.isoformat()
SPREADSHEET_ID = "review-c06-sheet"

# Same FIO, different GitHub login: the roster genuinely contains two students
# whose full names collide (the screenshot showed two "Иванов" rows).
FIO_IVANOV = "Иванов Иван"
GH_IVANOV_A = "c06-ivanov-a"
GH_IVANOV_B = "c06-ivanov-b"
FIO_PETROVA = "Петрова Анна"
GH_PETROVA = "c06-petrova"

GROUP_HEADERS = ["ФИО", "GitHub", LAB1_SHORT, LAB2_SHORT]


class FakeWorksheet:
    """Minimal worksheet for the gspread calls used by queue code and roster."""

    def __init__(self, title: str, rows: list[list[str]] | None = None, sheet_id: int = 1):
        self.title = title
        self.id = sheet_id
        self.values = [list(row) for row in (rows if rows is not None else [])]

    def _pad(self, row: int, col: int) -> None:
        while len(self.values) < row:
            self.values.append([])
        while len(self.values[row - 1]) < col:
            self.values[row - 1].append("")

    def row_values(self, row: int) -> list[str]:
        return list(self.values[row - 1]) if len(self.values) >= row else []

    def get_all_values(self) -> list[list[str]]:
        return [list(row) for row in self.values]

    def update_cell(self, row: int, col: int, value) -> None:
        self._pad(row, col)
        self.values[row - 1][col - 1] = str(value)

    def append_row(self, values, **_kwargs) -> None:
        self.values.append([str(value) for value in values])

    def batch_update(self, updates, **_kwargs) -> None:
        for update in updates:
            cell_range = update["range"]
            column = ord(cell_range[0].upper()) - ord("A") + 1
            row = int(cell_range[1:])
            self.update_cell(row, column, update["values"][0][0])


class FakeSpreadsheet:
    """In-memory workbook: roster sheets, today's queue and history."""

    def __init__(self) -> None:
        self.id = SPREADSHEET_ID
        self._next_id = 100
        self._sheets: dict[str, FakeWorksheet] = {
            GROUP: FakeWorksheet(GROUP, _group_grid(), sheet_id=1),
            OTHER_GROUP: FakeWorksheet(OTHER_GROUP, _group_grid(), sheet_id=2),
            queue_sheet_name(TODAY): FakeWorksheet(
                queue_sheet_name(TODAY), [list(QUEUE_HEADERS)], sheet_id=3
            ),
            "История_очереди": FakeWorksheet(
                "История_очереди", [list(HISTORY_HEADERS)], sheet_id=4
            ),
        }

    def worksheet(self, title: str) -> FakeWorksheet:
        try:
            return self._sheets[title]
        except KeyError:
            raise WorksheetNotFound(title) from None

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._sheets.values())

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        worksheet = FakeWorksheet(title, [["" for _ in range(cols)]], self._next_id)
        self._next_id += 1
        self._sheets[title] = worksheet
        return worksheet

    def fetch_sheet_metadata(self) -> dict:
        return {"properties": {"locale": "en_US"}}

    def batch_update(self, body) -> None:
        for request in body.get("requests", []):
            if "deleteSheet" in request:
                sheet_id = request["deleteSheet"]["sheetId"]
                for title, worksheet in list(self._sheets.items()):
                    if worksheet.id == sheet_id:
                        del self._sheets[title]
            elif "appendCells" in request:
                target = next(
                    worksheet
                    for worksheet in self._sheets.values()
                    if worksheet.id == request["appendCells"]["sheetId"]
                )
                for row in request["appendCells"]["rows"]:
                    target.append_row(
                        [
                            cell["userEnteredValue"]["stringValue"]
                            for cell in row["values"]
                        ]
                    )


def _group_grid() -> list[list[str]]:
    """Roster grid read by grading.queue.sheets_context (rows 3+ are students)."""
    return [
        GROUP_HEADERS,
        ["", "", LAB1_SHORT, LAB2_SHORT],
        [FIO_IVANOV, GH_IVANOV_A, "v", "v"],
        [FIO_IVANOV, GH_IVANOV_B, "v", "v"],
        [FIO_PETROVA, GH_PETROVA, "v", "v"],
    ]


def _course_info() -> dict:
    return {
        "name": "Review C06 course",
        "timezone": "UTC+3",
        "github": {"organization": "review-c06-org", "teachers": []},
        "google": {"spreadsheet": SPREADSHEET_ID, "student-name-column": 0},
        "labs": {
            LAB1: {
                "short-name": LAB1_SHORT,
                "github-prefix": "lab1",
                "template-repo": "review-c06-org/lab1-template",
                "repo-provisioning": "generate",
                "files": ["main.py"],
                "ci": ["workflows"],
            },
            LAB2: {
                "short-name": LAB2_SHORT,
                "github-prefix": "lab2",
                "template-repo": "review-c06-org/lab2-template",
                "repo-provisioning": "generate",
                "files": ["main.py"],
                "ci": ["workflows"],
            },
        },
        "_meta": {
            "filename": "review-c06.yaml",
            "status": "active",
            "priority": 0,
            "logo": None,
            "featured": False,
        },
    }


class SessionClock:
    """One active class slot; tests change it between requests instead of time."""

    def __init__(self, slot_id: str = "guap-mon-2") -> None:
        self.slot_id = slot_id

    def set(self, slot_id: str) -> None:
        self.slot_id = slot_id

    def current(self):
        return SimpleNamespace(
            slot_id=self.slot_id,
            subject="Review C06",
            starts_at=datetime(2026, 11, 8, 10, 40),
            ends_at=datetime(2026, 11, 8, 12, 10),
            room="101",
        )


def build_env(monkeypatch):
    """Install the fake workbook and app seams; yields the per-test environment."""
    spreadsheet = FakeSpreadsheet()
    clock = SessionClock()

    monkeypatch.setattr(main_module, "get_course_by_id", lambda course_id: _course_info())
    monkeypatch.setattr(
        main_module,
        "sheets_client",
        lambda: SimpleNamespace(open_by_key=lambda spreadsheet_id: spreadsheet),
    )
    monkeypatch.setattr(
        main_module, "_queue_active_session", lambda *args, **kwargs: clock.current()
    )
    monkeypatch.setattr(main_module, "_queue_next_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_queue_today_str", lambda course_info: TODAY_STR)
    monkeypatch.setattr(
        main_module, "_schedule_group_ids", lambda course_id: [GROUP, OTHER_GROUP]
    )
    # CI/GitHub checks are not part of C06; assume the queue gate is passed.
    monkeypatch.setattr(main_module, "ensure_ci_passed", lambda **kwargs: None)
    monkeypatch.setattr(main_module, "GitHubClient", lambda token: SimpleNamespace())
    monkeypatch.setattr(main_module, "_resolve_queue_team", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module.limiter, "enabled", False)

    reset_locks()
    reset_queue_cache()
    yield SimpleNamespace(spreadsheet=spreadsheet, clock=clock)
    reset_locks()
    reset_queue_cache()


def queue_rows(spreadsheet: FakeSpreadsheet):
    """Raw queue rows as the store sees them (for fixture assertions)."""
    from grading.queue.store import read_queue_rows

    return read_queue_rows(spreadsheet.worksheet(queue_sheet_name(TODAY)))


# --- Real HTTP surface used by the frontend -------------------------------


def queue_url(lab: str, suffix: str = "", group: str = GROUP) -> str:
    """Same path shape as frontend/src/api/index.js ``defenseQueueUrl``."""
    return f"/courses/{COURSE}/groups/{group}/labs/{lab}/queue{suffix}"


def student_client(github: str, fio: str, group: str = GROUP) -> TestClient:
    """TestClient carrying the signed student cookie the queue routes require."""
    cookie = build_student_session(main_module.signer, github, fio, COURSE, group)
    return TestClient(main_module.app, cookies={"student_session": cookie})


def admin_client() -> TestClient:
    """TestClient with a valid admin cookie (same signer as /admin/login)."""
    cookie = main_module.signer.sign(main_module.ADMIN_LOGIN.encode()).decode()
    return TestClient(main_module.app, cookies={"admin_session": cookie})


def queue_status(client: TestClient, lab: str = LAB1, group: str = GROUP) -> dict:
    return client.get(queue_url(lab, "/status", group)).json()


def queue_list(client: TestClient, lab: str = LAB1, group: str = GROUP) -> dict:
    return client.get(queue_url(lab, "", group)).json()


def queue_register(client: TestClient, lab: str = LAB1, group: str = GROUP):
    return client.post(queue_url(lab, "/register", group))


def queue_withdraw(client: TestClient, lab: str = LAB1, group: str = GROUP):
    return client.post(queue_url(lab, "/withdraw", group))


def queue_shift(client: TestClient, delta: int, lab: str = LAB1, group: str = GROUP):
    return client.post(queue_url(lab, "/shift", group), json={"delta": delta})


def admin_set_status(
    client: TestClient,
    identifier: str,
    status: str,
    lab: str = LAB1,
    group: str = GROUP,
):
    return client.post(
        f"/admin/courses/{COURSE}/groups/{group}/labs/{lab}/queue/set-status",
        json={"identifier": identifier, "status": status},
    )
