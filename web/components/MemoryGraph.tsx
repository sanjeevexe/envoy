"use client";

// The memory graph: entities and their links. Click one to see its facts, where each was seen, and its history;
// edit a fact (your edit outranks anything Envoy read) or delete a source (its facts go with it).
import { useEffect, useRef, useState } from "react";
import { MagnifyingGlassIcon, PencilSimpleIcon, TrashIcon } from "@phosphor-icons/react";
import { Button, Chip, cx, SectionLabel } from "@/components/ui";
import { api, ago, post } from "@/lib/api";

type Node = { id: string; type: string; name: string; facts: number; stale: boolean; user_edited: boolean };
type Edge = { id: string; source: string; target: string; relation: string };
type Fact = { id: string; attribute: string; value: string; current: boolean; stale: boolean; conflict: number; author?: string;
  recorded_at: number; valid_to?: number | null; sources: { id: string; where: string }[] };
type Entity = { entity: { id: string; type: string; name: string }; facts: Fact[]; links: { relation: string; id: string; type: string; name: string }[] };

// Node colors from the Sage palette (globals.css): greens for travel, apricots for shopping, inks for people and places;
// lighter ones in dark mode, so every node stands out from its card.
const LIGHT: Record<string, string> = { Person: "#1F2A24", Trip: "#5E9478", Flight: "#1F4F37", Reservation: "#5F6A63", Order: "#E8945A", Item: "#C2703A",
  Place: "#7A3B12", "Loyalty program": "#6F8F7C", Note: "#4E5A53", Hotel: "#5F6A63" };
const DARK: Record<string, string> = { Person: "#ECEEE9", Trip: "#5E9478", Flight: "#B5DEC6", Reservation: "#98A39C", Order: "#E8945A", Item: "#F2B68A",
  Place: "#C98A5A", "Loyalty program": "#8FB39E", Note: "#C2CAC4", Hotel: "#98A39C" };
const isDark = () => typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
const colorOf = (type: string) => (isDark() ? DARK : LIGHT)[type] ?? (isDark() ? "#C2CAC4" : "#4E5A53");
const token = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const FONT = '"Manrope Variable", Manrope, system-ui, sans-serif';

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
        ...graph.nodes.map((n) => ({ data: { id: n.id, label: `${n.type}\n${n.name}`.slice(0, 48), color: colorOf(n.type), stale: n.stale ? 1 : 0 } })),
        ...graph.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.relation } })),
      ];
      if (cy.current) cy.current.destroy();
      const [ink, surface, line, muted, tint] = ["--ink", "--surface", "--line-strong", "--muted", "--sage-tint"].map(token);
      cy.current = cytoscape({
        container: box.current, elements, wheelSensitivity: 0.3,
        style: [
          { selector: "node", style: { "background-color": "data(color)", label: "data(label)", "font-family": FONT, "font-size": 10, "font-weight": 600,
            "text-wrap": "wrap", "text-max-width": "120px", "text-valign": "bottom", "text-margin-y": 5, width: 26, height: 26, color: ink,
            "border-width": 3, "border-color": surface, "text-background-color": surface, "text-background-opacity": 0.85, "text-background-padding": "2px",
            "text-background-shape": "roundrectangle" } },
          { selector: "node[stale = 1]", style: { "border-width": 3, "border-style": "dashed", "border-color": "#E8945A" } },
          { selector: "node:selected", style: { "border-width": 4, "border-color": tint, "overlay-color": "#3E7C5C", "overlay-opacity": 0.12, "overlay-padding": 6 } },
          { selector: "edge", style: { width: 1.5, "line-color": line, "target-arrow-shape": "triangle", "target-arrow-color": line, "arrow-scale": 0.8,
            "curve-style": "bezier", label: "data(label)", "font-family": FONT, "font-size": 8, color: muted, "text-rotation": "autorotate",
            "text-background-color": surface, "text-background-opacity": 0.85, "text-background-padding": "1px" } },
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
  const types = [...new Set(graph.nodes.map((n) => n.type))];
  return (
    <div className="flex min-h-full flex-col lg:h-full lg:flex-row">
      <div className="flex min-h-[420px] flex-1 flex-col gap-3 p-4 md:p-6">
        <form role="search" className="flex h-12 items-center gap-1 rounded-full border border-control bg-surface pl-4 pr-1 focus-within:border-sage"
              onSubmit={(e) => { e.preventDefault(); if (q) api(`/api/memory/search?q=${encodeURIComponent(q)}`).then((r) => setNotes(r.markdown || "Nothing relevant.")); }}>
          <MagnifyingGlassIcon size={18} className="shrink-0 text-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search memory" placeholder="What does Envoy remember about…"
                 className="min-w-0 flex-1 bg-transparent px-2 text-[16px] outline-none placeholder:text-muted md:text-body" />
          <Button variant="primary" className="h-10">Search</Button>
        </form>
        {notes && <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-block border border-line bg-surface p-3 font-sans text-meta text-ink-2">{notes}</pre>}
        <div ref={box} role="img" aria-label="Memory graph: select something to see its facts" className="min-h-[320px] flex-1 overflow-hidden rounded-card border border-line bg-surface" />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-meta-2 text-muted">
          <span>{graph.nodes.length} things · {graph.edges.length} links</span>
          {types.map((t) => <span key={t} className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: colorOf(t) }} />{t}</span>)}
          <span className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-2.5 rounded-full border-2 border-dashed border-apricot" />may be out of date</span>
        </div>
      </div>
      <aside aria-label="Facts" className="w-full shrink-0 overflow-y-auto border-t border-line bg-raised p-4 md:p-6 lg:w-[380px] lg:border-l lg:border-t-0">
        {!entity ? <p className="text-body text-muted">Select something in the graph to see what Envoy knows about it, and where each fact was seen.</p> : (
          <div className="flex flex-col gap-4">
            <div>
              <div className="text-meta font-bold text-muted">{entity.entity.type}</div>
              <h2 className="mt-0.5 text-title font-bold">{entity.entity.name}</h2>
            </div>
            <label className="flex min-h-[44px] items-center gap-2.5 text-meta text-ink-2">
              <input type="checkbox" checked={showHistory} onChange={(e) => setShowHistory(e.target.checked)} /> Show earlier values
            </label>
            <ul className="flex flex-col gap-2">
              {facts.map((f) => (
                <li key={f.id} className={cx("rounded-block border border-line bg-surface px-4 py-3", !f.current && "opacity-70")}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-meta text-muted">{f.attribute.replace(/_/g, " ")}</span>
                    {f.current && <button onClick={() => setEdit({ attribute: f.attribute, value: f.value })} aria-label={`Edit ${f.attribute.replace(/_/g, " ")}`}
                                          className="-my-2 -mr-2 flex h-11 w-11 items-center justify-center rounded-full text-sage-ink hover:bg-sage-tint/60"><PencilSimpleIcon size={18} /></button>}
                  </div>
                  <div className={cx("text-row font-semibold [overflow-wrap:anywhere]", !f.current && "line-through")}>{f.value}</div>
                  {(f.stale && f.current) || f.conflict || f.author === "user" ? (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {f.stale && f.current && <Chip tone="apricot">May have changed</Chip>}
                      {f.conflict ? <Chip tone="apricot">Conflicts with your edit</Chip> : null}
                      {f.author === "user" && <Chip>Your edit</Chip>}
                    </div>
                  ) : null}
                  <div className="mt-1.5 flex flex-col">
                    {f.sources.map((s) => (
                      <div key={s.id} className="flex items-center justify-between gap-2 text-meta-2 text-muted">
                        <span className="min-w-0 [overflow-wrap:anywhere]">Seen in {s.where}</span>
                        <button onClick={() => deleteSource(s.id, s.where)} aria-label={`Delete the source: ${s.where}`}
                                className="-mr-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-full hover:bg-well"><TrashIcon size={16} /></button>
                      </div>
                    ))}
                  </div>
                  {!f.current && <div className="text-meta-2 text-muted">replaced {f.valid_to ? ago(f.valid_to) : ""}</div>}
                </li>
              ))}
            </ul>
            {edit && (
              <div className="rounded-block border border-sage bg-surface p-4">
                <label htmlFor="fact-edit" className="text-meta text-ink-2">Edit {edit.attribute.replace(/_/g, " ")}. Your edit outranks what Envoy reads.</label>
                <input id="fact-edit" value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })}
                       className="mt-2 h-11 w-full rounded-full border border-control bg-surface px-4 text-[16px] outline-none focus:border-sage md:text-body" />
                <div className="mt-3 flex gap-2"><Button variant="primary" onClick={saveEdit}>Save</Button><Button onClick={() => setEdit(null)}>Cancel</Button></div>
              </div>
            )}
            {entity.links.length > 0 && (
              <div>
                <SectionLabel className="mb-1.5">Linked</SectionLabel>
                <ul>
                  {entity.links.map((l) => (
                    <li key={l.id + l.relation}><button onClick={() => setSelected(l.id)} className="flex min-h-[44px] items-center gap-1.5 text-left text-row text-sage-ink hover:text-sage-deep">
                      <span className="text-muted">{l.relation.replace(/_/g, " ")}</span> {l.type} {l.name}</button></li>
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
