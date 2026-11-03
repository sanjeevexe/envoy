"""Cross-posting: one agent request, a post per destination (`cross_post`, mcp_server/server.py).

An agent names the routines the user shares with agents to post with, each with its inputs (Instagram's reel, TikTok's
post, YouTube's Short). Envoy runs them as one parent task with a part per destination, as a cross-app answer's parent
and parts (api/crossapp.py, whose kind it keeps, so the app shows the parts under it):

- **Parts are ordinary tasks** (`TaskRunner.start` with `parent`), each running its routine by name: the learned
  routine is what posts, and the part shows it. They run one after another (the posts usually share one phone), and
  every irreversible step still waits for the user's OK, part by part.
- **An outcome per destination:**
  - done: the part ended done (its routine's own checks held);
  - failed, or declined: it ended before any approved irreversible tap ran, so Envoy posted nothing there; not started:
    the cross-post was stopped (or the API restarted) before its turn;
  - waiting: on the user (an approval, a sign-in, the phone); verifying: the approved tap ran and its check is still
    going;
  - **outcome unknown:** an approved irreversible tap ran and the part ended without its checks holding (a timeout, a
    stop, a check that failed after the tap). The post may exist, and Envoy can't look for it: it says so, asks the user
    to check that app, and never posts there again by itself.
- **Retry** (`cross_post` with `retry`): only destinations whose last part failed or was declined, or that never started,
  run again. Done and unknown ones never do; one queued or under way is left to finish.
- **An app that saves its own copy of a post in the gallery runs last** (SAVES_COPY: TikTok, whose export lands in
  DCIM/Camera). The posting routines take "the gallery's newest video", so a part after TikTok's would pick TikTok's
  copy. A retry that would run after TikTok posted says to send the clip to the phone again first; the executor's
  clip check (the newest item against the last push) stops such a post before its first step otherwise.
- The tool returns the parent's id at once; get_task (its `posts`) and phone_updates follow it. A part held up longer
  than PART_LIMIT_S is stopped and judged like any other end.

Outcomes are read back from the task store (the parent's plan and part steps, its parts' tasks and their approvals), so
they, and a retry, hold after the API restarts.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Any

ENDED = ("done", "failed", "declined", "stopped")
WAITING = ("waiting_approval", "needs_you", "taken_over")
MAX_POSTS = 4
PART_LIMIT_S = 40 * 60  # a backstop for a part that hangs: the phone ask and the approval wait (15 min each) fit inside
SCREEN_CHANGED = "the screen changed before the action ran"  # api/approvals.py: said yes, then not acted on
RETRYABLE = ("failed", "declined", "not_started")
# Apps that save their own copy of what they post into the phone's gallery (Pixel 5, Nov 2: TikTok's exports in
# DCIM/Camera at 01:43 and 02:31, owner com.zhiliaoapp.musically): after one, the newest video is no longer the clip.
SAVES_COPY = {"com.zhiliaoapp.musically": "TikTok"}

TEXT = {
    "queued": "queued",
    "running": "posting…",
    "verifying": "verifying…: its post tap went through, and its check is still running",
    "waiting": "waiting for the user",
    "done": "done",
    "failed": "not posted: it stopped before its post step",
    "not_started": "not posted: it never started (the cross-post stopped first)",
    "declined": "not posted: the post wasn't approved",
    "unknown": "outcome unknown, check this one: its post tap went through and the run ended before its check finished",
    "stopped": "stopped",
}


@dataclass
class Post:
    routine: str
    app: str  # package
    app_name: str
    goal: str  # the routine's intent: what its part's task says it does
    inputs: dict[str, str] = field(default_factory=dict)
    label: str = ""  # how Envoy names this destination: its app, and its routine too when another post shares that app


def tapped(approvals: list[dict[str, Any]], before: float | None = None) -> bool:
    """An irreversible tap may have run in this part: an approval said yes (the user, or a standing approval they gave)
    while the part was still running (`before`: when it ended, if known), and wasn't then refused because the screen had
    changed while it waited (api/approvals.py). A yes given after the part ended reached nothing: its task was gone."""
    return any(a.get("status") == "approved" and not (a.get("note") or "").startswith(SCREEN_CHANGED)
               and (before is None or (a.get("decided_at") or 0) <= before) for a in approvals)


def outcome(task: dict[str, Any], approvals: list[dict[str, Any]], ended: bool, ended_at: float | None = None) -> str:
    """One part's outcome: queued, running, verifying, waiting, done, failed, declined or unknown. Its task's status alone
    can't say it once the part has ended (a task stopped while it waited for an approval can read "running" again when
    that approval is answered later), so an ended part is judged by done or not, and by whether a yes reached it."""
    status = task.get("status") or "queued"
    if not ended:
        if status in WAITING:
            return "waiting"
        return "verifying" if tapped(approvals) else ("queued" if status == "queued" else "running")
    if status == "done":
        return "done"
    if tapped(approvals, ended_at):
        return "unknown"
    return "declined" if status == "declined" else "failed"


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def in_order(posts: list[Post]) -> list[Post]:
    """The order the parts run in: as given, except that an app that saves its own copy of the post in the gallery goes
    after the others, so none of them picks that copy as the newest video."""
    return sorted(posts, key=lambda p: p.app in SAVES_COPY)


class CrossPost:
    def __init__(self, runner: Any) -> None:
        self.runner, self.store, self.bus = runner, runner.store, runner.bus
        self.queues: dict[str, list[Post]] = {}  # parent id → posts still to start (its job takes them in order)
        self.parent_of: dict[str, str] = {}  # a part under way → its parent
        self.finished: set[str] = set()  # parts whose phone work ended (the runner's task_finished)
        self.shown: dict[str, tuple] = {}  # parent id → what it last showed
        self.bus.listeners.append(self._on_event)

    # ---- starting ------------------------------------------------------------------------------

    def start(self, posts: list[Post], source: str, phone: str | None = None) -> dict[str, Any]:
        """The parent task; its parts start one after another (`in_order`), the first at once."""
        posts = in_order(posts)
        for p in posts:
            p.label = p.label or (p.app_name if [x.app for x in posts].count(p.app) == 1 else f"{p.app_name} ({p.routine})")
        goal = "Post to " + _join([p.label for p in posts])
        parent = self.store.create(goal, source, kind="crossapp", request=goal)
        pid = parent["id"]
        self.bus.publish("task", task=parent)
        last = [SAVES_COPY[p.app] for p in posts if p.app in SAVES_COPY and len(posts) > 1]
        self._step(pid, {"kind": "plan", "crosspost": True, "phone": phone,
                         "text": f"{len(posts)} posts, one after another: " + "; ".join(f"{p.app_name} with routine {p.routine}" for p in posts)
                         + (f" ({_join(last)} last: it saves its own copy of the post in the gallery)" if last else ""),
                         "posts": [asdict(p) for p in posts]})
        self._on_loop(lambda: self._queue(pid, posts, source, phone))
        return self.store.get(pid) or parent

    def retry(self, pid: str, source: str) -> dict[str, Any]:
        """Run again only the destinations whose last part failed or was declined, or that never started. Done ones and
        unknown ones never run again; a queued one or one under way is left to finish."""
        rows = self.view(pid)
        again = [r for r in rows if r["status"] in RETRYABLE]
        left = [{"app": r["label"], "status": r["status"]} for r in rows if r["status"] not in RETRYABLE]
        if not again:
            return {"error": "nothing to retry: " + "; ".join(f"{r['app']} is {r['status']}" for r in left)
                    + (". Outcome unknown means the post may exist: the user checks that app; Envoy won't post there again."
                       if any(r["status"] == "unknown" for r in left) else "")}
        plan = self._plan(pid) or {}
        posts = [Post(**p) for p in plan.get("posts", []) if p["routine"] in {r["routine"] for r in again}]
        # An app that saves its own copy of the post may have done so already (it posted, may have, or is posting): the
        # gallery's newest video is then that copy, not the clip, for every part that runs after it.
        saved = [r["label"] for r in rows if r["app"] in SAVES_COPY and r["attempts"] and r["status"] not in RETRYABLE]
        after = [r["label"] for r in again if r["app"] not in SAVES_COPY]
        heads_up = (f"{_join(saved)} saves its own copy of what it posts in the phone's gallery, so the newest video there may no "
                    f"longer be the clip: send the clip to the phone again (send_to_phone) before {_join(after)} runs. Otherwise Envoy "
                    "stops that post before its first step, since its routine takes the gallery's newest video.") if saved and after else None
        self._step(pid, {"kind": "note", "text": "retry: " + ", ".join(f"{r['label']} ({r['status']})" for r in again)
                         + ("; left as they are: " + ", ".join(f"{r['app']} ({r['status']})" for r in left) if left else "")
                         + (f". {heads_up}" if heads_up else "")})
        self._on_loop(lambda: self._queue(pid, posts, source, plan.get("phone")))
        label = {r["routine"]: r["label"] for r in again}
        return {"retrying": [label[p.routine] for p in in_order(posts)], "left_alone": left,
                **({"heads_up": [{"kind": "gallery", "text": heads_up, "level": "warn"}]} if heads_up else {})}

    def _on_loop(self, fn: Any) -> None:
        """The queues and the parent's job live on the runner's loop; an MCP tool may call in from a worker thread."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        loop = self.runner.loop
        if running is not None and (loop is None or running is loop):
            fn()
            return

        async def call() -> None:
            fn()
        if loop is None:
            raise RuntimeError("the task runner has no event loop yet")
        asyncio.run_coroutine_threadsafe(call(), loop).result(15)

    def _queue(self, pid: str, posts: list[Post], source: str, phone: str | None) -> None:
        q = self.queues.setdefault(pid, [])
        q.extend(p for p in posts if p.routine not in {x.routine for x in q})
        q[:] = in_order(q)  # a retry queued behind a part still to start keeps TikTok last too
        job = self.runner.jobs.get(pid)
        if job is None or job.done():  # its job ended (or never ran): a new one takes the queue
            self.runner.jobs[pid] = asyncio.get_running_loop().create_task(self._run(pid, source, phone))
        self._mirror(pid)

    def _start_part(self, pid: str, post: Post, source: str, phone: str | None) -> str:
        attempt = 1 + sum(1 for p in self.parts(pid) if p["routine"] == post.routine)
        task = self.runner.start(post.goal, source, routine=post.routine, inputs=dict(post.inputs), app=post.app, parent=pid,
                                 **({"phone": phone} if phone else {}))
        self.parent_of[task["id"]] = pid
        self._step(pid, {"kind": "part", "routine": post.routine, "task_id": task["id"], "attempt": attempt,
                         "text": f"{post.app_name}: routine {post.routine}" + (f", attempt {attempt}" if attempt > 1 else "")})
        return task["id"]

    # ---- the run -----------------------------------------------------------------------------------

    async def _run(self, pid: str, source: str, phone: str | None) -> None:
        t0 = time.time()
        current: str | None = None
        try:
            while self.queues.get(pid):
                post = self.queues[pid].pop(0)
                current = self._start_part(pid, post, source, phone)
                self._mirror(pid)
                await self._wait(pid, current)
                self._ended_part(pid, current)
                self.parent_of.pop(current, None)
                current = None
                self._mirror(pid)
            self._finish(pid, t0)  # no await from the queue's last look to here: a retry either joined it or starts anew
        except asyncio.CancelledError:
            if current is not None:
                self.runner.stop(current)
                self._ended_part(pid, current, said="stopped with the cross-post")
            self.queues.pop(pid, None)
            self._set(pid, status="stopped", detail="stopped by you", result=self._result(self.view(pid)), waiting_for=None,
                      **self._spend(pid))
            self.bus.publish("task_finished", task_id=pid, duration_s=round(time.time() - t0, 1))
            raise
        except Exception as e:  # noqa: BLE001 - a failure is reported, never crashes the server
            self.queues.pop(pid, None)
            self._set(pid, status="failed", detail=f"{type(e).__name__}: {e}"[:400], waiting_for=None)
            self.bus.publish("task_finished", task_id=pid, duration_s=round(time.time() - t0, 1))
        finally:
            self.shown.pop(pid, None)
            if current is not None:
                self.parent_of.pop(current, None)

    async def _wait(self, pid: str, tid: str) -> None:
        """Until the part's phone work has ended. One held up past PART_LIMIT_S is stopped, and judged like any other end."""
        deadline = time.time() + PART_LIMIT_S
        stopped = False
        while not self.ended(tid):
            if not stopped and time.time() > deadline:
                stopped = True
                self._step(pid, {"kind": "note", "text": f"{self._name(pid, tid)}: still not finished after {round(PART_LIMIT_S / 60)} min, so it was stopped"})
                self.runner.stop(tid)
            await asyncio.sleep(0.2)

    def _ended_part(self, pid: str, tid: str, said: str | None = None) -> None:
        """When the part's run ended, kept with the parent: a yes given after it reached nothing (see `tapped`)."""
        if said is None:
            row = next((r for r in self.view(pid) if r["task_id"] == tid), None)
            said = {"done": "done", "unknown": "outcome unknown"}.get(row["status"], f"not posted ({row['status']})") if row else "ended"
        self._step(pid, {"kind": "part_end", "task_id": tid, "time": time.time(), "text": f"{self._name(pid, tid)}: {said}"})

    def ended(self, tid: str) -> bool:
        task = self.store.get(tid) or {}
        if task.get("status") in ENDED or tid in self.finished:
            return True
        job = self.runner.jobs.get(tid)
        return job is None or job.done()

    def _finish(self, pid: str, t0: float) -> None:
        rows = self.view(pid)
        said = {r["status"] for r in rows}
        unknown = [r["label"] for r in rows if r["status"] == "unknown"]
        undone = [r for r in rows if r["status"] in RETRYABLE]
        if said == {"done"}:
            status, detail = "done", None
        elif unknown:
            status = "needs_you"
            detail = (f"Check {_join(unknown)} yourself: the post tap went through and its run ended before its check finished, "
                      "so the post may be there. Envoy won't post there again.")
        else:
            status = "declined" if all(r["status"] == "declined" for r in undone) else "failed"
            detail = "Not posted: " + "; ".join(f"{r['label']} ({r['status']})" for r in undone)
        if undone:
            detail = (detail + "; " if detail else "") + "a retry runs only " + _join([r["label"] for r in undone])
        self._set(pid, status=status, result=self._result(rows), detail=detail, waiting_for=None, **self._spend(pid))
        self.bus.publish("task_finished", task_id=pid, duration_s=round(time.time() - t0, 1))

    def _spend(self, pid: str) -> dict[str, Any]:
        kids = [self.store.get(p["task_id"]) or {} for p in self.parts(pid)]
        return {"model_calls": sum(k.get("model_calls") or 0 for k in kids), "cost_usd": round(sum(k.get("cost_usd") or 0 for k in kids), 5)}

    # ---- what it shows -------------------------------------------------------------------------------

    def is_crosspost(self, pid: str) -> bool:
        return self._plan(pid) is not None

    def _plan(self, pid: str) -> dict[str, Any] | None:
        return next((s for s in self.store.steps(pid) if s.get("kind") == "plan" and s.get("crosspost")), None)

    def parts(self, pid: str) -> list[dict[str, Any]]:
        return [s for s in self.store.steps(pid) if s.get("kind") == "part"]

    def _name(self, pid: str, tid: str) -> str:
        routine = next((p["routine"] for p in self.parts(pid) if p["task_id"] == tid), None)
        return next((p.get("label") or p["app_name"] for p in (self._plan(pid) or {}).get("posts", []) if p["routine"] == routine), "a part")

    def view(self, pid: str) -> list[dict[str, Any]]:
        """Each destination: its routine and app, its outcome (with what the user should do about it), its latest part's
        task and how many parts it has had."""
        plan, parts = self._plan(pid) or {}, self.parts(pid)
        ends = {s["task_id"]: s.get("time") for s in self.store.steps(pid) if s.get("kind") == "part_end"}
        queued = {p.routine for p in self.queues.get(pid, [])}
        rows = []
        for post in plan.get("posts", []):
            tries = [p for p in parts if p["routine"] == post["routine"]]
            task: dict[str, Any] = {}
            status = "not_started"  # "queued" below while it waits in the live queue; after a stop or a restart, a retry runs it
            if tries:
                tid = tries[-1]["task_id"]
                task = self.store.get(tid) or {}
                # a part_end is the cross-post done with that part, even while a stopped part's run is still unwinding
                status = outcome(task, self.store.approvals(task_id=tid), tid in ends or self.ended(tid), ends.get(tid))
            if post["routine"] in queued and status in (*RETRYABLE, "queued"):
                status = "queued"
            text = TEXT[status]
            if status == "unknown":
                text += f" ({task.get('detail') or task.get('status')}). Check {post['app_name']} yourself; Envoy won't post there again."
            elif status in RETRYABLE and task.get("detail"):
                text += f" ({task['detail']})"
            elif status == "waiting" and task.get("detail"):
                text += f": {task['detail']}"
            rows.append({"routine": post["routine"], "app": post["app"], "app_name": post["app_name"], "label": post.get("label") or post["app_name"],
                         "status": status, "text": text,
                         "task_id": tries[-1]["task_id"] if tries else None, "attempts": len(tries)})
        return rows

    def _result(self, rows: list[dict[str, Any]]) -> str:
        short = {"unknown": "outcome unknown, check this one", "failed": "not posted (failed)", "declined": "not posted (declined)",
                 "not_started": "not posted (never started)",
                 "verifying": "verifying…"}
        return " · ".join(f"{r['label']}: {short.get(r['status'], TEXT[r['status']])}" for r in rows)

    def _on_event(self, ev: dict[str, Any]) -> None:
        if ev.get("type") == "task_finished" and ev.get("task_id") in self.parent_of:
            self.finished.add(ev["task_id"])
            self._mirror(self.parent_of[ev["task_id"]])
        elif ev.get("type") == "task" and (pid := self.parent_of.get((ev.get("task") or {}).get("id"))):
            self._mirror(pid)

    def _mirror(self, pid: str) -> None:
        """While its parts run, the parent waits on the user when the part under way does, and shows each destination."""
        job = self.runner.jobs.get(pid)
        if job is not None and job.done():
            return
        rows = self.view(pid)
        waiting = next((r for r in rows if r["status"] == "waiting"), None)
        task = self.store.get(waiting["task_id"]) or {} if waiting else {}
        status = {"waiting_approval": "waiting_approval"}.get(task.get("status"), "needs_you") if waiting else "running"
        detail = f"{waiting['label']}: {task.get('detail') or 'waiting for you'}" if waiting else None
        shown = (status, detail, self._result(rows))
        if self.shown.get(pid) != shown:
            self.shown[pid] = shown
            self._set(pid, status=status, detail=detail, result=shown[2])

    def _set(self, tid: str, **fields: Any) -> None:
        task = self.store.update(tid, **fields)
        if task:
            self.bus.publish("task", task=task)

    def _step(self, tid: str, data: dict[str, Any]) -> None:
        self.runner._step(tid, data)
