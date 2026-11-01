"""Files back from the phone to the agent (phone-layer plan, T2c): `get_file` over MCP hands an agent short-lived
download links for the files Envoy itself kept in a task the agent started, and the links the task produced.

- **What there is.** The final screen (a picture Envoy takes right after a run's last look at the phone, never of a
  secure screen), the screen at each approval Envoy asked for (api/approvals.py's picture: what the user approved or
  declined), and the links in a task's result (a routine's outputs, the agent's answer: a posted reel's link). Nothing
  else: a download names a file by the task's own records (`final`, an approval's id), never by a path, so no other
  file on the Mac or the phone can be reached.
- **Whose.** Only tasks the calling agent started (contract 2): the task's `agent` (recorded when an agent's MCP call
  starts it) must be the calling agent's name (`api.auth.agent_name`). Muse's key gets Muse's tasks, another agent's key
  its own; tasks the user started (the web app, chat, Siri, a trigger) and tasks from before agent keys (no `agent`)
  are nobody's.
- **The links.** `/mcp/files/<task>/<file>?exp=…&sig=…` on the address the agent called, so a public address that
  serves /mcp and nothing else (Funnel) serves them too. HMAC-signed with a key held in memory only and good for 10
  minutes: an expired or altered link is a 401, and a restart ends every link. The link is the credential, so an agent
  can hand it to whatever fetches it. Each download is a line in `logs/files.jsonl` (never the signature).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.store import ACTIVE, TaskStore

FILES = "/mcp/files"  # under /mcp: wherever an agent reaches Envoy's MCP server, it reaches its files
LINK_S = 600  # how long a download link works
FINAL = "final"
FINAL_WIDTH = 720  # wide enough to read a receipt, small enough to fetch over a phone's connection
WHICH = ("final", "approval", "link")
ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
HOST = re.compile(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::\d{1,5})?")
LOCAL = ("127.0.0.1", "localhost", "[::1]")
URL = re.compile(r"https?://[^\s<>\"'`]+")
LABEL = re.compile(r"([A-Za-z][\w ]{0,40}):\s*$")  # "reel url: https://…" in a routine's outputs


def started_by(task: dict[str, Any]) -> str | None:
    """The agent that started a task (contract 2: `TaskStore.create` records the calling agent for an MCP task), or None:
    the user's own, or a task from before agent keys."""
    return task.get("agent") or None


def request_headers(call: Any) -> Any:
    """The HTTP headers of the MCP call a tool is answering, or None (in process, or a transport without them)."""
    try:
        return call.request_context.request.headers
    except Exception:  # noqa: BLE001
        return None


def link_base(headers: Any, fallback: str) -> str:
    """Where the agent reached Envoy, so the links work from there: the host it called (the dispatcher lets through only
    Envoy's own names and its public addresses), over https unless it's this Mac's own address."""
    host = (headers.get("host") if headers is not None else "") or ""
    if not HOST.fullmatch(host):
        return fallback
    name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]", 1)[0] + "]"
    proto = (headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    proto = proto if proto in ("http", "https") else ("http" if name in LOCAL else "https")
    return f"{proto}://{host}"


def links_in(text: str | None) -> list[dict[str, str]]:
    """The http(s) links in a task's result, each named when the result names it ("reel url: https://…")."""
    out: list[dict[str, str]] = []
    for m in URL.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?)]}")
        if len(url) > 2000 or any(x["url"] == url for x in out):
            continue
        label = LABEL.search((text or "")[max(0, m.start() - 48):m.start()])
        out.append({"url": url, **({"name": label.group(1).strip()} if label else {})})
    return out


def _when(t: float) -> str:
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


class TaskFiles:
    """`shots`: where the final screens go (a folder per task, next to the step pictures); `approvals`: where
    api/approvals.py keeps its pictures. Hooks into the runner's last look at the phone (`runner.on_final`)."""

    def __init__(self, tasks: TaskStore, runner: Any = None, *, shots: Path, approvals: Path, log: Path | None = None,
                 link_s: float = LINK_S, clock: Callable[[], float] = time.time) -> None:
        self.tasks, self.runner = tasks, runner
        self.shots, self.approval_shots, self.log = shots, approvals, log
        self.link_s, self.clock = link_s, clock
        self.key = secrets.token_bytes(32)  # in memory only: a restart ends every link
        self.missed: dict[str, str] = {}  # task id → why its final screen has no picture
        self.saving: dict[str, Any] = {}  # task id → the final screen's picture being taken
        if runner is not None and isinstance(getattr(runner, "on_final", None), list):
            runner.on_final.append(self.on_final)

    # ---- the final screen ---------------------------------------------------------------------------

    def on_final(self, tid: str, screen: Any, outputs: dict[str, Any]) -> None:
        """The runner's hook, right after a run's last look at its phone, while the task still holds it. The picture is
        taken in a thread, as the step pictures are, so a task on another phone never waits for it."""
        device = (getattr(self.runner, "devices", None) or {}).get(tid)
        if screen is None or device is None or not hasattr(device, "frame") or not ID.fullmatch(tid):
            return
        if getattr(screen, "secure", False):  # sign-in and payment screens: never a picture
            self.missed[tid] = "its last screen was a secure one (a sign-in or a payment), and Envoy keeps no picture of those"
            return
        self.missed.pop(tid, None)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # called from a worker thread
            self.save_final(tid, device)
            return
        job = self.saving[tid] = loop.run_in_executor(None, self.save_final, tid, device)
        job.add_done_callback(lambda done: self.saving.pop(tid, None) if self.saving.get(tid) is done else None)

    def save_final(self, tid: str, device: Any) -> Path | None:
        try:
            img = device.frame(FINAL_WIDTH, timeout=3)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            folder = self.shots / tid
            folder.mkdir(parents=True, exist_ok=True)
            part = folder / f".{FINAL}.jpg.part"
            part.write_bytes(buf.getvalue())
            return part.replace(folder / f"{FINAL}.jpg")
        except Exception:  # noqa: BLE001 - a run never fails over its picture
            self.missed[tid] = "Envoy couldn't take a picture of its last screen"
            return None

    # ---- get_file ------------------------------------------------------------------------------------

    def view(self, task_id: str, which: str | None, base: str, agent: str) -> dict[str, Any]:
        """get_file's answer: the task's files as download links, and its links, for the agent that started it."""
        task = self.tasks.get(task_id) if isinstance(task_id, str) and ID.fullmatch(task_id) else None
        if task is None:
            return {"error": f"no task {str(task_id)[:100]}"}
        root = (self.tasks.get(task["parent"]) or task) if task.get("parent") else task  # a part is its cross-app task's
        if not agent or started_by(root) != agent:
            return {"error": f"Envoy shares files only from tasks you ({agent}) started; {task_id} isn't one of them."}
        kinds = WHICH if not which or which == "all" else (which,) if which in WHICH else None
        if kinds is None:
            return {"error": f'which is one of {", ".join(WHICH)}, or leave it out for all of them'}
        ids = [task_id, *self._parts(task_id)]
        now = self.clock()
        files: list[dict[str, Any]] = []
        links: list[dict[str, str]] = []
        for tid in ids:
            t = task if tid == task_id else (self.tasks.get(tid) or {})
            if "final" in kinds and (path := self.shots / tid / f"{FINAL}.jpg").is_file():
                files.append(self._file(base, tid, FINAL, path, "the screen when the task ended", now))
            if "approval" in kinds:
                for a in self.tasks.approvals(task_id=tid):
                    path = self.approval_shots / str(a.get("screenshot") or "")
                    if a.get("screenshot") and path.is_file():
                        what = re.sub(r"\s+", " ", a.get("description") or "").strip()[:120]
                        files.append(self._file(base, tid, a["id"], path,
                                                f'the screen when Envoy asked the user to approve "{what}" ({a.get("status")})', now))
            if "link" in kinds:
                for x in [*links_in(t.get("result")), *links_in(t.get("detail"))]:
                    if not any(y["url"] == x["url"] for y in links):
                        links.append({**x, "task_id": tid})
        return {"task_id": task_id, "status": task["status"], "files": files, "links": links,
                "text": self._text(task, ids, kinds, files, links)}

    def _parts(self, tid: str) -> list[str]:
        with self.tasks.lock:
            return [r[0] for r in self.tasks.db.execute("SELECT id FROM tasks WHERE parent=? ORDER BY created_at", (tid,))]

    def _file(self, base: str, tid: str, fid: str, path: Path, about: str, now: float) -> dict[str, Any]:
        st = path.stat()
        url, exp = self.link(base, tid, fid, now)
        return {"which": FINAL if fid == FINAL else "approval", "task_id": tid, "file_id": fid, "type": "image/jpeg",
                "bytes": st.st_size, "saved": _when(st.st_mtime), "about": about, "url": url, "expires": _when(exp)}

    def _text(self, task: dict[str, Any], ids: list[str], kinds: tuple[str, ...], files: list[dict[str, Any]],
              links: list[dict[str, str]]) -> str:
        n = len(files)
        said = []
        if files:
            said.append(f"{n} file{'s' if n != 1 else ''}; each download link works for {round(self.link_s / 60)} minutes, so ask again for fresh ones")
        if links:
            said.append(f"{len(links)} link{'s' if len(links) != 1 else ''} from the task's result")
        out = (" and ".join(said) if said else "Envoy kept nothing of that kind for this task") + "."
        if "final" in kinds and not any(f["which"] == FINAL for f in files):
            why = next((self.missed[t] for t in ids if t in self.missed), None)
            out += (" Its final screen is being saved: ask again in a moment." if any(t in self.saving for t in ids) else
                    " The task is still running: its final screen comes when it ends." if task["status"] in ACTIVE else
                    f" There's no picture of the final screen: {why}." if why else " There's no picture of the final screen.")
        return out

    # ---- the links -------------------------------------------------------------------------------------

    def link(self, base: str, tid: str, fid: str, now: float | None = None) -> tuple[str, int]:
        exp = int((self.clock() if now is None else now) + self.link_s)
        return f"{base}{FILES}/{quote(tid, safe='')}/{quote(fid, safe='')}?exp={exp}&sig={self._sig(tid, fid, exp)}", exp

    def _sig(self, tid: str, fid: str, exp: int) -> str:
        mac = hmac.new(self.key, f"{tid}\n{fid}\n{exp}".encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode().rstrip("=")

    def check(self, tid: str, fid: str, exp: str, sig: str) -> str | None:
        """Why a download isn't allowed, or None."""
        if not (exp.isdigit() and len(exp) <= 12 and ID.fullmatch(tid) and ID.fullmatch(fid)
                and hmac.compare_digest(self._sig(tid, fid, int(exp)).encode(), sig.encode())):
            return "this isn't a download link Envoy made (or it was changed): ask get_file for a new one"
        if int(exp) < self.clock():
            return f"this download link expired at {_when(int(exp))}: ask get_file for a new one"
        return None

    def open(self, tid: str, fid: str) -> Path | None:
        """The file a signed link names, from the task's records, inside its own folder; else None."""
        if not (ID.fullmatch(tid) and ID.fullmatch(fid)):
            return None
        if fid == FINAL:
            path, root = self.shots / tid / f"{FINAL}.jpg", self.shots
        else:
            a = self.tasks.approval(fid)
            if a is None or a.get("task_id") != tid or not a.get("screenshot"):
                return None
            path, root = self.approval_shots / a["screenshot"], self.approval_shots
        path = path.resolve()
        return path if root.resolve() in path.parents and path.is_file() else None

    def note(self, request: Request, **rec: Any) -> None:
        if self.log is None:
            return
        rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "method": request.method, "host": request.headers.get("host"),
               "client": request.client.host if request.client else None, "forwarded_for": request.headers.get("x-forwarded-for"),
               "from_internet": "tailscale-funnel-request" in request.headers, **rec}
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")


def files_router(files: TaskFiles) -> APIRouter:
    """The downloads: no key, only a signed link from get_file."""
    router = APIRouter()

    @router.api_route(FILES + "/{tid}/{fid}", methods=["GET", "HEAD"])
    def download(tid: str, fid: str, request: Request, exp: str = "", sig: str = "") -> FileResponse:
        why = files.check(tid, fid, exp, sig)
        if why is not None:
            files.note(request, task_id=tid[:100], file_id=fid[:100], status=401)
            raise HTTPException(401, why)
        path = files.open(tid, fid)
        files.note(request, task_id=tid, file_id=fid, status=200 if path else 404)
        if path is None:
            raise HTTPException(404, "Envoy doesn't have that file any more")
        return FileResponse(path, media_type="image/jpeg", headers={
            "Content-Disposition": f'inline; filename="{tid}-{fid}.jpg"', "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})

    return router


__all__ = ["FILES", "TaskFiles", "files_router", "link_base", "links_in", "request_headers", "started_by"]
