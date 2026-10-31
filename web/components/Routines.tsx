"use client";

// Routines and their triggers. A routine was learned from one run, by the agent or by you (teach mode): what it does,
// its inputs, its versions and how its runs have gone; selecting one opens its detail. Teach a new routine opens the
// phone's "Show Envoy once" form. Triggers start tasks on their own.
import { useEffect, useRef, useState } from "react";
import { ChalkboardTeacherIcon, PlayIcon } from "@phosphor-icons/react";
import AppNotes from "@/components/AppNotes";
import RoutineDetail from "@/components/RoutineDetail";
import Triggers from "@/components/Triggers";
import { appIcon, Button, Card, Chip, RowIcon, Segmented } from "@/components/ui";
import { api, post } from "@/lib/api";

type R = { name: string; app: string; intent: string; active: number | null; versions: any[]; inputs: Record<string, string>; outputs: string[];
  steps: number; runs: number; success: number | null; recompile: boolean; taught?: boolean };

const VIEWS = ["Routines", "Triggers"] as const;

// `teach`: open the phone with an empty "Show Envoy once" form (page.tsx picks a phone that's free).
export default function RoutinesTab({ openTask, teach }: { openTask: (id: string) => void; teach: () => void }) {
  const [view, setView] = useState<(typeof VIEWS)[number]>("Routines");
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      {open && <RoutineDetail name={open} back={() => setOpen(null)} openTask={openTask} />}
      <div hidden={!!open} className="mx-auto w-full max-w-[760px] pb-8 md:pt-6">
        <div className="px-4 pb-1 pt-3"><Segmented options={VIEWS} value={view} onChange={setView} label="Routines or triggers" /></div>
        {view === "Routines" ? <Routines openTask={openTask} open={open} setOpen={setOpen} teach={teach} /> : <Triggers />}
      </div>
    </>
  );
}

function Routines({ openTask, open, setOpen, teach }: { openTask: (id: string) => void; open: string | null; setOpen: (n: string | null) => void; teach: () => void }) {
  const [list, setList] = useState<R[] | null>(null);
  const [returnTo, setReturnTo] = useState<string | null>(null);
  const rows = useRef<Record<string, HTMLButtonElement | null>>({});
  useEffect(() => { api("/api/routines").then(setList).catch(() => setList([])); }, []);
  useEffect(() => { if (open) setReturnTo(open); else if (returnTo) rows.current[returnTo]?.focus(); }, [open, returnTo]);
  const run = async (r: R) => {
    const task = await post("/api/tasks", { routine: r.name, inputs: {} });
    openTask(task.id);
  };
  return (
    <div className="ev-rise">
      <p className="px-6 pb-4 pt-3 text-meta text-ink-2">
        Each routine was learned from one run, by the agent or by you. It replays with no model calls while the app looks as expected, and repairs itself when it doesn&rsquo;t.
      </p>
      <div className="mx-4 mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button variant="sage" onClick={teach}><ChalkboardTeacherIcon size={18} />Teach a new routine</Button>
        <span className="min-w-[12rem] flex-1 text-meta text-ink-2">Do it once on the phone and Envoy learns it.</span>
      </div>
      <Card className="mx-4 overflow-hidden">
        {list === null && <p className="px-4 py-6 text-body text-muted">Loading…</p>}
        {list?.length === 0 && <p className="px-4 py-6 text-body text-muted">No routines yet. Ask Envoy to do something, or teach it once.</p>}
        {list?.map((r) => {
          const repairs = r.versions.filter((v) => v.source_task).length;
          const trial = r.versions.find((v) => v.status === "trial");
          return (
            <div key={r.name} className="flex items-center gap-3 border-b border-divider py-1 pl-4 pr-3 last:border-b-0">
              <button ref={(el) => { rows.current[r.name] = el; }} onClick={() => setOpen(r.name)} className="flex min-h-[64px] min-w-0 flex-1 items-center gap-3 py-2 text-left">
                <RowIcon icon={appIcon(r.app)} />
                <span className="min-w-0 flex-1">
                  <span className="block text-row font-semibold [overflow-wrap:anywhere]">{r.intent}</span>
                  <span className="mt-0.5 block text-meta-2 text-muted">
                    v{r.active ?? "?"} · {r.steps} steps · {r.runs ? `${r.runs} run${r.runs === 1 ? "" : "s"}, ${Math.round((r.success ?? 0) * 100)}% finished` : "not run yet"}
                    {Object.keys(r.inputs).length ? ` · needs ${Object.keys(r.inputs).join(", ").replace(/_/g, " ")}` : ""}
                  </span>
                  {(r.taught || repairs > 0 || trial || r.recompile) && (
                    <span className="mt-1.5 flex flex-wrap gap-1.5">
                      {r.taught && <Chip icon={ChalkboardTeacherIcon}>Taught by you</Chip>}
                      {repairs > 0 && <Chip>Repaired itself {repairs}×</Chip>}
                      {trial && <Chip tone="apricot">v{trial.version} on trial</Chip>}
                      {r.recompile && <Chip tone="apricot">Needs relearning</Chip>}
                    </span>
                  )}
                </span>
              </button>
              <button onClick={() => run(r)} aria-label={`Run ${r.intent}`} title="Run it now"
                      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-control bg-surface text-sage-ink hover:border-line-strong">
                <PlayIcon size={18} weight="fill" />
              </button>
            </div>
          );
        })}
      </Card>
      <AppNotes openTask={openTask} />
    </div>
  );
}
