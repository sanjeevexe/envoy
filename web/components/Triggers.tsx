"use client";

// Tasks that start on their own: at a time, before a flight (moving if it's delayed), on a watch, or on new email.
// What a trigger runs is fixed here by you; memory and emails only fill in typed values.
import { useEffect, useState } from "react";
import { api, post } from "@/lib/api";

type Trig = { id: string; kind: string; name: string; spec: any; action: any; enabled: boolean; last_fired: number | null; next: { at: number; for?: string }[] };

const PRESETS = [
  { label: "Check in 24 h before every flight", body: { kind: "before_fact", name: "Check in 24 h before every flight",
    spec: { entity_type: "Flight", minutes_before: 1440 }, action: { goal: "Check me in for my flight to {trip.destination}" } } },
  { label: "Watch my gate every 10 minutes", body: { kind: "watch", name: "Watch my gate", spec: { every_minutes: 10 },
    action: { routine: "skylark_get_flight_gate", inputs_from: {} } } },
  { label: "New SkyLark booking email: look up its gate", body: { kind: "email", name: "New SkyLark booking",
    spec: { sender_contains: "skylark" }, action: { routine: "skylark_get_flight_gate", inputs_from: { trip_city: "Trip.destination" } } } },
];

export default function Triggers() {
  const [list, setList] = useState<Trig[]>([]);
  const [json, setJson] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const load = () => api("/api/triggers").then(setList).catch(() => {});
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
                {t.next.length ? `next: ${t.next.map((n) => `${new Date(n.at * 1000).toLocaleString()}${n.for ? ` (${n.for})` : ""}`).join(", ")}` : "no upcoming run"}
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => post(`/api/triggers/${t.id}`, { enabled: !t.enabled }).then(load)} className="rounded bg-stone-100 px-2 py-1 text-xs">{t.enabled ? "Pause" : "Resume"}</button>
              <button onClick={() => api(`/api/triggers/${t.id}`, { method: "DELETE" }).then(load)} className="rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">Delete</button>
            </div>
          </li>
        ))}
        {list.length === 0 && <li className="text-sm text-stone-500">No triggers yet.</li>}
      </ul>
    </div>
  );
}
