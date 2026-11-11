"""Isolated review harness. Application code is loaded from REVIEW_SOURCE."""
import os
from pathlib import Path
import sys
import tempfile

SOURCE = Path(os.environ.get("REVIEW_SOURCE", str(Path(__file__).resolve().parents[1] / "source"))).resolve()
sys.path.insert(0, str(SOURCE))
os.chdir(SOURCE)
_LOG_DIR = tempfile.TemporaryDirectory(prefix="pr68-review-")
os.environ.update(ADMIN_LOGIN="review", ADMIN_PASSWORD="review-local-only",
                  SECRET_KEY="review-only", GITHUB_TOKEN="dummy",
                  LOG_DIR=_LOG_DIR.name)

import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace
import main
from grading.queue.session import build_student_session
from grading.queue.store import QUEUE_HEADERS, HISTORY_HEADERS
from grading.queue.schedule_window import reset_schedule_cache
from gspread.exceptions import WorksheetNotFound

DAY = "2026-11-09"
BASE = "/courses/review/groups/G1/labs"


class Worksheet:
    def __init__(self, title, rows, sheet_id):
        self.title, self.id = title, sheet_id
        self.values = [list(row) for row in rows]
        self.writes = []

    def row_values(self, row):
        return list(self.values[row - 1]) if len(self.values) >= row else []

    def col_values(self, col):
        return [row[col - 1] if len(row) >= col else "" for row in self.values]

    def cell(self, row, col):
        data = self.row_values(row)
        return SimpleNamespace(value=data[col - 1] if len(data) >= col else "")

    def get_all_values(self):
        return [list(row) for row in self.values]

    def update_cell(self, row, col, value):
        self.writes.append((row, col, str(value)))
        while len(self.values) < row:
            self.values.append([])
        while len(self.values[row - 1]) < col:
            self.values[row - 1].append("")
        self.values[row - 1][col - 1] = str(value)

    def append_row(self, values, **kwargs):
        self.values.append([str(v) for v in values])

    def batch_update(self, updates, **kwargs):
        for item in updates:
            address = item["range"]
            self.update_cell(int(address[1:]), ord(address[0]) - 64, item["values"][0][0])


class Spreadsheet:
    id = "synthetic-review-sheet"
    locale = "en_US"

    def __init__(self):
        self.sheets = {}
        self.add("Очередь-" + DAY, [QUEUE_HEADERS])
        self.add("История_очереди", [HISTORY_HEADERS])
        self.add("G1", [["№", "ФИО", "GitHub", "", ""],
                        ["", "", "", "L1", "L2"],
                        ["1", "Alice Synthetic", "alice", "v", "v"],
                        ["2", "Bob Synthetic", "bob", "v", "v"],
                        ["3", "Carol Synthetic", "carol", "v", "v"]])

    def add(self, title, rows):
        ws = Worksheet(title, rows, len(self.sheets) + 1)
        self.sheets[title] = ws
        return ws

    def worksheet(self, title):
        if title not in self.sheets:
            raise WorksheetNotFound(title)
        return self.sheets[title]

    def worksheets(self):
        return list(self.sheets.values())

    def fetch_sheet_metadata(self):
        return {"properties": {"locale": "en_US"}}

    def add_worksheet(self, title, rows, cols):
        return self.add(title, [])

    def batch_update(self, body):
        for request in body["requests"]:
            if "appendCells" in request:
                data = request["appendCells"]
                target = next(ws for ws in self.worksheets() if ws.id == data["sheetId"])
                for row in data["rows"]:
                    target.append_row([v["userEnteredValue"]["stringValue"] for v in row["values"]])
            if "deleteSheet" in request:
                sid = request["deleteSheet"]["sheetId"]
                self.sheets = {title: ws for title, ws in self.sheets.items() if ws.id != sid}


def course():
    return {"name": "Synthetic course", "timezone": "UTC+3",
            "github": {"organization": "synthetic-org"},
            "google": {"spreadsheet": "synthetic-review-sheet", "student-name-column": 1},
            "labs": {key: {"short-name": "L" + key, "github-prefix": "lab" + key,
                            "ignore-task-id": True, "ci": {"workflows": ["test"]}} for key in ("1", "2")}}


def ci_evaluation(passed=True):
    from grading.grader import GradeResult, GradeStatus, CIEvaluation
    from grading.ci_checker import format_ci_result_string
    return CIEvaluation(
        grade_result=GradeResult(GradeStatus.UPDATED, "v" if passed else "x",
                                 "synthetic CI result", format_ci_result_string(int(passed), 1)),
        ci_passed=passed,
    )


class FakeGrader:
    """Only GitHub-facing grader operations are substituted; evaluate_student is real."""
    def __init__(self, evaluation):
        self.evaluation = evaluation
    def check_repository(self, *args):
        return None
    def check_forbidden_files(self, *args):
        return None
    def _evaluate_ci_internal(self, *args):
        return self.evaluation


class OfflineGitHub:
    """GitHubClient-shaped fake; grading and CI evaluation stay unmodified."""
    conclusion = "success"

    def has_workflows_directory(self, *args):
        return True

    def get_latest_commit(self, *args):
        return SimpleNamespace(sha="synthetic-commit", files=[])

    def get_check_runs(self, *args):
        return [{"name": "test", "conclusion": self.conclusion,
                 "html_url": "https://example.invalid/check/1"}]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    ss = Spreadsheet()
    config = course()
    reset_schedule_cache()
    path = tmp_path / "review.yaml"
    path.write_text("""course-id: review
source: manual
timezone: UTC+3
auto_open_minutes_before: 15
auto_close_minutes_after: 0
groups:
  G1:
    group_id: G1
    slots:
      - id: mon-2
        date: '2026-11-09'
        start: '10:40'
        end: '12:10'
""")
    from grading.queue.schedule_window import active_session_for
    from datetime import datetime
    clock = {"now": datetime(2026, 11, 9, 11, 0)}
    monkeypatch.setattr(main, "get_course_by_id", lambda _: config)
    monkeypatch.setattr(main, "sheets_client", lambda: SimpleNamespace(open_by_key=lambda _: ss))
    monkeypatch.setattr(main, "_queue_today_str", lambda _: DAY)
    monkeypatch.setattr(main, "_schedule_group_ids", lambda _: ["G1"])
    monkeypatch.setattr(main, "_queue_active_session", lambda c, g, l: active_session_for(c, g, l, now=clock["now"], schedules_dir=tmp_path))
    monkeypatch.setattr(main, "_queue_next_session", lambda *a: None)
    github = OfflineGitHub()
    monkeypatch.setattr(main, "GitHubClient", lambda _: github)
    main.limiter.enabled = False
    with TestClient(main.app) as client:
        def login(username="alice", fio="Alice Synthetic"):
            client.cookies.set("student_session", build_student_session(main.signer, username, fio, "review", "G1"))
        login()
        client.cookies.set("admin_session", main.signer.sign(b"review").decode())
        yield SimpleNamespace(client=client, spreadsheet=ss, config=config,
                              clock=clock, path=path, login=login, github=github)
    reset_schedule_cache()
