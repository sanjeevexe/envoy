"use client";

// One routine, read only: its steps (how each target is found, the checks around it, its risk), its versions as a
// timeline (what each repair changed, the run that made it, how its trial went) and its runs against the agent run it
// was learned from.
import { KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Loc = {
  visual?: string; text_has?: string; text?: string; alt_texts?: string[]; desc?: string; hint?: string; resource_id?: string;
  kind?: string; cls?: string; parent?: string; siblings?: string[]; in_list?: boolean; picture?: boolean;
};
type Chk = { kind: string; text: string; locator: Loc | null };
type Act = { kind: string; verb: string; target: Loc | null; value?: string; submit?: boolean; detail?: string };
type StepV = {
  id: string; intent: string; risk: string; optional: boolean; note?: string; action: Act; pre: Chk[]; post: Chk[]; outputs: string[];
  changed_in?: { version: number; kind: string }[];
};
type Change = {
  step: string; intent: string; kind: string; what: string; before: any; after: any; why?: string; patch?: string; score?: number; reasons?: string[];
  follows?: string | null;
};
type Src = { task_id: string; goal?: string; status?: string; steps?: number; model_calls?: number; duration_s?: number; usd?: number | null };
type Version = {
  version: number; status: string; created?: string; parent?: number | null; origin: "compiled" | "recompiled" | "repaired"; notes: string[];
  changes: Change[]; shots: { label: string; intent?: string; before?: string; after?: string }[]; replaced_by?: number | null; diffable?: boolean;
  repair?: { task_id: string; rung: number | null; how: string | null; model_calls: number | null; run_rung: number | null; duration_s: number | null; time: string | null };
  compiled?: { task_id?: string; goal?: string; compiler?: string; at?: string; usd?: number; source: Src | null;
    verification: { case: string; passed: boolean; duration_s?: number; inputs: Record<string, string> }[] };
  trial?: { passed: boolean; task_id: string; status: string; model_calls?: number | null; duration_s?: number | null };
};
type Run = {
  time: string; kind: string; version: number; task_id: string; status: string; ok: boolean; rung: number; how: string; model_calls: number;
  duration_s: number | null; usd: number | null; usd_estimated: boolean; patches: number; device: string | null; app_task: string | null;
  saved: { calls: number; seconds: number; usd: number | null } | null; event: { kind: "repaired" | "trial"; version: number; passed?: boolean } | null;
};
type Detail = {
  name: string; app: string; intent: string; description: string; inputs: Record<string, { type: string; description: string; example?: string }>;
  outputs: string[]; active: number | null; shown: number; shown_status: string | null; trial: number | null; needs_recompile: boolean; steps: StepV[]; done: Chk[];
  versions: Version[]; runs: Run[];
  savings: { source: Src | null; runs: number; finished: number; compared: number; failed: number; model_calls: number; saved: { calls: number; seconds: number; usd: number };
    compile_usd: number | null; net_usd: number | null; paid_back_after: number | null; median_s: number | null };
};

// ---- formatting -------------------------------------------------------------------------------

const usd = (v?: number | null) => v == null ? "—" : `${v < 0 ? "−" : ""}$${Math.abs(v) < 0.01 ? Math.abs(v).toFixed(4) : Math.abs(v) < 1 ? Math.abs(v).toFixed(3) : Math.abs(v).toFixed(2)}`;
const secs = (v?: number | null) => {
  if (v == null) return "—";
  const sign = v < 0 ? "−" : "", a = Math.abs(v);
  if (a < 59.95) return `${sign}${+a.toFixed(1)} s`;
  const r = Math.round(a);
  return `${sign}${Math.floor(r / 60)} min${r % 60 ? ` ${r % 60} s` : ""}`;
};
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const when = (t?: string | null) => {
  if (!t) return "";
  const d = new Date(t.replace(" ", "T"));
  return isNaN(+d) ? t : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};
const RUNG: Record<number, string> = { 0: "clean replay", 1: "waited and retried", 2: "relaxed match", 3: "pop-up handled", 4: "local repair", 5: "agent took over", 6: "asked you" };
const OUTCOME: Record<string, { label: string; tone: string }> = {
  done: { label: "Done", tone: "bg-emerald-100 text-emerald-800" },
  agent_done: { label: "Done by the agent", tone: "bg-sky-100 text-sky-800" },
  done_unverified: { label: "Done, unverified", tone: "bg-emerald-50 text-emerald-800" },
  failed: { label: "Failed", tone: "bg-rose-100 text-rose-800" },
  agent_failed: { label: "Failed", tone: "bg-rose-100 text-rose-800" },
  declined: { label: "Declined", tone: "bg-stone-200 text-stone-700" },
  handoff: { label: "Needed you", tone: "bg-amber-100 text-amber-900" },
  needs_user: { label: "Needed you", tone: "bg-amber-100 text-amber-900" },
};
const RISK: Record<string, { tone: string; tip: string }> = {
  read: { tone: "bg-stone-100 text-stone-600", tip: "Only reads the screen or navigates" },
  reversible: { tone: "bg-sky-50 text-sky-800", tip: "Changes something that can be undone" },
  irreversible: { tone: "bg-rose-100 text-rose-800 font-semibold", tip: "Can't be undone: always asks for your approval, even in a routine" },
};
const FATE: Record<string, { label: (v: Version) => string; tone: string; dot: string }> = {
  active: { label: () => "Active", tone: "bg-emerald-100 text-emerald-800", dot: "bg-emerald-500" },
  trial: { label: () => "On trial", tone: "bg-amber-100 text-amber-900", dot: "bg-amber-400" },
  rejected: { label: () => "Rolled back", tone: "bg-rose-100 text-rose-800", dot: "bg-rose-500" },
  retired: { label: (v) => v.replaced_by ? `Replaced by v${v.replaced_by}` : "Replaced", tone: "bg-stone-200 text-stone-700", dot: "bg-stone-400" },
};
const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600";

// Input slots ({{trip_city}}) stand out as what the caller fills in.
function Slots({ text }: { text: string }) {
  const parts = text.split(/(\{\{\s*[a-zA-Z_]\w*\s*\}\})/);
  return <>{parts.map((p, i) => {
    const m = p.match(/^\{\{\s*(\w+)\s*\}\}$/);
    return m ? <span key={i} className="rounded bg-violet-100 px-1 font-mono text-[0.9em] text-violet-800"><span className="sr-only">input </span>{m[1]}</span> : p;
  })}</>;
}
const Q = ({ children }: { children: string }) => <>“<Slots text={children.length > 60 ? `${children.slice(0, 57)}…` : children} />”</>;

// ---- locators and checks ----------------------------------------------------------------------

const LOC_KEYS: (keyof Loc)[] = ["visual", "picture", "text_has", "text", "alt_texts", "desc", "hint", "resource_id", "kind", "parent", "siblings", "in_list"];
function locPart(k: keyof Loc, v: any): ReactNode {
  switch (k) {
    case "visual": return <>looks like <Q>{v}</Q></>;
    case "picture": return <>its recorded picture</>;
    case "text_has": return <>must show <Q>{v}</Q></>;
    case "text": return <>label <Q>{v}</Q></>;
    case "alt_texts": return <>earlier label {(v as string[]).map((t, i) => <span key={i}>{i ? ", " : ""}<Q>{t}</Q></span>)}</>;
    case "desc": return <>description <Q>{v}</Q></>;
    case "hint": return <>field <Q>{v}</Q></>;
    case "resource_id": return <>id <code className="font-mono"><Slots text={v} /></code></>;
    case "kind": return <>{v}</>;
    case "parent": return <>inside <code className="font-mono">{v}</code></>;
    case "siblings": return <>next to {(v as string[]).slice(0, 2).map((t, i) => <span key={i}>{i ? ", " : ""}<Q>{t}</Q></span>)}{v.length > 2 ? ` +${v.length - 2}` : ""}</>;
    case "in_list": return <>in a list</>;
    case "cls": return <>class <code className="font-mono">{v}</code></>;
  }
  return null;
}
const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

// How a target is found, attribute by attribute. With `other`, attributes that differ are marked: struck out on the
// before side, highlighted on the after side.
function Locator({ loc, other, side }: { loc: Loc | null; other?: Loc | null; side?: "before" | "after" }) {
  if (!loc) return <span className="text-stone-500">no target</span>;
  const keys = [...LOC_KEYS, ...(side && !same(loc.cls, other?.cls) ? ["cls" as const] : [])].filter((k) => loc[k] !== undefined);
  return (
    <ul className="flex flex-wrap gap-1" aria-label={side ? `${side === "before" ? "Before" : "After"}: how the target is found` : "How the target is found"}>
      {keys.map((k) => {
        const changed = side && other !== undefined && !same(loc[k], other?.[k]);
        const body = locPart(k, loc[k]);
        return (
          <li key={k} className={`rounded-md px-1.5 py-0.5 text-xs [overflow-wrap:anywhere] ${!changed ? "bg-stone-100 text-stone-700"
            : side === "before" ? "bg-rose-50 text-rose-900 ring-1 ring-rose-200" : "bg-emerald-50 text-emerald-900 ring-1 ring-emerald-300"}`}>
            {changed && side === "before" ? <del className="decoration-rose-400"><span className="sr-only">removed: </span>{body}</del>
              : changed ? <ins className="no-underline"><span aria-hidden>+ </span><span className="sr-only">added: </span>{body}</ins> : body}
          </li>
        );
      })}
    </ul>
  );
}

function Checks({ label, checks }: { label: string; checks: Chk[] }) {
  if (!checks.length) return null;
  return (
    <div className="mt-1 flex gap-2 text-xs">
      <span className="w-16 shrink-0 text-stone-500">{label}</span>
      <ul className="min-w-0 space-y-0.5">
        {checks.map((c, i) => <li key={i} className="[overflow-wrap:anywhere] text-stone-700"><span aria-hidden className="mr-1 text-emerald-600">✓</span><Slots text={c.text} /></li>)}
      </ul>
    </div>
  );
}

function Action({ a }: { a: Act }) {
  return (
    <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      <span className="font-medium text-stone-800">{a.verb}{a.kind === "type" && a.value != null && <> <Q>{a.value}</Q> into</>}</span>
      {a.target && <Locator loc={a.target} />}
      {a.detail && <span className="text-xs text-stone-500">{a.detail}</span>}
      {a.submit && <span className="text-xs text-stone-500">then Enter</span>}
    </div>
  );
}

// `bare`: without its intent, when the words above already say it (a step a repair added, in Muse's words).
function StepCard({ s, n, bare }: { s: StepV; n?: number; bare?: boolean }) {
  const risk = RISK[s.risk] ?? RISK.read;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {n != null && <span className="text-xs tabular-nums text-stone-400">{n}<span className="sr-only">.</span></span>}{" "}
        {!bare && <span className="font-medium [overflow-wrap:anywhere]"><Slots text={s.intent} /></span>}{" "}
        <span className={`rounded-full px-2 py-0.5 text-[11px] ${risk.tone}`} title={risk.tip}>{s.risk}</span>{" "}
        {s.optional && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-900 ring-1 ring-amber-200" title="Skipped when its screen doesn't appear">optional</span>}
        {(s.changed_in ?? []).map((c) => (
          <span key={c.version} className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-800 ring-1 ring-emerald-200">
            {c.kind === "inserted" ? "added" : "repaired"} in v{c.version}
          </span>
        ))}
      </div>
      <Action a={s.action} />
      <Checks label="Before" checks={s.pre} />
      <Checks label="After" checks={s.post} />
      {s.outputs.length > 0 && <div className="mt-1 flex gap-2 text-xs"><span className="w-16 shrink-0 text-stone-500">Reads</span><span className="text-stone-700">{s.outputs.join(", ")}</span></div>}
    </div>
  );
}

// ---- the three panels -------------------------------------------------------------------------

function Steps({ d }: { d: Detail }) {
  return (
    <div>
      {d.trial != null && d.trial !== d.shown && (
        <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">These are the steps of v{d.shown}, {d.active === d.shown ? "the active version" : "the version last active"}. v{d.trial} is on trial: the next run uses it.</p>
      )}
      <ol className="space-y-2">
        {d.steps.map((s, i) => <li key={s.id} className="rounded-xl bg-white p-3 shadow-sm"><StepCard s={s} n={i + 1} /></li>)}
      </ol>
      {d.done.length > 0 && <div className="mt-2 rounded-xl bg-white p-3 shadow-sm"><Checks label="Done when" checks={d.done} /></div>}
    </div>
  );
}

function ChangeView({ c }: { c: Change }) {
  return (
    <li className="rounded-lg border border-stone-200 bg-stone-50/60 p-2.5">
      <div className="text-sm [overflow-wrap:anywhere]">{c.kind === "inserted"
        ? <><span className="font-medium">New step</span>{c.follows && <span className="text-stone-500"> after “<Slots text={c.follows} />”</span>}</>
        : <><span className="font-medium"><Slots text={c.intent} /></span> <span className="text-stone-500">· {c.what}</span></>}</div>
      {c.why && <p className="mt-0.5 text-xs text-stone-600">{c.why}{c.score != null && ` Match score ${c.score.toFixed(2)}; a strict match needs 0.80.`}</p>}
      {(c.reasons ?? []).map((r, i) => <p key={i} className="mt-1 border-l-2 border-violet-300 pl-2 text-xs italic text-stone-700">Muse: “{r}”</p>)}
      {c.kind === "locator" && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <div><div className="mb-0.5 text-[11px] font-medium uppercase tracking-wide text-stone-500">Before</div><Locator loc={c.before} other={c.after} side="before" /></div>
          <div><div className="mb-0.5 text-[11px] font-medium uppercase tracking-wide text-stone-500">After</div><Locator loc={c.after} other={c.before} side="after" /></div>
        </div>
      )}
      {(c.kind === "check" || c.kind === "action" || c.kind === "risk") && (
        <div className="mt-2 grid gap-1 text-xs sm:grid-cols-2 sm:gap-2">
          <div><span className="text-[11px] font-medium uppercase tracking-wide text-stone-500">Before </span>
            {c.before ? <del className="rounded bg-rose-50 px-1 text-rose-900 decoration-rose-400"><Slots text={c.kind === "risk" ? c.before : c.before.text ?? c.before.verb} /></del> : <span className="text-stone-500">none</span>}</div>
          <div><span className="text-[11px] font-medium uppercase tracking-wide text-stone-500">After </span>
            {c.after ? <ins className="rounded bg-emerald-50 px-1 text-emerald-900 no-underline"><Slots text={c.kind === "risk" ? c.after : c.after.text ?? c.after.verb} /></ins> : <span className="text-stone-500">none</span>}</div>
        </div>
      )}
      {c.kind === "inserted" && c.after && <div className="mt-2 rounded-lg bg-white p-2 ring-1 ring-emerald-200"><StepCard s={c.after} bare={!!c.reasons?.includes(c.after.intent)} /></div>}
      {c.kind === "removed" && c.before && <div className="mt-2 rounded-lg bg-white p-2 opacity-70 ring-1 ring-rose-200"><StepCard s={c.before} /></div>}
    </li>
  );
}

function VersionItem({ v, d }: { v: Version; d: Detail }) {
  const fate = FATE[v.status] ?? { label: () => v.status, tone: "bg-stone-200 text-stone-700", dot: "bg-stone-400" };
  const src = v.compiled?.source;
  return (
    <li className="relative pb-6 pl-6 last:pb-0">
      <span aria-hidden className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 border-[#f7f7f5] ${fate.dot}`} />
      <h4 className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-base font-semibold">v{v.version}</span>{" "}
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${fate.tone}`}>{fate.label(v)}</span>{" "}
        <span className="text-xs text-stone-500">{when(v.created)}{v.origin === "repaired" && v.parent != null ? ` · from v${v.parent}` : ""}</span>
      </h4>
      <div className="mt-1.5 space-y-2 rounded-xl bg-white p-3 text-sm shadow-sm">
        {v.compiled && (
          <>
            <p><span className="font-medium">{v.origin === "recompiled" ? "Recompiled" : "Compiled"} from the agent's run</span>
              {v.compiled.goal && <> <span className="text-stone-700">“{v.compiled.goal}”</span></>}</p>
            {src ? (
              <p className="text-xs text-stone-600">
                The agent took {plural(src.steps ?? 0, "step")}, {plural(src.model_calls ?? 0, "model call")}, {secs(src.duration_s)} and {usd(src.usd)} at standard prices.
              </p>
            ) : <p className="text-xs text-stone-500">The agent run's trace isn't on this Mac.</p>}
            <p className="text-xs text-stone-600">
              {v.compiled.compiler && <>Compiled by {v.compiled.compiler}{v.compiled.usd != null && <> for {usd(v.compiled.usd)}</>}. </>}
              {v.compiled.verification.length > 0 && <>Verified by replaying it: {v.compiled.verification.map((c, i) => (
                <span key={i}>{i ? ", " : ""}{c.case.replace("-", " ")} {c.passed ? "passed" : "failed"}{c.duration_s != null && ` (${secs(c.duration_s)})`}</span>
              ))}.</>}
            </p>
            <p className="break-all font-mono text-[11px] text-stone-400">{v.compiled.task_id}</p>
          </>
        )}
        {v.repair && (
          <>
            <p><span className="font-medium">Repaired during a run</span>{v.repair.time && <span className="text-stone-500"> on {when(v.repair.time)}</span>}
              {v.repair.how && <>: {v.repair.rung === 4 ? "a local repair asked Muse what to do" : v.repair.rung === 2 ? "a relaxed match found the element with no model call" : v.repair.how}</>}
              .</p>
            {v.repair.model_calls != null && <p className="text-xs text-stone-600">That run made {plural(v.repair.model_calls, "model call")}{v.repair.duration_s != null && ` in ${secs(v.repair.duration_s)}`}
              {v.repair.run_rung != null && v.repair.rung != null && v.repair.run_rung > v.repair.rung && `, and later needed ${RUNG[v.repair.run_rung] ?? `rung ${v.repair.run_rung}`}`}.</p>}
            <p className="break-all font-mono text-[11px] text-stone-400">{v.repair.task_id}</p>
            {v.changes.length > 0 ? (
              <ul className="space-y-2" aria-label={`What v${v.version} changed`}>{v.changes.map((c, i) => <ChangeView key={i} c={c} />)}</ul>
            ) : v.diffable === false ? (
              <p className="rounded-lg bg-stone-50 px-2.5 py-2 text-xs text-stone-600">Can't compare it with v{v.parent}: one of their files is missing or unreadable. The patch log below says what the repair meant to change.</p>
            ) : (
              <p className="rounded-lg bg-stone-50 px-2.5 py-2 text-xs text-stone-600">No step changed: the repair wrote back the locator the step already had.</p>
            )}
            {v.shots.length > 0 && (
              <div className="space-y-2">
                {v.shots.map((s) => (
                  <figure key={s.before ?? s.after} className="flex flex-wrap items-center gap-2">
                    {s.before && <a href={s.before} target="_blank" rel="noreferrer" className={`rounded text-center text-[11px] text-stone-500 ${focusRing}`}>
                      <img src={s.before} alt={`The screen the routine didn't expect (${s.label}), before the repair`} className="h-44 w-auto rounded-md border border-stone-200 sm:h-56" />
                      <span aria-hidden className="mt-0.5 block">What it found</span></a>}
                    {s.before && s.after && <span aria-hidden className="pb-4 text-stone-400">→</span>}
                    {s.after && <a href={s.after} target="_blank" rel="noreferrer" className={`rounded text-center text-[11px] text-stone-500 ${focusRing}`}>
                      <img src={s.after} alt={`The screen after the repair's action (${s.label})`} className="h-44 w-auto rounded-md border border-stone-200 sm:h-56" />
                      <span aria-hidden className="mt-0.5 block">After the fix</span></a>}
                    <figcaption className="w-full text-xs text-stone-500">The repair at {s.label}{s.intent && <> (“<Slots text={s.intent} />”)</>}. Select a picture to open it full size.</figcaption>
                  </figure>
                ))}
              </div>
            )}
            {v.notes.length > 0 && (
              <details className="text-xs text-stone-500">
                <summary className={`cursor-pointer rounded ${focusRing}`}>Patch log ({v.notes.length})</summary>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 font-mono text-[11px] [overflow-wrap:anywhere]">{v.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
              </details>
            )}
          </>
        )}
        {v.status === "trial" && <p className="rounded-lg bg-amber-50 px-2.5 py-2 text-xs text-amber-900">The next run uses v{v.version}. If it finishes with no help (no model call, no agent), v{v.version} becomes active; otherwise it's rolled back and v{d.active} stays.</p>}
        {v.trial && (
          <p className={`rounded-lg px-2.5 py-2 text-xs ${v.trial.passed ? "bg-emerald-50 text-emerald-900" : "bg-rose-50 text-rose-900"}`}>
            <span aria-hidden>{v.trial.passed ? "✓ " : "✗ "}</span>
            {v.trial.passed
              ? <>Trial passed: the next run finished on its own{v.trial.model_calls != null && ` (${plural(v.trial.model_calls, "model call")}${v.trial.duration_s != null ? `, ${secs(v.trial.duration_s)}` : ""})`}, so v{v.version} became active.</>
              : <>Trial failed: the next run {v.trial.status === "done" || v.trial.status === "agent_done" ? "needed help" : `ended ${v.trial.status}`}{v.trial.model_calls ? ` (${plural(v.trial.model_calls, "model call")})` : ""}, so v{v.version} was rolled back and v{v.parent} stayed active.</>}
          </p>
        )}
      </div>
    </li>
  );
}

function Versions({ d }: { d: Detail }) {
  const repairs = d.versions.filter((v) => v.origin === "repaired");
  const noop = repairs.filter((v) => !v.changes.length && v.diffable !== false).length;
  return (
    <div>
      <p className="mb-3 text-sm text-stone-600">
        {repairs.length
          ? <>A run that needed help leaves a patch; it becomes a new version on trial, and the next run decides it. {plural(repairs.length, "repair")} so far
            {noop > 0 && <>; {noop === repairs.length ? (noop === 1 ? "it" : "all of them") : noop} left the steps as they were</>}.</>
          : <>No repairs yet. When a run needs help, the fix becomes a new version on trial, and the next run decides it.</>}
      </p>
      <ol className="ml-2 border-l-2 border-stone-200" aria-label="Versions, oldest first">{d.versions.map((v) => <VersionItem key={v.version} v={v} d={d} />)}</ol>
    </div>
  );
}

function RunEvent({ r }: { r: Run }) {
  if (!r.event) return null;
  return r.event.kind === "repaired"
    ? <div className="text-xs text-emerald-800">Repaired a step, proposing v{r.event.version}</div>
    : <div className={`text-xs ${r.event.passed ? "text-emerald-800" : "text-rose-800"}`}>Trial of v{r.event.version}: {r.event.passed ? "passed" : "rolled back"}</div>;
}

function Savings({ d }: { d: Detail }) {
  const s = d.savings, src = s.source;
  if (!src) return <p className="text-sm text-stone-600">The agent run this routine was learned from isn't on this Mac, so there's nothing to compare its runs with.</p>;
  const perRun = src.usd ?? 0;
  const more = s.compile_usd && perRun > 0 ? Math.max(1, Math.ceil((s.compile_usd - s.saved.usd) / perRun)) : null;
  return (
    <p className="text-sm text-stone-700">
      The agent's run took {plural(src.model_calls ?? 0, "model call")}, {secs(src.duration_s)} and {usd(src.usd)} at standard prices.{" "}
      {s.compared
        ? <>Against it, the routine's {plural(s.compared, "finished run")} saved <strong>{plural(s.saved.calls, "model call")}</strong>, <strong>{secs(s.saved.seconds)}</strong> and <strong>{usd(s.saved.usd)}</strong>.</>
        : <>The routine hasn't run since.</>}
      {s.compile_usd != null && <>{" "}Learning it cost {usd(s.compile_usd)} once{s.paid_back_after ? <>; the savings covered that by run {s.paid_back_after}.</>
        : more ? <>; at {usd(perRun)} saved a run, it pays for itself after {plural(more, s.compared ? "more run" : "run")}.</> : "."}</>}
      {s.failed > 0 && <> {plural(s.failed, "run")} didn't finish and {s.failed === 1 ? "isn't" : "aren't"} counted.</>}
      {s.finished > s.compared && <> {plural(s.finished - s.compared, "finished run")} came from a version whose agent run isn't on this Mac.</>}
    </p>
  );
}

function Runs({ d, openTask }: { d: Detail; openTask: (id: string) => void }) {
  const runs = [...d.runs].reverse();
  const outcome = (r: Run) => {
    const o = OUTCOME[r.status] ?? { label: r.status, tone: "bg-stone-200 text-stone-700" };
    return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${o.tone}`}>{o.label}</span>;
  };
  const whenCell = (r: Run) => r.app_task
    ? <button onClick={() => openTask(r.app_task!)} className={`rounded text-left text-sky-700 underline-offset-2 hover:underline ${focusRing}`}>{when(r.time)}<span className="sr-only">: open this task</span></button>
    : when(r.time);
  const cost = (r: Run) => r.model_calls ? `${r.usd_estimated ? "≈" : ""}${usd(r.usd)}` : "$0";
  const saved = (r: Run) => r.saved ? `${plural(r.saved.calls, "call")} · ${secs(r.saved.seconds)} · ${usd(r.saved.usd)}` : "—";
  return (
    <div>
      <div className="mb-3 rounded-xl bg-white p-3 shadow-sm"><Savings d={d} /></div>
      {!runs.length ? <p className="text-sm text-stone-500">No runs yet.</p> : (
        <>
          <ul className="space-y-2 sm:hidden" aria-label="Runs, newest first">
            {runs.map((r, i) => (
              <li key={i} className="rounded-xl bg-white p-3 text-sm shadow-sm">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0"><div className="font-medium">{whenCell(r)}</div>
                    <div className="text-xs text-stone-500">v{r.version}{r.device ? ` · ${r.device}` : ""}{r.kind !== "run" ? ` · ${r.kind}` : ""}</div></div>
                  {outcome(r)}
                </div>
                <div className="mt-1 text-xs text-stone-700">{plural(r.model_calls, "model call")} ({cost(r)}) · {secs(r.duration_s)} · {RUNG[r.rung] ?? r.how}</div>
                {r.saved && <div className="mt-0.5 text-xs text-emerald-800">Saved {saved(r)}</div>}
                <RunEvent r={r} />
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto rounded-xl bg-white shadow-sm sm:block">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Runs of this routine, newest first, with what each saved against the agent's run</caption>
              <thead className="text-xs text-stone-500"><tr>
                <th scope="col" className="p-2">When</th><th scope="col" className="p-2">Version</th><th scope="col" className="p-2">Phone</th>
                <th scope="col" className="p-2">Outcome</th><th scope="col" className="p-2 text-right">Model calls</th><th scope="col" className="p-2 text-right">Time</th>
                <th scope="col" className="p-2">Saved vs the agent</th>
              </tr></thead>
              <tbody>
                {runs.map((r, i) => (
                  <tr key={i} className="border-t border-stone-100 align-top">
                    <td className="whitespace-nowrap p-2">{whenCell(r)}</td>
                    <td className="p-2">v{r.version}{r.kind !== "run" && <div className="text-xs text-stone-500">{r.kind}</div>}</td>
                    <td className="p-2 text-xs">{r.device ?? <span className="text-stone-400" title="Runs started outside the app don't record their phone">—<span className="sr-only">not recorded</span></span>}</td>
                    <td className="p-2">{outcome(r)}<div className="mt-0.5 text-xs text-stone-500">{RUNG[r.rung] ?? r.how}</div><RunEvent r={r} /></td>
                    <td className="p-2 text-right tabular-nums">{r.model_calls}<div className="text-xs text-stone-500">{cost(r)}</div></td>
                    <td className="whitespace-nowrap p-2 text-right tabular-nums">{secs(r.duration_s)}</td>
                    <td className="p-2 text-xs text-emerald-800">{saved(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {runs.some((r) => r.usd_estimated) && <p className="mt-2 text-xs text-stone-500">≈ Runs record model calls, not dollars: their calls are priced at the agent run's cost per call.</p>}
        </>
      )}
    </div>
  );
}

// ---- the view ---------------------------------------------------------------------------------

const PANELS = ["Steps", "Versions", "Runs"] as const;
type Panel = (typeof PANELS)[number];

export default function RoutineDetail({ name, back, openTask }: { name: string; back: () => void; openTask: (id: string) => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>("Steps");
  const [yaml, setYaml] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const tabs = useRef<Record<string, HTMLButtonElement | null>>({});

  useEffect(() => {
    setD(null); setError(null); setYaml(null);
    api<Detail>(`/api/routines/${encodeURIComponent(name)}/detail`).then((x) => {
      setD(x);
      setPanel(x.versions.length > 1 ? "Versions" : "Steps");  // a repaired routine opens on its story
    }).catch((e) => setError(e.message ?? "couldn't load this routine"));
  }, [name]);
  useEffect(() => { if (d) heading.current?.focus(); }, [d]);

  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = PANELS.indexOf(panel);
    const next = e.key === "ArrowRight" ? (i + 1) % PANELS.length : e.key === "ArrowLeft" ? (i + PANELS.length - 1) % PANELS.length
      : e.key === "Home" ? 0 : e.key === "End" ? PANELS.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    setPanel(PANELS[next]);
    tabs.current[PANELS[next]]?.focus();
  };

  const backButton = <button onClick={back} className={`mb-3 rounded text-sm text-stone-500 hover:text-stone-800 ${focusRing}`}>← All routines</button>;
  if (error) return <div className="p-4">{backButton}<p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900">Couldn't load {name}: {error}</p></div>;
  if (!d) return <div className="p-4" aria-busy="true">{backButton}<p className="text-sm text-stone-500">Loading {name}…</p></div>;

  const s = d.savings, src = s.source;
  const repairs = d.versions.filter((v) => v.origin === "repaired").length;
  const counts: Record<Panel, number> = { Steps: d.steps.length, Versions: d.versions.length, Runs: d.runs.length };
  return (
    <div className="p-4">
      {backButton}
      <h2 ref={heading} tabIndex={-1} className="text-lg font-semibold leading-snug outline-none">{d.intent}</h2>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-500">
        <span className="font-mono [overflow-wrap:anywhere]">{d.name}</span><span aria-hidden>·</span><span className="mr-1">{d.app}</span>
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-medium text-emerald-800">{d.active != null ? `v${d.active} active` : `no active version · v${d.shown} shown (${d.shown_status ?? "?"})`}</span>
        {d.trial != null && <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-900">v{d.trial} on trial</span>}
        {repairs > 0 && <span className="rounded-full bg-violet-100 px-2 py-0.5 font-medium text-violet-800">self-repaired {repairs}×</span>}
      </div>
      {d.description && <p className="mt-2 max-w-3xl text-sm text-stone-600">{d.description}</p>}
      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <div className="flex gap-1"><dt className="text-stone-500">Inputs</dt><dd>{Object.keys(d.inputs).length ? Object.entries(d.inputs).map(([k, v], i) => (
          <span key={k}>{i ? ", " : ""}<span className="font-mono">{k}</span>{v.example && <span className="text-stone-500"> (e.g. {v.example})</span>}</span>)) : "none"}</dd></div>
        {d.outputs.length > 0 && <div className="flex gap-1"><dt className="text-stone-500">Outputs</dt><dd className="font-mono">{d.outputs.join(", ")}</dd></div>}
      </dl>
      {d.needs_recompile && <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">It failed more than half of its recent runs, so it's flagged to be recompiled from a fresh agent run.</p>}

      <dl className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {([
          ["Runs", `${s.runs}`, s.runs ? `${s.finished} finished${s.failed ? `, ${s.failed} didn't` : ""}` : "none yet", ""],
          ["Model calls", `${s.model_calls}`, src?.model_calls != null ? `in its runs · the agent: ${src.model_calls}` : "in its runs", ""],
          ["Time per run", secs(s.median_s), src?.duration_s != null ? `median · the agent: ${secs(src.duration_s)}` : "median", ""],
          ["Saved", s.compared ? usd(s.saved.usd) : "—", s.compared ? `${plural(s.saved.calls, "call")} · ${secs(s.saved.seconds)} · at standard prices`
            : s.finished ? "no agent run to compare with" : "no runs yet", "text-emerald-800"],
        ] as const).map(([label, value, sub, tone]) => (
          <div key={label} className="rounded-xl bg-white p-2.5 shadow-sm sm:p-3">
            <dt className="text-xs text-stone-500">{label}</dt>
            <dd className={`text-lg font-semibold tabular-nums sm:text-xl ${tone}`}>{value}</dd>
            <dd className="text-xs text-stone-500">{sub}</dd>
          </div>
        ))}
      </dl>

      <div role="tablist" aria-label="Routine details" className="mt-4 flex gap-1 border-b border-stone-200">
        {PANELS.map((p) => (
          <button key={p} role="tab" id={`routine-tab-${p}`} aria-selected={panel === p} aria-controls={`routine-panel-${p}`} tabIndex={panel === p ? 0 : -1}
                  ref={(el) => { tabs.current[p] = el; }} onClick={() => setPanel(p)} onKeyDown={onTabKey}
                  className={`-mb-px whitespace-nowrap rounded-t px-3 py-2 text-sm ${focusRing} ${panel === p ? "border-b-2 border-stone-800 font-medium" : "text-stone-500 hover:text-stone-800"}`}>
            {p} <span className="text-xs tabular-nums text-stone-400">{counts[p]}</span>
          </button>
        ))}
      </div>
      {PANELS.map((p) => (
        <div key={p} role="tabpanel" id={`routine-panel-${p}`} aria-labelledby={`routine-tab-${p}`} hidden={panel !== p} tabIndex={0} className={`rounded pt-3 ${focusRing}`}>
          <h3 className="sr-only">{p}</h3>
          {p === "Steps" && <Steps d={d} />}
          {p === "Versions" && <Versions d={d} />}
          {p === "Runs" && <Runs d={d} openTask={openTask} />}
        </div>
      ))}

      <details className="mt-4 text-sm" onToggle={(e) => {
        if ((e.target as HTMLDetailsElement).open && yaml === null) api(`/api/routines/${encodeURIComponent(name)}?version=${d.shown}`).then((r) => setYaml(r.yaml)).catch(() => setYaml("(couldn't load it)"));
      }}>
        <summary className={`cursor-pointer rounded text-stone-500 hover:text-stone-800 ${focusRing}`}>The routine file (YAML, v{d.shown})</summary>
        <pre className="mt-2 max-h-[50vh] overflow-auto rounded-xl bg-stone-900 p-3 text-xs text-stone-100">{yaml ?? "Loading…"}</pre>
      </details>
    </div>
  );
}
