"use client";

// Learned routines: what each does, its inputs, versions, and how its runs have gone. Selecting one opens its detail.
import { useEffect, useRef, useState } from "react";
import RoutineDetail from "@/components/RoutineDetail";
import { api, post } from "@/lib/api";

type R = { name: string; app: string; intent: string; active: number | null; versions: any[]; inputs: Record<string, string>; outputs: string[];
  steps: number; runs: number; success: number | null; recompile: boolean };

export default function Routines({ openTask }: { openTask: (id: string) => void }) {
  const [list, setList] = useState<R[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [returnTo, setReturnTo] = useState<string | null>(null);
  const rows = useRef<Record<string, HTMLButtonElement | null>>({});
  useEffect(() => { api("/api/routines").then(setList).catch(() => {}); }, []);
  useEffect(() => { if (!open && returnTo) rows.current[returnTo]?.focus(); }, [open, returnTo]);
  const run = async (r: R) => {
    const task = await post("/api/tasks", { routine: r.name, inputs: {} });
    openTask(task.id);
  };
  if (open) return <RoutineDetail name={open} back={() => { setReturnTo(open); setOpen(null); }} openTask={openTask} />;
  return (
    <div className="p-4">
      <p className="mb-3 text-sm text-stone-600">Each routine was learned from one run by the agent. It replays with no model calls while the app looks as expected, and repairs itself when it doesn't. Select one to see its steps, versions and runs.</p>
      <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-stone-500"><tr>
            <th className="p-2">Routine</th><th className="hidden p-2 sm:table-cell">Inputs</th><th className="hidden p-2 sm:table-cell">Steps</th><th className="p-2">Versions</th><th className="p-2">Runs</th><th className="p-2" />
          </tr></thead>
          <tbody>
            {list.map((r) => {
              const repairs = r.versions.filter((v) => v.source_task).length;
              const trial = r.versions.find((v) => v.status === "trial");
              return (
                <tr key={r.name} className="border-t border-stone-100 align-top">
                  <td className="p-2"><button ref={(el) => { rows.current[r.name] = el; }} onClick={() => setOpen(r.name)}
                    className="rounded text-left font-medium text-sky-700 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600">{r.intent}</button>
                    <div className="text-xs text-stone-500 [overflow-wrap:anywhere]">{r.name}</div></td>
                  <td className="hidden p-2 text-xs sm:table-cell">{Object.keys(r.inputs).join(", ") || "none"}</td>
                  <td className="hidden p-2 sm:table-cell">{r.steps}</td>
                  <td className="p-2 text-xs">v{r.active ?? "?"} active · {r.versions.length} in all
                    {repairs > 0 && <div className="whitespace-nowrap text-violet-800">self-repaired {repairs}×</div>}
                    {trial && <div className="whitespace-nowrap text-amber-800">v{trial.version} on trial</div>}</td>
                  <td className="p-2 text-xs">{r.runs ? `${r.runs} run${r.runs === 1 ? "" : "s"}, ${Math.round((r.success ?? 0) * 100)}% ok` : "—"}{r.recompile && <div className="text-amber-700">needs recompiling</div>}</td>
                  <td className="p-2"><button onClick={() => run(r)} aria-label={`Run ${r.intent}`} className="rounded bg-stone-800 px-2 py-1 text-xs text-white">Run</button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
