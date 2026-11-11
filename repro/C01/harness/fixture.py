"""Synthetic in-memory state for the C01 browser harness.

Nothing here touches Google Sheets, GitHub, the filesystem or the network.
The objects implement the small part of the gspread contract that the pinned
application actually calls (see grading/queue/store.py, grading/sheets_client.py
and main.py:register_student).

The fixture is deliberately a *contract fake* of the data source, not a
replacement of the HTTP API: the real ``main.app`` routes run unchanged.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from gspread.exceptions import WorksheetNotFound

COURSE_ID = "review-c01"
SPREADSHEET_ID = "review-c01-sheet"
GROUPS = ["4431", "4432"]
INFO_SHEETS = ["График", "Очередь", "История"]
LAB_KEY = "1"
LAB_SHORT = "ЛР1"
LAB_PREFIX = "lab1"
LAB2_KEY = "2"
LAB2_SHORT = "ЛР2"
LAB2_PREFIX = "lab2"

QUEUE_HEADERS = ["ПОЗИЦИЯ", "ГРУППА", "ФИО", "ЛР", "Пар№", "Статус"]
HISTORY_SHEET = "История_очереди"
HISTORY_HEADERS = ["Дата", "ПОЗИЦИЯ", "ГРУППА", "ФИО", "ЛР", "Пар№", "Статус"]

ROSTER = {
    "4431": [
        ("Иванов Иван Иванович", ""),
        ("Петрова Полина Сергеевна", "review-petrova"),
        ("Сидоров Олег Петрович", ""),
    ],
    "4432": [
        ("Альфа Алина Андреевна", ""),
        ("Бета Борис Борисович", "review-beta"),
    ],
}


class FakeCell:
    def __init__(self, value: Any = "", row: int = 1, col: int = 1):
        self.value = value
        self.row = row
        self.col = col


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]] | None = None, sheet_id: int = 1):
        self.title = title
        self.id = sheet_id
        self.values = [list(row) for row in (rows or [])]

    # -- gspread surface used by the pinned app -------------------------
    def _pad(self, row: int, col: int) -> None:
        while len(self.values) < row:
            self.values.append([])
        while len(self.values[row - 1]) < col:
            self.values[row - 1].append("")

    def row_values(self, row: int) -> list[str]:
        if row < 1 or row > len(self.values):
            return []
        return [str(value) for value in self.values[row - 1]]

    def col_values(self, col: int) -> list[str]:
        return [
            str(row[col - 1]) if len(row) >= col else ""
            for row in self.values
        ]

    def get_all_values(self) -> list[list[str]]:
        return [[str(value) for value in row] for row in self.values]

    def cell(self, row: int, col: int) -> FakeCell:
        self._pad(row, col)
        return FakeCell(self.values[row - 1][col - 1], row, col)

    def update_cell(self, row: int, col: int, value: Any) -> None:
        self._pad(row, col)
        self.values[row - 1][col - 1] = "" if value is None else str(value)

    def append_row(self, values: list[Any], **_kwargs) -> None:
        self.values.append(["" if value is None else str(value) for value in values])

    def find(self, query: str, **_kwargs) -> FakeCell | None:
        for row_index, row in enumerate(self.values, start=1):
            for col_index, value in enumerate(row, start=1):
                if str(value) == str(query):
                    return FakeCell(value, row_index, col_index)
        return None

    def batch_update(self, updates: list[dict], **_kwargs) -> None:
        for update in updates:
            rng = update.get("range")
            if not rng:
                continue
            row = int(rng[1:])
            col = ord(rng[0].upper()) - ord("A") + 1
            values = update.get("values") or [[""]]
            self.update_cell(row, col, values[0][0])


class FakeSpreadsheet:
    """In-memory workbook: group sheets plus queue/history/info sheets."""

    def __init__(self):
        self.id = SPREADSHEET_ID
        self._sheets: dict[str, FakeWorksheet] = {}
        self._next_id = 100
        self.today_str = date.today().isoformat()
        self._build()

    def _build(self) -> None:
        self._sheets.clear()
        self._next_id = 100
        self._add("График", [["График занятий"], ["синтетические данные"]], 1)
        for group in GROUPS:
            self._add(group, self._group_grid(group), self._next_id)
        self._add(HISTORY_SHEET, [HISTORY_HEADERS], self._next_id)
        queue_rows = [QUEUE_HEADERS]
        if ROSTER["4431"]:
            queue_rows.append(["1", "4431", ROSTER["4431"][1][0], LAB_SHORT, "2", "ждёт"])
        self._add(f"Очередь-{self.today_str}", queue_rows, self._next_id)

    def _group_grid(self, group: str) -> list[list[str]]:
        # docs/DEVELOPMENT.md: row 1 has the GitHub header and deadlines,
        # row 2 the lab short names, students start at row 3.
        grid = [
            ["", "", "31.12.2026", "", "GitHub"],
            ["№", "ФИО", LAB_SHORT, LAB2_SHORT, ""],
        ]
        for number, (fio, github) in enumerate(ROSTER[group], start=1):
            grid.append([str(number), fio, "", "", github])
        return grid

    def _add(self, title: str, rows: list[list[str]], sheet_id: int) -> FakeWorksheet:
        worksheet = FakeWorksheet(title, rows, sheet_id)
        self._sheets[title] = worksheet
        self._next_id = max(self._next_id, sheet_id) + 1
        return worksheet

    # -- gspread surface used by the pinned app -------------------------
    def worksheet(self, title: str) -> FakeWorksheet:
        if title not in self._sheets:
            raise WorksheetNotFound(title)
        return self._sheets[title]

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._sheets.values())

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        del rows, cols
        return self._add(title, [], self._next_id)

    def batch_update(self, body: dict) -> None:
        for request in body.get("requests", []):
            if "deleteSheet" in request:
                sheet_id = request["deleteSheet"]["sheetId"]
                for title, worksheet in list(self._sheets.items()):
                    if worksheet.id == sheet_id:
                        del self._sheets[title]
            elif "appendCells" in request:
                sheet_id = request["appendCells"]["sheetId"]
                target = next(
                    (worksheet for worksheet in self._sheets.values() if worksheet.id == sheet_id),
                    None,
                )
                if target is None:
                    continue
                for row in request["appendCells"].get("rows", []):
                    values = [
                        cell["userEnteredValue"].get("stringValue", "")
                        for cell in row.get("values", [])
                    ]
                    target.append_row(values)
            # addFilterView / addProtectedRange are metadata-only for the harness.

    def fetch_sheet_metadata(self) -> dict:
        return {"properties": {"locale": "en_US"}}


class FakeSheetsClient:
    def __init__(self, spreadsheet: FakeSpreadsheet):
        self._spreadsheet = spreadsheet

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        if key != SPREADSHEET_ID:
            raise WorksheetNotFound(f"unknown spreadsheet {key!r}")
        return self._spreadsheet


class SyntheticState:
    """Mutable synthetic world. ``reset()`` rebuilds it in memory only."""

    def __init__(self):
        self.spreadsheet = FakeSpreadsheet()
        self.calls: list[dict[str, str]] = []
        self.reset()

    def reset(self) -> None:
        self.spreadsheet = FakeSpreadsheet()
        self.spreadsheet.today_str = self._today_str()
        self.spreadsheet._build()
        self.calls.clear()
        self.session = self._session()
        self.groups = list(GROUPS)

    def _today_str(self) -> str:
        return datetime.now().date().isoformat()

    def course_info(self) -> dict[str, Any]:
        return {
            "name": "Synthetic Review Course",
            "semester": "Autumn 2026",
            "university": "Review Lab",
            "timezone": "UTC+3",
            "github": {"organization": "review-org", "teachers": []},
            "google": {
                "spreadsheet": SPREADSHEET_ID,
                "info-sheet": list(INFO_SHEETS),
                "task-id-column": 0,
                "student-name-column": 1,
                "lab-column-offset": 1,
            },
            "labs": {
                LAB_KEY: {
                    "short-name": LAB_SHORT,
                    "github-prefix": LAB_PREFIX,
                },
                LAB2_KEY: {
                    "short-name": LAB2_SHORT,
                    "github-prefix": LAB2_PREFIX,
                },
            },
            "_meta": {
                "filename": "review-c01.yaml",
                "status": "active",
                "priority": 1000,
                "logo": "",
                "featured": False,
            },
        }

    def _session(self):
        from grading.schedule import ScheduledSession

        today = datetime.now().date()
        starts = datetime.combine(today, time(10, 40))
        ends = datetime.combine(today, time(12, 10))
        return ScheduledSession(
            course_id=COURSE_ID,
            group_id="4431",
            subject="Synthetic defense",
            starts_at=starts,
            ends_at=ends,
            auto_open_at=starts.replace(hour=10, minute=25),
            auto_close_at=ends.replace(hour=12, minute=20),
            source="manual",
            slot_id="review-slot-2",
            allowed_lab_ids=[LAB_KEY, LAB2_KEY],
            room="A-101",
        )

    def roster(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for group in self.groups:
            worksheet = self.spreadsheet.worksheet(group)
            grid = worksheet.get_all_values()
            github_col = grid[0].index("GitHub") if grid and "GitHub" in grid[0] else 4
            result[group] = [
                {
                    "row": row_index,
                    "fio": row[1] if len(row) > 1 else "",
                    "github": row[github_col] if len(row) > github_col else "",
                }
                for row_index, row in enumerate(grid[2:], start=3)
            ]
        return result

    def queue(self) -> list[dict[str, Any]]:
        worksheet = self.spreadsheet.worksheet(f"Очередь-{self.spreadsheet.today_str}")
        return [
            dict(zip(QUEUE_HEADERS, row))
            for row in worksheet.get_all_values()[1:]
            if any(row)
        ]

    def history(self) -> list[dict[str, Any]]:
        worksheet = self.spreadsheet.worksheet(HISTORY_SHEET)
        return [
            dict(zip(HISTORY_HEADERS, row))
            for row in worksheet.get_all_values()[1:]
            if any(row)
        ]

    def snapshot(self) -> dict[str, Any]:
        course = self.course_info()
        return {
            "course": {
                "id": COURSE_ID,
                "name": course["name"],
                "groups": list(self.groups),
                "labs": {
                    key: {"short-name": value["short-name"], "github-prefix": value["github-prefix"]}
                    for key, value in course["labs"].items()
                },
                "spreadsheet": SPREADSHEET_ID,
            },
            "today": self.spreadsheet.today_str,
            "session": {
                "slot_id": self.session.slot_id,
                "starts_at": self.session.starts_at.isoformat(),
                "ends_at": self.session.ends_at.isoformat(),
                "room": self.session.room,
            },
            "roster": self.roster(),
            "queue": self.queue(),
            "history": self.history(),
            "calls": self.calls[-100:],
        }
