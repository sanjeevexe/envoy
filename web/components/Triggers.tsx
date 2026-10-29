"use client";

// Tasks that start on their own: at a time, before a flight (moving if it's delayed), on a watch, on new email, or when
// a remembered fact changes. What a trigger runs is fixed here by you; memory, emails and changes only fill in typed
// values. A watcher pushes when its run changed a fact it watches ("Gate changed: B12 → C14"); otherwise it's quiet.
import { useEffect, useState } from "react";
import {
  BellRingingIcon, BellSlashIcon, ClockIcon, EnvelopeSimpleIcon, EyeIcon, GraphIcon, PauseIcon, PlayIcon, PlusIcon, TrashIcon, type Icon,
} from "@phosphor-icons/react";
import { Button, Card, Chip, clock, cx, RowIcon, SectionLabel } from "@/components/ui";
import { ago, api, post } from "@/lib/api";

const KIND: Record<string, Icon> = { time: ClockIcon, before_fact: ClockIcon, watch: EyeIcon, email: EnvelopeSimpleIcon, fact_changed: GraphIcon };

type Trig = {
  id: string; kind: string; name: string; spec: any; action: any; enabled: boolean; last_fired: number | null;
  next: { at: number; for?: string }[]; alerts?: { on: boolean; attributes: string[] };
};
type Change = {
  id: number; time: number; task_id: string; entity_label: string; attribute: string; old: string; new: string; title: string;
  pushed: number; why_not: string | null;
};

const PRESETS = [
  { label: "Watch my gate every minute and tell me when it changes", body: { kind: "watch", name: "Watch my gate (alerts)",
    spec: { every_minutes: 1, alert: true }, action: { routine: "skylark_get_flight_gate", inputs_from: {} } } },
  { label: "When my flight's departure time changes, look up its gate", body: { kind: "fact_changed", name: "Departure changed: look up the gate",
    spec: { entity_type: "Flight", attribute: "depart_time" },
    action: { routine: "skylark_get_flight_gate", inputs_from: { trip_city: "trip.destination" }, goal: "My flight {flight.number} now leaves at {change.new}: what's its gate?" } } },
  { label: "Check in 24 h before every flight", body: { kind: "before_fact", name: "Check in 24 h before every flight",
    spec: { entity_type: "Flight", minutes_before: 1440 }, action: { goal: "Check me in for my flight to {trip.destination}" } } },
  { label: "Watch my gate every 10 minutes", body: { kind: "watch", name: "Watch my gate", spec: { every_minutes: 10 },
    action: { routine: "skylark_get_flight_gate", inputs_from: {} } } },
  { label: "New SkyLark booking email: look up its gate", body: { kind: "email", name: "New SkyLark booking",
    spec: { sender_contains: "skylark" }, action: { routine: "skylark_get_flight_gate", inputs_from: { trip_city: "Trip.destination" } } } },
];

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
            <div className="min-w-0 flex-1">
              <div className="text-row font-semibold [overflow-wrap:anywhere]">{t.name}{!t.enabled && <span className="font-normal text-muted"> · paused</span>}</div>
              <div className="mt-0.5 text-meta-2 text-muted [overflow-wrap:anywhere]">Runs {t.action.goal ? `“${t.action.goal}”` : `the routine ${t.action.routine}`}</div>
              <div className="text-meta-2 text-muted">
                {t.kind === "fact_changed" ? `When ${t.spec.entity_type.toLowerCase()} ${(t.spec.attributes ?? [t.spec.attribute]).join(" or ").replace(/_/g, " ")} changes`
                  : t.next.length ? `Next ${t.next.map((n) => `${clock(n.at)}${n.for ? ` (${n.for})` : ""}`).join(", ")}` : "Nothing coming up"}
              </div>
              {t.alerts && (t.kind === "watch" || t.alerts.on) && (
                <div className="mt-1.5">
                  {t.alerts.on
                    ? <Chip tone="apricot" icon={BellRingingIcon}>Tells you when {t.alerts.attributes.map((a) => (a === "*" ? "anything" : a.replace(/_/g, " "))).join(", ")} changes</Chip>
                    : <Chip tone="neutral" icon={BellSlashIcon}>Quiet: changes show in the task</Chip>}
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
                  placeholder='{"kind": "time", "name": "Sunday coupons", "spec": {"daily_at": "9:00"}, "action": {"goal": "..."}}'
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
