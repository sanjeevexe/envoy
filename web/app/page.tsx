"use client";

// Envoy's web app. On a phone (the iPhone's Home Screen app): five tabs, Home, Activity, Phone, Memory and Routines,
// with Settings from the header; the live phone is its own tab (streamed only while it's open). On a wider screen: a
// sidebar with the same places, the content at a readable width, and the live phone on the right (not beside the
// Phone tab, nor the Memory graph, which fills the width).
// Links (and notifications) open the right place: ?task=…, ?phone=<avd>, ?offer=<id> (the offer's card in a sheet);
// /approve/?id=… is its own page.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CaretLeftIcon, DeviceMobileIcon, GraphIcon, HouseIcon, PulseIcon, RepeatIcon, SlidersHorizontalIcon, type Icon,
} from "@phosphor-icons/react";
import Activity from "@/components/Activity";
import { ApprovalSheet } from "@/components/Approvals";
import { OfferSheet } from "@/components/Offers";
import Avatar, { MOOD_LABEL, Wordmark } from "@/components/Avatar";
import Home from "@/components/Home";
import LivePhone, { PhoneSwitch } from "@/components/LivePhone";
import MemoryGraph from "@/components/MemoryGraph";
import Pair from "@/components/Pair";
import RoutinesTab from "@/components/Routines";
import SettingsPage from "@/components/Settings";
import { ACTIVE } from "@/components/Tasks";
import { cx } from "@/components/ui";
import { api, ApiError, Approval, EnvoyEvent, Lease, Offer, Step, Task, useEvents } from "@/lib/api";
import { registerServiceWorker, useMedia } from "@/lib/device";
import { useMood } from "@/lib/mood";

type Tab = "Home" | "Activity" | "Phone" | "Memory" | "Routines" | "Settings";
const NAV: { tab: Tab; icon: Icon }[] = [
  { tab: "Home", icon: HouseIcon }, { tab: "Activity", icon: PulseIcon }, { tab: "Phone", icon: DeviceMobileIcon },
  { tab: "Memory", icon: GraphIcon }, { tab: "Routines", icon: RepeatIcon },
];

export default function Page() {
  const mobile = useMedia("(max-width: 767px)");
  const [tab, setTab] = useState<Tab>("Home");
  const [back, setBack] = useState<Tab>("Home"); // where Settings goes back to
  const [teachAsk, setTeachAsk] = useState<{ goal: string } | null>(null); // "Show me once": the Teach form with a failed task's goal
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [profile, setProfile] = useState("");
  const [publicUrl, setPublicUrl] = useState<string>();
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const [steps, setSteps] = useState<Record<string, Step[]>>({});
  const [approvals, setApprovals] = useState<Record<string, Approval>>({});
  const [offers, setOffers] = useState<Offer[]>([]); // Envoy's questions waiting for your answer
  const [leases, setLeases] = useState<Record<string, Lease>>({});
  const [avd, setAvd] = useState("envoy-test");
  const [openTask, setOpenTask] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<string | null>(null); // the approval in the sheet
  const [asking, setAsking] = useState<string | null>(null); // the offer in the sheet (a push opened it)
  const [memVersion, setMemVersion] = useState(0);
  const [briefVersion, setBriefVersion] = useState(0);
  const [toast, setToast] = useState<{ text: string; key: number } | null>(null);
  const [listening, setListening] = useState(false);
  const [lastStepAt, setLastStepAt] = useState(0);

  const say = useCallback((text: string) => {
    const key = Date.now();
    setToast({ text, key });
    setTimeout(() => setToast((t) => (t?.key === key ? null : t)), 5000);
  }, []);

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

  const loadOffers = useCallback(() => { api<Offer[]>("/api/offers?status=pending").then(setOffers).catch(() => {}); }, []);

  // Where a link (or a notification) points: ?task=…, ?phone=<avd>, ?offer=<id>, ?handoff=<id> (a file from the Mac).
  const route = useCallback((href: string) => {
    const u = new URL(href, location.origin);
    if (u.pathname.startsWith("/approve")) { location.href = u.href; return; }
    const t = u.searchParams.get("task");
    const phone = u.searchParams.get("phone");
    const offer = u.searchParams.get("offer");
    if (offer) { setAsking(offer); setTab("Home"); }
    else if (phone) { setAvd(phone); setTab(window.matchMedia("(max-width: 767px)").matches ? "Phone" : "Home"); }
    else if (t) { setOpenTask(t); setTab("Activity"); }
    else if (u.searchParams.get("handoff")) setTab("Activity");
  }, []);

  useEffect(() => {
    load();
    route(location.href);
    registerServiceWorker(route);
  }, [load, route]);

  // Phones come and go (a USB cable): refresh the list now and then.
  useEffect(() => { if (authed) loadOffers(); }, [authed, loadOffers]);

  useEffect(() => {
    if (!authed) return;
    const id = setInterval(() => {
      api<Lease[]>("/api/devices").then((ds) => setLeases((m) => ({ ...m, ...Object.fromEntries(ds.map((d) => [d.avd, { ...m[d.avd], ...d }])) }))).catch(() => {});
    }, 10000);
    return () => clearInterval(id);
  }, [authed]);

  const connected = useEvents(useCallback((e: EnvoyEvent) => {
    switch (e.type) {
      case "task": setTasks((m) => ({ ...m, [e.task.id]: e.task })); if (["done", "failed", "declined"].includes(e.task.status)) setBriefVersion((v) => v + 1); break;
      case "step": setSteps((m) => ({ ...m, [e.task_id]: [...(m[e.task_id] ?? []), e.step] })); setLastStepAt(Date.now()); break;
      case "approval_requested":
      case "approval_decided":
        setApprovals((m) => ({ ...m, [e.approval.id]: e.approval }));
        setBriefVersion((v) => v + 1);
        if (e.type === "approval_requested") setTab((t) => (t === "Home" || t === "Phone" ? t : "Activity"));
        break;
      case "takeover": case "hand_back": case "takeover_requested":
        setLeases((m) => ({ ...m, [e.avd]: { ...(m[e.avd] ?? { avd: e.avd, task_id: null, since: 0, reason: "" }), task_id: e.task_id,
          user_control: e.type === "takeover" ? true : e.type === "hand_back" ? false : !!m[e.avd]?.user_control, reason: e.reason ?? "" } }));
        if (e.type === "takeover_requested") setAvd(e.avd);
        break;
      case "teach": {  // teach mode (backend/api/teach.py): the phone's Recording line, and Learning it after Finish
        const t = e.teach ?? {};
        const on = ["recording", "compiling", "replaying"].includes(t.status);
        setLeases((m) => (m[t.device] ? { ...m, [t.device]: { ...m[t.device], teach: on ? t : null } } : m));
        break;
      }
      case "memory": setMemVersion((v) => v + 1); break;
      case "fact_changed": setBriefVersion((v) => v + 1); break;
      case "offer":  // one you asked for in chat shows in the conversation itself: no toast for it
        setBriefVersion((v) => v + 1);
        loadOffers();
        if (e.change === "created" && !["chat", "voice"].includes(e.offer?.source)) say(e.offer?.title ?? "Envoy has a question");
        break;
      case "handoff": setBriefVersion((v) => v + 1); break;
      case "photo": say(e.summary); break;
      case "paired": say(`Paired: ${e.name}`); break;
    }
  }, [say, loadOffers]));
  useEffect(() => { if (connected) loadOffers(); }, [connected, loadOffers]);  // what changed while the stream was down

  const taskList = useMemo(() => Object.values(tasks).sort((a, b) => b.created_at - a.created_at), [tasks]);
  const pending = Object.values(approvals).filter((a) => a.status === "pending");
  const needs = taskList.find((t) => t.status === "needs_you" && t.device === avd && t.waiting_for !== "phone");
  // Everything waiting on you, as Activity's "Needs you" lists it: approvals, tasks that need you (a phone ask, a
  // takeover) and Envoy's questions. The sidebar count, the tab's dot and the avatar's mood all use this one count.
  const questions = offers.filter((o) => o.status === "pending" && (!o.expires_at || o.expires_at > Date.now() / 1000));
  const waitingOnYou = pending.length + taskList.filter((t) => t.status === "needs_you").length + questions.length;
  const mood = useMood({ connected, tasks, waiting: waitingOnYou, lastStepAt, listening });
  const phones = Object.values(leases).sort((a, b) => (a.kind === "phone" ? 1 : 0) - (b.kind === "phone" ? 1 : 0));

  const go = (t: Tab) => {
    if (t === "Settings") setBack(tab === "Settings" ? back : tab);
    setTab(t);
    if (t !== "Activity") setOpenTask(null);
  };
  const openTaskTab = (id: string) => { setOpenTask(id); setTab("Activity"); };
  const watch = (device?: string) => { if (device) setAvd(device); if (mobile) setTab("Phone"); };
  const showMe = (goal: string, device?: string) => { if (device && leases[device]) setAvd(device); setTeachAsk({ goal }); setTab("Phone"); };
  // The task a phone is busy with: its lease's, else an active task on it (leases are refreshed every 10 s).
  const phoneTask = (d: string): Task | undefined => {
    const own = tasks[leases[d]?.task_id ?? ""];
    return own && ACTIVE.includes(own.status) ? own : taskList.find((t) => t.device === d && ACTIVE.includes(t.status));
  };
  const busy = (d: string) => !!phoneTask(d) || !!leases[d]?.user_control || !!leases[d]?.teach;
  // Teach a new routine (Routines): an empty "Show Envoy once" form, on an idle emulator if this phone is busy. With none
  // free, the phone says it's busy and the form opens when it's free.
  const teachNew = () => showMe("", busy(avd) ? phones.find((d) => d.kind !== "phone" && d.running !== false && !busy(d.avd))?.avd : undefined);

  if (authed === null) return <main className="h-[100dvh] bg-page" />;
  if (authed === false) return <Pair onPaired={load} />;

  const reviewed = reviewing ? tasks[approvals[reviewing]?.task_id ?? ""]?.device : undefined;
  const current = phoneTask(avd);
  const sheet = (reviewing && <ApprovalSheet id={reviewing} onClose={() => setReviewing(null)} device={reviewed ? leases[reviewed]?.name ?? reviewed : undefined} />)
    || (asking && <OfferSheet id={asking} onClose={() => setAsking(null)} openTask={openTaskTab} />);
  const phoneView = (
    <div className="flex flex-col gap-3">
      <PhoneSwitch phones={phones} avd={avd} onChange={setAvd} />
      <LivePhone key={avd} avd={avd} lease={leases[avd]} needsYou={needs ? needs.detail ?? "Envoy needs you" : null} mobile={mobile} teachAsk={teachAsk}
                 task={current} steps={current ? steps[current.id] : undefined} openTask={openTaskTab}
                 ended={(id) => !!tasks[id] && !ACTIVE.includes(tasks[id].status)} />
    </div>
  );
  const content = (
    <>
      <div hidden={tab !== "Home"} className="h-full">
        <Home tasks={tasks} openTask={openTaskTab} review={setReviewing} mood={mood} connected={connected} version={briefVersion} compact={mobile}
              onListening={setListening} goPhone={() => go("Phone")} device={leases[avd]} watch={watch} />
      </div>
      {tab === "Activity" && <Activity tasks={taskList} all={tasks} steps={steps} approvals={Object.values(approvals)} openTask={openTask} setOpenTask={setOpenTask}
                                       review={setReviewing} watch={watch} leases={leases} mood={mood} goPhone={() => go("Phone")} version={briefVersion}
                                       showMe={showMe} />}
      {tab === "Phone" && <div className="mx-auto w-full max-w-[520px] p-4 md:pt-8">{phoneView}</div>}
      {tab === "Memory" && <MemoryGraph version={memVersion} mobile={mobile} />}
      {tab === "Routines" && <RoutinesTab openTask={openTaskTab} teach={teachNew} />}
      {tab === "Settings" && <SettingsPage publicUrl={publicUrl} profile={profile} />}
    </>
  );
  const toastEl = toast && (
    <div role="status" key={toast.key} className="ev-toast pointer-events-none fixed inset-x-4 top-[max(64px,calc(env(safe-area-inset-top)+56px))] z-50 mx-auto flex max-w-md items-center gap-3 rounded-card bg-ink px-4 py-3 text-meta text-on-ink shadow-toast md:top-6">
      <Avatar mood="done" size={32} /><span className="min-w-0 flex-1">{toast.text}</span>
    </div>
  );
  const status = <span className="sr-only" role="status">{MOOD_LABEL[mood]}</span>;

  if (mobile) {
    const titled = tab !== "Home";
    return (
      <main className="flex h-[100dvh] flex-col bg-page">
        {tab === "Activity" && openTask ? <div className="h-[env(safe-area-inset-top)] shrink-0" /> : (  /* a task brings its own header */
        <header className="flex h-[calc(56px+env(safe-area-inset-top))] shrink-0 items-center justify-between gap-2 pl-4 pr-3 pt-[env(safe-area-inset-top)]">
          {tab === "Settings" ? (
            <div className="flex items-center gap-1">
              <button onClick={() => go(back)} aria-label={`Back to ${back}`} className="-ml-2 flex h-11 w-11 items-center justify-center rounded-full hover:bg-well"><CaretLeftIcon size={22} /></button>
              <h1 className="text-title font-bold">Settings</h1>
            </div>
          ) : titled ? (
            <div className="flex min-w-0 items-center gap-2.5">
              <Avatar mood={mood} size={30} />
              <h1 className="truncate text-title font-bold">{tab}</h1>
            </div>
          ) : (
            <DevicePill lease={leases[avd]} needsYou={!!needs || !!leases[avd]?.user_control} offline={mood === "offline"} onClick={() => go("Phone")} />
          )}
          {tab !== "Settings" && (
            <button onClick={() => go("Settings")} aria-label="Settings" className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-well">
              <SlidersHorizontalIcon size={22} />
            </button>
          )}
        </header>
        )}
        <div key={tab === "Home" ? "home" : tab} className="ev-fade min-h-0 flex-1 overflow-y-auto">{content}</div>
        <nav aria-label="Envoy" className="grid shrink-0 grid-cols-5 border-t border-line bg-raised px-1 pb-[max(8px,env(safe-area-inset-bottom))] pt-1.5">
          {NAV.map(({ tab: t, icon: I }) => {
            const active = tab === t;
            const dot = (t === "Activity" && waitingOnYou > 0) || (t === "Phone" && (!!needs || !!leases[avd]?.user_control));
            return (
              <button key={t} onClick={() => go(t)} aria-current={active ? "page" : undefined}
                      aria-label={dot ? `${t}, needs you` : t}
                      className={cx("flex h-[52px] flex-col items-center justify-center gap-1 text-tab", active ? "font-bold text-sage-ink" : "font-semibold text-muted")}>
                <span className={cx("relative flex h-7 w-[52px] items-center justify-center rounded-full transition-colors", active && "bg-sage-tint")}>
                  <I size={22} weight={active ? "fill" : "regular"} />
                  {dot && <span className="absolute right-[11px] top-px h-[9px] w-[9px] rounded-full border-2 border-raised bg-apricot" />}
                </span>
                {t}
              </button>
            );
          })}
        </nav>
        {status}{sheet}{toastEl}
      </main>
    );
  }

  return (
    <main className="flex h-screen bg-page">
      <nav aria-label="Envoy" className="flex w-[232px] shrink-0 flex-col border-r border-line bg-raised px-3 pb-4 pt-5">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <Avatar mood={mood} size={40} label />
          <Wordmark size={26} />
        </div>
        {NAV.map(({ tab: t, icon: I }) => {
          const active = tab === t;
          const count = t === "Activity" ? waitingOnYou : 0;
          return (
            <button key={t} onClick={() => go(t)} aria-current={active ? "page" : undefined}
                    className={cx("mb-1 flex h-11 items-center gap-3 rounded-full px-3 text-[14px] transition-colors", active ? "bg-sage-tint font-bold text-sage-ink" : "font-semibold text-ink-2 hover:bg-well")}>
              <I size={20} weight={active ? "fill" : "regular"} />
              <span className="flex-1 text-left">{t}</span>
              {count > 0 && <span className="rounded-full bg-apricot-tint px-2 py-0.5 text-meta-2 font-bold text-apricot-ink">{count}<span className="sr-only"> waiting on you</span></span>}
            </button>
          );
        })}
        <div className="flex-1" />
        {profile && <p className="mb-2 px-3 text-meta-2 text-muted">{profile === "demo" ? "Demo memory (SkyLark test data)" : "Your memory"}</p>}
        <button onClick={() => go("Settings")} aria-current={tab === "Settings" ? "page" : undefined}
                className={cx("flex h-11 items-center gap-3 rounded-full px-3 text-[14px] transition-colors", tab === "Settings" ? "bg-sage-tint font-bold text-sage-ink" : "font-semibold text-ink-2 hover:bg-well")}>
          <SlidersHorizontalIcon size={20} weight={tab === "Settings" ? "fill" : "regular"} /> Settings
        </button>
      </nav>
      <section key={tab === "Home" ? "home" : tab} className="ev-fade min-w-0 flex-1 overflow-y-auto">{content}</section>
      {tab !== "Phone" && tab !== "Memory" && (  /* the graph gets the room */
        <aside aria-label="Live phone" className="w-[360px] shrink-0 overflow-y-auto border-l border-line bg-raised p-5">{phoneView}</aside>
      )}
      {status}{sheet}{toastEl}
    </main>
  );
}

function DevicePill({ lease, needsYou, offline, onClick }: { lease?: Lease; needsYou: boolean; offline: boolean; onClick: () => void }) {
  const off = offline || lease?.running === false || (lease?.kind === "phone" && lease.state !== "device");
  const name = lease?.name ?? lease?.avd ?? "No phone";
  return (
    <button onClick={onClick} aria-label={`${name}${off ? ", off" : needsYou ? ", needs you" : lease?.task_id ? ", Envoy is using it" : ""}: open the phone`}
            className="flex h-11 min-w-0 items-center gap-2 rounded-full border border-control bg-surface pl-3 pr-4 text-meta font-semibold">
      <DeviceMobileIcon size={18} className="shrink-0" />
      <span className="truncate">{name}</span>
      <span aria-hidden className={cx("h-2 w-2 shrink-0 rounded-full", off ? "bg-line-strong" : needsYou ? "bg-apricot" : "bg-sage")} />
    </button>
  );
}

