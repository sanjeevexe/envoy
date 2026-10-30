"use client";

// Tasks as they happen. The list (Activity), and one task: what you asked, Envoy's answer with where it remembered
// things from, every step as it streams in (the picture it took, what it did and why, its risk), and what it cost.
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRightIcon, CaretDownIcon, CaretLeftIcon, DeviceMobileIcon, DownloadSimpleIcon, GraphIcon, HandIcon, InfoIcon, KeyIcon,
  LightbulbIcon, ListChecksIcon, LockIcon, ProhibitIcon, RepeatIcon, RobotIcon, ShieldCheckIcon, WarningCircleIcon, type Icon,
} from "@phosphor-icons/react";
import Avatar, { type Mood } from "@/components/Avatar";
import { appIcon, Card, Chip, cx, Done, RowIcon, sentence, Spinner, words } from "@/components/ui";
import { rememberedFrom } from "@/components/Chat";
import { api, ago, Approval, media, post, PreflightLine, Step, Task } from "@/lib/api";

// Cross-app answers: a part is shown under its parent task, by the app it asks.
const APPS: Record<string, string> = {
  "com.skylark.air": "SkyLark", "com.amazon.mShop.android.shopping": "Amazon", "com.target.ui": "Target", "com.starbucks.mobilecard": "Starbucks",
  "com.chipotle.ordering": "Chipotle", "com.dd.doordash": "DoorDash", "com.google.android.gm": "Gmail", "com.google.android.apps.maps": "Google Maps",
  "com.google.android.apps.youtube.music": "YouTube Music", "com.google.android.youtube": "YouTube", "com.android.vending": "Play Store",
  "com.android.chrome": "Chrome", "com.android.settings": "Settings", "com.google.android.calendar": "Calendar", "com.google.android.contacts": "Contacts",
  "com.instagram.android": "Instagram",
};
export const appName = (pkg?: string | null) => (pkg ? APPS[pkg] ?? pkg.split(".").pop() ?? pkg : "an app");

export const ACTIVE = ["queued", "running", "needs_you", "taken_over", "waiting_approval"];
const STATUS: Record<string, { label: string; tone: "sage" | "apricot" | "neutral" }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "sage" },
  needs_you: { label: "Needs you", tone: "apricot" },
  taken_over: { label: "You're in control", tone: "sage" },
  waiting_approval: { label: "Needs your OK", tone: "apricot" },
  done: { label: "Done", tone: "sage" },
  failed: { label: "Didn't finish", tone: "neutral" },
  declined: { label: "Declined", tone: "neutral" },
  stopped: { label: "Stopped", tone: "neutral" },
};

export function StatusChip({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: sentence(status.replace(/_/g, " ")), tone: "neutral" as const };
  return <Chip tone={s.tone} className="shrink-0">{s.label}</Chip>;
}

const source = (t: Task) => t.source.startsWith("trigger:") ? `your trigger “${t.source.slice(8)}”` : t.source === "voice" ? "your voice" : t.source === "mcp" ? "an assistant" : t.source === "siri" ? "Siri" : t.source;

export function TaskList({ tasks, open }: { tasks: Task[]; open: (id: string) => void }) {
  if (!tasks.length) return <p className="px-4 py-6 text-body text-muted">No tasks yet. Ask Envoy something on Home.</p>;
  const ids = new Set(tasks.map((t) => t.id));
  const parts = (pid: string) => tasks.filter((t) => t.parent === pid).sort((a, b) => a.created_at - b.created_at);
  return (
    <ul>
      {tasks.filter((t) => !t.parent || !ids.has(t.parent)).map((t) => (
        <li key={t.id} className="border-b border-divider last:border-b-0">
          <button onClick={() => open(t.id)} className="flex min-h-[64px] w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-raised">
            <RowIcon icon={t.kind === "crossapp" ? ListChecksIcon : t.routine ? RepeatIcon : appIcon(t.app)} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-row font-semibold">{t.goal}</span>
              <span className="mt-0.5 block truncate text-meta-2 text-muted">
                {ago(t.created_at)} · from {source(t)}{t.routine ? " · a routine" : t.kind === "crossapp" ? " · several apps" : ""}{t.result ? ` · ${t.result}` : ""}
              </span>
            </span>
            <StatusChip status={t.status} />
          </button>
          {t.kind === "crossapp" && parts(t.id).map((p) => (
            <button key={p.id} onClick={() => open(p.id)} className="flex min-h-[48px] w-full items-center gap-3 py-2 pl-[64px] pr-4 text-left hover:bg-raised">
              <span className="min-w-0 flex-1 truncate text-meta-2 text-muted">
                <span className="font-bold text-ink-2">{appName(p.app)}</span> · {p.device ?? "waiting for a phone"}{p.result ? ` · ${p.result}` : p.detail ? ` · ${p.detail}` : ""}
              </span>
              <StatusChip status={p.status} />
            </button>
          ))}
        </li>
      ))}
    </ul>
  );
}

// The parts of a cross-app task, each with its own live status (from the page's task events).
function Parts({ id, all, open }: { id: string; all?: Record<string, Task>; open?: (id: string) => void }) {
  const [fetched, setFetched] = useState<Task[]>([]);
  useEffect(() => { if (!all) api("/api/tasks?limit=100").then((ts: Task[]) => setFetched(ts.filter((t) => t.parent === id))).catch(() => {}); }, [id, all]);
  const parts = (all ? Object.values(all).filter((t) => t.parent === id) : fetched).sort((a, b) => a.created_at - b.created_at);
  if (!parts.length) return null;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {parts.map((p) => (
        <button key={p.id} onClick={() => open?.(p.id)} className="rounded-block border border-line bg-surface p-4 text-left hover:border-line-strong">
          <span className="flex items-center justify-between gap-2">
            <span className="text-body font-bold">{appName(p.app)}</span><StatusChip status={p.status} />
          </span>
          <span className="mt-1 block text-meta-2 text-muted">{p.device ?? "waiting for a phone"}{p.routine ? " · a routine" : ""}</span>
          <span className="mt-1 block text-row">{p.result || p.detail || p.goal}</span>
        </button>
      ))}
    </div>
  );
}

// ---- one task -------------------------------------------------------------------------------------------------------

const secs = (s: number) => (s < 60 ? `${Math.max(1, Math.round(s))} s` : `${Math.floor(s / 60)} min${Math.round(s % 60) ? ` ${Math.round(s % 60)} s` : ""}`);
const usd = (v?: number) => (!v ? "$0" : v < 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(2)}`);

// What Envoy says about the task, in its own voice.
function reply(t: Task): string {
  switch (t.status) {
    case "queued": case "running": return "On it.";
    case "waiting_approval": return "I need your OK before I go on.";
    case "needs_you": return t.detail ? `I need you: ${t.detail}.`.replace(/\.\.$/, ".") : "I need you on the phone.";
    case "taken_over": return "You're in control. I'll wait until you hand it back.";
    case "done": return "Done.";
    case "failed": return t.detail ? `That didn't work: ${t.detail}` : "That didn't work.";
    case "declined": return "Declined, so I stopped there.";
    case "stopped": return "Stopped.";
  }
  return sentence(t.status);
}
const taskMood = (t: Task, fresh: boolean): Mood =>
  t.status === "running" ? (fresh ? "working" : "thinking") : t.status === "queued" ? "thinking" : ["needs_you", "waiting_approval"].includes(t.status) ? "needs" : "idle";

// "seat: 14C; gate: B12" → pairs; anything else stays a sentence.
function Result({ text }: { text: string }) {
  const pairs = text.split(/;\s*/).map((p) => p.match(/^([\w ]{1,40}):\s*(.+)$/));
  if (pairs.length > 1 && pairs.every(Boolean)) {
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-block border border-line bg-surface px-4 py-3 text-row">
        {pairs.map((m, i) => <div key={i} className="contents"><dt className="text-meta text-muted">{sentence(m![1])}</dt><dd className="font-semibold">{m![2]}</dd></div>)}
      </dl>
    );
  }
  return <p className="font-serif text-voice-2">{text}</p>;
}

type Line = { s: Step; icon: "done" | "spin" | Icon; tone?: "sage" | "apricot" | "neutral"; text: string; quiet?: boolean };
// Steps are recorded once they're done; a routine step still in progress says so ("running").
function line(s: Step): Line | null {
  const text = s.text ?? "";
  switch (s.kind) {
    case "plan": case "replan": return { s, icon: ListChecksIcon, tone: "neutral", text: `Plan: ${text}`, quiet: true };
    case "action": return { s, icon: s.error ? WarningCircleIcon : "done", tone: s.error ? "apricot" : undefined, text: sentence(text) };
    case "routine_step":
      if (s.status === "skipped") return { s, icon: InfoIcon, tone: "neutral", text: `${words(text)} (skipped)`, quiet: true };
      if (s.status === "failed") return { s, icon: WarningCircleIcon, tone: "apricot", text: words(text) };
      return { s, icon: s.status === "running" ? "spin" : "done", text: words(text) };
    case "memory": return { s, icon: GraphIcon, tone: "sage", text: "Saved what it saw to memory" };
    case "change": return { s, icon: GraphIcon, tone: "apricot", text };
    case "approval": return { s, icon: ShieldCheckIcon, tone: "sage", text };
    case "handoff": return { s, icon: HandIcon, tone: "apricot", text: sentence(text) };
    case "popup": return { s, icon: InfoIcon, tone: "neutral", text: sentence(text), quiet: true };
    case "error": return { s, icon: WarningCircleIcon, tone: "apricot", text: sentence(s.error ?? text) };
    case "finish": return null;
    case "preflight": return null; // shown as the Before I start card
    case "note": return text.startsWith("using routine") ? null : { s, icon: InfoIcon, tone: "neutral", text: sentence(text), quiet: true };
  }
  return { s, icon: InfoIcon, tone: "neutral", text: sentence(text || s.kind), quiet: true };
}

// Before I start (api/preflight.py): what to expect, said before the task runs. Warnings in apricot, a stop in brick.
// Also for an offer's card, before its Yes.
const PREFLIGHT_ICON: Record<PreflightLine["kind"], Icon> = {
  device: DeviceMobileIcon, blocked: ProhibitIcon, memory: GraphIcon, install: DownloadSimpleIcon, signin: KeyIcon, approval: ShieldCheckIcon,
  routine: RepeatIcon, app_note: LightbulbIcon,
};

export function BeforeIStart({ lines, className }: { lines: PreflightLine[]; className?: string }) {
  if (!lines.length) return null;
  return (
    <section aria-label="Before I start" className={cx("flex items-start gap-2.5", className)}>
      <Avatar mood="thinking" size={36} />
      <Card className="min-w-0 flex-1 px-4 pb-3 pt-2.5">
        <h3 className="text-meta font-bold text-muted">Before I start</h3>
        <ul className="mt-1.5 flex flex-col gap-2">
          {lines.map((l, i) => {
            const I = PREFLIGHT_ICON[l.kind] ?? InfoIcon;
            return (
              <li key={i} className="flex items-start gap-2.5">
                {l.level === "stop"
                  ? <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brick text-white"><I size={13} /></span>
                  : <RowIcon icon={I} tone={l.level === "warn" ? "apricot" : "neutral"} size={24} />}
                <span className={cx("min-w-0 pt-0.5 text-row [overflow-wrap:anywhere]",
                  l.level === "stop" ? "font-semibold text-brick" : l.level === "warn" ? "text-apricot-ink" : "text-ink-2")}>{l.text}</span>
              </li>
            );
          })}
        </ul>
      </Card>
    </section>
  );
}

const RISK: Record<string, string> = { read: "Only reads", reversible: "Can be undone", irreversible: "Can't be undone" };

function StepRow({ l, isNew }: { l: Line; isNew: boolean }) {
  const [open, setOpen] = useState(false);
  const s = l.s;
  const more = !!(s.shot || s.reason || s.risk || s.detail || s.approval || s.error || s.entities?.length || (s.sources && Object.keys(s.sources).length)
    || s.kind === "change");
  const mark = l.icon === "done" ? <Done /> : l.icon === "spin" ? <Spinner /> : <RowIcon icon={l.icon} tone={l.tone} size={24} />;
  const head = (
    <>
      {mark}
      <span className={cx("min-w-0 flex-1 text-row [overflow-wrap:anywhere]", l.icon === "spin" && "font-bold", l.quiet && "text-ink-2")}>{l.text}</span>
      {l.icon === "spin" ? <span className="shrink-0 text-meta-2 text-muted">now</span> : s.risk === "irreversible" ? <span className="h-2 w-2 shrink-0 rounded-full bg-brick" title="Can't be undone" /> : null}
      {more && <CaretDownIcon size={16} className={cx("shrink-0 text-muted transition-transform", open && "rotate-180")} />}
    </>
  );
  return (
    <li className={cx(isNew && "ev-step")}>
      {more ? (
        <button onClick={() => setOpen(!open)} aria-expanded={open} className="-mx-2 flex min-h-[44px] w-[calc(100%+16px)] items-center gap-3 rounded-sm px-2 py-1.5 text-left hover:bg-raised">{head}</button>
      ) : <div className="flex min-h-[40px] items-center gap-3 py-1.5">{head}</div>}
      {open && (
        <div className="ev-fade mb-2 ml-9 flex gap-3 rounded-block bg-raised p-3">
          {s.shot && <a href={media(`/api/shots/${s.shot}`)} target="_blank" rel="noreferrer" className="shrink-0">
            <img src={media(`/api/shots/${s.shot}`)} alt="The phone's screen at this step" className="h-36 w-[66px] rounded-sm border border-line object-cover object-top" /></a>}
          <div className="min-w-0 space-y-1 text-meta">
            {s.reason && <p className="text-ink-2">{sentence(s.reason)}</p>}
            {s.risk && <p className={cx("font-semibold", s.risk === "irreversible" ? "text-brick" : "text-muted")}>{RISK[s.risk] ?? s.risk}</p>}
            {s.kind === "routine_step" && <p className="text-muted">{s.rung ? `Needed help: ${s.detail || `rung ${s.rung}`}` : s.detail || "A clean replay, no model call"}</p>}
            {s.approval && <p className="text-muted">{s.approval.approved ? "Approved" : "Not approved"} by {s.approval.by}</p>}
            {s.kind === "change" && <p className="text-muted">{s.entity_label}{s.source ? ` · seen in ${s.source}` : ""} · {s.pushed ? `sent to your devices${s.alerted_for ? ` (for “${s.alerted_for}”)` : ""}` : `not sent: ${s.why_not}`}</p>}
            {s.entities?.length ? <p className="text-muted">{s.entities.join(" · ")}</p> : null}
            {s.sources && Object.entries(s.sources).map(([k, v]) => <p key={k} className="text-muted">{k.replace(/_/g, " ")}: {rememberedFrom(v)}</p>)}
            {s.error && <p className="text-apricot-ink">{s.error}</p>}
            {s.kind === "memory" && <p className="text-muted">{sentence(s.text ?? "")}</p>}
            <p className="text-meta-2 text-muted">{new Date(s.time * 1000).toLocaleTimeString()}</p>
          </div>
        </div>
      )}
    </li>
  );
}

export function TaskDetail({ id, task, liveSteps, back, all, open, review, watch, deviceName }: {
  id: string; task?: Task; liveSteps: Step[]; back: () => void; all?: Record<string, Task>; open?: (id: string) => void;
  review?: (approvalId: string) => void; watch?: (device?: string) => void; deviceName?: (avd?: string) => string | undefined;
}) {
  const [data, setData] = useState<{ task: Task; steps: Step[]; approvals: Approval[] } | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const seen = useRef<Set<number> | null>(null); // the steps already there when the page opened (the rest animate in)
  useEffect(() => { api(`/api/tasks/${id}`).then(setData).catch(() => setData(null)); }, [id, task?.status, liveSteps.length]);
  const t = task ?? data?.task;
  const active = !!t && ACTIVE.includes(t.status);
  useEffect(() => {
    if (!active) return;
    const i = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(i);
  }, [active]);
  if (!t) return <div className="p-4"><BackButton back={back} /><p className="p-2 text-body text-muted">Loading…</p></div>;

  // the stored steps, plus any that streamed in since they were fetched
  const stored = data?.steps ?? [];
  const steps = [...stored, ...liveSteps.filter((s) => s.seq > (stored[stored.length - 1]?.seq ?? 0))];
  if (seen.current === null && data) seen.current = new Set(steps.map((s) => s.seq));
  const lines = steps.map(line).filter(Boolean) as Line[];
  if (t.status === "running" && !lines.some((l) => l.icon === "spin")) {  // what it's doing now isn't a step yet
    lines.push({ s: { seq: -1, time: now, kind: "now" }, icon: "spin", text: "Looking at the screen" });
  }
  const pendingApprovals = (data?.approvals ?? []).filter((a) => a.status === "pending");
  const decided = (data?.approvals ?? []).filter((a) => a.status !== "pending");
  const remembered = steps.flatMap((s) => Object.values(s.sources ?? {})).map(rememberedFrom);
  const routineNote = steps.find((s) => s.kind === "note" && s.text?.startsWith("using routine"))?.text?.match(/ v(\d+)/)?.[1];
  const preflight = steps.find((s) => s.kind === "preflight")?.lines ?? [];
  const lastStepAt = steps.length ? steps[steps.length - 1].time : 0;
  const elapsed = (active ? now : t.updated_at) - t.created_at;
  const device = deviceName?.(t.device) ?? t.device;
  const status = active
    ? t.status === "running" || t.status === "queued" ? <><Spinner size={12} stroke={4} /> {t.device ? `Working on ${t.device.startsWith("envoy") ? "the" : "your"} ${device}` : "Getting a phone ready"}</>
      : t.status === "taken_over" ? <>You&rsquo;re in control of {device}</> : <span className="text-apricot-ink">{t.status === "waiting_approval" ? "Waiting for your OK" : "Waiting for you"}</span>
    : <span className="text-muted">{STATUS[t.status]?.label ?? t.status} · {ago(t.updated_at)}</span>;
  const fromYou = !t.source.startsWith("trigger:");

  return (
    <div className="flex min-h-full flex-col">
      <div className="sticky top-0 z-10 border-b border-line bg-page/95 backdrop-blur">
       <div className="mx-auto flex min-h-[68px] w-full max-w-[740px] items-center gap-1 py-2 pl-1.5 pr-3 md:pl-2">
        <BackButton back={back} />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-title font-bold">{t.goal}</h2>
          <div className="mt-0.5 flex items-center gap-1.5 text-meta-2 font-semibold text-sage-ink">{status}</div>
        </div>
        {active && (
          <button onClick={() => post(`/api/tasks/${id}/stop`)} className="flex h-11 shrink-0 items-center gap-1.5 rounded-full border border-control bg-surface px-4 text-meta font-bold hover:border-line-strong">
            <span aria-hidden className="h-2.5 w-2.5 rounded-[2.5px] bg-ink" /> Stop
          </button>
        )}
       </div>
      </div>

      <div className="mx-auto flex w-full max-w-[680px] flex-1 flex-col gap-4 px-4 pb-8 pt-5">
        {fromYou ? (
          <div className="ev-rise max-w-[78%] self-end rounded-[20px_20px_6px_20px] bg-ink px-4 py-3 text-body text-on-ink [overflow-wrap:anywhere]">{t.request ?? t.goal}</div>
        ) : <p className="ev-rise text-meta text-muted">Started by {source(t)}</p>}
        {t.parent && <button onClick={() => open?.(t.parent!)} className="flex h-11 items-center gap-1 self-start text-meta font-bold text-sage-ink">Part of a question across apps <ArrowUpRightIcon size={14} /></button>}
        <BeforeIStart lines={preflight} className="ev-rise ev-r2" />

        <div className="ev-rise ev-r2 flex items-start gap-2.5">
          <Avatar mood={taskMood(t, now - lastStepAt < 1.5)} size={44} />
          <div className="flex min-w-0 flex-1 flex-col gap-2 pt-1.5">
            <p className="font-serif text-voice-2">{reply(t)}</p>
            {t.result && <Result text={t.result} />}
            {t.kind === "crossapp" && t.status === "done" && t.detail && <p className="font-serif text-voice-2">{t.detail}</p>}
            {remembered.length > 0 && (
              <span className="flex flex-wrap gap-1.5">{[...new Set(remembered)].map((r) => <Chip key={r} icon={GraphIcon}>Remembered from {r}</Chip>)}</span>
            )}
          </div>
        </div>

        {t.kind === "crossapp" && <Parts id={id} all={all} open={open} />}

        {(lines.length > 0 || pendingApprovals.length > 0) && (
          <Card className="ev-rise ev-r3 pb-3 pl-4 pr-2 pt-2">
            <div className="flex items-center justify-between">
              <h3 className="text-body font-bold">{t.routine ? "Routine steps" : t.kind === "agent" ? "What I did" : "Steps"}</h3>
              {t.device && watch && active && (
                <button onClick={() => watch(t.device)} className="flex h-11 items-center gap-1.5 rounded-full px-3 text-meta font-bold text-sage-ink hover:bg-sage-tint/60">
                  <DeviceMobileIcon size={16} /> Watch live
                </button>
              )}
            </div>
            <ol className="flex flex-col pr-2" aria-label="Steps" aria-live="polite">
              {lines.map((l) => <StepRow key={l.s.seq} l={l} isNew={!!seen.current && !seen.current.has(l.s.seq)} />)}
              {pendingApprovals.map((a) => (
                <li key={a.id} className="ev-step">
                  <button onClick={() => review?.(a.id)} className="flex min-h-[44px] w-full items-center gap-3 text-left">
                    <RowIcon icon={LockIcon} tone="apricot" size={24} />
                    <span className="min-w-0 flex-1 truncate text-row text-ink-2">{a.description}</span>
                    <Chip tone="apricot" className="text-[12px] font-bold">Needs your OK</Chip>
                  </button>
                </li>
              ))}
            </ol>
            {decided.length > 0 && (
              <ul className="mt-1 border-t border-divider pt-2 text-meta text-muted">
                {decided.map((a) => (
                  <li key={a.id} className="flex min-h-[32px] items-center gap-2">
                    <ShieldCheckIcon size={16} className="shrink-0" />
                    <span className="min-w-0 [overflow-wrap:anywhere]">{a.description}: {a.status}{a.decided_by ? ` by ${a.decided_by}` : ""}{a.note ? ` (${a.note})` : ""}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mr-2 mt-2 flex items-center gap-2 border-t border-divider pt-3 text-meta-2 text-muted">
              {t.routine ? <RepeatIcon size={14} className="shrink-0" /> : <RobotIcon size={14} className="shrink-0" />}
              <span>
                {t.routine ? `Routine${routineNote ? ` v${routineNote}` : ""}` : t.kind === "crossapp" ? "Across apps" : "The agent"} · {t.model_calls ?? 0} model call{t.model_calls === 1 ? "" : "s"} · {usd(t.cost_usd)} · {secs(Math.max(0, elapsed))}{active ? " so far" : ""}
              </span>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function BackButton({ back }: { back: () => void }) {
  return (
    <button onClick={back} aria-label="Back to activity" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full hover:bg-well">
      <CaretLeftIcon size={22} />
    </button>
  );
}
