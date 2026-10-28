"use client";

// Tasks as they happen: each step with its screenshot, what was done, why, and its risk.
import { useEffect, useState } from "react";
import { api, ago, Approval, post, STATUS, Step, Task } from "@/lib/api";

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status, tone: "bg-stone-200" };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${s.tone}`}>{s.label}</span>;
}

// Cross-app answers: a part is shown under its parent task, by the app it asks.
const APPS: Record<string, string> = {
  "com.skylark.air": "SkyLark", "com.amazon.mShop.android.shopping": "Amazon", "com.target.ui": "Target", "com.starbucks.mobilecard": "Starbucks",
  "com.chipotle.ordering": "Chipotle", "com.dd.doordash": "DoorDash", "com.google.android.gm": "Gmail", "com.google.android.apps.maps": "Google Maps",
  "com.google.android.apps.youtube.music": "YouTube Music", "com.google.android.youtube": "YouTube", "com.android.vending": "Play Store",
  "com.android.chrome": "Chrome", "com.android.settings": "Settings", "com.google.android.calendar": "Calendar", "com.google.android.contacts": "Contacts",
};
export const appName = (pkg?: string) => (pkg ? APPS[pkg] ?? pkg.split(".").pop() ?? pkg : "app");

function PartRow({ t, open }: { t: Task; open: (id: string) => void }) {
  return (
    <button onClick={() => open(t.id)} className="flex w-full items-start justify-between gap-3 py-1.5 pl-8 pr-4 text-left hover:bg-white">
      <div className="min-w-0 text-xs">
        <span className="font-medium text-stone-700">{appName(t.app)}</span>
        <span className="text-stone-500"> · {t.device ?? "waiting for a phone"}{t.result ? ` · ${t.result}` : t.detail ? ` · ${t.detail}` : ""}</span>
      </div>
      <StatusBadge status={t.status} />
    </button>
  );
}

export function TaskList({ tasks, open }: { tasks: Task[]; open: (id: string) => void }) {
  if (!tasks.length) return <p className="p-4 text-sm text-stone-500">No tasks yet. Ask Envoy something in Chat.</p>;
  const ids = new Set(tasks.map((t) => t.id));
  const parts = (pid: string) => tasks.filter((t) => t.parent === pid).sort((a, b) => a.created_at - b.created_at);
  return (
    <ul className="divide-y divide-stone-200">
      {tasks.filter((t) => !t.parent || !ids.has(t.parent)).map((t) => (
        <li key={t.id}>
          <button onClick={() => open(t.id)} className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-white">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{t.goal}</div>
              <div className="truncate text-xs text-stone-500">
                {t.source} · {ago(t.created_at)}{t.routine ? ` · routine ${t.routine}` : t.kind === "crossapp" ? " · cross-app" : t.kind ? ` · ${t.kind}` : ""}{t.result ? ` · ${t.result}` : ""}
              </div>
            </div>
            <StatusBadge status={t.status} />
          </button>
          {t.kind === "crossapp" && parts(t.id).map((p) => <PartRow key={p.id} t={p} open={open} />)}
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
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {parts.map((p) => (
        <button key={p.id} onClick={() => open?.(p.id)} className="rounded-lg bg-white p-3 text-left shadow-sm hover:ring-1 hover:ring-stone-300">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold">{appName(p.app)}</span>
            <StatusBadge status={p.status} />
          </div>
          <div className="mt-1 text-xs text-stone-500">{p.device ?? "waiting for a phone"}{p.routine ? ` · routine ${p.routine}` : p.kind ? ` · ${p.kind}` : ""}</div>
          <div className="mt-1 text-sm">{p.result || p.detail || p.goal}</div>
        </button>
      ))}
    </div>
  );
}

const RISK: Record<string, string> = { read: "text-stone-500", reversible: "text-sky-700", irreversible: "text-rose-700 font-semibold" };

export function TaskDetail({ id, task, liveSteps, back, all, open }: {
  id: string; task?: Task; liveSteps: Step[]; back: () => void; all?: Record<string, Task>; open?: (id: string) => void;
}) {
  const [data, setData] = useState<{ task: Task; steps: Step[]; approvals: Approval[] } | null>(null);
  useEffect(() => { api(`/api/tasks/${id}`).then(setData).catch(() => setData(null)); }, [id, task?.status, liveSteps.length]);
  const t = task ?? data?.task;
  const steps = data?.steps ?? liveSteps;
  if (!t) return <p className="p-4 text-sm">Loading…</p>;
  const active = ["queued", "running", "needs_you", "taken_over", "waiting_approval"].includes(t.status);
  return (
    <div className="p-4">
      <button onClick={back} className="mb-3 text-sm text-stone-500">← All tasks</button>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t.goal}</h2>
          <div className="text-xs text-stone-500">
            from {t.source} · {t.device ?? "no phone yet"}{t.routine ? ` · routine ${t.routine}` : ""} · {t.model_calls ?? 0} model calls
          </div>
          {t.parent && <button onClick={() => open?.(t.parent!)} className="text-xs text-sky-700">part of a cross-app question ↑</button>}
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={t.status} />
          {active && <button onClick={() => post(`/api/tasks/${id}/stop`)} className="rounded-md bg-rose-600 px-2 py-1 text-xs font-medium text-white">Stop</button>}
        </div>
      </div>
      {t.result && <div className={`mt-3 rounded-lg px-3 py-2 text-sm ${active ? "bg-stone-100 text-stone-700" : "bg-emerald-50 text-emerald-900"}`}>{t.result}</div>}
      {t.kind === "crossapp" && <Parts id={id} all={all} open={open} />}
      {t.status === "failed" && t.detail && <div className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900">{t.detail}</div>}
      {(data?.approvals ?? []).length > 0 && (
        <div className="mt-3 space-y-1">
          {data!.approvals.map((a) => (
            <div key={a.id} className="rounded-lg bg-white px-3 py-2 text-sm shadow-sm">
              <span className="font-medium">Approval:</span> {a.description}{" "}
              <span className={a.status === "approved" ? "text-emerald-700" : a.status === "pending" ? "text-amber-700" : "text-stone-600"}>
                {a.status}{a.decided_by ? ` by ${a.decided_by}` : ""}{a.note ? ` (${a.note})` : ""}
              </span>
            </div>
          ))}
        </div>
      )}
      <ol className="mt-4 space-y-2">
        {steps.map((s) => (
          <li key={s.seq} className="flex gap-3 rounded-lg bg-white p-2 shadow-sm">
            {s.shot ? <img src={`/api/shots/${s.shot}`} alt="" className="h-28 w-[52px] shrink-0 rounded object-cover object-top" />
                    : (s.kind === "action" || s.kind === "routine_step") ? <div className="h-28 w-[52px] shrink-0 rounded bg-stone-100" title="No picture: secure screen or none taken" /> : null}
            <div className="min-w-0 text-sm">
              <div className="font-medium">
                {s.kind === "routine_step" ? `Step ${s.text}` : s.text}
                {s.risk && <span className={`ml-2 text-xs ${RISK[s.risk] ?? ""}`}>{s.risk}</span>}
              </div>
              {s.reason && <div className="text-stone-600">{s.reason}</div>}
              {s.kind === "routine_step" && <div className="text-xs text-stone-500">{s.status}{s.rung ? ` (rung ${s.rung})` : ""}{s.detail ? ` · ${s.detail}` : ""}</div>}
              {s.approval && <div className="text-xs">{s.approval.approved ? "✅ approved" : "⛔ not approved"} by {s.approval.by}</div>}
              {s.kind === "memory" && s.entities && <div className="text-xs text-stone-500">{s.entities.join(", ")}</div>}
              {s.sources && Object.keys(s.sources).length > 0 && (
                <div className="text-xs text-stone-500">{Object.entries(s.sources).map(([k, v]) => `${k} from ${v}`).join("; ")}</div>
              )}
              {s.error && <div className="text-xs text-rose-700">{s.error}</div>}
              <div className="text-[11px] text-stone-400">{s.kind} · {new Date(s.time * 1000).toLocaleTimeString()}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
