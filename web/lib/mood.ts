"use client";

// The avatar's mood from real state, highest priority first:
// 1. offline: the event stream isn't connected (after a short grace on first load);
// 2. needs: something is waiting on you (page.tsx's count, the same as Activity's badge: an approval, a task that needs
//    you, a phone ask, or a question from Envoy);
// 3. listening: dictation is on;
// 4. working: a task is running and its steps are arriving (one in the last ~1.5 s);
// 5. thinking: a task is queued, or running with no step in the last ~1.5 s;
// 6. done: a task just finished: for ~3 s, then back to idle;
// 7. idle.
import { useEffect, useRef, useState } from "react";
import type { Mood } from "@/components/Avatar";
import type { Task } from "@/lib/api";

const STEP_FRESH_MS = 1500;
const DONE_MS = 3000;
const GRACE_MS = 2500;

export function useMood({ connected, tasks, waiting, lastStepAt, listening }: {
  connected: boolean; tasks: Record<string, Task>; waiting: number; lastStepAt: number; listening: boolean;
}): Mood {
  const [now, setNow] = useState(() => Date.now());
  const [mountedAt] = useState(() => Date.now());
  const [doneUntil, setDoneUntil] = useState(0);
  const seen = useRef<Record<string, string>>({});

  // A task that moves from active to done shows the done face once.
  useEffect(() => {
    let finished = false;
    for (const t of Object.values(tasks)) {
      const before = seen.current[t.id];
      if (before && before !== "done" && t.status === "done") finished = true;
      seen.current[t.id] = t.status;
    }
    if (finished) setDoneUntil(Date.now() + DONE_MS);
  }, [tasks]);

  const list = Object.values(tasks);
  const running = list.some((t) => t.status === "running");
  const queued = list.some((t) => t.status === "queued");
  const ticking = running || queued || doneUntil > now || !connected;
  useEffect(() => {
    if (!ticking) return;
    const id = setInterval(() => setNow(Date.now()), 400);
    return () => clearInterval(id);
  }, [ticking]);
  // a step that just arrived counts at once, without waiting for the next tick
  useEffect(() => setNow(Date.now()), [lastStepAt]);

  if (!connected && now - mountedAt > GRACE_MS) return "offline";
  if (waiting > 0) return "needs";
  if (listening) return "listening";
  if (running && now - lastStepAt < STEP_FRESH_MS) return "working";
  if (running || queued) return "thinking";
  if (doneUntil > now) return "done";
  return "idle";
}
