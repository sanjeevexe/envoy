"""Shared test setup."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _outbox_in_a_temp_folder(tmp_path_factory, monkeypatch):
    """Every API a test builds watches its own outbox (api/handoff.py), never the user's ~/Envoy Outbox."""
    monkeypatch.setenv("ENVOY_OUTBOX", str(tmp_path_factory.mktemp("outbox")))
