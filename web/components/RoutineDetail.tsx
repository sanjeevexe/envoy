"use client";

// One routine, read only: its steps (how each target is found, the checks around it, its risk), its versions as a
// timeline (what each repair changed, the run that made it, how its trial went) and its runs against the agent run it
// was learned from.
import { KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { CaretLeftIcon } from "@phosphor-icons/react";
import { appIcon, RowIcon } from "@/components/ui";
import { api, media } from "@/lib/api";

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
// The app's display name back to its package, for its icon.
const PACKAGES: Record<string, string> = { SkyLark: "com.skylark.air", DoorDash: "com.dd.doordash", Amazon: "com.amazon.mShop.android.shopping",
  Starbucks: "com.starbucks.mobilecard", Target: "com.target.ui", Chipotle: "com.chipotle.ordering" };
const appPackage = (app: string) => (app.includes(".") ? app : PACKAGES[app.replace(/ app$/, "")] ?? app);
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const when = (t?: string | null) => {
  if (!t) return "";
  const d = new Date(t.replace(" ", "T"));
  return isNaN(+d) ? t : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};
const RUNG: Record<number, string> = { 0: "clean replay", 1: "waited and retried", 2: "relaxed match", 3: "pop-up handled", 4: "local repair", 5: "agent took over", 6: "asked you" };
const OUTCOME: Record<string, { label: string; tone: string }> = {
  done: { label: "Done", tone: "bg-sage-tint text-sage-ink" },
  agent_done: { label: "Done by the agent", tone: "bg-well text-ink-2" },
  done_unverified: { label: "Done, unverified", tone: "bg-sage-tint text-sage-ink" },
  failed: { label: "Failed", tone: "bg-apricot-tint text-apricot-ink" },
  agent_failed: { label: "Failed", tone: "bg-apricot-tint text-apricot-ink" },
  declined: { label: "Declined", tone: "bg-well text-ink-2" },
  handoff: { label: "Needed you", tone: "bg-apricot-tint text-apricot-ink" },
  needs_user: { label: "Needed you", tone: "bg-apricot-tint text-apricot-ink" },
};
const RISK: Record<string, { tone: string; tip: string }> = {
  read: { tone: "bg-well text-ink-2", tip: "Only reads the screen or navigates" },
  reversible: { tone: "bg-well text-ink-2", tip: "Changes something that can be undone" },
  irreversible: { tone: "bg-surface text-brick font-semibold ring-1 ring-line", tip: "Can't be undone: always asks for your approval, even in a routine" },
};
const FATE: Record<string, { label: (v: Version) => string; tone: string; dot: string }> = {
  active: { label: () => "Active", tone: "bg-sage-tint text-sage-ink", dot: "bg-sage" },
  trial: { label: () => "On trial", tone: "bg-apricot-tint text-apricot-ink", dot: "bg-apricot" },
  rejected: { label: () => "Rolled back", tone: "bg-apricot-tint text-apricot-ink", dot: "bg-apricot" },
  retired: { label: (v) => v.replaced_by ? `Replaced by v${v.replaced_by}` : "Replaced", tone: "bg-well text-ink-2", dot: "bg-line-strong" },
};

// Input slots ({{trip_city}}) stand out as what the caller fills in.
function Slots({ text }: { text: string }) {
  const parts = text.split(/(\{\{\s*[a-zA-Z_]\w*\s*\}\})/);
  return <>{parts.map((p, i) => {
    const m = p.match(/^\{\{\s*(\w+)\s*\}\}$/);
    return m ? <span key={i} className="rounded-sm bg-sage-tint px-1 font-mono text-[0.9em] text-sage-ink"><span className="sr-only">input </span>{m[1]}</span> : p;
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
  if (!loc) return <span className="text-muted">no target</span>;
  const keys = [...LOC_KEYS, ...(side && !same(loc.cls, other?.cls) ? ["cls" as const] : [])].filter((k) => loc[k] !== undefined);
  return (
    <ul className="flex flex-wrap gap-1" aria-label={side ? `${side === "before" ? "Before" : "After"}: how the target is found` : "How the target is found"}>
      {keys.map((k) => {
        const changed = side && other !== undefined && !same(loc[k], other?.[k]);
        const body = locPart(k, loc[k]);
        return (
          <li key={k} className={`rounded-sm px-1.5 py-0.5 text-meta-2 [overflow-wrap:anywhere] ${!changed ? "bg-well text-ink-2"
            : side === "before" ? "bg-apricot-tint text-apricot-ink ring-1 ring-apricot-line" : "bg-sage-tint text-sage-ink ring-1 ring-sage"}`}>
            {changed && side === "before" ? <del className="decoration-apricot"><span className="sr-only">removed: </span>{body}</del>
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
    <div className="mt-1 flex gap-2 text-meta-2">
      <span className="w-16 shrink-0 text-muted">{label}</span>
      <ul className="min-w-0 space-y-0.5">
        {checks.map((c, i) => <li key={i} className="[overflow-wrap:anywhere] text-ink-2"><span aria-hidden className="mr-1 text-sage">✓</span><Slots text={c.text} /></li>)}
      </ul>
    </div>
  );
}

function Action({ a }: { a: Act }) {
  return (
    <div className="mt-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-meta">
      <span className="font-medium text-ink">{a.verb}{a.kind === "type" && a.value != null && <> <Q>{a.value}</Q> into</>}</span>
      {a.target && <Locator loc={a.target} />}
      {a.detail && <span className="text-meta-2 text-muted">{a.detail}</span>}
      {a.submit && <span className="text-meta-2 text-muted">then Enter</span>}
    </div>
  );
}

// `bare`: without its intent, when the words above already say it (a step a repair added, in Muse's words).
function StepCard({ s, n, bare }: { s: StepV; n?: number; bare?: boolean }) {
  const risk = RISK[s.risk] ?? RISK.read;
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {n != null && <span className="text-meta-2 tabular-nums text-muted">{n}<span className="sr-only">.</span></span>}{" "}
        {!bare && <span className="font-medium [overflow-wrap:anywhere]"><Slots text={s.intent} /></span>}{" "}
        <span className={`rounded-full px-2 py-0.5 text-tab ${risk.tone}`} title={risk.tip}>{s.risk}</span>{" "}
        {s.optional && <span className="rounded-full bg-apricot-tint px-2 py-0.5 text-tab text-apricot-ink ring-1 ring-apricot-line" title="Skipped when its screen doesn't appear">optional</span>}
        {(s.changed_in ?? []).map((c) => (
          <span key={c.version} className="rounded-full bg-sage-tint px-2 py-0.5 text-tab text-sage-ink ring-1 ring-sage-track">
            {c.kind === "inserted" ? "added" : "repaired"} in v{c.version}
          </span>
        ))}
      </div>
      <Action a={s.action} />
      <Checks label="Before" checks={s.pre} />
      <Checks label="After" checks={s.post} />
      {s.outputs.length > 0 && <div className="mt-1 flex gap-2 text-meta-2"><span className="w-16 shrink-0 text-muted">Reads</span><span className="text-ink-2">{s.outputs.join(", ")}</span></div>}
    </div>
  );
}

// ---- the three panels -------------------------------------------------------------------------

function Steps({ d }: { d: Detail }) {
  return (
    <div>
      {d.trial != null && d.trial !== d.shown && (
        <p className="mb-3 rounded-block bg-apricot-tint px-3 py-2 text-meta text-apricot-ink">These are the steps of v{d.shown}, {d.active === d.shown ? "the active version" : "the version last active"}. v{d.trial} is on trial: the next run uses it.</p>
      )}
      <ol className="space-y-2">
        {d.steps.map((s, i) => <li key={s.id} className="rounded-card border border-line bg-surface p-4"><StepCard s={s} n={i + 1} /></li>)}
      </ol>
      {d.done.length > 0 && <div className="mt-2 rounded-card border border-line bg-surface p-4"><Checks label="Done when" checks={d.done} /></div>}
    </div>
  );
}

function ChangeView({ c }: { c: Change }) {
  return (
    <li className="rounded-block border border-line bg-raised p-2.5">
      <div className="text-meta [overflow-wrap:anywhere]">{c.kind === "inserted"
        ? <><span className="font-medium">New step</span>{c.follows && <span className="text-muted"> after “<Slots text={c.follows} />”</span>}</>
        : <><span className="font-medium"><Slots text={c.intent} /></span> <span className="text-muted">· {c.what}</span></>}</div>
      {c.why && <p className="mt-0.5 text-meta-2 text-ink-2">{c.why}{c.score != null && ` Match score ${c.score.toFixed(2)}; a strict match needs 0.80.`}</p>}
      {(c.reasons ?? []).map((r, i) => <p key={i} className="mt-1 border-l-2 border-sage-track pl-2 text-meta-2 italic text-ink-2">Muse: “{r}”</p>)}
      {c.kind === "locator" && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <div><div className="mb-0.5 text-tab font-medium text-muted">Before</div><Locator loc={c.before} other={c.after} side="before" /></div>
          <div><div className="mb-0.5 text-tab font-medium text-muted">After</div><Locator loc={c.after} other={c.before} side="after" /></div>
        </div>
      )}
      {(c.kind === "check" || c.kind === "action" || c.kind === "risk") && (
        <div className="mt-2 grid gap-1 text-meta-2 sm:grid-cols-2 sm:gap-2">
          <div><span className="text-tab font-medium text-muted">Before </span>
            {c.before ? <del className="rounded-sm bg-apricot-tint px-1 text-apricot-ink decoration-apricot"><Slots text={c.kind === "risk" ? c.before : c.before.text ?? c.before.verb} /></del> : <span className="text-muted">none</span>}</div>
          <div><span className="text-tab font-medium text-muted">After </span>
            {c.after ? <ins className="rounded-sm bg-sage-tint px-1 text-sage-ink no-underline"><Slots text={c.kind === "risk" ? c.after : c.after.text ?? c.after.verb} /></ins> : <span className="text-muted">none</span>}</div>
        </div>
      )}
      {c.kind === "inserted" && c.after && <div className="mt-2 rounded-block bg-surface p-2 ring-1 ring-sage-track"><StepCard s={c.after} bare={!!c.reasons?.includes(c.after.intent)} /></div>}
      {c.kind === "removed" && c.before && <div className="mt-2 rounded-block bg-surface p-2 opacity-70 ring-1 ring-apricot-line"><StepCard s={c.before} /></div>}
    </li>
  );
}

function VersionItem({ v, d }: { v: Version; d: Detail }) {
  const fate = FATE[v.status] ?? { label: () => v.status, tone: "bg-well text-ink-2", dot: "bg-line-strong" };
  const src = v.compiled?.source;
  return (
    <li className="relative pb-6 pl-6 last:pb-0">
      <span aria-hidden className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full border-2 border-[#f7f7f5] ${fate.dot}`} />
      <h4 className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-title font-semibold">v{v.version}</span>{" "}
        <span className={`rounded-full px-2 py-0.5 text-meta-2 font-medium ${fate.tone}`}>{fate.label(v)}</span>{" "}
        <span className="text-meta-2 text-muted">{when(v.created)}{v.origin === "repaired" && v.parent != null ? ` · from v${v.parent}` : ""}</span>
      </h4>
      <div className="mt-1.5 space-y-2 rounded-card border border-line bg-surface p-4 text-meta">
        {v.compiled && (
          <>
            <p><span className="font-medium">{v.origin === "recompiled" ? "Recompiled" : "Compiled"} from the agent's run</span>
              {v.compiled.goal && <> <span className="text-ink-2">“{v.compiled.goal}”</span></>}</p>
            {src ? (
              <p className="text-meta-2 text-ink-2">
                The agent took {plural(src.steps ?? 0, "step")}, {plural(src.model_calls ?? 0, "model call")}, {secs(src.duration_s)} and {usd(src.usd)} at standard prices.
              </p>
            ) : <p className="text-meta-2 text-muted">The agent run's trace isn't on this Mac.</p>}
            <p className="text-meta-2 text-ink-2">
              {v.compiled.compiler && <>Compiled by {v.compiled.compiler}{v.compiled.usd != null && <> for {usd(v.compiled.usd)}</>}. </>}
              {v.compiled.verification.length > 0 && <>Verified by replaying it: {v.compiled.verification.map((c, i) => (
                <span key={i}>{i ? ", " : ""}{c.case.replace("-", " ")} {c.passed ? "passed" : "failed"}{c.duration_s != null && ` (${secs(c.duration_s)})`}</span>
              ))}.</>}
            </p>
            <p className="break-all font-mono text-tab text-muted">{v.compiled.task_id}</p>
          </>
        )}
        {v.repair && (
          <>
            <p><span className="font-medium">Repaired during a run</span>{v.repair.time && <span className="text-muted"> on {when(v.repair.time)}</span>}
              {v.repair.how && <>: {v.repair.rung === 4 ? "a local repair asked Muse what to do" : v.repair.rung === 2 ? "a relaxed match found the element with no model call" : v.repair.how}</>}
              .</p>
            {v.repair.model_calls != null && <p className="text-meta-2 text-ink-2">That run made {plural(v.repair.model_calls, "model call")}{v.repair.duration_s != null && ` in ${secs(v.repair.duration_s)}`}
              {v.repair.run_rung != null && v.repair.rung != null && v.repair.run_rung > v.repair.rung && `, and later needed ${RUNG[v.repair.run_rung] ?? `rung ${v.repair.run_rung}`}`}.</p>}
            <p className="break-all font-mono text-tab text-muted">{v.repair.task_id}</p>
            {v.changes.length > 0 ? (
              <ul className="space-y-2" aria-label={`What v${v.version} changed`}>{v.changes.map((c, i) => <ChangeView key={i} c={c} />)}</ul>
            ) : v.diffable === false ? (
              <p className="rounded-block bg-raised px-2.5 py-2 text-meta-2 text-ink-2">Can't compare it with v{v.parent}: one of their files is missing or unreadable. The patch log below says what the repair meant to change.</p>
            ) : (
              <p className="rounded-block bg-raised px-2.5 py-2 text-meta-2 text-ink-2">No step changed: the repair wrote back the locator the step already had.</p>
            )}
            {v.shots.length > 0 && (
              <div className="space-y-2">
                {v.shots.map((s) => (
                  <figure key={s.before ?? s.after} className="flex flex-wrap items-center gap-2">
                    {s.before && <a href={media(s.before)} target="_blank" rel="noreferrer" className="rounded-sm text-center text-tab text-muted">
                      <img src={media(s.before)} alt={`The screen the routine didn't expect (${s.label}), before the repair`} className="h-44 w-auto rounded-sm border border-line sm:h-56" />
                      <span aria-hidden className="mt-0.5 block">What it found</span></a>}
                    {s.before && s.after && <span aria-hidden className="pb-4 text-muted">→</span>}
                    {s.after && <a href={media(s.after)} target="_blank" rel="noreferrer" className="rounded-sm text-center text-tab text-muted">
                      <img src={media(s.after)} alt={`The screen after the repair's action (${s.label})`} className="h-44 w-auto rounded-sm border border-line sm:h-56" />
                      <span aria-hidden className="mt-0.5 block">After the fix</span></a>}
                    <figcaption className="w-full text-meta-2 text-muted">The repair at {s.label}{s.intent && <> (“<Slots text={s.intent} />”)</>}. Select a picture to open it full size.</figcaption>
                  </figure>
                ))}
              </div>
            )}
            {v.notes.length > 0 && (
              <details className="text-meta-2 text-muted">
                <summary className="cursor-pointer rounded-sm">Patch log ({v.notes.length})</summary>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 font-mono text-tab [overflow-wrap:anywhere]">{v.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
              </details>
            )}
          </>
        )}
        {v.status === "trial" && <p className="rounded-block bg-apricot-tint px-2.5 py-2 text-meta-2 text-apricot-ink">The next run uses v{v.version}. If it finishes with no help (no model call, no agent), v{v.version} becomes active; otherwise it's rolled back and v{d.active} stays.</p>}
        {v.trial && (
          <p className={`rounded-block px-2.5 py-2 text-meta-2 ${v.trial.passed ? "bg-sage-tint text-sage-ink" : "bg-apricot-tint text-apricot-ink"}`}>
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
      <p className="mb-3 text-meta text-ink-2">
        {repairs.length
          ? <>A run that needed help leaves a patch; it becomes a new version on trial, and the next run decides it. {plural(repairs.length, "repair")} so far
            {noop > 0 && <>; {noop === repairs.length ? (noop === 1 ? "it" : "all of them") : noop} left the steps as they were</>}.</>
          : <>No repairs yet. When a run needs help, the fix becomes a new version on trial, and the next run decides it.</>}
      </p>
      <ol className="ml-2 border-l-2 border-line" aria-label="Versions, oldest first">{d.versions.map((v) => <VersionItem key={v.version} v={v} d={d} />)}</ol>
    </div>
  );
}

function RunEvent({ r }: { r: Run }) {
  if (!r.event) return null;
  return r.event.kind === "repaired"
    ? <div className="text-meta-2 text-sage-ink">Repaired a step, proposing v{r.event.version}</div>
    : <div className={`text-meta-2 ${r.event.passed ? "text-sage-ink" : "text-apricot-ink"}`}>Trial of v{r.event.version}: {r.event.passed ? "passed" : "rolled back"}</div>;
}

function Savings({ d }: { d: Detail }) {
  const s = d.savings, src = s.source;
  if (!src) return <p className="text-meta text-ink-2">The agent run this routine was learned from isn't on this Mac, so there's nothing to compare its runs with.</p>;
  const perRun = src.usd ?? 0;
  const more = s.compile_usd && perRun > 0 ? Math.max(1, Math.ceil((s.compile_usd - s.saved.usd) / perRun)) : null;
  return (
    <p className="text-meta text-ink-2">
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
    const o = OUTCOME[r.status] ?? { label: r.status, tone: "bg-well text-ink-2" };
    return <span className={`rounded-full px-2 py-0.5 text-meta-2 font-medium ${o.tone}`}>{o.label}</span>;
  };
  const whenCell = (r: Run) => r.app_task
    ? <button onClick={() => openTask(r.app_task!)} className="rounded-sm text-left text-sage-ink underline-offset-2 hover:underline">{when(r.time)}<span className="sr-only">: open this task</span></button>
    : when(r.time);
  const cost = (r: Run) => r.model_calls ? `${r.usd_estimated ? "≈" : ""}${usd(r.usd)}` : "$0";
  const saved = (r: Run) => r.saved ? `${plural(r.saved.calls, "call")} · ${secs(r.saved.seconds)} · ${usd(r.saved.usd)}` : "—";
  return (
    <div>
      <div className="mb-3 rounded-card border border-line bg-surface p-4"><Savings d={d} /></div>
      {!runs.length ? <p className="text-meta text-muted">No runs yet.</p> : (
        <>
          <ul className="space-y-2 sm:hidden" aria-label="Runs, newest first">
            {runs.map((r, i) => (
              <li key={i} className="rounded-card border border-line bg-surface p-4 text-meta">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0"><div className="font-medium">{whenCell(r)}</div>
                    <div className="text-meta-2 text-muted">v{r.version}{r.device ? ` · ${r.device}` : ""}{r.kind !== "run" ? ` · ${r.kind}` : ""}</div></div>
                  {outcome(r)}
                </div>
                <div className="mt-1 text-meta-2 text-ink-2">{plural(r.model_calls, "model call")} ({cost(r)}) · {secs(r.duration_s)} · {RUNG[r.rung] ?? r.how}</div>
                {r.saved && <div className="mt-0.5 text-meta-2 text-sage-ink">Saved {saved(r)}</div>}
                <RunEvent r={r} />
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto rounded-card border border-line bg-surface sm:block">
            <table className="w-full text-left text-meta">
              <caption className="sr-only">Runs of this routine, newest first, with what each saved against the agent's run</caption>
              <thead className="text-meta-2 text-muted"><tr>
                <th scope="col" className="p-2">When</th><th scope="col" className="p-2">Version</th><th scope="col" className="p-2">Phone</th>
                <th scope="col" className="p-2">Outcome</th><th scope="col" className="p-2 text-right">Model calls</th><th scope="col" className="p-2 text-right">Time</th>
                <th scope="col" className="p-2">Saved vs the agent</th>
              </tr></thead>
              <tbody>
                {runs.map((r, i) => (
                  <tr key={i} className="border-t border-divider align-top">
                    <td className="whitespace-nowrap p-2">{whenCell(r)}</td>
                    <td className="p-2">v{r.version}{r.kind !== "run" && <div className="text-meta-2 text-muted">{r.kind}</div>}</td>
                    <td className="p-2 text-meta-2">{r.device ?? <span className="text-muted" title="Runs started outside the app don't record their phone">—<span className="sr-only">not recorded</span></span>}</td>
                    <td className="p-2">{outcome(r)}<div className="mt-0.5 text-meta-2 text-muted">{RUNG[r.rung] ?? r.how}</div><RunEvent r={r} /></td>
                    <td className="p-2 text-right tabular-nums">{r.model_calls}<div className="text-meta-2 text-muted">{cost(r)}</div></td>
                    <td className="whitespace-nowrap p-2 text-right tabular-nums">{secs(r.duration_s)}</td>
                    <td className="p-2 text-meta-2 text-sage-ink">{saved(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {runs.some((r) => r.usd_estimated) && <p className="mt-2 text-meta-2 text-muted">≈ Runs record model calls, not dollars: their calls are priced at the agent run's cost per call.</p>}
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

  const backButton = (
    <button onClick={back} className="-ml-2 mb-2 flex h-11 items-center gap-1 rounded-full pl-2 pr-3 text-meta font-bold text-sage-ink hover:bg-sage-tint/60">
      <CaretLeftIcon size={18} /> All routines
    </button>
  );
  if (error) return <div className="mx-auto max-w-[920px] p-4 md:p-6">{backButton}<p role="alert" className="rounded-block bg-apricot-tint px-3 py-2 text-meta text-apricot-ink">Couldn't load {name}: {error}</p></div>;
  if (!d) return <div className="mx-auto max-w-[920px] p-4 md:p-6" aria-busy="true">{backButton}<p className="text-meta text-muted">Loading {name}…</p></div>;

  const s = d.savings, src = s.source;
  const repairs = d.versions.filter((v) => v.origin === "repaired").length;
  const counts: Record<Panel, number> = { Steps: d.steps.length, Versions: d.versions.length, Runs: d.runs.length };
  return (
    <div className="mx-auto max-w-[920px] p-4 pb-10 md:p-6">
      {backButton}
      <div className="flex items-start gap-3">
        <RowIcon icon={appIcon(appPackage(d.app))} size={44} />
        <div className="min-w-0">
          <h2 ref={heading} tabIndex={-1} className="font-serif text-display-2 font-normal leading-tight tracking-[-0.01em] outline-none">{d.intent}</h2>
          <div className="mt-1 text-meta-2 text-muted"><span className="font-mono [overflow-wrap:anywhere]">{d.name}</span> · {d.app}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-meta-2">
        <span className="rounded-full bg-sage-tint px-2.5 py-1 font-semibold text-sage-ink">{d.active != null ? `v${d.active} active` : `no active version · v${d.shown} shown (${d.shown_status ?? "?"})`}</span>
        {d.trial != null && <span className="rounded-full bg-apricot-tint px-2.5 py-1 font-semibold text-apricot-ink">v{d.trial} on trial</span>}
        {repairs > 0 && <span className="rounded-full bg-sage-tint px-2.5 py-1 font-semibold text-sage-ink">repaired itself {repairs}×</span>}
      </div>
      {d.description && <p className="mt-2 max-w-3xl text-meta text-ink-2">{d.description}</p>}
      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-meta-2">
        <div className="flex gap-1"><dt className="text-muted">Inputs</dt><dd>{Object.keys(d.inputs).length ? Object.entries(d.inputs).map(([k, v], i) => (
          <span key={k}>{i ? ", " : ""}<span className="font-mono">{k}</span>{v.example && <span className="text-muted"> (e.g. {v.example})</span>}</span>)) : "none"}</dd></div>
        {d.outputs.length > 0 && <div className="flex gap-1"><dt className="text-muted">Outputs</dt><dd className="font-mono">{d.outputs.join(", ")}</dd></div>}
      </dl>
      {d.needs_recompile && <p className="mt-2 rounded-block bg-apricot-tint px-3 py-2 text-meta text-apricot-ink">It failed more than half of its recent runs, so it's flagged to be recompiled from a fresh agent run.</p>}

      <dl className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {([
          ["Runs", `${s.runs}`, s.runs ? `${s.finished} finished${s.failed ? `, ${s.failed} didn't` : ""}` : "none yet", ""],
          ["Model calls", `${s.model_calls}`, src?.model_calls != null ? `in its runs · the agent: ${src.model_calls}` : "in its runs", ""],
          ["Time per run", secs(s.median_s), src?.duration_s != null ? `median · the agent: ${secs(src.duration_s)}` : "median", ""],
          ["Saved", s.compared ? usd(s.saved.usd) : "—", s.compared ? `${plural(s.saved.calls, "call")} · ${secs(s.saved.seconds)} · at standard prices`
            : s.finished ? "no agent run to compare with" : "no runs yet", "text-sage-ink"],
        ] as const).map(([label, value, sub, tone]) => (
          <div key={label} className="rounded-card border border-line bg-surface p-3 sm:p-4">
            <dt className="text-meta-2 text-muted">{label}</dt>
            <dd className={`text-title font-semibold tabular-nums sm:text-display-2 ${tone}`}>{value}</dd>
            <dd className="text-meta-2 text-muted">{sub}</dd>
          </div>
        ))}
      </dl>

      <div role="tablist" aria-label="Routine details" className="mt-5 inline-flex rounded-full bg-well p-1">
        {PANELS.map((p) => (
          <button key={p} role="tab" id={`routine-tab-${p}`} aria-selected={panel === p} aria-controls={`routine-panel-${p}`} tabIndex={panel === p ? 0 : -1}
                  ref={(el) => { tabs.current[p] = el; }} onClick={() => setPanel(p)} onKeyDown={onTabKey}
                  className={`h-9 whitespace-nowrap rounded-full px-4 text-meta font-bold ${panel === p ? "bg-surface text-ink shadow-[0_1px_2px_rgba(31,42,36,0.08)]" : "text-muted hover:text-ink"}`}>
            {p} <span className="text-meta-2 tabular-nums text-muted">{counts[p]}</span>
          </button>
        ))}
      </div>
      {PANELS.map((p) => (
        <div key={p} role="tabpanel" id={`routine-panel-${p}`} aria-labelledby={`routine-tab-${p}`} hidden={panel !== p} tabIndex={0} className="ev-fade rounded-sm pt-4">
          <h3 className="sr-only">{p}</h3>
          {p === "Steps" && <Steps d={d} />}
          {p === "Versions" && <Versions d={d} />}
          {p === "Runs" && <Runs d={d} openTask={openTask} />}
        </div>
      ))}

      <details className="mt-4 text-meta" onToggle={(e) => {
        if ((e.target as HTMLDetailsElement).open && yaml === null) api(`/api/routines/${encodeURIComponent(name)}?version=${d.shown}`).then((r) => setYaml(r.yaml)).catch(() => setYaml("(couldn't load it)"));
      }}>
        <summary className="flex min-h-[44px] cursor-pointer items-center rounded-sm font-semibold text-ink-2 hover:text-ink">The routine file (YAML, v{d.shown})</summary>
        <pre className="mt-2 max-h-[50vh] overflow-auto rounded-block bg-ink p-4 font-mono text-meta-2 text-white">{yaml ?? "Loading…"}</pre>
      </details>
    </div>
  );
}
