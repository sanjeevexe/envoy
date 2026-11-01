"use client";

// The memory graph, drawn here on a Canvas 2D element over a live force simulation (d3-force; d3-zoom for pan and pinch,
// d3-quadtree to find the node under the pointer). Quiet neutral nodes sized by how connected they are, with a soft
// tint by group (travel sage, shopping apricot) and "you" larger in sage; hairline links with no labels or arrows;
// names under the nodes that fade as you zoom out. Hovering a node lights it, its neighbors and their links in the sage
// accent and dims the rest; dragging one pulls its neighbors along. On open the nodes bloom out from the center and the
// view follows them until it fits; under prefers-reduced-motion the layout settles before the first frame.
import { useEffect, useRef } from "react";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { quadtree, type Quadtree } from "d3-quadtree";
import { pointers, select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";

export type GNode = { id: string; type: string; name: string; facts: number; stale: boolean; user_edited: boolean };
export type GEdge = { id: string; source: string; target: string; relation: string };
export type Group = "you" | "travel" | "shopping" | "other";
export const GROUP_TYPES: Record<Exclude<Group, "you" | "other">, string[]> = {
  travel: ["Trip", "Flight", "Reservation", "Hotel"],
  shopping: ["Order", "Item", "Usual"],
};
export const groupOf = (type: string): Group =>
  type === "Person" ? "you" : GROUP_TYPES.travel.includes(type) ? "travel" : GROUP_TYPES.shopping.includes(type) ? "shopping" : "other";
// The label under a node: the name's first part ("SL 482" of "SL 482 · Fri, Oct 30, 2026"); hovering shows it whole.
export const shortName = (name: string) => name.split(" · ")[0] || name;

type N = GNode & SimulationNodeDatum & { r: number; degree: number; group: Group; you: boolean };
type L = SimulationLinkDatum<N> & { id: string; relation: string; source: N; target: N };
export type GraphControls = { zoomBy: (f: number) => void; fit: () => void };

type Props = {
  nodes: GNode[]; edges: GEdge[];
  shown: Set<string> | null;  // the nodes to show (group filters, Focus); null: all of them
  selected: string | null; onSelect: (id: string | null) => void;
  marked: Set<string> | null;  // search matches, lit until the search is cleared
  pointed: string | null;  // a node focused from the list of things (keyboard): drawn as hovered
  controls: React.MutableRefObject<GraphControls | null>;
  label: string; padTop?: number; padBottom?: number;
};

const FONT = '"Manrope Variable", Manrope, system-ui, sans-serif';
const HOVER_DELAY = 100, EASE_MS = 150, MAX_FIT = 1.7, MIN_K = 0.12, MAX_K = 6;

// Colors come from the tokens in globals.css, read again when the theme changes.
type Palette = { page: string; node: string; accent: string; travel: string; shopping: string; apricot: string; link: string; label: string; strong: string; muted: string };
const hex = (c: string) => { const h = c.replace("#", ""); const f = h.length === 3 ? h.split("").map((x) => x + x).join("") : h; return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16)); };
const mix = (a: string, b: string, t: number) => `rgb(${hex(a).map((v, i) => Math.round(v + (hex(b)[i] - v) * t)).join(",")})`;
function palette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim() || "#888888";
  const dark = document.documentElement.dataset.theme === "dark";  // Settings › Appearance (lib/theme.ts)
  const node = v("--muted"), accent = dark ? v("--sage-ink") : v("--sage"), apricot = dark ? v("--apricot-ink") : v("--apricot");
  return { page: v("--page"), node, accent, travel: mix(node, accent, dark ? 0.5 : 0.42), shopping: mix(node, apricot, dark ? 0.45 : 0.45), apricot,
    link: dark ? v("--line-strong") : mix(v("--line-strong"), v("--muted"), 0.18), label: v("--ink-2"), strong: v("--ink"), muted: v("--muted") };
}

const ease = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
const smooth = (a: number, b: number, x: number) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

class Engine {
  canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; dpr = 1; w = 0; h = 0;
  nodes: N[] = []; links: L[] = []; byId = new Map<string, N>(); adj = new Map<string, Set<string>>();
  active: N[] = []; activeLinks: L[] = []; tree: Quadtree<N> | null = null;
  sim: Simulation<N, L>; zoomer: ZoomBehavior<HTMLCanvasElement, unknown>; t: ZoomTransform = zoomIdentity;
  pal: Palette; reduced: boolean; follow = true; fresh = true; dirty = true; raf = 0; padTop = 72; padBottom = 72;
  hover: string | null = null; hoverShown: string | null = null; hoverAt = 0; hoverFrom = 0; hoverLevel = 0; hoverTimer: ReturnType<typeof setTimeout> | null = null;
  selected: string | null = null; marked: Set<string> | null = null; pointed: string | null = null; shown: Set<string> | null = null;
  drag: { n: N; x: number; y: number; moved: boolean; id: number } | null = null; dragged = false;
  tapped: string | null = null; tapTimer: ReturnType<typeof setTimeout> | null = null;
  onSelect: (id: string | null) => void = () => {};
  stop: () => void;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.pal = palette();
    this.reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.sim = forceSimulation<N, L>().stop().on("tick", () => { this.dirty = true; this.tree = null; });
    this.zoomer = zoom<HTMLCanvasElement, unknown>().scaleExtent([MIN_K, MAX_K])
      .filter((ev: any) => {
        if (ev.type === "wheel") return true;
        if (ev.type === "dblclick" || ev.button) return false;
        if (ev.touches?.length > 1) { this.endDrag(); return true; }  // a second finger: pinch, whatever the first one held
        const [p] = pointers(ev, canvas);
        return !p || !this.hit(p[0], p[1]);  // a node under the finger is dragged, not panned
      })
      .on("zoom", (ev) => { this.t = ev.transform; if (ev.sourceEvent) this.follow = false; this.dirty = true; });
    const sel = select(canvas).call(this.zoomer).on("dblclick.zoom", null);

    const resize = new ResizeObserver(() => this.resize());
    resize.observe(canvas);
    // the theme is data-theme on <html> (lib/theme.ts): read the tokens again whenever it changes
    const theme = new MutationObserver(() => { this.pal = palette(); this.dirty = true; });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const down = (e: PointerEvent) => this.down(e), move = (e: PointerEvent) => this.move(e), up = (e: PointerEvent) => this.up(e);
    const leave = () => this.setHover(null), click = (e: MouseEvent) => this.click(e);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("pointerleave", leave);
    canvas.addEventListener("click", click);
    document.fonts?.ready.then(() => { this.dirty = true; });  // names in Manrope once it's loaded
    const frame = () => { this.frame(); this.raf = requestAnimationFrame(frame); };
    this.raf = requestAnimationFrame(frame);
    this.stop = () => {
      cancelAnimationFrame(this.raf); this.sim.stop(); resize.disconnect(); theme.disconnect(); sel.on(".zoom", null);
      canvas.removeEventListener("pointerdown", down); canvas.removeEventListener("pointermove", move); canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up); canvas.removeEventListener("pointerleave", leave); canvas.removeEventListener("click", click);
      if (this.hoverTimer) clearTimeout(this.hoverTimer);
      if (this.tapTimer) clearTimeout(this.tapTimer);
    };
    this.resize();
  }

  resize() {
    const r = this.canvas.getBoundingClientRect();
    this.dpr = window.devicePixelRatio || 1;
    this.w = r.width; this.h = r.height;
    this.canvas.width = Math.max(1, Math.round(r.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * this.dpr));
    this.dirty = true;
    if (this.follow) this.fitNow(!this.fresh);
  }

  // ---- the data ------------------------------------------------------------------------------------------------

  setData(nodes: GNode[], edges: GEdge[]) {
    const old = this.byId;
    this.adj = new Map(nodes.map((n) => [n.id, new Set<string>()]));
    const ok = edges.filter((e) => this.adj.has(e.source) && this.adj.has(e.target) && e.source !== e.target);
    ok.forEach((e) => { this.adj.get(e.source)!.add(e.target); this.adj.get(e.target)!.add(e.source); });
    // "you": the Person with the most links
    const you = nodes.filter((n) => n.type === "Person").sort((a, b) => this.adj.get(b.id)!.size - this.adj.get(a.id)!.size)[0]?.id;
    const first = old.size === 0, many = nodes.length > 60;
    this.nodes = nodes.map((n, i) => {
      const prev = old.get(n.id);
      const degree = this.adj.get(n.id)!.size;
      // size by links and facts, in a small range (smaller when there are many)
      const r = n.id === you ? (many ? 9 : 11) : many ? Math.min(6.5, 2.6 + 0.9 * Math.sqrt(degree + n.facts / 3)) : Math.min(9, 3.6 + 1.5 * Math.sqrt(degree + n.facts / 3));
      // a new node starts next to a neighbor that's already placed, else close to the center (the bloom)
      const near = prev ?? [...this.adj.get(n.id)!].map((id) => old.get(id)).find(Boolean);
      const a = i * 2.39996, d = first ? 2 + 1.5 * Math.sqrt(i) : 8;
      return { ...n, r, degree, group: groupOf(n.type), you: n.id === you,
        x: prev?.x ?? (near?.x ?? 0) + d * Math.cos(a), y: prev?.y ?? (near?.y ?? 0) + d * Math.sin(a), vx: prev?.vx, vy: prev?.vy };
    });
    this.byId = new Map(this.nodes.map((n) => [n.id, n]));
    this.links = ok.map((e) => ({ id: e.id, relation: e.relation, source: this.byId.get(e.source)!, target: this.byId.get(e.target)! }));
    if (first && this.nodes.length) this.fresh = true;
    this.restart(first ? 1 : 0.5);
    if (first && this.nodes.length && !this.reduced) { const t = this.fitTarget(); if (t) this.setTransform(t); }  // bloom from the middle
  }

  setShown(shown: Set<string> | null) {
    if (shown === this.shown || (shown && this.shown && shown.size === this.shown.size && [...shown].every((id) => this.shown!.has(id)))) return;
    this.shown = shown;
    this.follow = true;  // a different set of nodes: fit it again
    this.restart(0.6);
  }

  restart(alpha: number) {
    const shown = this.shown;
    this.active = shown ? this.nodes.filter((n) => shown.has(n.id)) : this.nodes;
    const on = new Set(this.active.map((n) => n.id));
    this.activeLinks = this.links.filter((l) => on.has(l.source.id) && on.has(l.target.id));
    const n = this.active.length, small = n < 40;
    // tuned so 10–30 nodes spread out with room for their names, and 150 stay apart; a thing with no links is pulled
    // in harder, so it sits near the rest instead of drifting to the edge
    const pull = (d: N) => (!this.linked(d) ? 0.11 : small ? 0.07 : 0.03);
    this.sim.nodes(this.active)
      .force("link", forceLink<N, L>(this.activeLinks).id((d) => d.id).distance((l) => (small ? 58 : 30 + 4 * Math.sqrt(Math.min(this.deg(l.source), this.deg(l.target)))))
        .strength((l) => 0.9 / Math.min(this.deg(l.source), this.deg(l.target))))
      .force("charge", forceManyBody<N>().strength((d) => (small ? -260 : -110 - 6 * Math.min(d.degree, 10))).distanceMax(small ? 600 : 460))
      .force("x", forceX<N>(0).strength(pull))
      .force("y", forceY<N>(0).strength(pull))
      .force("collide", forceCollide<N>((d) => d.r + (small ? 10 : 3)))
      .alpha(alpha);
    this.tree = null;
    if (this.reduced || !n) {  // settle before drawing: no drift
      this.sim.stop();
      this.sim.tick(Math.ceil(Math.log(this.sim.alphaMin()) / Math.log(1 - this.sim.alphaDecay())));
      this.fitNow(false);
    } else this.sim.restart();
    this.dirty = true;
  }

  deg(n: N) { return Math.max(1, this.adj.get(n.id)?.size ?? 1); }
  linked(n: N) { return this.activeLinks.some((l) => l.source === n || l.target === n); }

  // ---- the camera ----------------------------------------------------------------------------------------------

  fitTarget(): ZoomTransform | null {
    if (!this.active.length || !this.w) return null;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of this.active) {
      const half = Math.max(n.r, shortName(n.name).length * 3.4);  // room for its name, about as wide as it's drawn
      x0 = Math.min(x0, n.x! - half); x1 = Math.max(x1, n.x! + half);
      y0 = Math.min(y0, n.y! - n.r); y1 = Math.max(y1, n.y! + n.r + 18);
    }
    const side = Math.min(48, this.w * 0.06), top = this.padTop, bottom = this.padBottom;
    const k = Math.min(MAX_FIT, (this.w - 2 * side) / Math.max(1, x1 - x0), (this.h - top - bottom) / Math.max(1, y1 - y0));
    const kk = Math.max(MIN_K, k);
    return zoomIdentity.translate(this.w / 2 - kk * (x0 + x1) / 2, top + (this.h - top - bottom) / 2 - kk * (y0 + y1) / 2).scale(kk);
  }

  setTransform(t: ZoomTransform) { this.zoomer.transform(select(this.canvas), t); }

  fitNow(animate: boolean) {
    const t = this.fitTarget();
    if (!t) return;
    if (animate && !this.reduced) { this.follow = true; this.dirty = true; } else this.setTransform(t);
  }

  zoomBy(f: number) {
    this.follow = false;
    const t = this.t, cx = this.w / 2, cy = this.h / 2;
    const k = Math.min(MAX_K, Math.max(MIN_K, t.k * f));
    this.setTransform(zoomIdentity.translate(cx - (cx - t.x) * (k / t.k), cy - (cy - t.y) * (k / t.k)).scale(k));
  }

  // ---- pointer ---------------------------------------------------------------------------------------------------

  hit(px: number, py: number): N | null {
    if (!this.active.length) return null;
    if (!this.tree) this.tree = quadtree<N>().x((d) => d.x!).y((d) => d.y!).addAll(this.active);
    const [x, y] = this.t.invert([px, py]);
    const slack = 8 / this.t.k;  // a finger's worth of room, whatever the zoom
    const n = this.tree.find(x, y, 12 + slack);
    return n && Math.hypot(n.x! - x, n.y! - y) <= n.r + slack ? n : null;
  }

  at(e: { clientX: number; clientY: number }) { const r = this.canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }

  down(e: PointerEvent) {
    if (e.button || this.drag) return;
    const [x, y] = this.at(e);
    const n = this.hit(x, y);
    if (!n) return;
    e.preventDefault();
    this.canvas.setPointerCapture(e.pointerId);
    this.drag = { n, x, y, moved: false, id: e.pointerId };
    this.dragged = false;
    n.fx = n.x; n.fy = n.y;
  }

  move(e: PointerEvent) {
    const [x, y] = this.at(e);
    const d = this.drag;
    if (d && d.id === e.pointerId) {
      if (!d.moved && Math.hypot(x - d.x, y - d.y) < 4) return;
      if (!d.moved) { d.moved = true; this.sim.alphaTarget(0.25).restart(); this.setHover(d.n.id); }  // its neighborhood lights up, by touch too
      const [wx, wy] = this.t.invert([x, y]);
      d.n.fx = wx; d.n.fy = wy;
      this.dirty = true;
      return;
    }
    if (e.pointerType === "mouse" && !e.buttons) {
      const n = this.hit(x, y);
      this.canvas.style.cursor = n ? "pointer" : "grab";
      this.setHover(n?.id ?? null);
    }
  }

  up(e: PointerEvent) {
    const d = this.drag;
    if (!d || d.id !== e.pointerId) return;
    this.drag = null;
    if (d.moved) { this.dragged = true; this.sim.alphaTarget(0); if (e.pointerType !== "mouse") this.setHover(null); }
    d.n.fx = null; d.n.fy = null;  // let go: it settles back among its neighbors
    if (d.moved || e.type !== "pointerup") return;
    if (e.pointerType === "mouse") { this.onSelect(d.n.id); return; }
    // a tap selects on the click that follows it: selecting now would open the phone's sheet under the finger, and that
    // click would land on the sheet's backdrop and close it again
    this.tapped = d.n.id;
    if (this.tapTimer) clearTimeout(this.tapTimer);
    this.tapTimer = setTimeout(() => this.takeTap(), 450);
  }

  takeTap() {
    if (this.tapTimer) clearTimeout(this.tapTimer);
    const id = this.tapped;
    this.tapped = null;
    if (id) this.onSelect(id);
  }

  endDrag() {
    if (!this.drag) return;
    this.drag.n.fx = null; this.drag.n.fy = null;
    this.drag = null;
    this.sim.alphaTarget(0);
    this.setHover(null);
  }

  click(e: MouseEvent) {  // a click on empty space clears the selection (a drag or a pan doesn't)
    if (this.tapped) { this.takeTap(); return; }
    if (this.dragged) { this.dragged = false; return; }
    const [x, y] = this.at(e);
    if (!this.hit(x, y) && this.selected) this.onSelect(null);
  }

  setHover(id: string | null) {
    if (id === this.hover) return;
    this.hover = id;
    if (this.hoverTimer) clearTimeout(this.hoverTimer);
    const apply = () => { this.hoverFrom = this.hoverLevel; this.hoverAt = performance.now(); if (this.hover) this.hoverShown = this.hover; this.dirty = true; };
    // a short wait before lighting up, so passing over nodes doesn't flicker; leaving is at once
    if (id && !this.reduced) this.hoverTimer = setTimeout(apply, this.hoverShown && this.hoverLevel > 0 ? 0 : HOVER_DELAY);
    else apply();
  }

  // ---- drawing ---------------------------------------------------------------------------------------------------

  frame() {
    const now = performance.now();
    const lit = this.pointed ?? this.hover;
    // the hover's strength eases in and out over ~150 ms
    const goal = this.pointed ? 1 : this.hover && this.hoverShown === this.hover ? 1 : 0;
    if (this.pointed) this.hoverShown = this.pointed;
    const level = this.reduced || this.pointed ? goal : this.hoverFrom + (goal - this.hoverFrom) * ease((now - this.hoverAt) / EASE_MS);
    if (Math.abs(level - this.hoverLevel) > 0.001) { this.hoverLevel = level; this.dirty = true; }
    if (level === 0 && !lit) this.hoverShown = null;

    if (this.follow && this.active.length) {  // the bloom: the view follows the nodes until they settle, then stops
      const t = this.fitTarget();
      if (t) {
        const f = this.fresh ? 0.12 : 0.18;
        const nt = zoomIdentity.translate(this.t.x + (t.x - this.t.x) * f, this.t.y + (t.y - this.t.y) * f).scale(this.t.k + (t.k - this.t.k) * f);
        if (Math.abs(nt.k - this.t.k) > 1e-4 || Math.abs(nt.x - this.t.x) > 0.05 || Math.abs(nt.y - this.t.y) > 0.05) this.setTransform(nt);
        else if (this.sim.alpha() < 0.05) { this.follow = false; this.fresh = false; }
      }
    }
    if (!this.dirty) return;
    this.dirty = false;
    this.draw();
  }

  draw() {
    const { ctx, pal, t } = this;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.w, this.h);
    const focus = this.hoverShown && this.hoverLevel > 0 ? this.hoverShown : null;
    const near = focus ? this.adj.get(focus) ?? new Set<string>() : null;
    const lvl = this.hoverLevel;
    const marked = this.marked && this.marked.size ? this.marked : null;
    const dim = (id: string) => {  // how far back a node sits: hover and a search both light some and dim the rest
      let a = 1;
      if (focus) a *= id === focus || near!.has(id) ? 1 : 1 - 0.85 * lvl;
      else if (marked) a *= marked.has(id) ? 1 : 0.3;
      return a;
    };
    const k = t.k, X = (n: N) => t.x + k * n.x!, Y = (n: N) => t.y + k * n.y!;
    const R = (n: N) => n.r * Math.min(k, 1.9) ** 0.9;

    // links: hairlines, lit in the accent when they touch the hovered node
    ctx.lineCap = "round";
    for (const l of this.activeLinks) {
      const lit = focus && (l.source.id === focus || l.target.id === focus);
      const a = lit ? 1 : Math.min(dim(l.source.id), dim(l.target.id)) * (marked && !focus && !(marked.has(l.source.id) && marked.has(l.target.id)) ? 0.6 : 1);
      ctx.globalAlpha = lit ? 0.35 + 0.65 * lvl : a * 0.9;
      ctx.strokeStyle = lit ? pal.accent : pal.link;
      ctx.lineWidth = lit ? 1.4 : Math.max(0.6, Math.min(1.2, 0.5 + 0.4 * k));
      ctx.beginPath(); ctx.moveTo(X(l.source), Y(l.source)); ctx.lineTo(X(l.target), Y(l.target)); ctx.stroke();
    }

    // nodes
    for (const n of this.active) {
      const x = X(n), y = Y(n), r = R(n), a = dim(n.id);
      if (x < -40 || y < -40 || x > this.w + 40 || y > this.h + 40) continue;
      ctx.globalAlpha = a;
      ctx.fillStyle = n.you ? pal.accent : n.group === "travel" ? pal.travel : n.group === "shopping" ? pal.shopping : pal.node;
      if (focus && (n.id === focus || near!.has(n.id)) && !n.you && n.group === "other") ctx.fillStyle = mix(pal.node, pal.accent, 0.35 * lvl);
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      if (n.stale) {  // facts that may be out of date: a thin apricot ring
        ctx.strokeStyle = pal.apricot; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, Math.PI * 2); ctx.stroke();
      }
      if (n.user_edited) {  // something you edited: a tiny dot
        ctx.fillStyle = pal.strong; ctx.strokeStyle = pal.page; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(x + r * 0.75, y - r * 0.75, 2.2, 0, Math.PI * 2); ctx.stroke(); ctx.fill();
      }
      const ring = n.id === this.selected ? 2 : n.id === focus ? 1.5 * lvl : marked?.has(n.id) && !focus ? 1.5 : 0;
      if (ring) {
        ctx.globalAlpha = n.id === this.selected ? 1 : a;
        ctx.strokeStyle = pal.accent; ctx.lineWidth = ring;
        ctx.beginPath(); ctx.arc(x, y, r + (n.stale ? 5.5 : 4), 0, Math.PI * 2); ctx.stroke();
      }
    }

    // names: they fade as you zoom out (sooner for small, less connected nodes); the hovered node, its neighbors, the
    // selection and search matches always say theirs
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    const size = 11.5 * Math.min(1.25, Math.max(0.85, k ** 0.5));
    const many = this.active.length > 60;
    for (const n of this.active) {
      const x = X(n), y = Y(n);
      if (x < -120 || y < -40 || x > this.w + 120 || y > this.h + 40) continue;
      const shout = n.id === focus || n.id === this.selected || (!!focus && near!.has(n.id)) || (!focus && !!marked?.has(n.id));
      // a big graph's overview shows only "you"; names come in as you zoom (hubs first)
      const from = n.you ? 0 : many ? (n.degree >= 6 ? 1.05 : 1.45) : n.degree >= 4 ? 0.4 : 0.6;
      let a = shout ? 1 : smooth(from, from + 0.3, k) * dim(n.id);
      if (focus && !shout) a *= 1 - lvl * 0.9;
      if (a < 0.03) continue;
      const main = n.id === focus;
      ctx.globalAlpha = a;
      ctx.font = `${main || n.id === this.selected ? 700 : n.you ? 650 : 550} ${size}px ${FONT}`;
      ctx.fillStyle = main || n.id === this.selected ? pal.strong : pal.label;
      ctx.lineWidth = 3; ctx.strokeStyle = pal.page; ctx.lineJoin = "round";
      const text = main ? n.name : shortName(n.name);
      const ty = y + R(n) + (n.stale ? 6 : 4);
      ctx.strokeText(text, x, ty); ctx.fillText(text, x, ty);  // a halo in the page's color keeps names legible over links
      if (main) {
        ctx.font = `500 ${size * 0.88}px ${FONT}`; ctx.fillStyle = pal.muted;
        ctx.strokeText(n.type, x, ty + size * 1.3); ctx.fillText(n.type, x, ty + size * 1.3);
      }
    }

    // the hovered node's relations, on its links ("travels on"): only while hovering
    if (focus && lvl > 0.2) {
      ctx.font = `500 ${size * 0.85}px ${FONT}`; ctx.textBaseline = "middle";
      const f = this.byId.get(focus)!, fy = Y(f) + R(f) + 4;
      const taken = [{ x0: X(f) - 90, x1: X(f) + 90, y0: fy, y1: fy + size * 2.4 }];  // the hovered node's name and type
      for (const l of this.activeLinks) {
        if (l.source.id !== focus && l.target.id !== focus) continue;
        const text = l.relation.replace(/_/g, " "), w = ctx.measureText(text).width;
        if (Math.hypot(X(l.source) - X(l.target), Y(l.source) - Y(l.target)) < w + 2 * R(l.source) + 2 * R(l.target) + 24) continue;  // only where it fits
        const x = (X(l.source) + X(l.target)) / 2, y = (Y(l.source) + Y(l.target)) / 2;
        const box = { x0: x - w / 2 - 3, x1: x + w / 2 + 3, y0: y - size * 0.6, y1: y + size * 0.6 };
        if (taken.some((b) => box.x0 < b.x1 && b.x0 < box.x1 && box.y0 < b.y1 && b.y0 < box.y1)) continue;  // nor on top of another
        taken.push(box);
        ctx.globalAlpha = lvl;
        ctx.fillStyle = pal.accent; ctx.strokeStyle = pal.page; ctx.lineWidth = 3;
        ctx.strokeText(text, x, y); ctx.fillText(text, x, y);
      }
    }
    ctx.globalAlpha = 1;
  }
}

export default function GraphCanvas({ nodes, edges, shown, selected, onSelect, marked, pointed, controls, label, padTop = 72, padBottom = 72 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const engine = useRef<Engine | null>(null);
  useEffect(() => {
    const e = new Engine(ref.current!);
    engine.current = e;
    controls.current = { zoomBy: (f) => e.zoomBy(f), fit: () => { e.follow = true; e.fitNow(true); } };
    return () => { e.stop(); engine.current = null; controls.current = null; };
  }, [controls]);
  useEffect(() => { engine.current?.setData(nodes, edges); }, [nodes, edges]);
  useEffect(() => { engine.current?.setShown(shown); }, [shown]);
  useEffect(() => { const e = engine.current; if (e) { e.selected = selected; e.dirty = true; } }, [selected]);
  useEffect(() => { const e = engine.current; if (e) { e.marked = marked; e.dirty = true; } }, [marked]);
  useEffect(() => { const e = engine.current; if (e) { e.pointed = pointed; e.dirty = true; } }, [pointed]);
  useEffect(() => { const e = engine.current; if (e) { e.padTop = padTop; e.padBottom = padBottom; } }, [padTop, padBottom]);
  useEffect(() => { if (engine.current) engine.current.onSelect = onSelect; }, [onSelect]);
  return <canvas ref={ref} role="img" aria-label={label} className="absolute inset-0 h-full w-full cursor-grab touch-none select-none" />;
}
