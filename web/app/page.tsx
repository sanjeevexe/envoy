"use client";

// Envoy's web app: chat, tasks, approvals, memory, routines and triggers, with the live phone beside them.
import { useCallback, useEffect, useMemo, useState } from "react";
import Approvals from "@/components/Approvals";
import Chat from "@/components/Chat";
import LivePhone from "@/components/LivePhone";
import MemoryGraph from "@/components/MemoryGraph";
import Routines from "@/components/Routines";
import Settings from "@/components/Settings";
import { TaskDetail, TaskList } from "@/components/Tasks";
import Triggers from "@/components/Triggers";
import { api, ApiError, Approval, EnvoyEvent, Lease, Step, Task, useEvents } from "@/lib/api";

const TABS = ["Chat", "Tasks", "Approvals", "Memory", "Routines", "Triggers", "Settings"] as const;
type Tab = (typeof TABS)[number];

export default function Home() {
  const [tab, setTab] = useState<Tab>("Chat");
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [profile, setProfile] = useState("");
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const [steps, setSteps] = useState<Record<string, Step[]>>({});
  const [approvals, setApprovals] = useState<Record<string, Approval>>({});
  const [leases, setLeases] = useState<Record<string, Lease>>({});
  const [avd, setAvd] = useState("envoy-test");
  const [openTask, setOpenTask] = useState<string | null>(null);
  const [memVersion, setMemVersion] = useState(0);

  const load = useCallback(() => {
    api("/api/state").then((s) => {
      setAuthed(true);
      setProfile(s.profile);
      setTasks(Object.fromEntries(s.tasks.map((t: Task) => [t.id, t])));
      setApprovals(Object.fromEntries(s.approvals.map((a: Approval) => [a.id, a])));
      setLeases(Object.fromEntries(s.devices.map((d: Lease) => [d.avd, d])));
    }).catch((e) => setAuthed(e instanceof ApiError && e.status === 401 ? false : true));
  }, []);

  useEffect(() => {
    load();
    const t = new URLSearchParams(location.search).get("task");
    if (t) { setOpenTask(t); setTab("Tasks"); }
  }, [load]);

  const connected = useEvents(useCallback((e: EnvoyEvent) => {
    switch (e.type) {
      case "task": setTasks((m) => ({ ...m, [e.task.id]: e.task })); break;
      case "step": setSteps((m) => ({ ...m, [e.task_id]: [...(m[e.task_id] ?? []), e.step] })); break;
      case "approval_requested":
      case "approval_decided": setApprovals((m) => ({ ...m, [e.approval.id]: e.approval })); if (e.type === "approval_requested") setTab((t) => t === "Chat" ? t : "Approvals"); break;
      case "takeover": case "hand_back": case "takeover_requested":
        setLeases((m) => ({ ...m, [e.avd]: { ...(m[e.avd] ?? { avd: e.avd, task_id: null, since: 0, reason: "" }), task_id: e.task_id,
          user_control: e.type === "takeover" ? true : e.type === "hand_back" ? false : !!m[e.avd]?.user_control, reason: e.reason ?? "" } }));
        if (e.type === "takeover_requested") setAvd(e.avd);
        break;
      case "memory": setMemVersion((v) => v + 1); break;
    }
  }, []));

  const taskList = useMemo(() => Object.values(tasks).sort((a, b) => b.created_at - a.created_at), [tasks]);
  const pending = Object.values(approvals).filter((a) => a.status === "pending");
  const needs = taskList.find((t) => t.status === "needs_you" && t.device === avd);

  if (authed === false) {
    return (
      <main className="mx-auto max-w-md p-8 text-sm">
        <h1 className="text-xl font-semibold">Envoy</h1>
        <p className="mt-2">Open the sign-in link the Envoy server printed when it started (it sets a cookie for this browser).</p>
      </main>
    );
  }

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold">Envoy</span>
          {profile && <span className="rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600">{profile === "demo" ? "demo (SkyLark test data)" : "your memory"}</span>}
        </div>
        <span className={`text-xs ${connected ? "text-emerald-700" : "text-rose-700"}`}>{connected ? "● live" : "● reconnecting"}</span>
      </header>
      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <nav className="flex gap-1 overflow-x-auto border-b border-stone-200 bg-white px-2">
            {TABS.map((t) => (
              <button key={t} onClick={() => { setTab(t); if (t !== "Tasks") setOpenTask(null); }}
                      className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-stone-800 font-medium" : "text-stone-500"}`}>
                {t}{t === "Approvals" && pending.length > 0 && <span className="ml-1 rounded-full bg-rose-600 px-1.5 text-xs text-white">{pending.length}</span>}
                {t === "Tasks" && taskList.some((x) => x.status === "needs_you") && <span className="ml-1 text-amber-600">●</span>}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {tab === "Chat" && <Chat tasks={tasks} openTask={(id) => { setOpenTask(id); setTab("Tasks"); }} />}
            {tab === "Tasks" && (openTask
              ? <TaskDetail id={openTask} task={tasks[openTask]} liveSteps={steps[openTask] ?? []} back={() => setOpenTask(null)} />
              : <TaskList tasks={taskList} open={setOpenTask} />)}
            {tab === "Approvals" && <Approvals approvals={Object.values(approvals)} />}
            {tab === "Memory" && <MemoryGraph version={memVersion} />}
            {tab === "Routines" && <Routines openTask={(id) => { setOpenTask(id); setTab("Tasks"); }} />}
            {tab === "Triggers" && <Triggers />}
            {tab === "Settings" && <Settings />}
          </div>
        </section>
        <aside className="w-full shrink-0 overflow-y-auto border-t border-stone-200 bg-stone-50 p-4 md:w-[340px] md:border-l md:border-t-0">
          <div className="mb-2 flex gap-1 text-xs">
            {["envoy-test", "envoy-real"].map((d) => (
              <button key={d} onClick={() => setAvd(d)} className={`rounded px-2 py-1 ${avd === d ? "bg-stone-800 text-white" : "bg-white"}`}>
                {d === "envoy-test" ? "Test phone" : "Real-app phone"}{leases[d] && leases[d].running === false ? " (off)" : ""}
              </button>
            ))}
          </div>
          {pending.length > 0 && tab !== "Approvals" && (
            <button onClick={() => setTab("Approvals")} className="mb-2 w-full rounded-lg bg-rose-600 px-3 py-2 text-left text-sm text-white">
              {pending.length} approval{pending.length > 1 ? "s" : ""} waiting: {pending[0].description}
            </button>
          )}
          <LivePhone key={avd} avd={avd} lease={leases[avd]} needsYou={needs ? needs.detail ?? "Envoy needs you" : null} />
        </aside>
      </div>
    </main>
  );
}
