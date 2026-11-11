"""Pytest wiring for the independent C08 shift fixture."""

from __future__ import annotations

import pytest

import c08_fixture as fx


@pytest.fixture
def env(monkeypatch):
    yield from fx.build_env(monkeypatch)
