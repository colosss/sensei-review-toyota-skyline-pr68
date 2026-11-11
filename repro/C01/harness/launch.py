#!/usr/bin/env python3
"""Finite lifecycle launcher for the C01 browser harness.

Usage (coordinator starts this as a Playwright server child process):

    python3 repro/C01/harness/launch.py --hold

Serves:
  * real built frontend  http://127.0.0.1:18281
  * pinned backend       http://127.0.0.1:18280

The process stays alive on purpose only in ``--hold`` mode and exits on
SIGTERM/SIGINT, terminating both children. ``--selftest`` starts both
children, performs an end-to-end HTTP check, then shuts everything down and
exits; it never leaves a server running.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[2]
RUNTIME_DIR = REPO_ROOT / "scratch" / "pipeline" / "C01" / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

CHILDREN: list[subprocess.Popen] = []


def _wait(url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as error:  # noqa: BLE001 - readiness probe
            last = error
        time.sleep(0.2)
    raise RuntimeError(f"not ready: {url}: {last}")


def _spawn(name: str, args: list[str]) -> subprocess.Popen:
    log_path = RUNTIME_DIR / f"{name}.log"
    log = log_path.open("ab")
    process = subprocess.Popen(
        args,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    log.close()
    CHILDREN.append(process)
    return process


def start(api_port: int, static_port: int) -> None:
    _spawn(
        "backend",
        [sys.executable, str(HARNESS_DIR / "app_server.py"), "--port", str(api_port)],
    )
    _spawn(
        "static",
        [
            sys.executable,
            str(HARNESS_DIR / "static_server.py"),
            "--port",
            str(static_port),
            "--api-base",
            f"http://127.0.0.1:{api_port}",
        ],
    )
    api = f"http://127.0.0.1:{api_port}"
    static = f"http://127.0.0.1:{static_port}"
    _wait(f"{api}/__harness__/health")
    _wait(f"{static}/")


def stop() -> None:
    for process in CHILDREN:
        if process.poll() is None:
            process.terminate()
    deadline = time.time() + 8
    for process in CHILDREN:
        remaining = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
    CHILDREN.clear()


def _request(opener, method: str, url: str, payload: dict | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw.decode(errors="replace")
        return error.code, body


def selftest(api_port: int, static_port: int) -> dict:
    api = f"http://127.0.0.1:{api_port}"
    static = f"http://127.0.0.1:{static_port}"
    cookie_jar = CookieJar()
    browserless = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    plain = urllib.request.build_opener()
    results: dict[str, object] = {}

    results["backend_health"] = _request(plain, "GET", f"{api}/__harness__/health")
    results["courses"] = _request(plain, "GET", f"{api}/courses?status=active")
    results["groups"] = _request(plain, "GET", f"{api}/courses/review-c01/groups")
    results["labs"] = _request(plain, "GET", f"{api}/courses/review-c01/groups/4431/labs")

    registration = _request(
        browserless,
        "POST",
        f"{api}/courses/review-c01/groups/4431/register",
        {
            "surname": "Иванов",
            "name": "Иван",
            "patronymic": "Иванович",
            "github": "review-ivanov",
        },
    )
    results["registration"] = registration
    results["registration_cookie"] = sorted(cookie.name for cookie in cookie_jar)

    results["grade"] = _request(
        browserless,
        "POST",
        f"{api}/courses/review-c01/groups/4431/labs/1/grade",
        {"github": "review-ivanov"},
    )
    results["queue_status"] = _request(
        browserless, "GET", f"{api}/courses/review-c01/groups/4431/labs/1/queue/status"
    )
    results["queue_register"] = _request(
        browserless, "POST", f"{api}/courses/review-c01/groups/4431/labs/1/queue/register"
    )
    results["queue_list"] = _request(
        plain, "GET", f"{api}/courses/review-c01/groups/4431/labs/1/queue"
    )

    admin_jar = CookieJar()
    admin = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(admin_jar))
    results["admin_login"] = _request(
        admin,
        "POST",
        f"{api}/admin/login",
        {"login": "review-admin", "password": "review-admin-local-only"},
    )
    results["admin_check_auth"] = _request(admin, "GET", f"{api}/admin/check-auth")
    results["admin_queue_today"] = _request(
        admin, "GET", f"{api}/admin/courses/review-c01/queue/today"
    )
    results["admin_set_status"] = _request(
        admin,
        "POST",
        f"{api}/admin/courses/review-c01/groups/4431/labs/1/queue/set-status",
        {"identifier": "Петрова Полина Сергеевна", "status": "сдал"},
    )
    results["queue_after_admin_set_status"] = _request(
        plain, "GET", f"{api}/courses/review-c01/groups/4431/labs/1/queue"
    )

    results["state_after_register"] = _request(plain, "GET", f"{api}/__harness__/state")
    results["reset"] = _request(plain, "POST", f"{api}/__harness__/reset")
    results["state_after_reset"] = _request(plain, "GET", f"{api}/__harness__/state")

    with urllib.request.urlopen(f"{static}/", timeout=10) as response:
        index_html = response.read()
        results["static_index"] = (response.status, b"C01 harness" not in index_html and b"root" in index_html)
    with urllib.request.urlopen(f"{static}/assets/index-CF2nrC2I.js", timeout=10) as response:
        bundle = response.read()
        results["static_bundle_rewrite"] = {
            "status": response.status,
            "has_harness_api": f"http://127.0.0.1:{api_port}".encode() in bundle,
            "has_stock_api": b"http://localhost:8000" in bundle,
        }
    results["static_relative_api"] = _request(plain, "GET", f"{static}/api/v1/courses")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", type=int, default=18280)
    parser.add_argument("--static-port", type=int, default=18281)
    parser.add_argument("--hold", action="store_true", help="keep serving until SIGTERM/SIGINT")
    parser.add_argument("--selftest", action="store_true", help="run finite checks and exit")
    parser.add_argument("--report", help="write the selftest JSON to this path")
    args = parser.parse_args()

    if not args.hold and not args.selftest:
        parser.error("choose --hold or --selftest")

    def _handle_signal(_signum, _frame):
        stop()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        start(args.api_port, args.static_port)
        if args.hold:
            print(
                json.dumps(
                    {
                        "event": "harness_ready",
                        "ui": f"http://127.0.0.1:{args.static_port}/",
                        "api": f"http://127.0.0.1:{args.api_port}",
                        "reset": f"http://127.0.0.1:{args.api_port}/__harness__/reset",
                        "inspect": f"http://127.0.0.1:{args.api_port}/__harness__/state",
                        "pid": os.getpid(),
                    }
                ),
                flush=True,
            )
            while True:
                time.sleep(1)
                for child in CHILDREN:
                    if child.poll() is not None:
                        raise SystemExit(f"child exited early with {child.returncode}; see {RUNTIME_DIR}")
        else:
            report = selftest(args.api_port, args.static_port)
            text = json.dumps(report, ensure_ascii=False, indent=2)
            print(text)
            if args.report:
                Path(args.report).write_text(text + "\n", encoding="utf-8")
            return 0
    finally:
        stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
