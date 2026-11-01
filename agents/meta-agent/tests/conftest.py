"""The agent's tests:  uv run --project backend pytest -q agents/meta-agent/tests  (from the repo root)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _outbox_in_a_temp_folder(tmp_path_factory, monkeypatch):
    """An Envoy a test builds watches its own outbox, never the user's ~/Envoy Outbox (as backend/tests/conftest.py does)."""
    monkeypatch.setenv("ENVOY_OUTBOX", str(tmp_path_factory.mktemp("outbox")))
