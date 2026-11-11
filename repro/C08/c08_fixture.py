"""C08 fixture: independent in-memory queue state for the shift matrix.

Deliberately self-contained: does not import or reuse repro/C06 helpers.
One course, one group, two labs, three students with distinct FIO so that
same-name identity collision (Q03) cannot influence shift results.

Real FastAPI endpoints are driven through TestClient; only Sheets, CI/GitHub
and the active class slot are replaced by the app's own seams.  No network,
no browser, no real Sheets, no file writes.
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

COURSE = "review-c08"
GROUP = "C08-G"
LAB1 = "1"
LAB2 = "2"
LAB1_SHORT = "ЛР1"
LAB2_SHORT = "ЛР2"
TODAY = date(2026, 11, 8)
TODAY_STR = TODAY.isoformat()
SPREADSHEET_ID = "review-c08-sheet"

FIO_A, GH_A = "Альфа Студент", "c08-alpha"
FIO_B, GH_B = "Бета Студент", "c08-beta"
FIO_C, GH_C = "Гамма Студент", "c08-gamma"

GROUP_HEADERS = ["ФИО", "GitHub", LAB1_SHORT, LAB2_SHORT]


class FakeWorksheet:
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
    def __init__(self) -> None:
        self.id = SPREADSHEET_ID
        self._next_id = 100
        self._sheets: dict[str, FakeWorksheet] = {
            GROUP: FakeWorksheet(GROUP, _group_grid(), sheet_id=1),
            queue_sheet_name(TODAY): FakeWorksheet(
                queue_sheet_name(TODAY), [list(QUEUE_HEADERS)], sheet_id=2
            ),
            "История_очереди": FakeWorksheet(
                "История_очереди", [list(HISTORY_HEADERS)], sheet_id=3
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
    return [
        GROUP_HEADERS,
        ["", "", LAB1_SHORT, LAB2_SHORT],
        [FIO_A, GH_A, "v", "v"],
        [FIO_B, GH_B, "v", "v"],
        [FIO_C, GH_C, "v", "v"],
    ]


def _course_info() -> dict:
    return {
        "name": "Review C08 course",
        "timezone": "UTC+3",
        "github": {"organization": "review-c08-org", "teachers": []},
        "google": {"spreadsheet": SPREADSHEET_ID, "student-name-column": 0},
        "labs": {
            LAB1: {
                "short-name": LAB1_SHORT,
                "github-prefix": "lab1",
                "template-repo": "review-c08-org/lab1-template",
                "repo-provisioning": "generate",
                "files": ["main.py"],
                "ci": ["workflows"],
            },
            LAB2: {
                "short-name": LAB2_SHORT,
                "github-prefix": "lab2",
                "template-repo": "review-c08-org/lab2-template",
                "repo-provisioning": "generate",
                "files": ["main.py"],
                "ci": ["workflows"],
            },
        },
        "_meta": {
            "filename": "review-c08.yaml",
            "status": "active",
            "priority": 0,
            "logo": None,
            "featured": False,
        },
    }


class SessionClock:
    def __init__(self, slot_id: str = "guap-mon-2") -> None:
        self.slot_id = slot_id

    def current(self):
        return SimpleNamespace(
            slot_id=self.slot_id,
            subject="Review C08",
            starts_at=datetime(2026, 11, 8, 10, 40),
            ends_at=datetime(2026, 11, 8, 12, 10),
            room="101",
        )


def build_env(monkeypatch):
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
        main_module, "_schedule_group_ids", lambda course_id: [GROUP]
    )
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
    from grading.queue.store import read_queue_rows

    return read_queue_rows(spreadsheet.worksheet(queue_sheet_name(TODAY)))


def queue_url(lab: str, suffix: str = "") -> str:
    return f"/courses/{COURSE}/groups/{GROUP}/labs/{lab}/queue{suffix}"


def student_client(github: str, fio: str) -> TestClient:
    cookie = build_student_session(main_module.signer, github, fio, COURSE, GROUP)
    return TestClient(main_module.app, cookies={"student_session": cookie})


def queue_register(client: TestClient, lab: str = LAB1):
    return client.post(queue_url(lab, "/register"))


def queue_shift(client: TestClient, delta, lab: str = LAB1):
    return client.post(queue_url(lab, "/shift"), json={"delta": delta})


def queue_status(client: TestClient, lab: str = LAB1) -> dict:
    return client.get(queue_url(lab, "/status")).json()


def register_three():
    clients = [
        student_client(GH_A, FIO_A),
        student_client(GH_B, FIO_B),
        student_client(GH_C, FIO_C),
    ]
    for client in clients:
        response = queue_register(client, LAB1)
        assert response.status_code == 200, response.text
    return clients
