"use client";

// Envoy's web app: chat, tasks, approvals, memory, routines and triggers, with the live phone beside them.
// Phase 5: on a phone (the iPhone's Home Screen app) the same app gets bottom tabs, with the live phone as its own tab
// (streamed only while it's open), and a notification's link opens the right tab.
import { useCallback, useEffect, useMemo, useState } from "react";
import Approvals from "@/components/Approvals";
import Chat from "@/components/Chat";
import Companion from "@/components/Companion";
import LivePhone from "@/components/LivePhone";
import MemoryGraph from "@/components/MemoryGraph";
import Pair from "@/components/Pair";
import PhoneAsk from "@/components/PhoneAsk";
import Routines from "@/components/Routines";
import Settings from "@/components/Settings";
import { TaskDetail, TaskList } from "@/components/Tasks";
import Triggers from "@/components/Triggers";
import { api, ApiError, Approval, EnvoyEvent, Lease, Step, Task, useEvents } from "@/lib/api";
import { registerServiceWorker, useMedia } from "@/lib/device";

const TABS = ["Chat", "Tasks", "Approvals", "Memory", "Routines", "Triggers", "Devices", "Settings"] as const;
type Tab = (typeof TABS)[number] | "Phone" | "More";
const MOBILE_TABS: { tab: Tab; label: string; icon: string }[] = [
  { tab: "Chat", label: "Chat", icon: "💬" }, { tab: "Phone", label: "Phone", icon: "📱" }, { tab: "Approvals", label: "Approvals", icon: "✅" },
  { tab: "Memory", label: "Memory", icon: "🧠" }, { tab: "More", label: "More", icon: "☰" },
];
const MORE: Tab[] = ["Tasks", "Routines", "Triggers", "Devices", "Settings"];

export default function Home() {
  const mobile = useMedia("(max-width: 767px)");
  const [tab, setTab] = useState<Tab>("Chat");
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [profile, setProfile] = useState("");
  const [publicUrl, setPublicUrl] = useState<string>();
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const [steps, setSteps] = useState<Record<string, Step[]>>({});
  const [approvals, setApprovals] = useState<Record<string, Approval>>({});
  const [leases, setLeases] = useState<Record<string, Lease>>({});
  const [avd, setAvd] = useState("envoy-test");
  const [openTask, setOpenTask] = useState<string | null>(null);
  const [memVersion, setMemVersion] = useState(0);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(() => {
    api("/api/state").then((s) => {
      setAuthed(true);
      setProfile(s.profile);
      setPublicUrl(s.public_url);
      setTasks(Object.fromEntries(s.tasks.map((t: Task) => [t.id, t])));
      setApprovals(Object.fromEntries(s.approvals.map((a: Approval) => [a.id, a])));
      setLeases(Object.fromEntries(s.devices.map((d: Lease) => [d.avd, d])));
    }).catch((e) => setAuthed(e instanceof ApiError && e.status === 401 ? false : true));
  }, []);

  // Where a link (or a notification) points: ?task=…, ?phone=<avd>.
  const route = useCallback((href: string) => {
    const u = new URL(href, location.origin);
    if (u.pathname.startsWith("/approve")) { location.href = u.href; return; }
    const t = u.searchParams.get("task");
    const phone = u.searchParams.get("phone");
    if (phone) { setAvd(phone); setTab(window.matchMedia("(max-width: 767px)").matches ? "Phone" : "Chat"); }
    else if (t) { setOpenTask(t); setTab("Tasks"); }
  }, []);

  useEffect(() => {
    load();
    route(location.href);
    registerServiceWorker(route);
  }, [load, route]);

  // Phones come and go (a USB cable): refresh the list now and then.
  useEffect(() => {
    if (!authed) return;
    const id = setInterval(() => {
      api<Lease[]>("/api/devices").then((ds) => setLeases((m) => ({ ...m, ...Object.fromEntries(ds.map((d) => [d.avd, { ...m[d.avd], ...d }])) }))).catch(() => {});
    }, 10000);
    return () => clearInterval(id);
  }, [authed]);

  const connected = useEvents(useCallback((e: EnvoyEvent) => {
    switch (e.type) {
      case "task": setTasks((m) => ({ ...m, [e.task.id]: e.task })); break;
      case "step": setSteps((m) => ({ ...m, [e.task_id]: [...(m[e.task_id] ?? []), e.step] })); break;
      case "approval_requested":
      case "approval_decided": setApprovals((m) => ({ ...m, [e.approval.id]: e.approval })); if (e.type === "approval_requested") setTab((t) => t === "Chat" || t === "Phone" ? t : "Approvals"); break;
      case "takeover": case "hand_back": case "takeover_requested":
        setLeases((m) => ({ ...m, [e.avd]: { ...(m[e.avd] ?? { avd: e.avd, task_id: null, since: 0, reason: "" }), task_id: e.task_id,
          user_control: e.type === "takeover" ? true : e.type === "hand_back" ? false : !!m[e.avd]?.user_control, reason: e.reason ?? "" } }));
        if (e.type === "takeover_requested") setAvd(e.avd);
        break;
      case "memory": setMemVersion((v) => v + 1); break;
      case "photo": setToast(e.summary); setTimeout(() => setToast(null), 5000); break;
      case "paired": setToast(`Paired: ${e.name}`); setTimeout(() => setToast(null), 5000); break;
    }
  }, []));

  const taskList = useMemo(() => Object.values(tasks).sort((a, b) => b.created_at - a.created_at), [tasks]);
  const pending = Object.values(approvals).filter((a) => a.status === "pending");
  const needs = taskList.find((t) => t.status === "needs_you" && t.device === avd);
  const phoneAsk = taskList.find((t) => t.waiting_for === "phone" && t.status === "needs_you");
  const phones = Object.values(leases).sort((a, b) => (a.kind === "phone" ? 1 : 0) - (b.kind === "phone" ? 1 : 0));
  const go = (t: Tab) => { setTab(t); if (t !== "Tasks") setOpenTask(null); };
  const openTaskTab = (id: string) => { setOpenTask(id); setTab("Tasks"); };

  if (authed === null) return <main className="h-[100dvh]" />;
  if (authed === false) return <Pair onPaired={load} />;

  const content = (
    <>
      {tab === "Chat" && <Chat tasks={tasks} openTask={openTaskTab} compact={mobile} />}
      {tab === "Tasks" && (openTask
        ? <TaskDetail id={openTask} task={tasks[openTask]} liveSteps={steps[openTask] ?? []} back={() => setOpenTask(null)} />
        : <TaskList tasks={taskList} open={setOpenTask} />)}
      {tab === "Approvals" && <Approvals approvals={Object.values(approvals)} />}
      {tab === "Memory" && <MemoryGraph version={memVersion} />}
      {tab === "Routines" && <Routines openTask={openTaskTab} />}
      {tab === "Triggers" && <Triggers />}
      {tab === "Devices" && <Companion publicUrl={publicUrl} />}
      {tab === "Settings" && <Settings />}
    </>
  );
  const phoneSwitch = (
    <div className="mb-2 flex gap-1 text-xs">
      {phones.map((d) => (
        <button key={d.avd} onClick={() => setAvd(d.avd)} className={`rounded px-2 py-1 ${avd === d.avd ? "bg-stone-800 text-white" : "bg-white"}`}>
          {d.kind === "phone" ? `📱 ${d.name ?? "Your phone"}` : d.name ?? d.avd}
          {d.kind === "phone" && d.state === "unauthorized" ? " (allow USB debugging)" : d.running === false ? " (off)" : ""}
        </button>
      ))}
    </div>
  );
  const toastEl = toast && <div className="pointer-events-none fixed inset-x-4 top-16 z-20 mx-auto max-w-md rounded-xl bg-stone-900/95 px-4 py-3 text-sm text-white shadow-lg">{toast}</div>;

  if (mobile) {
    return (
      <main className="flex h-[100dvh] flex-col">
        <header className="flex items-center justify-between border-b border-stone-200 bg-white px-4 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))]">
          <span className="text-lg font-semibold">Envoy</span>
          <span className={`text-xs ${connected ? "text-emerald-700" : "text-rose-700"}`}>{connected ? "● live" : "● can't reach your Mac"}</span>
        </header>
        {phoneAsk && <div className="p-3 pb-0"><PhoneAsk task={phoneAsk} large /></div>}
        {pending.length > 0 && tab !== "Approvals" && (
          <button onClick={() => go("Approvals")} className="bg-rose-600 px-4 py-2 text-left text-sm text-white">
            {pending.length} approval{pending.length > 1 ? "s" : ""} waiting: {pending[0].description}
          </button>
        )}
        {needs && tab !== "Phone" && (
          <button onClick={() => go("Phone")} className="bg-amber-500 px-4 py-2 text-left text-sm text-amber-950">Envoy needs you on the phone: {needs.detail ?? "take over"}</button>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {tab === "Phone" ? (
            <div className="p-3">{phoneSwitch}<LivePhone key={avd} avd={avd} lease={leases[avd]} needsYou={needs ? needs.detail ?? "Envoy needs you" : null} mobile /></div>
          ) : tab === "More" ? (
            <ul className="divide-y divide-stone-200 bg-white">
              {MORE.map((t) => (
                <li key={t}><button onClick={() => go(t)} className="flex w-full items-center justify-between px-4 py-4 text-left text-base">{t}<span className="text-stone-400">›</span></button></li>
              ))}
              {profile && <li className="px-4 py-3 text-xs text-stone-500">{profile === "demo" ? "Demo memory (SkyLark test data)" : "Your memory"}</li>}
            </ul>
          ) : content}
        </div>
        <nav className="grid grid-cols-5 border-t border-stone-200 bg-white pb-[env(safe-area-inset-bottom)]">
          {MOBILE_TABS.map(({ tab: t, label, icon }) => {
            const active = tab === t || (t === "More" && MORE.includes(tab));
            return (
              <button key={t} onClick={() => go(t)} className={`relative flex flex-col items-center gap-0.5 py-2 text-[11px] ${active ? "font-semibold text-stone-900" : "text-stone-500"}`}>
                <span className="text-xl leading-none">{icon}</span>{label}
                {t === "Approvals" && pending.length > 0 && <span className="absolute right-4 top-1 rounded-full bg-rose-600 px-1.5 text-[10px] text-white">{pending.length}</span>}
                {t === "Phone" && (needs || leases[avd]?.user_control) && <span className="absolute right-5 top-1 h-2 w-2 rounded-full bg-amber-500" />}
              </button>
            );
          })}
        </nav>
        {toastEl}
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
      <div className="flex min-h-0 flex-1 flex-row">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <nav className="flex gap-1 overflow-x-auto border-b border-stone-200 bg-white px-2">
            {TABS.map((t) => (
              <button key={t} onClick={() => go(t)}
                      className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-stone-800 font-medium" : "text-stone-500"}`}>
                {t}{t === "Approvals" && pending.length > 0 && <span className="ml-1 rounded-full bg-rose-600 px-1.5 text-xs text-white">{pending.length}</span>}
                {t === "Tasks" && taskList.some((x) => x.status === "needs_you") && <span className="ml-1 text-amber-600">●</span>}
              </button>
            ))}
          </nav>
          <div className="min-h-0 flex-1 overflow-y-auto">{content}</div>
        </section>
        <aside className="w-[340px] shrink-0 overflow-y-auto border-l border-stone-200 bg-stone-50 p-4">
          {phoneSwitch}
          {phoneAsk && <div className="mb-2"><PhoneAsk task={phoneAsk} /></div>}
          {pending.length > 0 && tab !== "Approvals" && (
            <button onClick={() => go("Approvals")} className="mb-2 w-full rounded-lg bg-rose-600 px-3 py-2 text-left text-sm text-white">
              {pending.length} approval{pending.length > 1 ? "s" : ""} waiting: {pending[0].description}
            </button>
          )}
          <LivePhone key={avd} avd={avd} lease={leases[avd]} needsYou={needs ? needs.detail ?? "Envoy needs you" : null} />
        </aside>
      </div>
      {toastEl}
    </main>
  );
}
