#!/usr/bin/env python3
"""C01 scenario: stock local deployment port path vs. documented startup.

Observes, without Docker and without changing anything:

* ``source/docker-compose.yml`` publishes frontend ``8080:80``;
* ``source/frontend.Dockerfile`` runs nginx unprivileged and ``EXPOSE 8080``;
* ``source/nginx.conf`` has ``listen 8080`` and no API proxy;
* the built frontend defaults to ``http://localhost:8000`` and the only dev
  proxy lives in ``vite.config.js`` (``npm run dev``), not in nginx;
* the same compose/nginx files are byte-identical to the PR base
  ``eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39``.

Default mode prints the observation and exits 0 (a scenario recorder).
``--assert`` turns the documented-startup contract into assertions and exits
1 on the pinned code; this is evidence of an inherited configuration defect,
not a PR regression.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "source"
BASE = "eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def base_file(name: str) -> str:
    return subprocess.run(
        ["git", "-C", str(SOURCE), "--no-pager", "show", f"{BASE}:{name}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def observe() -> dict:
    compose = yaml.safe_load(read(SOURCE / "docker-compose.yml"))
    frontend_ports = compose["services"]["frontend"]["ports"]
    nginx = read(SOURCE / "nginx.conf")
    dockerfile = read(SOURCE / "frontend.Dockerfile")
    vite = read(SOURCE / "frontend/courses-front/vite.config.js")
    api = read(SOURCE / "frontend/courses-front/src/api/index.js")

    return {
        "compose_frontend_ports": frontend_ports,
        "nginx_listen": "listen 8080;" in nginx,
        "nginx_has_api_proxy": "proxy_pass" in nginx,
        "dockerfile_exposes_8080": "EXPOSE 8080" in dockerfile,
        "vite_dev_proxy_only": "'/api'" in vite and "target: 'http://localhost:8000'" in vite,
        "frontend_default_api_base": 'http://localhost:8000' in api.splitlines()[0],
        "compose_identical_to_base": read(SOURCE / "docker-compose.yml") == base_file("docker-compose.yml"),
        "nginx_identical_to_base": nginx == base_file("nginx.conf"),
        "base": BASE,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--assert-contract",
        action="store_true",
        dest="check_contract",
        help="assert the documented-startup contract",
    )
    args = parser.parse_args()
    data = observe()
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if not args.check_contract:
        return 0

    published = data["compose_frontend_ports"]
    failures = []
    if published != ["8080:8080"]:
        failures.append(
            "EXPECTED frontend publish mapping to match nginx listen 8080 "
            f"(e.g. 8080:8080); ACTUAL {published}; nginx listens 8080, "
            "so container port 80 has no listener"
        )
    if not data["nginx_has_api_proxy"]:
        # Not a defect on its own: the built UI talks to :8000 directly and
        # the backend enables CORS. Recorded to separate proxy from port.
        print(
            "NOTE nginx has no /api proxy; the student path uses the absolute "
            "API base URL, so this is not a failure criterion.",
            file=sys.stderr,
        )
    for failure in failures:
        print(failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
