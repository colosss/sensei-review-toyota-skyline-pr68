#!/usr/bin/env python3
"""C01 harness ASGI backend: the pinned app with synthetic seams.

The application code under ``scratch/runtime/app`` is imported read-only and
its routes run unchanged. Only the boundaries that would otherwise leave the
process are replaced:

* ``sheets_client`` -> in-memory gspread-compatible fake;
* course lookup -> one synthetic course;
* schedule window -> one synthetic active session;
* ``requests.get`` -> fake GitHub ``/users/{login}`` response; every other
  outbound HTTP call raises instead of touching the network;
* ``evaluate_student`` / ``ensure_ci_passed`` -> synthetic CI pass
  (contract: same return objects as ``grading.bulk``).

The harness helpers live under ``/__harness__/`` and are not part of the
application. They are available only on the loopback port passed by the
launcher.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[2]
APP_DIR = REPO_ROOT / "scratch" / "runtime" / "app"
LOG_DIR = REPO_ROOT / "scratch" / "pipeline" / "C01" / "runtime" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

sys.dont_write_bytecode = True
os.environ["ADMIN_LOGIN"] = "review-admin"
os.environ["ADMIN_PASSWORD"] = "review-admin-local-only"
os.environ["SECRET_KEY"] = "synthetic-c01-harness-secret"
os.environ["GITHUB_TOKEN"] = "synthetic-not-a-token"
os.environ["LOG_DIR"] = str(LOG_DIR)
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

os.chdir(APP_DIR)
sys.path.insert(0, str(HARNESS_DIR))
sys.path.insert(0, str(APP_DIR))

import requests  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402

import main as app_module  # noqa: E402
from grading.bulk import StudentOutcome  # noqa: E402

from fixture import COURSE_ID, SyntheticState  # noqa: E402

STATE = SyntheticState()
STARTED = {"value": False}


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers: dict[str, str] = {}
        self.text = json.dumps(self._payload)
        self.ok = status_code < 400

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"fake status {self.status_code}")


def _blocked(method: str):
    def call(url, *_args, **_kwargs):
        raise requests.ConnectionError(
            f"harness blocks external HTTP ({method} {url}); "
            "only the synthetic GitHub user check is available"
        )

    return call


def _fake_github_get(url, *_args, **_kwargs) -> FakeResponse:
    if url.startswith("https://api.github.com/users/"):
        login = url.rsplit("/", 1)[-1]
        return FakeResponse(200, {"login": login, "type": "User"})
    raise requests.ConnectionError(
        f"harness blocks external HTTP (GET {url}); use the synthetic CI seam"
    )


def _synthetic_ci_outcome() -> StudentOutcome:
    return StudentOutcome(
        status="updated",
        cell_value="v",
        message="Synthetic CI: все проверки пройдены",
        passed="3/3 проверок пройдено",
        checks=["synthetic-ci: success"],
    )


def _fake_evaluate_student(
    grader,
    org,
    username,
    lab_config,
    course_info,
    sheet_context,
    repo_name=None,
):
    del grader, org, username, lab_config, course_info, repo_name
    # Mimic the real laziness: the callback populates the caller's write
    # target only when grading reaches the Sheets stage.
    sheet_context()
    return _synthetic_ci_outcome()


def _fake_ensure_ci_passed(**_kwargs):
    return None, _synthetic_ci_outcome()


def _fake_course(course_id: str) -> dict:
    if course_id != COURSE_ID:
        raise HTTPException(status_code=404, detail="Course not found")
    return STATE.course_info()


def install_seams() -> None:
    app_module.get_course_by_id = _fake_course
    app_module.iter_course_configs = lambda: iter([(COURSE_ID, STATE.course_info())])
    app_module.sheets_client = lambda: _sheets_client()
    app_module._queue_active_session = lambda *_a, **_kw: STATE.session
    app_module._queue_next_session = lambda *_a, **_kw: None
    app_module._queue_today_str = lambda _course_info: STATE.spreadsheet.today_str
    app_module._schedule_group_ids = lambda _course_id: list(STATE.groups)
    app_module.evaluate_student = _fake_evaluate_student
    app_module.ensure_ci_passed = _fake_ensure_ci_passed
    requests.get = _fake_github_get
    requests.post = _blocked("POST")
    requests.patch = _blocked("PATCH")
    requests.put = _blocked("PUT")
    requests.delete = _blocked("DELETE")


def _sheets_client():
    from fixture import FakeSheetsClient

    return FakeSheetsClient(STATE.spreadsheet)


def _contract() -> dict:
    return {
        "mode": "synthetic",
        "app_sha_expected": "20bea22cf4a1cbc19634a984883ff52764ce9d6d",
        "app_dir": "scratch/runtime/app (read-only import)",
        "course": COURSE_ID,
        "helpers": {
            "GET /__harness__/health": "liveness",
            "GET /__harness__/state": "synthetic roster, queue, history, session, recent calls",
            "POST /__harness__/reset": "rebuild in-memory fixture and reset rate-limit buckets",
            "GET /__harness__/contract": "this document",
        },
        "overrides": [
            "get_course_by_id / iter_course_configs -> one synthetic course",
            "sheets_client -> in-memory gspread fake (roster, queue, history)",
            "schedule window -> one active synthetic session",
            "requests.get -> fake api.github.com/users/{login}; other outbound calls blocked",
            "evaluate_student / ensure_ci_passed -> synthetic passing CI",
        ],
        "not_overridden": [
            "HTTP routes, request models, auth/cookie signing, queue store logic, Sheets contract usage",
            "the served frontend is the real built dist; only http://localhost:8000 is rewritten on the wire",
        ],
    }


class HarnessASGI:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            STATE.calls.append({"method": scope.get("method", "?"), "path": path})
            if path.startswith("/__harness__/"):
                await self._helper(path, scope, send)
                return
        await self.application(scope, receive, send)

    async def _helper(self, path: str, scope, send) -> None:
        method = scope.get("method", "GET")
        if path == "/__harness__/health":
            body = {"ok": True, "mode": "synthetic", "course": COURSE_ID}
            status = 200
        elif path == "/__harness__/contract":
            body, status = _contract(), 200
        elif path == "/__harness__/state":
            body, status = STATE.snapshot(), 200
        elif path == "/__harness__/reset":
            if method != "POST":
                body, status = {"detail": "POST required"}, 405
            else:
                STATE.reset()
                app_module.limiter.reset()
                body, status = {"ok": True, "state": STATE.snapshot()}, 200
        else:
            body, status = {"detail": "unknown harness helper"}, 404
        response = JSONResponse(body, status_code=status)
        await response(scope, receive=None, send=send)


def build_app():
    install_seams()
    STARTED["value"] = True
    return HarnessASGI(app_module.app)


app = build_app()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18280)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()

    import uvicorn

    print(
        json.dumps(
            {
                "event": "backend_ready",
                "url": f"http://{args.host}:{args.port}",
                "app_dir": str(APP_DIR),
                "state": "in-memory",
            }
        ),
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level, access_log=False)


if __name__ == "__main__":
    main()
