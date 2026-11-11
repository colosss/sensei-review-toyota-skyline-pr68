"""Q03 pytest wiring: reuse the C06 fake workbook helper.

The helper lives in repro/C06/ (shared, unchanged).  Pytest imports this
conftest before the Q03 test module, so the sibling directory is on sys.path
for ``import c06_fake_sheets``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

C06_DIR = Path(__file__).resolve().parents[1] / "C06"
if str(C06_DIR) not in sys.path:
    sys.path.insert(0, str(C06_DIR))

import c06_fake_sheets as fx  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    """One fresh in-memory workbook and session clock per test."""
    yield from fx.build_env(monkeypatch)
