"use client";

// The memory graph: entities and their links. Click one to see its facts, where each was seen, and its history;
// edit a fact (your edit outranks anything Envoy read) or delete a source (its facts go with it).
import { useEffect, useRef, useState } from "react";
import { api, ago, post } from "@/lib/api";

type Node = { id: string; type: string; name: string; facts: number; stale: boolean; user_edited: boolean };
type Edge = { id: string; source: string; target: string; relation: string };
type Fact = { id: string; attribute: string; value: string; current: boolean; stale: boolean; conflict: number; author?: string;
  recorded_at: number; valid_to?: number | null; sources: { id: string; where: string }[] };
type Entity = { entity: { id: string; type: string; name: string }; facts: Fact[]; links: { relation: string; id: string; type: string; name: string }[] };

const COLORS: Record<string, string> = { Trip: "#2563eb", Flight: "#0891b2", Person: "#7c3aed", Order: "#d97706", Reservation: "#059669",
  Place: "#65a30d", Note: "#78716c", Hotel: "#db2777" };

export default function MemoryGraph({ version }: { version: number }) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<any>(null);
  const [graph, setGraph] = useState<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  const [selected, setSelected] = useState<string | null>(null);
  const [entity, setEntity] = useState<Entity | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [edit, setEdit] = useState<{ attribute: string; value: string } | null>(null);
  const [q, setQ] = useState("");
  const [notes, setNotes] = useState<string | null>(null);

  useEffect(() => { api("/api/memory/graph").then(setGraph).catch(() => {}); }, [version]);
  useEffect(() => { if (selected) api(`/api/memory/entity/${selected}`).then(setEntity).catch(() => setEntity(null)); }, [selected, version]);

  useEffect(() => {
    let alive = true;
    import("cytoscape").then(({ default: cytoscape }) => {
      if (!alive || !box.current) return;
      const elements = [
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: `${n.type}\n${n.name}`.slice(0, 48), color: COLORS[n.type] ?? "#57534e", stale: n.stale ? 1 : 0 } })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.relation } })),
      ];
      if (cy.current) cy.current.destroy();
      cy.current = cytoscape({
        container: box.current, elements, wheelSensitivity: 0.3,
        style: [
          { selector: "node", style: { "background-color": "data(color)", label: "data(label)", "font-size": 9, "text-wrap": "wrap", "text-max-width": "110px",
            "text-valign": "bottom", "text-margin-y": 4, width: 22, height: 22, color: "#292524" } },
          { selector: "node[stale = 1]", style: { "border-width": 2, "border-style": "dashed", "border-color": "#f59e0b" } },
          { selector: "node:selected", style: { "border-width": 3, "border-color": "#111" } },
          { selector: "edge", style: { width: 1.5, "line-color": "#d6d3d1", "target-arrow-shape": "triangle", "target-arrow-color": "#d6d3d1",
            "curve-style": "bezier", label: "data(label)", "font-size": 7, color: "#a8a29e" } },
        ],
        layout: { name: "cose", animate: false, padding: 20, nodeRepulsion: () => 9000 },
      });
      cy.current.on("tap", "node", (ev: any) => setSelected(ev.target.id()));
    });
    return () => { alive = false; };
  }, [graph]);

  const saveEdit = async () => {
    if (!edit || !selected) return;
    await post(`/api/memory/entity/${selected}/fact`, edit);
    setEdit(null);
    api(`/api/memory/entity/${selected}`).then(setEntity);
  };
  const deleteSource = async (sid: string, where: string) => {
    if (!confirm(`Delete the source "${where}"? Facts that only it supported are removed from memory.`)) return;
    await api(`/api/memory/source/${sid}`, { method: "DELETE" });
    api("/api/memory/graph").then(setGraph);
    if (selected) api(`/api/memory/entity/${selected}`).then(setEntity).catch(() => setEntity(null));
  };

  const facts = entity?.facts.filter((f) => showHistory || f.current) ?? [];
  return (
    <div className="flex h-full flex-col lg:flex-row">
      <div className="flex min-h-[360px] flex-1 flex-col">
        <form className="flex gap-2 p-3" onSubmit={(e) => { e.preventDefault(); if (q) api(`/api/memory/search?q=${encodeURIComponent(q)}`).then((r) => setNotes(r.markdown || "(nothing relevant)")); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="What does Envoy remember about…" className="min-w-0 flex-1 rounded-md border border-stone-300 px-2 py-1 text-sm" />
          <button className="rounded-md bg-stone-800 px-3 py-1 text-sm text-white">Search</button>
        </form>
        {notes && <pre className="mx-3 mb-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-white p-2 text-xs shadow-sm">{notes}</pre>}
        <div ref={box} className="m-3 flex-1 rounded-xl bg-white shadow-sm" />
        <div className="px-3 pb-3 text-xs text-stone-500">{graph.nodes.length} entities · {graph.edges.length} links · dashed = may be out of date</div>
      </div>
      <aside className="w-full shrink-0 overflow-y-auto border-t border-stone-200 p-4 lg:w-96 lg:border-l lg:border-t-0">
        {!entity ? <p className="text-sm text-stone-500">Click an entity to see its facts and where each came from.</p> : (
          <div className="space-y-3 text-sm">
            <div>
              <div className="text-xs uppercase tracking-wide text-stone-500">{entity.entity.type}</div>
              <h3 className="text-base font-semibold">{entity.entity.name}</h3>
            </div>
            <label className="flex items-center gap-2 text-xs text-stone-600">
              <input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} /> Show history
            </label>
            <ul className="space-y-2">
              {facts.map((f) => (
                <li key={f.id} className={`rounded-lg bg-white p-2 shadow-sm ${f.current ? "" : "opacity-60"}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-xs text-stone-500">{f.attribute.replace(/_/g, " ")}</span>
                    {f.current && <button onClick={() => setEdit({ attribute: f.attribute, value: f.value })} className="text-xs text-sky-700">Edit</button>}
                  </div>
                  <div className={`font-medium ${f.current ? "" : "line-through"}`}>{f.value}
                    {f.stale && f.current && <span className="ml-2 text-xs font-normal text-amber-700">may have changed</span>}
                    {f.conflict ? <span className="ml-2 text-xs font-normal text-rose-700">conflicts with your edit</span> : null}
                    {f.author === "user" && <span className="ml-2 text-xs font-normal text-violet-700">your edit</span>}
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {f.sources.map((s) => (
                      <div key={s.id} className="flex items-center justify-between gap-2 text-xs text-stone-500">
                        <span>{s.where}</span>
                        <button onClick={() => deleteSource(s.id, s.where)} className="text-rose-600">Delete source</button>
                      </div>
                    ))}
                  </div>
                  {!f.current && <div className="text-[11px] text-stone-400">replaced {f.valid_to ? ago(f.valid_to) : ""}</div>}
                </li>
              ))}
            </ul>
            {edit && (
              <div className="rounded-lg bg-violet-50 p-2">
                <div className="text-xs text-stone-600">Edit {edit.attribute.replace(/_/g, " ")} (your edit outranks what Envoy reads)</div>
                <div className="mt-1 flex gap-2">
                  <input value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} className="min-w-0 flex-1 rounded border px-2 py-1" />
                  <button onClick={saveEdit} className="rounded bg-violet-600 px-3 py-1 text-white">Save</button>
                  <button onClick={() => setEdit(null)} className="rounded bg-stone-200 px-2 py-1">Cancel</button>
                </div>
              </div>
            )}
            {entity.links.length > 0 && (
              <div>
                <div className="text-xs uppercase tracking-wide text-stone-500">Linked</div>
                <ul className="mt-1 space-y-1">
                  {entity.links.map((l) => (
                    <li key={l.id + l.relation}><button onClick={() => setSelected(l.id)} className="text-sky-700">{l.relation} → {l.type} {l.name}</button></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
