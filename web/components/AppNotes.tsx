"use client";

// App notes: what Envoy has learned about how each app works, from its own runs. Each note says where it was learned
// (the task and step) and how often it held; Retire takes one out of the agent's prompts.
import { useEffect, useState } from "react";
import { ago, api, post } from "@/lib/api";

type Source = { task_id?: string; step?: number; outcome?: string; kind?: string; observed_at?: number };
type Note = { id: string; app: string; text: string; status: string; confirmations: number; first_seen: number; last_confirmed: number; sources: Source[] };

const APP_NAMES: Record<string, string> = {
  "com.skylark.air": "SkyLark", "com.starbucks.mobilecard": "Starbucks", "com.dd.doordash": "DoorDash", "com.amazon.mShop.android.shopping": "Amazon",
  "com.chipotle.ordering": "Chipotle", "com.google.android.apps.maps": "Google Maps",
};

export default function AppNotes({ openTask }: { openTask: (id: string) => void }) {
  const [apps, setApps] = useState<{ app: string; notes: Note[] }[]>([]);
  const load = () => api("/api/app-notes").then((r) => setApps(r.apps)).catch(() => {});
  useEffect(() => { load(); }, []);
  const retire = async (n: Note) => { await post(`/api/app-notes/${n.id}/retire`); load(); };
  return (
    <div className="px-4 pb-4">
      <h2 className="mb-1 text-sm font-semibold text-stone-800">App notes</h2>
      <p className="mb-3 text-sm text-stone-600">Short notes Envoy wrote about how each app works, after its own runs. The agent and repairs read them; they are about the apps, never about you.</p>
      {apps.length === 0 && <p className="text-sm text-stone-500">No notes yet.</p>}
      {apps.map(({ app, notes }) => (
        <div key={app} className="mb-3 overflow-x-auto rounded-xl bg-white shadow-sm">
          <div className="border-b border-stone-100 p-2 text-xs font-medium text-stone-700">{APP_NAMES[app] ?? app} <span className="text-stone-400">{app}</span></div>
          <table className="w-full text-left text-sm">
            <tbody>
              {notes.map((n) => {
                const last = n.sources[0];
                return (
                  <tr key={n.id} className="border-t border-stone-100 align-top first:border-t-0">
                    <td className="p-2">{n.text}
                      <div className="text-xs text-stone-500">
                        seen {n.confirmations}×, last {ago(n.last_confirmed)}
                        {last?.task_id && <> · from <button onClick={() => openTask(last.task_id!)} className="text-sky-700 hover:underline">{last.task_id}{last.step ? ` step ${last.step}` : ""}</button></>}
                        {last?.kind === "routine" && " (a repair)"}
                      </div></td>
                    <td className="p-2 text-right"><button onClick={() => retire(n)} aria-label={`Retire note: ${n.text}`}
                      className="rounded border border-stone-300 px-2 py-1 text-xs text-stone-700 hover:bg-stone-50">Retire</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
