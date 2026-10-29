"use client";

// Tasks that start on their own: at a time, before a flight (moving if it's delayed), on a watch, on new email, or when
// a remembered fact changes. What a trigger runs is fixed here by you; memory, emails and changes only fill in typed
// values. A watcher pushes when its run changed a fact it watches ("Gate changed: B12 → C14"); otherwise it's quiet.
// Each trigger can ask you first ("Check in for SL 482?", a card with Yes) or just do it. The presets are in
// lib/trigger-presets.json, which a backend test renders against the demo's values.
import { useEffect, useState } from "react";
import {
  BellRingingIcon, BellSlashIcon, ChatCircleDotsIcon, ClockIcon, EnvelopeSimpleIcon, EyeIcon, GraphIcon, PauseIcon, PlayIcon, PlusIcon, TrashIcon, type Icon,
} from "@phosphor-icons/react";
import { Button, Card, clock, cx, RowIcon, SectionLabel, Segmented } from "@/components/ui";
import { ago, api, post } from "@/lib/api";
import PRESETS from "@/lib/trigger-presets.json";

const KIND: Record<string, Icon> = { time: ClockIcon, before_fact: ClockIcon, watch: EyeIcon, email: EnvelopeSimpleIcon, fact_changed: GraphIcon };

type Trig = {
  id: string; kind: string; name: string; spec: any; action: any; enabled: boolean; last_fired: number | null;
  next: { at: number; for?: string }[]; alerts?: { on: boolean; attributes: string[] };
};
type Change = {
  id: number; time: number; task_id: string; entity_label: string; attribute: string; old: string; new: string; title: string;
  pushed: number; why_not: string | null;
};

const ASK = ["Ask me first", "Just do it"] as const;

export default function Triggers() {
  const [list, setList] = useState<Trig[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const [json, setJson] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    api("/api/triggers").then(setList).catch(() => {});
    api("/api/alerts?limit=8").then(setChanges).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const add = async (body: any) => {
    setErr(null);
    try { await post("/api/triggers", body); load(); } catch (e: any) { setErr(e.message); }
  };
  const control = "flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-control bg-surface hover:border-line-strong";
  return (
    <div className="ev-rise flex flex-col gap-2">
      <p className="px-6 pb-2 pt-3 text-meta text-ink-2">
        Tasks that start on their own: at a time, before a flight (moving if it&rsquo;s delayed), on a watch, on new email, or when something Envoy remembers changes.
        What a trigger runs is fixed here by you; memory and emails only fill in its values.
      </p>
      <Card className="mx-4 overflow-hidden">
        {list.length === 0 && <p className="px-4 py-6 text-body text-muted">No triggers yet. Add one below.</p>}
        {list.map((t) => (
          <div key={t.id} className={cx("flex items-start gap-3 border-b border-divider py-3 pl-4 pr-3 last:border-b-0", !t.enabled && "opacity-70")}>
            <span className="pt-0.5"><RowIcon icon={KIND[t.kind] ?? ClockIcon} tone={t.enabled ? "sage" : "neutral"} /></span>
            <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-start">
            <div className="min-w-0 flex-1">
              <div className="text-row font-semibold [overflow-wrap:anywhere]">{t.name}{!t.enabled && <span className="font-normal text-muted"> · paused</span>}</div>
              <div className="mt-0.5 text-meta-2 text-muted [overflow-wrap:anywhere]">{t.action.ask ? "Asks, then runs" : "Runs"} {t.action.goal ? `“${t.action.goal}”` : `the routine ${t.action.routine}`}</div>
              <div className="text-meta-2 text-muted">
                {t.kind === "fact_changed" ? `When ${t.spec.entity_type.toLowerCase()} ${(t.spec.attributes ?? [t.spec.attribute]).join(" or ").replace(/_/g, " ")} changes`
                  : t.next.length ? `Next ${t.next.map((n) => `${clock(n.at)}${n.for ? ` (${n.for})` : ""}`).join(", ")}` : "Nothing coming up"}
              </div>
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
              <div className="mt-2">
                <Segmented options={ASK} value={t.action.ask ? ASK[0] : ASK[1]} label={`When ${t.name} fires`}
                           onChange={(v) => post(`/api/triggers/${t.id}`, { ask: v === ASK[0] }).then(load).catch((e) => setErr(e.message))} />
              </div>
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
      <details className="mx-4 mt-1 rounded-block border border-line bg-surface px-4">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-meta font-semibold text-ink-2">Write one yourself (JSON)</summary>
        <textarea value={json} onChange={(e) => setJson(e.target.value)} rows={6} aria-label="Trigger as JSON"
                  placeholder='{"kind": "time", "name": "Sunday coupons", "spec": {"weekly_on": {"days": ["sun"], "at": "9:00"}}, "action": {"goal": "...", "ask": true}}'
                  className="w-full rounded-sm border border-control bg-raised p-3 font-mono text-meta-2 outline-none focus:border-sage" />
        <Button variant="primary" className="mb-4 mt-2" onClick={() => { try { add(JSON.parse(json)); } catch { setErr("That isn't valid JSON"); } }}>Add</Button>
      </details>
      {err && <p role="alert" className="mx-4 rounded-block bg-apricot-tint px-4 py-2.5 text-meta text-apricot-ink">{err}</p>}

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
