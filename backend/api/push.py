"""Push notifications to the iPhone (design doc, iPhone companion › Approvals: "web push notifications, which iOS supports
for Home Screen web apps from iOS 16.4").

Web Push with VAPID (RFC 8030/8291/8292; the encryption and signing come from pywebpush). The app subscribes from a
tap on "Turn on notifications"; each device's subscription is stored here. Envoy pushes when:
- an approval is **asked** (one that your own request already gave, or a standing approval, doesn't ask, so it
  doesn't push either);
- Envoy needs you to **take over** the phone (a sign-in, a bot check);
- a task is **done, failed or declined** (tasks started by a trigger push only when they fail);
- a task a trigger started **changed a remembered fact** it watches ("Gate changed: B12 → C14"; api/alerts.py decides,
  and sends through `notify` with kind `change`);
- Envoy **offers** to do something ("Should I check you in for SL 482?", api/offers.py), when the proactivity setting
  says so: `off` never, `important` (the default) for triggers, files from the Mac and trigger requests, `all` always.
  Approvals and takeovers aren't proactivity: they push whatever the setting. The push opens the offer; only a tap on
  its Yes in the app (your session, a POST) says yes.

A push carries a title, a line of text and the page to open; tapping it opens that page. It never carries an approval's
nonce, so it can't decide anything: the approval page still needs your session and a POST.

When the service worker shows a notification, it posts a receipt; the time from sending to the receipt is the delivery
time (logs/push.jsonl).
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from api.store import API_DIR, REPO, TaskStore

LOG = REPO / "logs" / "push.jsonl"
SCHEMA = """
CREATE TABLE IF NOT EXISTS push_subs (
  id TEXT PRIMARY KEY, device_id TEXT, endpoint TEXT UNIQUE, p256dh TEXT, auth TEXT, created_at REAL, last_ok REAL,
  last_error TEXT, failures INTEGER DEFAULT 0, user_agent TEXT
);
"""
FINAL = {"done": "Done", "failed": "Failed", "declined": "Declined", "needs_you": "Stopped: waiting for you"}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class VapidKeys:
    """The server's VAPID key pair, made on first start (data/api/vapid_private.pem, readable only by you)."""

    def __init__(self, folder: Path = API_DIR) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        self.pem_path = folder / "vapid_private.pem"
        if not self.pem_path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            key = ec.generate_private_key(ec.SECP256R1())
            self.pem_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                        serialization.NoEncryption()))
            self.pem_path.chmod(0o600)
        key = serialization.load_pem_private_key(self.pem_path.read_bytes(), password=None)
        raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)  # type: ignore[union-attr]
        self.public_key = _b64(raw)  # the app's applicationServerKey

    def vapid(self) -> Any:
        from py_vapid import Vapid
        return Vapid.from_file(str(self.pem_path))


class Pusher:
    def __init__(self, store: TaskStore, keys: VapidKeys, public_base: str | Callable[[], str], *,
                 send: Callable[..., Any] | None = None, subject: str | None = None) -> None:
        self.store, self.keys = store, keys
        self._base = public_base
        self._subject = subject or os.environ.get("ENVOY_VAPID_SUB")
        self._send = send  # tests pass a fake; otherwise pywebpush
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="push")
        self.sent: dict[str, dict[str, Any]] = {}  # push id → what was sent and when (for receipts)
        self._lock = threading.Lock()
        with store.lock:
            store.db.executescript(SCHEMA)
            store.db.commit()

    @property
    def base(self) -> str:
        return self._base() if callable(self._base) else self._base

    @property
    def subject(self) -> str:
        """VAPID's contact (`sub`): this server's own https origin (no port, no path), not anyone's email."""
        if self._subject:
            return self._subject
        host = self.base.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        return f"https://{host}" if self.base.startswith("https://") and "." in host else "mailto:envoy@localhost"

    # ---- subscriptions -------------------------------------------------------------------------

    def subscribe(self, sub: dict[str, Any], device_id: str | None, user_agent: str = "") -> dict[str, Any]:
        endpoint = str(sub.get("endpoint") or "")
        keys = sub.get("keys") or {}
        local = endpoint.startswith(("http://127.0.0.1:", "http://localhost:"))  # a test push service on this Mac
        if not (endpoint.startswith("https://") or local) or not keys.get("p256dh") or not keys.get("auth"):
            raise ValueError("not a push subscription")
        sid = f"push-{secrets.token_hex(4)}"
        with self.store.lock:
            self.store.db.execute(
                "INSERT INTO push_subs (id, device_id, endpoint, p256dh, auth, created_at, user_agent) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth, device_id=excluded.device_id, failures=0",
                (sid, device_id, endpoint, keys["p256dh"], keys["auth"], time.time(), user_agent[:200]))
            self.store.db.commit()
            row = self.store.db.execute("SELECT id FROM push_subs WHERE endpoint=?", (endpoint,)).fetchone()
        return {"id": row["id"], "service": endpoint.split("/")[2]}

    def unsubscribe(self, endpoint: str) -> bool:
        with self.store.lock:
            cur = self.store.db.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))
            self.store.db.commit()
        return cur.rowcount > 0

    def forget_device(self, device_id: str) -> None:
        with self.store.lock:
            self.store.db.execute("DELETE FROM push_subs WHERE device_id=?", (device_id,))
            self.store.db.commit()

    def subscriptions(self) -> list[dict[str, Any]]:
        with self.store.lock:
            rows = self.store.db.execute("SELECT id, device_id, endpoint, created_at, last_ok, last_error, failures FROM push_subs").fetchall()
        return [{**dict(r), "service": r["endpoint"].split("/")[2]} for r in rows]

    # ---- sending -------------------------------------------------------------------------------

    def notify(self, kind: str, title: str, body: str, path: str, *, tag: str | None = None, urgency: str = "normal",
               ttl: int = 3600, push_id: str | None = None) -> list[Any]:
        """Push to every subscription, in worker threads; returns the futures. `push_id`: the caller's own id for it."""
        with self.store.lock:
            subs = [dict(r) for r in self.store.db.execute("SELECT * FROM push_subs").fetchall()]
        pid = push_id or f"p{int(time.time() * 1000)}-{secrets.token_hex(2)}"
        payload = {"id": pid, "kind": kind, "title": title[:80], "body": body[:180], "url": path, "tag": tag or pid, "sent_at": time.time()}
        with self._lock:
            self.sent[pid] = {"kind": kind, "sent_at": payload["sent_at"], "receipts": []}
            if len(self.sent) > 500:
                self.sent.pop(next(iter(self.sent)))
        return [self.pool.submit(self._deliver, s, payload, urgency, ttl) for s in subs]

    def _deliver(self, sub: dict[str, Any], payload: dict[str, Any], urgency: str, ttl: int) -> dict[str, Any]:
        info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
        endpoint = sub["endpoint"]
        aud = "/".join(endpoint.split("/")[:3])
        t0 = time.perf_counter()
        status, error = 0, None
        try:
            if self._send is not None:
                resp = self._send(info, json.dumps(payload), urgency=urgency, ttl=ttl)
            else:
                from pywebpush import webpush
                resp = webpush(info, json.dumps(payload), vapid_private_key=self.keys.vapid(),
                               vapid_claims={"sub": self.subject, "aud": aud, "exp": int(time.time()) + 12 * 3600},
                               ttl=ttl, headers={"Urgency": urgency}, timeout=10)
            status = getattr(resp, "status_code", 201)
        except Exception as e:  # noqa: BLE001 - pywebpush raises WebPushException with the response attached
            status = getattr(getattr(e, "response", None), "status_code", 0) or 0
            error = f"{type(e).__name__}: {e}"[:300]
        ms = round((time.perf_counter() - t0) * 1000, 1)
        ok = 200 <= status < 300
        with self.store.lock:
            if status in (404, 410):  # the subscription is gone (app removed, permission revoked)
                self.store.db.execute("DELETE FROM push_subs WHERE id=?", (sub["id"],))
            elif ok:
                self.store.db.execute("UPDATE push_subs SET last_ok=?, failures=0, last_error=NULL WHERE id=?", (time.time(), sub["id"]))
            else:
                self.store.db.execute("UPDATE push_subs SET failures=failures+1, last_error=? WHERE id=?", (error or f"HTTP {status}", sub["id"]))
            self.store.db.commit()
        rec = {"time": time.time(), "event": "sent", "push": payload["id"], "kind": payload["kind"], "service": endpoint.split("/")[2],
               "status": status, "send_ms": ms, "error": error}
        _log(rec)
        return rec

    def receipt(self, push_id: str, shown_at: float | None = None) -> dict[str, Any] | None:
        """The service worker showed the notification: delivery time = now − sent."""
        now = time.time()
        with self._lock:
            sent = self.sent.get(push_id)
            if sent is None:
                return None
            rec = {"time": now, "event": "receipt", "push": push_id, "kind": sent["kind"], "delivery_ms": round((now - sent["sent_at"]) * 1000),
                   "device_clock_ms": round((shown_at - sent["sent_at"]) * 1000) if shown_at else None}
            sent["receipts"].append(rec)
        _log(rec)
        return rec

    # ---- which events push ---------------------------------------------------------------------

    def on_event(self, ev: dict[str, Any]) -> None:
        """An EventBus listener (runs on the API's loop; sending happens in worker threads)."""
        kind = ev.get("type")
        if kind == "approval_requested":
            a = ev.get("approval") or {}
            task = self.store.get(ev.get("task_id") or a.get("task_id") or "") or {}
            self.notify("approval", "Envoy needs your OK", f"{a.get('description') or 'An irreversible step'}"
                        + (f" · {task.get('goal')}" if task.get("goal") else ""), f"/approve/?id={a.get('id')}",
                        tag=a.get("id"), urgency="high", ttl=900)
        elif kind == "takeover_requested":
            tid = ev.get("task_id")
            self.notify("takeover", "Envoy needs you to take over", ev.get("reason") or "The phone needs you",
                        f"/?phone={ev.get('avd')}" + (f"&task={tid}" if tid else ""), tag=f"takeover-{ev.get('avd')}", urgency="high", ttl=1800)
        elif kind == "phone_requested":
            tid = ev.get("task_id")
            task = self.store.get(tid or "") or {}
            body = task.get("goal") or "Envoy wants to use your phone for a task"
            self.notify("phone", f"Use your {ev.get('model') or 'Android phone'}?", f"{ev['reason']}: {body}" if ev.get("reason") else body,
                        f"/?task={tid}", tag=f"phone-{tid}", urgency="high", ttl=900)
        elif kind == "offer" and ev.get("change") == "created":
            from api.offers import pushes
            offer = ev.get("offer") or {}
            if offer.get("status") != "pending" or not pushes(offer.get("kind") or "", self.store.setting("proactivity")):
                return
            goal = (offer.get("action") or {}).get("goal")
            ttl = int(max(60, min(86400, offer["expires_at"] - time.time()))) if offer.get("expires_at") else 6 * 3600
            self.notify("offer", offer.get("title") or "Envoy has a question", (offer.get("body") or goal or "Open Envoy to answer")[:180],
                        f"/?offer={offer.get('id')}", tag=f"offer-{offer.get('id')}", urgency="normal", ttl=ttl)
        elif kind == "task_finished":
            task = self.store.get(ev.get("task_id") or "") or {}
            if task.get("parent"):
                return  # a part of a cross-app question (api/crossapp.py): only its parent's answer pushes
            status = task.get("status")
            if status not in FINAL:
                return
            if str(task.get("source", "")).startswith("trigger") and status == "done":
                return  # scheduled runs (watchers) are quiet unless something goes wrong
            line = task.get("result") if status == "done" else (task.get("detail") or task.get("result"))
            self.notify("task", f"{FINAL[status]}: {task.get('goal', 'task')}"[:80], (line or "")[:180] or "Open Envoy for details",
                        f"/?task={task.get('id')}", tag=task.get("id"), urgency="normal")


def _log(rec: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")
