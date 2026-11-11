"""T01: team identity, per-group/lab isolation and lock/cache keys.

Scope: queue-only, supported single-process paths.  C06's list-scope defect is
not repeated here: these tests check the *storage keys* and the team resolver,
not the HTTP list rendering.

Contract under test (pinned PR source):

* ``grading/queue/teams_bridge.py:20-53`` maps the signed student's GitHub login
  to the team of *this* lab and returns ``TEAMS_UNAVAILABLE`` / ``NO_TEAM``;
  the roster login is case-insensitive and teachers are excluded
  (``grading/teams.py:222-226,324-403,462-468``).
* Queue rows are keyed by ``group + fio + lab`` (``store.py:270-311,413-433``);
  for a team the identity is the team title, and
  ``TeamRegistry.create_team`` enforces a title unique per org+prefix
  (``grading/teams.py:552-561``), so a title is a valid queue identity there.
* Locks: ``grading/queue/locks.py:12-26`` is keyed by the spreadsheet id;
  ``grading/teams.py:265-283`` is keyed by ``(course_id, canonical lab_key)``.
* Cache: ``cache.py:13,27-63`` is keyed by
  ``(course_id, group_id, lab_key, today)``; the team list cache is keyed by
  ``(org, github_prefix)`` (``grading/teams.py:258,308-322``).

Isolation: in-memory fakes only (spreadsheet id ``review-persistence-B``,
org ``review-t01-org``), synthetic logins/repos; no network, no real GitHub or
Sheets, no file writes, no browser.
"""

import threading
from datetime import date

import pytest
from gspread.exceptions import WorksheetNotFound

from grading.queue.cache import get_queue, reset_queue_cache
from grading.queue.errors import QueueError
from grading.queue.locks import locked_course, reset_locks, sheet_lock
from grading.queue.store import (
    QUEUE_HEADERS,
    STATUS_WAITING,
    find_waiting,
    list_waiting,
    queue_sheet_name,
    read_queue_rows,
    register,
)
from grading.queue.teams_bridge import resolve_team_for_user
from grading.teams import TeamRegistry, lab_lock, reset_teams_state

ORG = "review-t01-org"
PREFIX = "os-task5"
OTHER_PREFIX = "os-task4"
COURSE = "review-t01"
DAY = date(2026, 11, 8)
SPREADSHEET_ID = "review-persistence-B"


# ---------------------------------------------------------------------------
# Fake GitHub (same method surface and payload shape GitHubClient parses)
# ---------------------------------------------------------------------------
class FakeGitHub:
    def __init__(self, repos, rosters):
        # repos: {org: [{"name": ..., "description": ...}]}
        # rosters: {repo_name: {"collaborators": [...], "invitations": [...]}}
        # A roster value of None simulates an unreadable roster.
        self.repos = repos
        self.rosters = rosters
        self.repo_calls = []

    def list_org_repos(self, org):
        self.repo_calls.append(org)
        return self.repos.get(org)

    def list_collaborators(self, org, repo, affiliation="direct"):
        roster = self.rosters.get(repo)
        if roster is None:
            return None
        return roster.get("collaborators", [])

    def list_invitations(self, org, repo):
        roster = self.rosters.get(repo)
        if roster is None:
            return None
        return roster.get("invitations", [])

    def repo_exists(self, org, repo):
        return False

    def update_repo(self, org, repo, payload):
        raise AssertionError(f"unexpected GitHub mutation for {org}/{repo}")


def _collaborator(login, push=True, admin=False):
    return {"login": login, "permissions": {"push": push, "admin": admin}}


def _teams_github():
    repos = {
        ORG: [
            {"name": "os-task5-team-1", "description": "Альфа"},
            {"name": "os-task5-team-2", "description": "Бета"},
            {"name": "os-task4-team-1", "description": "Чужая лаба"},
            {"name": "os-task5-alice", "description": "Личный репозиторий"},
        ],
    }
    rosters = {
        "os-task5-team-1": {
            "collaborators": [
                _collaborator("alice"),
                _collaborator("teacher1"),          # teacher with push
                _collaborator("owner1", admin=True),  # org owner via org role
            ],
            "invitations": [
                {"invitee": {"login": "bob"}, "expired": True},
            ],
        },
        "os-task5-team-2": {
            "collaborators": [_collaborator("carol")],
            "invitations": [],
        },
        "os-task4-team-1": {
            "collaborators": [_collaborator("dave")],
            "invitations": [],
        },
    }
    return FakeGitHub(repos, rosters)


def _lab_config():
    return {"short-name": "ЛР5", "github-prefix": PREFIX, "team": {}}


def _course():
    return {
        "github": {"organization": ORG, "teachers": ["teacher1"]},
        "labs": {"5": _lab_config()},
    }


@pytest.fixture(autouse=True)
def clean_module_state():
    reset_teams_state()
    reset_locks()
    reset_queue_cache()
    yield
    reset_teams_state()
    reset_locks()
    reset_queue_cache()


# ---------------------------------------------------------------------------
# Team identity
# ---------------------------------------------------------------------------
def test_team_member_resolution_is_lab_scoped_and_case_insensitive():
    github = _teams_github()

    alice = resolve_team_for_user(github, _course(), _lab_config(), "alice")
    assert alice.title == "Альфа"
    assert alice.repo_name == "os-task5-team-1"
    assert set(alice.members) == {"alice", "bob"}, (
        "pending invitations hold a place and must be part of the team identity"
    )

    assert resolve_team_for_user(github, _course(), _lab_config(), "ALICE").title == "Альфа"
    assert resolve_team_for_user(github, _course(), _lab_config(), "bob").title == "Альфа"

    for outsider in ("teacher1", "owner1"):
        with pytest.raises(QueueError) as error:
            resolve_team_for_user(github, _course(), _lab_config(), outsider)
        assert error.value.code == "NO_TEAM", (
            f"{outsider} is a teacher/admin collaborator, not a team member; "
            f"got {error.value.code}"
        )

    # dave is in another lab's team: the resolver must not see it.
    with pytest.raises(QueueError) as error:
        resolve_team_for_user(github, _course(), _lab_config(), "dave")
    assert error.value.code == "NO_TEAM"


def test_unreadable_roster_blocks_instead_of_silently_reporting_no_team():
    github = _teams_github()
    github.rosters["os-task5-team-2"] = None  # one roster cannot be read

    # A student in a readable team still resolves.
    assert resolve_team_for_user(github, _course(), _lab_config(), "alice").title == "Альфа"

    # A student found in no readable team is not silently "teamless".
    with pytest.raises(QueueError) as error:
        resolve_team_for_user(github, _course(), _lab_config(), "zed")
    assert error.value.code == "TEAMS_UNAVAILABLE"


def test_individual_lab_returns_none_without_github_calls():
    github = _teams_github()
    assert resolve_team_for_user(
        github, _course(), {"short-name": "ЛР1"}, "alice"
    ) is None
    assert github.repo_calls == []


def test_team_title_uniqueness_makes_the_queue_title_identity_safe():
    github = _teams_github()
    result = TeamRegistry(github).create_team(
        course_id=COURSE,
        lab_key="5",
        org=ORG,
        github_prefix=PREFIX,
        template_repo="os-task5-template",
        username="zed",
        title="альфа",  # same title, different case
    )
    assert result.error_code == "TITLE_TAKEN", (
        f"expected TITLE_TAKEN before provisioning, got {result.error_code}: {result.message}"
    )


# ---------------------------------------------------------------------------
# Team list cache keys
# ---------------------------------------------------------------------------
def test_team_list_cache_is_keyed_by_org_and_prefix():
    github = _teams_github()
    github.repos["other-org"] = [{"name": "os-task5-team-9", "description": "Гамма"}]
    github.rosters["os-task5-team-9"] = {"collaborators": [], "invitations": []}
    registry = TeamRegistry(github)

    registry.list_teams(ORG, PREFIX)
    registry.list_teams(ORG, PREFIX)
    assert github.repo_calls == [ORG], "the same org+prefix must hit the cache"

    registry.list_teams(ORG, OTHER_PREFIX)
    registry.list_teams("other-org", PREFIX)
    assert github.repo_calls == [ORG, ORG, "other-org"], (
        "a different lab prefix and a different org must not share the cache entry"
    )

    registry.invalidate(ORG, PREFIX)
    registry.list_teams(ORG, PREFIX)
    assert github.repo_calls == [ORG, ORG, "other-org", ORG], "invalidate must refetch"


# ---------------------------------------------------------------------------
# Queue row isolation by group/lab and lock/cache keys
# ---------------------------------------------------------------------------
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
        return [str(value) for value in self.values[row - 1]] if len(self.values) >= row else []

    def get_all_values(self):
        return [[str(value) for value in row] for row in self.values]

    def update_cell(self, row, col, value):
        self._pad(row, col)
        self.values[row - 1][col - 1] = str(value)

    def append_row(self, values, **_kwargs):
        self.values.append([str(value) for value in values])


class FakeSpreadsheet:
    def __init__(self):
        self.id = SPREADSHEET_ID
        self._sheets = {
            queue_sheet_name(DAY): FakeWorksheet(
                queue_sheet_name(DAY), [list(QUEUE_HEADERS)]
            )
        }

    def worksheet(self, title):
        try:
            return self._sheets[title]
        except KeyError:
            raise WorksheetNotFound(title) from None

    def worksheets(self):
        return list(self._sheets.values())


def _register(sheet, group, lab, fio, session_no=None):
    return register(
        sheet, DAY, group, fio, lab, session_no=session_no, group_ids=["4431", "4432"]
    )


def test_team_rows_are_isolated_by_group_and_lab():
    spreadsheet = FakeSpreadsheet()
    worksheet = spreadsheet.worksheet(queue_sheet_name(DAY))

    assert _register(spreadsheet, "4431", "ЛР5", "Альфа") == 1
    assert _register(spreadsheet, "4432", "ЛР5", "Альфа") == 1
    assert _register(spreadsheet, "4431", "ЛР6", "Альфа") == 1

    rows = read_queue_rows(worksheet)
    assert [(row.group, row.lab, row.fio, row.position) for row in rows] == [
        ("4431", "ЛР5", "Альфа", 1),
        ("4432", "ЛР5", "Альфа", 1),
        ("4431", "ЛР6", "Альфа", 1),
    ]

    only_g1 = list_waiting(rows, "4431", "ЛР5")
    assert [row.group for row in only_g1] == ["4431"]
    assert find_waiting(rows, "4431", "ЛР5", "Альфа").lab == "ЛР5"
    assert find_waiting(rows, "4431", "ЛР5", "Бета") is None
    assert find_waiting(rows, "4432", "ЛР6", "Альфа") is None


def test_queue_cache_key_separates_course_group_lab_and_day():
    built = []

    def builder(label):
        def build():
            built.append(label)
            return [label]
        return build

    get_queue("sheet", COURSE, "4431", "ЛР5", "2026-11-08", builder("a"))
    get_queue("sheet", COURSE, "4431", "ЛР5", "2026-11-08", builder("a-again"))
    get_queue("sheet", COURSE, "4431", "ЛР6", "2026-11-08", builder("other-lab"))
    get_queue("sheet", COURSE, "4432", "ЛР5", "2026-11-08", builder("other-group"))
    get_queue("sheet", "other-course", "4431", "ЛР5", "2026-11-08", builder("other-course"))
    get_queue("sheet", COURSE, "4431", "ЛР5", "2026-11-09", builder("other-day"))

    assert built == ["a", "other-lab", "other-group", "other-course", "other-day"]


def test_lock_keys_scope_and_serialize():
    assert sheet_lock(SPREADSHEET_ID) is sheet_lock(SPREADSHEET_ID)
    assert sheet_lock(SPREADSHEET_ID) is not sheet_lock("another-sheet")
    assert lab_lock(COURSE, "5") is lab_lock(COURSE, "5")
    assert lab_lock(COURSE, "5") is not lab_lock(COURSE, "6")

    entered = []
    first_inside = threading.Event()
    release_first = threading.Event()

    def worker(name):
        with locked_course(SPREADSHEET_ID):
            entered.append(name)
            if name == "first":
                first_inside.set()
                assert release_first.wait(2), "test release event timed out"
        entered.append(f"{name}-done")

    first = threading.Thread(target=worker, args=("first",))
    second = threading.Thread(target=worker, args=("second",))
    first.start()
    assert first_inside.wait(2), "first worker did not enter the lock"
    second.start()
    assert entered == ["first"], f"the same spreadsheet lock did not serialize: {entered!r}"
    release_first.set()
    first.join(2)
    second.join(2)

    assert entered == ["first", "first-done", "second", "second-done"], entered
