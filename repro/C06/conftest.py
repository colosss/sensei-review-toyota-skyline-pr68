"""Pytest wiring for the isolated C06 fixture (kept outside source/)."""

from __future__ import annotations

import pytest

import c06_fake_sheets as fx


@pytest.fixture
def env(monkeypatch):
    """One fresh in-memory workbook and session clock per test."""
    yield from fx.build_env(monkeypatch)
