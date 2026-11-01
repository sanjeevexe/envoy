"use client";

// Memory: the graph of what Envoy remembers (components/GraphCanvas.tsx), edge to edge, with the search box, the groups
// (each toggles its nodes), zoom and fit floating over it. Select something to see its facts, where each was seen, and
// its history; edit a fact (your edit outranks anything Envoy read) or delete a source (its facts go with it). Focus shows
// only the selection's neighborhood, one or two links out. With nothing selected, you can tell Envoy your usual order
// from a place (memory/usual.py), which "order my usual from …" then uses. On the Mac the facts are the right column; on
// the iPhone they're a sheet. A visually hidden list of every thing keeps it all reachable by keyboard and screen reader.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CrosshairSimpleIcon, FrameCornersIcon, ListBulletsIcon, MagnifyingGlassIcon, MinusIcon, PencilSimpleIcon, PlusIcon, TrashIcon, XIcon,
} from "@phosphor-icons/react";
import GraphCanvas, { groupOf, type GEdge, type GNode, type GraphControls, type Group } from "@/components/GraphCanvas";
import Sheet from "@/components/Sheet";
import { Button, Chip, cx, IconButton, SectionLabel } from "@/components/ui";
import { api, ago, post } from "@/lib/api";

type Fact = { id: string; attribute: string; value: string; current: boolean; stale: boolean; conflict: number; author?: string;
  recorded_at: number; valid_to?: number | null; sources: { id: string; where: string }[] };
type Entity = { entity: { id: string; type: string; name: string }; facts: Fact[]; links: { relation: string; id: string; type: string; name: string }[] };

// The groups, as the graph tints them (GraphCanvas's palette, from the same tokens)
const GROUPS: { g: Group; label: string; dot: string }[] = [
  { g: "you", label: "You", dot: "var(--sage)" },
  { g: "travel", label: "Travel", dot: "color-mix(in srgb, var(--muted), var(--sage) 55%)" },
  { g: "shopping", label: "Shopping", dot: "color-mix(in srgb, var(--muted), var(--apricot) 60%)" },
  { g: "other", label: "Places and programs", dot: "var(--muted)" },
];
const STOP = new Set(["what", "does", "envoy", "remember", "remembers", "about", "the", "my", "is", "are", "was", "when", "where", "which", "who",
  "how", "do", "did", "for", "from", "of", "to", "in", "on", "at", "and", "or", "a", "an", "me", "i", "you", "your", "know", "tell", "show"]);

// Things a search names: its words in a thing's name or type ("SL 482", "Denver", "flights"), and the things the answer
// names in bold.
function matches(q: string, answer: string, nodes: GNode[]): Set<string> {
  const words = q.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w && !STOP.has(w) && (w.length > 2 || /\d/.test(w))).map((w) => w.replace(/s$/, ""));
  const bold = [...answer.matchAll(/\*\*([^*]+)\*\*/g)].map((m) => m[1].toLowerCase());
  return new Set(nodes.filter((n) => {
    const hay = `${n.name} ${n.type}`.toLowerCase();
    return words.some((w) => hay.includes(w)) || bold.some((b) => b.includes(n.name.split(" · ")[0].toLowerCase()) || hay.includes(b));
  }).map((n) => n.id));
}

export default function MemoryGraph({ version, mobile }: { version: number; mobile?: boolean }) {
  const [graph, setGraph] = useState<{ nodes: GNode[]; edges: GEdge[] }>({ nodes: [], edges: [] });
  const [selected, setSelected] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);  // the iPhone's facts sheet (closing it keeps the selection)
  const [entity, setEntity] = useState<Entity | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [edit, setEdit] = useState<{ attribute: string; value: string } | null>(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [marked, setMarked] = useState<Set<string> | null>(null);
  const [off, setOff] = useState<Set<Group>>(new Set());
  const [depth, setDepth] = useState<0 | 1 | 2>(0);  // Focus: only the selection's neighborhood, 1 or 2 links out
  const [pointed, setPointed] = useState<string | null>(null);
  const [usualOpen, setUsualOpen] = useState(false);
  const controls = useRef<GraphControls | null>(null);

  const reload = useCallback(() => api("/api/memory/graph").then(setGraph).catch(() => {}), []);
  useEffect(() => { reload(); }, [version, reload]);
  useEffect(() => { if (selected) api(`/api/memory/entity/${selected}`).then(setEntity).catch(() => setEntity(null)); else setEntity(null); }, [selected, version]);
  useEffect(() => { setEdit(null); if (!selected) setDepth(0); }, [selected]);

  const select = useCallback((id: string | null) => { setSelected(id); setSheet(!!id); }, []);
  const groups = useMemo(() => GROUPS.map((x) => ({ ...x, count: graph.nodes.filter((n) => groupOf(n.type) === x.g).length })).filter((x) => x.count), [graph]);
  const shown = useMemo(() => {
    if (depth && selected && graph.nodes.some((n) => n.id === selected)) {  // the local graph: breadth first from the selection
      const near = new Map<string, string[]>();
      for (const e of graph.edges) { (near.get(e.source) ?? near.set(e.source, []).get(e.source)!).push(e.target); (near.get(e.target) ?? near.set(e.target, []).get(e.target)!).push(e.source); }
      const seen = new Set([selected]);
      let ring = [selected];
      for (let d = 0; d < depth; d++) ring = ring.flatMap((id) => (near.get(id) ?? []).filter((x) => !seen.has(x) && (seen.add(x), true)));
      return seen;
    }
    return off.size ? new Set(graph.nodes.filter((n) => !off.has(groupOf(n.type)) || n.id === selected).map((n) => n.id)) : null;
  }, [graph, off, depth, selected]);

  const search = (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setMarked(matches(q, "", graph.nodes));
    api(`/api/memory/search?q=${encodeURIComponent(q)}`).then((r) => {
      const md = r.markdown || "Nothing relevant.";
      setAnswer(md);
      setMarked(matches(q, md, graph.nodes));
    }).catch(() => setAnswer("Couldn't search just now."));
  };
  const clearSearch = () => { setQ(""); setAnswer(null); setMarked(null); };

  const facts = (
    <Facts entity={entity} showHistory={showHistory} setShowHistory={setShowHistory} edit={edit} setEdit={setEdit} select={select}
           onClose={mobile ? () => setSheet(false) : () => select(null)}
           saveEdit={async () => {
             if (!edit || !selected) return;
             await post(`/api/memory/entity/${selected}/fact`, edit);
             setEdit(null);
             api(`/api/memory/entity/${selected}`).then(setEntity);
           }}
           deleteSource={async (sid, where) => {
             if (!confirm(`Delete the source "${where}"? Facts that only it supported are removed from memory.`)) return;
             await api(`/api/memory/source/${sid}`, { method: "DELETE" });
             reload();
             if (selected) api(`/api/memory/entity/${selected}`).then(setEntity).catch(() => select(null));
           }} />
  );
  const usual = <Usual onSaved={(id) => { reload(); setUsualOpen(false); select(id); }} />;
  const name = graph.nodes.find((n) => n.id === selected)?.name;

  return (
    <div className="flex h-full min-h-0">
      <div className="relative min-w-0 flex-1 overflow-hidden bg-page">
        <GraphCanvas nodes={graph.nodes} edges={graph.edges} shown={shown} selected={selected} onSelect={select} marked={marked} pointed={pointed}
                     controls={controls} padTop={mobile ? 76 : 84} padBottom={mobile ? 76 : 70}
                     label={`Memory graph: ${graph.nodes.length} things and ${graph.edges.length} links. The list of things after it selects one.`} />
        <ul className="sr-only" aria-label="Things in memory">
          {graph.nodes.map((n) => (
            <li key={n.id}><button onClick={() => select(n.id)} onFocus={() => setPointed(n.id)} onBlur={() => setPointed(null)} aria-pressed={selected === n.id}>
              {n.type}: {n.name}{n.stale ? " (may be out of date)" : ""}</button></li>
          ))}
        </ul>

        {/* top: search (and its answer); the selection's Focus */}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start gap-2 p-3 md:p-4">
          <div className="pointer-events-auto flex min-w-0 max-w-[420px] flex-1 flex-col gap-2">
            <form role="search" onSubmit={search}
                  className="flex h-12 items-center gap-1 rounded-full border border-control bg-surface/95 pl-4 pr-1 shadow-[0_1px_2px_rgba(31,42,36,0.06)] backdrop-blur focus-within:border-sage">
              <MagnifyingGlassIcon size={18} className="shrink-0 text-muted" />
              <input value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) clearSearch(); }} aria-label="Search memory" enterKeyHint="search"
                     placeholder="What does Envoy remember about…" className="min-w-0 flex-1 bg-transparent px-2 text-[16px] outline-none placeholder:text-muted md:text-body" />
              {(answer || marked) ? <IconButton label="Clear the search" type="button" onClick={clearSearch}><XIcon size={18} /></IconButton>
                : !mobile && <Button variant="primary" className="h-10">Search</Button>}
            </form>
            {answer && (
              <div role="status" className="max-h-[38vh] overflow-auto rounded-block border border-line bg-surface/95 px-4 py-3 text-meta text-ink-2 backdrop-blur [overflow-wrap:anywhere]">
                {answer.split(/\*\*([^*]+)\*\*/g).map((part, i) => (i % 2 ? <b key={i} className="text-ink">{part}</b> : part))}
                {marked && <p className="mt-1.5 text-meta-2 text-muted">{marked.size ? `${marked.size} lit in the graph` : "Nothing in the graph matches it by name."}</p>}
              </div>
            )}
          </div>
          {mobile && !selected && (
            <Button className="pointer-events-auto h-12 shrink-0 bg-surface/95" onClick={() => setUsualOpen(true)}>Your usual</Button>
          )}
        </div>
        {selected && (
          <div className={cx("pointer-events-auto absolute right-3 flex items-center gap-1.5 rounded-full border border-line bg-surface/95 p-1 backdrop-blur md:right-4 md:top-4",
                             mobile ? "top-[72px]" : "top-4")} role="group" aria-label={`Focus on ${name ?? "the selection"}`}>
            <button onClick={() => setDepth(depth ? 0 : 1)} aria-pressed={!!depth}
                    className={cx("flex h-9 items-center gap-1.5 rounded-full px-3 text-meta font-bold transition-colors", depth ? "bg-sage text-white" : "text-ink-2 hover:bg-well")}>
              <CrosshairSimpleIcon size={16} />Focus</button>
            {!!depth && ([1, 2] as const).map((d) => (
              <button key={d} onClick={() => setDepth(d)} aria-pressed={depth === d} aria-label={`${d} link${d > 1 ? "s" : ""} out`}
                      className={cx("h-9 min-w-[36px] rounded-full px-2.5 text-meta font-bold", depth === d ? "bg-sage-tint text-sage-ink" : "text-muted hover:bg-well")}>{d}</button>
            ))}
            {mobile && !sheet && <button onClick={() => setSheet(true)} className="flex h-9 items-center gap-1.5 rounded-full px-3 text-meta font-bold text-sage-ink hover:bg-well">
              <ListBulletsIcon size={16} />Facts</button>}
          </div>
        )}

        {/* bottom: the groups (each toggles its nodes) and the legend; zoom and fit */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end gap-2 p-3 md:p-4">
          <div className="pointer-events-auto flex min-w-0 flex-1 flex-col gap-1.5">
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Groups">
              {groups.map(({ g, label, dot, count }) => (
                <button key={g} onClick={() => setOff((s) => { const n = new Set(s); if (n.has(g)) n.delete(g); else n.add(g); return n; })} aria-pressed={!off.has(g)}
                        className={cx("flex h-9 items-center gap-1.5 rounded-full border px-3 text-meta-2 font-semibold backdrop-blur transition-colors",
                          off.has(g) ? "border-line bg-page/80 text-muted line-through decoration-1" : "border-line bg-surface/90 text-ink-2 hover:border-line-strong")}>
                  <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: dot, opacity: off.has(g) ? 0.4 : 1 }} />{label}<span className="text-muted">{count}</span>
                </button>
              ))}
            </div>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-meta-2 text-muted">
              <span>{graph.nodes.length} things · {graph.edges.length} links</span>
              <span className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-2.5 rounded-full border-[1.5px] border-apricot" />may be out of date</span>
              <span className="flex items-center gap-1.5"><span aria-hidden className="h-1.5 w-1.5 rounded-full bg-ink" />you edited it</span>
            </p>
          </div>
          <div className="pointer-events-auto flex shrink-0 flex-col gap-1.5 md:flex-row">
            <IconButton label="Zoom in" variant="surface" onClick={() => controls.current?.zoomBy(1.4)}><PlusIcon size={18} /></IconButton>
            <IconButton label="Zoom out" variant="surface" onClick={() => controls.current?.zoomBy(1 / 1.4)}><MinusIcon size={18} /></IconButton>
            <IconButton label="Fit the graph" variant="surface" onClick={() => controls.current?.fit()}><FrameCornersIcon size={18} /></IconButton>
          </div>
        </div>
        {graph.nodes.length === 0 && (
          <p className="absolute inset-x-0 top-1/2 px-8 text-center text-body text-muted">Nothing remembered yet. What Envoy reads in your apps and emails shows up here.</p>
        )}
      </div>

      {!mobile && (
        <aside aria-label="Facts" className="w-[380px] shrink-0 overflow-y-auto border-l border-line bg-raised p-6">
          {selected ? facts : (
            <div className="flex flex-col gap-5">
              <p className="text-body text-muted">Select something in the graph to see what Envoy knows about it, and where each fact was seen.</p>
              {usual}
            </div>
          )}
        </aside>
      )}
      {mobile && selected && sheet && <Sheet label={name ?? "Facts"} onClose={() => setSheet(false)}>{facts}</Sheet>}
      {mobile && usualOpen && <Sheet label="Your usual" onClose={() => setUsualOpen(false)}>{usual}</Sheet>}
    </div>
  );
}

function Facts({ entity, showHistory, setShowHistory, edit, setEdit, select, onClose, saveEdit, deleteSource }: {
  entity: Entity | null; showHistory: boolean; setShowHistory: (v: boolean) => void; edit: { attribute: string; value: string } | null;
  setEdit: (e: { attribute: string; value: string } | null) => void; select: (id: string) => void; onClose: () => void; saveEdit: () => void;
  deleteSource: (sid: string, where: string) => void;
}) {
  if (!entity) return <p className="py-6 text-body text-muted" aria-busy="true">Loading…</p>;
  const facts = entity.facts.filter((f) => showHistory || f.current);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-meta font-bold text-muted">{entity.entity.type}</div>
          <h2 className="mt-0.5 text-title font-bold [overflow-wrap:anywhere]">{entity.entity.name}</h2>
        </div>
        <IconButton label="Close" onClick={onClose} className="-mr-2 -mt-1"><XIcon size={18} /></IconButton>
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
              <li key={l.id + l.relation}><button onClick={() => select(l.id)} className="flex min-h-[44px] items-center gap-1.5 text-left text-row text-sage-ink hover:text-sage-deep">
                <span className="text-muted">{l.relation.replace(/_/g, " ")}</span> {l.type} {l.name}</button></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// Your usual: what you always get from a place. Ask for "my usual from …" and Envoy orders it.
function Usual({ onSaved }: { onSaved: (entity: string) => void }) {
  const [usual, setUsual] = useState({ place: "", order: "", app: "" });
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      const r = await post<{ entity: string }>("/api/memory/usual", usual);
      setUsual({ place: "", order: "", app: "" });
      setError(null);
      onSaved(r.entity);
    } catch {
      setError("Couldn't save it: a place and an order are needed.");
    }
  };
  return (
    <form className="flex flex-col gap-2 rounded-block border border-line bg-surface p-4" aria-labelledby="usual-title"
          onSubmit={(e) => { e.preventDefault(); if (usual.place.trim() && usual.order.trim()) save(); }}>
      <SectionLabel id="usual-title">Your usual</SectionLabel>
      <p className="text-meta text-ink-2">What you always get from a place. Ask for &ldquo;my usual from&nbsp;…&rdquo; and Envoy orders it.</p>
      {([["place", "Place", "Thai Basil"], ["order", "Order", "a pad see ew and a Thai iced tea"], ["app", "App you order it on (optional)", ""]] as const).map(([k, label, hint]) => (
        <label key={k} className="flex flex-col gap-1 text-meta text-ink-2">{label}
          <input value={usual[k]} onChange={(e) => setUsual({ ...usual, [k]: e.target.value })} placeholder={hint}
                 className="h-11 w-full rounded-full border border-control bg-surface px-4 text-[16px] text-ink outline-none placeholder:text-muted focus:border-sage md:text-body" />
        </label>
      ))}
      {error && <p role="alert" className="text-meta text-brick">{error}</p>}
      <Button variant="primary" className="mt-1 self-start" disabled={!usual.place.trim() || !usual.order.trim()}>Save</Button>
    </form>
  );
}
