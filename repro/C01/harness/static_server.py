#!/usr/bin/env python3
"""Static server for the real built frontend (C01 harness).

Serves ``frontend/courses-front/dist`` exactly as built. The only wire-level
change is replacing the build-time default ``http://localhost:8000`` inside
the JavaScript bundle with the harness backend origin. The app files on disk
are not modified.

No ``/api`` proxy is added on purpose: the stock nginx config does not have
one either, so requests that the UI sends to relative ``/api/...`` paths stay
observable as 404 from this origin. The public student path uses the
API base URL from ``src/api/index.js`` and therefore reaches the backend
directly (the backend enables CORS).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HARNESS_DIR = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_DIR.parents[2]
DIST_DIR = REPO_ROOT / "scratch" / "runtime" / "app" / "frontend" / "courses-front" / "dist"
DEFAULT_API_BASE = "http://localhost:8000"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webp": "image/webp",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json",
}


class Handler(BaseHTTPRequestHandler):
    api_base = "http://127.0.0.1:18280"
    server_version = "C01HarnessStatic/1.0"

    def log_message(self, *_args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = urlsplit(self.path).path

        if path.startswith("/api/") or path == "/api":
            self._send(
                404,
                json.dumps(
                    {
                        "detail": "harness static origin has no /api proxy",
                        "path": path,
                        "hint": "the stock nginx.conf has no API proxy either",
                    }
                ).encode(),
                "application/json",
            )
            return

        if path in ("", "/"):
            path = "/index.html"

        candidate = (DIST_DIR / path.lstrip("/")).resolve()
        try:
            candidate.relative_to(DIST_DIR)
        except ValueError:
            self._send(404, b"not found", "text/plain")
            return

        if not candidate.is_file():
            candidate = DIST_DIR / "index.html"

        data = candidate.read_bytes()
        content_type = MIME.get(candidate.suffix.lower()) or mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if candidate.suffix == ".js":
            data = data.replace(DEFAULT_API_BASE.encode(), self.api_base.encode())
        self._send(200, data, content_type)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18281)
    parser.add_argument("--api-base", default="http://127.0.0.1:18280")
    args = parser.parse_args()

    if not (DIST_DIR / "index.html").is_file():
        raise SystemExit(f"built frontend not found: {DIST_DIR}")

    Handler.api_base = args.api_base.rstrip("/")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "event": "static_ready",
                "url": f"http://{args.host}:{args.port}",
                "dist": str(DIST_DIR),
                "api_base_rewrite": Handler.api_base,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
