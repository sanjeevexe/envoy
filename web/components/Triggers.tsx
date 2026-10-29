"use client";

// Tasks that start on their own: at a time, before a flight (moving if it's delayed), on a watch, on new email, or when
// a remembered fact changes. What a trigger runs is fixed here by you; memory, emails and changes only fill in typed
// values. A watcher pushes when its run changed a fact it watches ("Gate changed: B12 → C14"); otherwise it's quiet.
import { useEffect, useState } from "react";
import { ago, api, post } from "@/lib/api";

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
  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => <button key={p.label} onClick={() => add(p.body)} className="rounded-md bg-white px-3 py-1.5 text-sm shadow-sm">+ {p.label}</button>)}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-stone-600">Write a trigger (JSON)</summary>
        <textarea value={json} onChange={(e) => setJson(e.target.value)} rows={6} placeholder='{"kind": "time", "name": "Sunday coupons", "spec": {"daily_at": "9:00"}, "action": {"goal": "..."}}'
                  className="mt-2 w-full rounded border border-stone-300 p-2 font-mono text-xs" />
        <button onClick={() => { try { add(JSON.parse(json)); } catch { setErr("That isn't valid JSON"); } }} className="rounded bg-stone-800 px-3 py-1 text-white">Add</button>
      </details>
      {err && <div className="rounded bg-rose-50 p-2 text-sm text-rose-800">{err}</div>}
      <ul className="space-y-2">
        {list.map((t) => (
          <li key={t.id} className="flex items-start justify-between gap-3 rounded-xl bg-white p-3 text-sm shadow-sm">
            <div>
              <div className="font-medium">{t.name}</div>
              <div className="text-xs text-stone-500">{t.kind} · runs {t.action.goal ?? `routine ${t.action.routine}`}</div>
              <div className="text-xs text-stone-500">
                {t.kind === "fact_changed" ? `runs when ${t.spec.entity_type}.${(t.spec.attributes ?? [t.spec.attribute]).join(" or ")} changes`
                  : t.next.length ? `next: ${t.next.map((n) => `${new Date(n.at * 1000).toLocaleString()}${n.for ? ` (${n.for})` : ""}`).join(", ")}` : "no upcoming run"}
              </div>
              {t.alerts && (t.kind === "watch" || t.alerts.on) && (
                <div className={`text-xs ${t.alerts.on ? "text-amber-800" : "text-stone-500"}`}>
                  {t.alerts.on ? `🔔 alerts on: ${t.alerts.attributes.map((a) => (a === "*" ? "any change" : a.replace(/_/g, " "))).join(", ")}` : "alerts off: changes show in the task, no push"}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              {t.kind === "watch" && t.alerts && (
                <button onClick={() => post(`/api/triggers/${t.id}`, { alert: !t.alerts!.on }).then(load)} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
                  {t.alerts.on ? "Alerts off" : "Alerts on"}
                </button>
              )}
              <button onClick={() => post(`/api/triggers/${t.id}`, { enabled: !t.enabled }).then(load)} className="rounded bg-stone-100 px-2 py-1 text-xs">{t.enabled ? "Pause" : "Resume"}</button>
              <button onClick={() => api(`/api/triggers/${t.id}`, { method: "DELETE" }).then(load)} className="rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">Delete</button>
            </div>
          </li>
        ))}
        {list.length === 0 && <li className="text-sm text-stone-500">No triggers yet.</li>}
      </ul>
      {changes.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-medium text-stone-700">Recent changes</h3>
          <ul className="space-y-1">
            {changes.map((c) => (
              <li key={c.id} className="rounded-lg bg-amber-50 px-3 py-2 text-sm">
                <a href={`/?task=${c.task_id}`} className="font-medium text-amber-950 underline-offset-2 hover:underline">{c.title}</a>
                <div className="text-xs text-amber-900">{c.entity_label} · {ago(c.time)} · {c.pushed ? "🔔 pushed" : `not pushed: ${c.why_not}`}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
