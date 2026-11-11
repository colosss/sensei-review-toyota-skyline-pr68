#!/usr/bin/env python3
"""Check the review baseline without executing application code."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
scope = json.loads((ROOT / "REVIEW_SCOPE.json").read_text())

def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()

try:
    for relative, expected in scope["pinned_commits"].items():
        path = ROOT / relative
        # A missing submodule may otherwise resolve to its parent repository.
        if Path(git(path, "rev-parse", "--show-toplevel")).resolve() != path.resolve():
            raise ValueError(f"{relative}: submodule is not initialized")
        actual = git(path, "rev-parse", "HEAD")
        if actual != expected:
            raise ValueError(f"{relative}: expected {expected}, got {actual}")
        if git(path, "status", "--porcelain", "--untracked-files=normal"):
            raise ValueError(f"{relative}: working tree has changes; inspect git status")
        print(f"OK {relative}: {actual}")
except (subprocess.CalledProcessError, ValueError) as error:
    print(f"Baseline check failed: {error}", file=sys.stderr)
    sys.exit(1)
print("Baseline is pinned and clean. Application behavior has not been tested.")
