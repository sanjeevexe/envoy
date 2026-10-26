"""Fake results shared by the MCP stub and its REST fallback.

Nothing here touches a phone or real memory: `memory_search` always returns the
same fake trip and `run_task` only records the request.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

FAKE_TRIP = {
    "entity": "Trip: Chicago, Oct 30",
    "facts": [
        {"attribute": "airline", "value": "SkyLark", "source": "SkyLark app, today 9:41 AM"},
        {"attribute": "flight", "value": "SL 482", "source": "SkyLark app, today 9:41 AM"},
        {"attribute": "route", "value": "ATL to ORD", "source": "SkyLark app, today 9:41 AM"},
        {"attribute": "date", "value": "2026-10-30", "source": "email from SkyLark, Oct 12"},
        {"attribute": "departure", "value": "6:10 AM", "source": "SkyLark app, today 9:41 AM"},
        {"attribute": "gate", "value": "B12", "source": "SkyLark app, today 9:41 AM"},
        {"attribute": "seat", "value": "14C", "source": "SkyLark app, today 9:41 AM"},
        {"attribute": "confirmation_code", "value": "KX7Q2M", "source": "email from SkyLark, Oct 12"},
    ],
    "note": "Fake data from the Envoy Phase 0 connector stub.",
}


def memory_search(query: str) -> dict:
    """Return the fake trip for any query, in the shape the real tool will use."""
    return {"query": query, "results": [FAKE_TRIP]}


def public_base_url() -> str:
    return os.environ.get("MCP_PUBLIC_URL", "").rstrip("/") or "http://127.0.0.1:" + os.environ.get("MCP_PORT", "8765")


def run_task(goal: str) -> dict:
    """Pretend to start a task: return a fake task ID and a fake approval link."""
    task_id = "task_" + secrets.token_hex(4)
    return {
        "task_id": task_id,
        "status": "waiting_for_approval",
        "goal": goal,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approval": {
            "needed_for": "Confirm check-in for SkyLark SL 482 (ATL to ORD, Oct 30)",
            "approve_url": f"{public_base_url()}/approve/{task_id}",
            "note": "Only the user can approve, on Envoy's own approval page. This assistant cannot approve.",
        },
        "stub": True,
    }
