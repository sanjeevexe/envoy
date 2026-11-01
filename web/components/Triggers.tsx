"use client";

// Tasks that start on their own: at a time, before a flight (moving if it's delayed), on a watch, on new email, or when
// a remembered fact changes, or when an app notifies Envoy's phone (the apps you let Envoy watch, Settings › Phones). What a
// trigger runs is fixed here by you; memory, emails, changes and notifications only fill in typed values. A watcher pushes
// when its run changed a fact it watches ("Gate changed: B12 → C14"); otherwise it's quiet. A notification trigger can
// just tell you (a push) and your assistants (phone_updates), and what it caught is listed below, codes hidden.
// Each trigger can ask you first ("Check in for SL 482?", a card with Yes) or just do it. The presets are in
// lib/trigger-presets.json, which a backend test renders against the demo's values.
import { useEffect, useState } from "react";
import {
  BellRingingIcon, BellSimpleIcon, BellSimpleRingingIcon, BellSlashIcon, ChatCircleDotsIcon, ClockIcon, EnvelopeSimpleIcon, EyeIcon, GraphIcon, PauseIcon, PlayIcon,
  PlusIcon, TrashIcon, WarningCircleIcon, type Icon,
} from "@phosphor-icons/react";
import { watchingLine } from "@/components/NotificationWatch";
import { appName } from "@/components/Tasks";
import { Button, Card, clock, cx, RowIcon, SectionLabel, Segmented } from "@/components/ui";
import { ago, api, post, type NotificationEvent, type WatchSettings } from "@/lib/api";
import PRESETS from "@/lib/trigger-presets.json";

const KIND: Record<string, Icon> = { time: ClockIcon, before_fact: ClockIcon, watch: EyeIcon, email: EnvelopeSimpleIcon, fact_changed: GraphIcon, notification: BellSimpleIcon };

type Trig = {
  id: string; kind: string; name: string; spec: any; action: any; enabled: boolean; last_fired: number | null;
  next: { at: number; for?: string }[]; alerts?: { on: boolean; attributes: string[] };
};
type Change = {
  id: number; time: number; task_id: string; entity_label: string; attribute: string; old: string; new: string; title: string;
  pushed: number; why_not: string | null;
};

const ASK = ["Ask me first", "Just do it"] as const;

// A notification trigger's apps (one package or a list) and when it fires, as api/notifications.py's describe() says it.
const appsOf = (spec: any): string[] => (Array.isArray(spec?.package) ? spec.package : spec?.package ? [spec.package] : []);
const orList = (xs: string[]) => (xs.length > 2 ? `${xs.slice(0, -1).join(", ")} or ${xs[xs.length - 1]}` : xs.join(" or "));
function whenNotified(spec: any, names: Record<string, string>): string {
  const about = [spec.contains && `with \u201c${spec.contains}\u201d`, spec.title_contains && `titled \u201c${spec.title_contains}\u201d`,
    spec.text_contains && `saying \u201c${spec.text_contains}\u201d`].filter(Boolean);
  const phone = !spec.phone ? "Envoy\u2019s phone" : spec.phone === "envoy-test" ? "the test phone" : spec.phone;
  return `When ${orList(appsOf(spec).map((p) => names[p] ?? appName(p))) || "an app"} notifies ${phone}${about.length ? ` ${about.join(" and ")}` : ""}`;
}
const runs = (a: any) => !!(a?.goal || a?.routine);
// "Instagram: maya.makes", or just "TikTok" when the app's title is its own name (as the push says it).
export const caughtTitle = (n: { app: string; title?: string }) =>
  (n.title && n.title.toLowerCase() !== n.app.toLowerCase() ? `${n.app}: ${n.title}` : n.app);

// `focus`: a trigger to show (a push opened it, ?trigger=…); `version` changes when a notification trigger caught one.
export default function Triggers({ focus, version = 0 }: { focus?: string | null; version?: number }) {
  const [list, setList] = useState<Trig[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const [watch, setWatch] = useState<WatchSettings | null>(null);
  const [caught, setCaught] = useState<NotificationEvent[]>([]);
  const [json, setJson] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const loadCaught = () => { api<{ events: NotificationEvent[] }>("/api/notifications?limit=8").then((r) => setCaught(r.events)).catch(() => {}); };
  const load = () => {
    api("/api/triggers").then(setList).catch(() => {});
    api("/api/alerts?limit=8").then(setChanges).catch(() => {});
    api<WatchSettings>("/api/settings/notifications").then(setWatch).catch(() => {});
    loadCaught();
  };
  useEffect(() => { load(); }, []);
  useEffect(() => { if (version) loadCaught(); }, [version]);
  useEffect(() => {
    if (focus && list.some((t) => t.id === focus)) document.getElementById(`trigger-${focus}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focus, list]);
  const names = Object.fromEntries((watch?.apps ?? []).map((a) => [a.package, a.name]));
  const add = async (body: any) => {
    setErr(null);
    try { await post("/api/triggers", body); load(); return true; } catch (e: any) { setErr(e.message); return false; }
  };
  const control = "flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-control bg-surface hover:border-line-strong";
  return (
    <div className="ev-rise flex flex-col gap-2">
      <p className="px-6 pb-2 pt-3 text-meta text-ink-2">
        Tasks that start on their own: at a time, before a flight (moving if it&rsquo;s delayed), on a watch, on new email, when something Envoy remembers changes,
        or when an app notifies Envoy&rsquo;s phone. What a trigger runs is fixed here by you; memory, emails and notifications only fill in its values.
      </p>
      <Card className="mx-4 overflow-hidden">
        {list.length === 0 && <p className="px-4 py-6 text-body text-muted">No triggers yet. Add one below.</p>}
        {list.map((t) => (
          <div key={t.id} id={`trigger-${t.id}`} className={cx("flex items-start gap-3 border-b border-divider py-3 pl-4 pr-3 last:border-b-0", !t.enabled && "opacity-70",
                                                          focus === t.id && "bg-sage-tint/40")}>
            <span className="pt-0.5"><RowIcon icon={KIND[t.kind] ?? ClockIcon} tone={t.enabled ? "sage" : "neutral"} /></span>
            <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-start">
            <div className="min-w-0 flex-1">
              <div className="text-row font-semibold [overflow-wrap:anywhere]">{t.name}{!t.enabled && <span className="font-normal text-muted"> · paused</span>}</div>
              <div className="mt-0.5 text-meta-2 text-muted [overflow-wrap:anywhere]">
                {!runs(t.action) ? (t.spec.push === false ? "Tells your assistants (no push)" : "Tells you and your assistants")
                  : `${t.action.ask ? "Asks, then runs" : "Runs"} ${t.action.goal ? `“${t.action.goal}”` : `the routine ${t.action.routine}`}`}
              </div>
              <div className="text-meta-2 text-muted [overflow-wrap:anywhere]">
                {t.kind === "fact_changed" ? `When ${t.spec.entity_type.toLowerCase()} ${(t.spec.attributes ?? [t.spec.attribute]).join(" or ").replace(/_/g, " ")} changes`
                  : t.kind === "notification" ? whenNotified(t.spec, names)
                  : t.next.length ? `Next ${t.next.map((n) => `${clock(n.at)}${n.for ? ` (${n.for})` : ""}`).join(", ")}` : "Nothing coming up"}
              </div>
              {t.kind === "notification" && watch && appsOf(t.spec).some((p) => !watch.on.includes(p)) && (
                <div className="mt-1 flex items-start gap-1.5 text-meta-2 font-semibold text-apricot-ink">
                  <WarningCircleIcon size={14} className="mt-0.5 shrink-0" />
                  <span className="[overflow-wrap:anywhere]">Envoy isn&rsquo;t watching {orList(appsOf(t.spec).filter((p) => !watch.on.includes(p)).map((p) => names[p] ?? appName(p)))}: turn it on in Settings &rsaquo; Phones to hear from it.</span>
                </div>
              )}
              {t.alerts && (t.kind === "watch" || t.alerts.on) && (
                <div className={cx("mt-1 flex items-start gap-1.5 text-meta-2 font-semibold", t.alerts.on ? "text-apricot-ink" : "text-muted")}>
                  {t.alerts.on ? <BellRingingIcon size={14} className="mt-0.5 shrink-0" /> : <BellSlashIcon size={14} className="mt-0.5 shrink-0" />}
                  {t.alerts.on ? `Tells you when ${t.alerts.attributes.map((a) => (a === "*" ? "anything" : a.replace(/_/g, " "))).join(", ")} changes` : "Quiet: changes show in the task"}
                </div>
              )}
              {t.action.ask && (
                <div className="mt-1 flex items-start gap-1.5 text-meta-2 font-semibold text-sage-ink">
                  <ChatCircleDotsIcon size={14} className="mt-0.5 shrink-0" />
                  <span className="[overflow-wrap:anywhere]">Asks you first{t.action.offer_title ? `: “${t.action.offer_title}”` : ""}. Nothing runs until you say yes.</span>
                </div>
              )}
              {runs(t.action) && (
                <div className="mt-2">
                  <Segmented options={ASK} value={t.action.ask ? ASK[0] : ASK[1]} label={`When ${t.name} fires`}
                             onChange={(v) => post(`/api/triggers/${t.id}`, { ask: v === ASK[0] }).then(load).catch((e) => setErr(e.message))} />
                </div>
              )}
            </div>
            <div className="flex shrink-0 gap-1.5">
              {t.kind === "watch" && t.alerts && (
                <button onClick={() => post(`/api/triggers/${t.id}`, { alert: !t.alerts!.on }).then(load)} className={control}
                        aria-label={t.alerts.on ? `Turn off alerts for ${t.name}` : `Turn on alerts for ${t.name}`} title={t.alerts.on ? "Turn alerts off" : "Turn alerts on"}>
                  {t.alerts.on ? <BellSlashIcon size={18} /> : <BellRingingIcon size={18} />}
                </button>
              )}
              <button onClick={() => post(`/api/triggers/${t.id}`, { enabled: !t.enabled }).then(load)} className={control}
                      aria-label={t.enabled ? `Pause ${t.name}` : `Resume ${t.name}`} title={t.enabled ? "Pause" : "Resume"}>
                {t.enabled ? <PauseIcon size={18} /> : <PlayIcon size={18} />}
              </button>
              <button onClick={() => api(`/api/triggers/${t.id}`, { method: "DELETE" }).then(load)} className={control} aria-label={`Delete ${t.name}`} title="Delete">
                <TrashIcon size={18} />
              </button>
            </div>
            </div>
          </div>
        ))}
      </Card>

      <SectionLabel className="px-6 pb-0.5 pt-5">Add a trigger</SectionLabel>
      <div className="flex flex-wrap gap-2 px-4">
        {PRESETS.map((p) => (
          <button key={p.label} onClick={() => add(p.body)} className="flex min-h-[44px] items-center gap-2 rounded-block border border-control bg-surface px-4 py-2 text-left text-meta font-semibold hover:border-line-strong">
            <PlusIcon size={16} className="shrink-0 text-sage-ink" />{p.label}
          </button>
        ))}
      </div>
      <NotificationForm watch={watch} add={add} />
      <details className="mx-4 mt-1 rounded-block border border-line bg-surface px-4">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-meta font-semibold text-ink-2">Write one yourself (JSON)</summary>
        <textarea value={json} onChange={(e) => setJson(e.target.value)} rows={6} aria-label="Trigger as JSON"
                  placeholder='{"kind": "time", "name": "Sunday coupons", "spec": {"weekly_on": {"days": ["sun"], "at": "9:00"}}, "action": {"goal": "...", "ask": true}}'
                  className="w-full rounded-sm border border-control bg-raised p-3 font-mono text-meta-2 outline-none focus:border-sage" />
        <Button variant="primary" className="mb-4 mt-2" onClick={() => { try { add(JSON.parse(json)); } catch { setErr("That isn't valid JSON"); } }}>Add</Button>
      </details>
      {err && <p role="alert" className="mx-4 rounded-block bg-apricot-tint px-4 py-2.5 text-meta text-apricot-ink">{err}</p>}

      {caught.length > 0 && (
        <>
          <SectionLabel className="px-6 pb-0.5 pt-5">Caught on Envoy&rsquo;s phone</SectionLabel>
          <Card className="mx-4 overflow-hidden">
            {caught.map((n) => (
              <div key={n.id} className="flex min-h-[60px] items-center gap-3 border-b border-divider px-4 py-3 last:border-b-0">
                <RowIcon icon={BellSimpleRingingIcon} tone="apricot" />
                <span className="min-w-0 flex-1">
                  <span className="block text-row font-semibold [overflow-wrap:anywhere]">{caughtTitle(n)}</span>
                  <span className="mt-0.5 block text-meta-2 text-muted [overflow-wrap:anywhere]">{n.text ? `${n.text} · ` : ""}{ago(n.time)}</span>
                </span>
              </div>
            ))}
          </Card>
          {watch?.watching.map((w) => <p key={w.phone} className="px-6 pt-1 text-meta-2 text-muted">{watchingLine(w, names)}</p>)}
        </>
      )}

      {changes.length > 0 && (
        <>
          <SectionLabel className="px-6 pb-0.5 pt-5">Recent changes</SectionLabel>
          <Card className="mx-4 overflow-hidden">
            {changes.map((c) => (
              <a key={c.id} href={`/?task=${c.task_id}`} className="flex min-h-[60px] items-center gap-3 border-b border-divider px-4 py-3 text-ink last:border-b-0 hover:bg-raised hover:text-ink">
                <RowIcon icon={GraphIcon} tone="apricot" />
                <span className="min-w-0 flex-1">
                  <span className="block text-row font-semibold [overflow-wrap:anywhere]">{c.title}</span>
                  <span className="mt-0.5 block text-meta-2 text-muted">{c.entity_label} · {ago(c.time)} · {c.pushed ? "sent to your devices" : `not sent: ${c.why_not}`}</span>
                </span>
              </a>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}

// "When an app notifies Envoy's phone": the apps you let Envoy watch (Settings › Phones), words to look for, and what to do.
const THEN = ["Just tell me", "Ask me first"] as const;

function NotificationForm({ watch, add }: { watch: WatchSettings | null; add: (body: any) => Promise<boolean> }) {
  const on = (watch?.apps ?? []).filter((a) => a.on);
  const [apps, setApps] = useState<string[] | null>(null);  // null: every watched app, until you pick
  const [contains, setContains] = useState("");
  const [then, setThen] = useState<(typeof THEN)[number]>(THEN[0]);
  const [goal, setGoal] = useState("");
  if (!watch) return null;
  const field = "h-11 w-full rounded-full border border-control bg-surface px-4 text-meta outline-none focus:border-sage";
  const box = "mx-4 mt-2 flex flex-col gap-3 rounded-block border border-line bg-surface px-4 py-4";
  if (!on.length) {
    return (
      <div className={box}>
        <span className="flex items-center gap-2 text-meta font-semibold"><BellSimpleIcon size={16} className="text-sage-ink" />When an app notifies Envoy&rsquo;s phone</span>
        <p className="text-meta-2 text-muted">Turn on the apps Envoy may watch in Settings &rsaquo; Phones &rsaquo; Watch notifications first.</p>
      </div>
    );
  }
  const picked = apps ?? on.map((a) => a.package);
  const name = (p: string) => on.find((a) => a.package === p)?.name ?? appName(p);
  const flip = (p: string) => setApps(picked.includes(p) ? picked.filter((x) => x !== p) : [...picked, p]);
  const ok = picked.length > 0 && (then === THEN[0] || goal.trim().length > 0);
  const submit = async () => {
    const words = contains.trim();
    const done = await add({
      kind: "notification", name: `${orList(picked.map(name))}${words ? `: \u201c${words}\u201d` : " notifications"}`,
      spec: { package: picked.length === 1 ? picked[0] : picked, ...(words ? { contains: words } : {}) },
      action: then === THEN[1] ? { goal: goal.trim(), ask: true } : {},
    });
    if (done) { setContains(""); setGoal(""); setApps(null); setThen(THEN[0]); }
  };
  return (
    <div className={box}>
      <span className="flex items-center gap-2 text-meta font-semibold"><BellSimpleIcon size={16} className="text-sage-ink" />When an app notifies Envoy&rsquo;s phone</span>
      <div role="group" aria-label="Apps" className="flex flex-wrap gap-2">
        {on.map((a) => (
          <button key={a.package} aria-pressed={picked.includes(a.package)} onClick={() => flip(a.package)}
                  className={cx("h-11 rounded-full border px-4 text-meta font-semibold", picked.includes(a.package) ? "border-sage bg-sage-tint text-sage-ink" : "border-control bg-surface text-ink-2")}>
            {a.name}
          </button>
        ))}
      </div>
      <input value={contains} onChange={(e) => setContains(e.target.value)} maxLength={80} placeholder="with the words… (optional, e.g. comment)" aria-label="Words the notification has" className={field} />
      <div><Segmented options={THEN} value={then} onChange={setThen} label="Then" /></div>
      {then === THEN[1] && (
        <input value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={200} placeholder="What should I offer to do? e.g. Open the comments on my latest post"
               aria-label="What Envoy asks to do" className={field} />
      )}
      <p className="text-meta-2 text-muted">
        {then === THEN[0] ? "Envoy tells your iPhone and your assistants (Muse, over MCP) each time, with codes hidden." : "Each time, Envoy asks \u201cShould I\u2026?\u201d and does nothing until you say yes."}
      </p>
      <Button variant="primary" className="self-start" disabled={!ok} onClick={submit}><PlusIcon size={16} />Add</Button>
    </div>
  );
}
