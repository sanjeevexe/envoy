"use client";

// Learned routines: what each does, its inputs, versions, and how its runs have gone.
import { useEffect, useState } from "react";
import { api, post } from "@/lib/api";

type R = { name: string; app: string; intent: string; active: number | null; versions: any[]; inputs: Record<string, string>; outputs: string[];
  steps: number; runs: number; success: number | null; recompile: boolean };

export default function Routines({ openTask }: { openTask: (id: string) => void }) {
  const [list, setList] = useState<R[]>([]);
  const [yaml, setYaml] = useState<{ name: string; text: string } | null>(null);
  useEffect(() => { api("/api/routines").then(setList).catch(() => {}); }, []);
  const show = (name: string) => api(`/api/routines/${name}`).then((r) => setYaml({ name, text: r.yaml }));
  const run = async (r: R) => {
    const task = await post("/api/tasks", { routine: r.name, inputs: {} });
    openTask(task.id);
  };
  return (
    <div className="p-4">
      <p className="mb-3 text-sm text-stone-600">Each routine was learned from one run by the agent. It replays with no model calls while the app looks as expected, and repairs itself when it doesn't.</p>
      <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-stone-500"><tr>
            <th className="p-2">Routine</th><th className="p-2">Inputs</th><th className="p-2">Steps</th><th className="p-2">Versions</th><th className="p-2">Runs</th><th className="p-2" />
          </tr></thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.name} className="border-t border-stone-100 align-top">
                <td className="p-2"><button onClick={() => show(r.name)} className="font-medium text-sky-700">{r.intent}</button><div className="text-xs text-stone-500">{r.name}</div></td>
                <td className="p-2 text-xs">{Object.keys(r.inputs).join(", ") || "none"}</td>
                <td className="p-2">{r.steps}</td>
                <td className="p-2 text-xs">v{r.active ?? "?"} active · {r.versions.length} in all</td>
                <td className="p-2 text-xs">{r.runs ? `${r.runs} runs, ${Math.round((r.success ?? 0) * 100)}% ok` : "—"}{r.recompile && <div className="text-amber-700">needs recompiling</div>}</td>
                <td className="p-2"><button onClick={() => run(r)} className="rounded bg-stone-800 px-2 py-1 text-xs text-white">Run</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {yaml && (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-sm"><span className="font-medium">{yaml.name}</span><button onClick={() => setYaml(null)} className="text-stone-500">Close</button></div>
          <pre className="max-h-[50vh] overflow-auto rounded-xl bg-stone-900 p-3 text-xs text-stone-100">{yaml.text}</pre>
        </div>
      )}
    </div>
  );
}
