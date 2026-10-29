"use client";

// App notes: what Envoy has learned about how each app works, from its own runs. Each note says where it was learned
// (the task and step) and how often it held; Retire takes one out of the agent's prompts.
import { useEffect, useState } from "react";
import { appName } from "@/components/Tasks";
import { appIcon, Card, RowIcon, SectionLabel } from "@/components/ui";
import { ago, api, post } from "@/lib/api";

type Source = { task_id?: string; step?: number; outcome?: string; kind?: string; observed_at?: number };
type Note = { id: string; app: string; text: string; status: string; confirmations: number; first_seen: number; last_confirmed: number; sources: Source[] };

export default function AppNotes({ openTask }: { openTask: (id: string) => void }) {
  const [apps, setApps] = useState<{ app: string; notes: Note[] }[]>([]);
  const load = () => api("/api/app-notes").then((r) => setApps(r.apps)).catch(() => {});
  useEffect(() => { load(); }, []);
  const retire = async (n: Note) => { await post(`/api/app-notes/${n.id}/retire`); load(); };
  return (
    <section aria-labelledby="app-notes" className="pt-6">
      <SectionLabel id="app-notes" className="px-6">App notes</SectionLabel>
      <p className="px-6 pb-3 pt-1 text-meta text-ink-2">
        Short notes Envoy wrote about how each app works, after its own runs. The agent and repairs read them; they are about the apps, never about you.
      </p>
      {apps.length === 0 && <p className="px-6 text-meta text-muted">No notes yet.</p>}
      <div className="flex flex-col gap-3 px-4">
        {apps.map(({ app, notes }) => (
          <Card key={app} className="overflow-hidden">
            <div className="flex items-center gap-3 border-b border-divider px-4 py-3">
              <RowIcon icon={appIcon(app)} size={32} />
              <span className="min-w-0"><span className="block text-row font-bold">{appName(app)}</span><span className="block truncate text-meta-2 text-muted">{app}</span></span>
            </div>
            {notes.map((n) => {
              const last = n.sources[0];
              return (
                <div key={n.id} className="flex items-start gap-3 border-b border-divider py-3 pl-4 pr-3 last:border-b-0">
                  <div className="min-w-0 flex-1">
                    <p className="text-row [overflow-wrap:anywhere]">{n.text}</p>
                    <p className="mt-0.5 text-meta-2 text-muted">
                      Seen {n.confirmations}×, last {ago(n.last_confirmed)}
                      {last?.task_id && <> · from <button onClick={() => openTask(last.task_id!)} className="font-semibold text-sage-ink hover:text-sage-deep">
                        a task{last.step ? `, step ${last.step}` : ""}</button></>}
                      {last?.kind === "routine" && " (a repair)"}
                    </p>
                  </div>
                  <button onClick={() => retire(n)} aria-label={`Retire note: ${n.text}`}
                          className="h-11 shrink-0 rounded-full border border-control bg-surface px-4 text-meta font-bold hover:border-line-strong">Retire</button>
                </div>
              );
            })}
          </Card>
        ))}
      </div>
    </section>
  );
}
