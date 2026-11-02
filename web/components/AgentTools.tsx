"use client";

// Learned routines as agents' tools (backend/api/sharing.py): a routine you share, while it has an active version, is a
// tool of its own in the tool list of Muse and of any agent whose key has the "run" group (api/agents.py). Settings ›
// Agents shows that list exactly as Muse sees it, and keeps it current (it's what to film if an agent keeps its own list
// until it reconnects); `/?settings=agents#agent-tools` opens it, scrolled to the list. A tool that appears while it's open
// scrolls into view, marked New. Each routine's page has its "Share with agents" switch.
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, HandPalmIcon, PlugsConnectedIcon, SparkleIcon } from "@phosphor-icons/react";
import { appIcon, Card, Chip, cx, RowIcon, Section, Switch } from "@/components/ui";
import { ago, api, post, type AgentTool, type AgentToolsInfo } from "@/lib/api";

const SHARING = "/api/routines/sharing";

// The sharing state; with `every`, read again that often while the page is visible, so a routine learned or shared
// elsewhere shows up here too.
export function useSharing(every?: number): [AgentToolsInfo | null, (next: AgentToolsInfo) => void, string | null] {
  const [info, setInfo] = useState<AgentToolsInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let gone = false;
    const load = () => api<AgentToolsInfo>(SHARING).then((x) => { if (!gone) { setInfo(x); setError(null); } })
      .catch((e) => { if (!gone) setError(e.message ?? "couldn't load them"); });
    load();
    const t = every ? setInterval(() => { if (document.visibilityState === "visible") load(); }, every) : undefined;
    return () => { gone = true; if (t) clearInterval(t); };
  }, [every]);
  return [info, setInfo, error];
}

// On a routine's page: share it with agents or not. Off by default; approvals are the same either way.
export function ShareWithAgents({ name }: { name: string }) {
  const [info, setInfo] = useSharing();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!info) return null;
  const on = info.shared.includes(name);
  const tool = info.tools.find((t) => t.routine === name);
  const flip = async (next: boolean) => {
    setBusy(true); setError(null);
    try { setInfo(await post<AgentToolsInfo>(`/api/routines/${encodeURIComponent(name)}/share`, { on: next })); }
    catch (e: any) { setError(e.message ?? "couldn't change it"); }
    finally { setBusy(false); }
  };
  return (
    <div className="mt-3 flex max-w-3xl items-center gap-3 rounded-card border border-line bg-surface py-2 pl-4 pr-3">
      <RowIcon icon={PlugsConnectedIcon} tone={on ? "sage" : "neutral"} />
      <div className="min-w-0 flex-1">
        <p className="text-row font-semibold">Share with agents</p>
        <p className="text-meta-2 text-muted [overflow-wrap:anywhere]">
          {on && tool ? <>Muse and your other agents see it as the tool <code className="font-mono font-semibold text-sage-ink">{tool.tool}</code>. Anything irreversible still waits for your OK.</>
            : on ? "Shared, but it has no active version, so agents don't see it yet."
            : "Off: it isn't in any agent's tool list."}
        </p>
        {on && tool && <a href="/?settings=agents#agent-tools" className="mt-0.5 inline-flex items-center gap-1 text-meta-2 font-bold text-sage-ink hover:text-sage-deep">
          See every agent tool <ArrowRightIcon size={13} /></a>}
        {error && <p role="alert" className="text-meta-2 text-apricot-ink">{error}</p>}
      </div>
      <Switch on={on} onChange={flip} disabled={busy} label="Share with agents" />
    </div>
  );
}

// `tool(trip_city, seat?, phone?)`: how an agent calls it. An input memory can fill is marked optional, and so is the
// phone it runs on. A long name breaks after an underscore, and the arguments between each other, never inside one.
function Signature({ t }: { t: AgentTool }) {
  const args = [...t.inputs.map((i) => ({ name: `${i.name}${i.required ? "" : "?"}`, strong: i.required, title: i.description })),
    ...(t.phone ? [{ name: "phone?", strong: false, title: 'Which phone runs it: an id from list_phones, "phone" or "emulator"' }] : [])];
  return (
    <code className="font-mono text-[15px] font-semibold leading-snug [overflow-wrap:break-word] md:text-[17px]">
      <span className="text-sage-ink">{t.tool.split("_").map((part, n) => <span key={n}>{n ? <>_<wbr /></> : null}{part}</span>)}</span>
      <span className="text-muted">(</span>
      {args.map((a, n) => (
        <span key={a.name}>
          <span title={a.title} className={cx("whitespace-nowrap", a.strong ? "text-ink" : "text-muted")}>{a.name}{n < args.length - 1 ? <span className="text-muted">,</span> : null}</span>
          {n < args.length - 1 ? " " : null}
        </span>
      ))}
      <span className="text-muted">)</span>
    </code>
  );
}

// `added`: when this tool appeared while the list was open (it's marked New, with a sage edge, until you leave).
function ToolRow({ t, added }: { t: AgentTool; added?: number }) {
  return (
    <div id={`agent-tool-${t.tool}`} className={cx("flex scroll-mt-24 gap-3 border-b border-divider px-4 py-4 last:border-b-0",
      !!added && "ev-rise bg-sage-tint/50 shadow-[inset_4px_0_0_var(--sage)]")}>
      <RowIcon icon={appIcon(t.app)} />
      <div className="min-w-0 flex-1">
        <Signature t={t} />
        <p className="mt-0.5 text-meta text-ink-2">{t.title} · {t.app_name} · v{t.version}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {!!added && <span role="status" className="inline-flex items-center gap-1.5 rounded-full bg-sage px-2.5 py-1 text-meta-2 font-bold text-white">
            <SparkleIcon size={14} weight="fill" />New · added {ago(added)}</span>}
          {t.irreversible ? <Chip tone="apricot" icon={HandPalmIcon}><span className="md:hidden">Asks you first</span>
            <span className="hidden md:inline">Asks you before the step that can&rsquo;t be undone</span></Chip>
            : t.read_only ? <Chip tone="neutral">Only reads</Chip> : null}
        </div>
        {t.inputs.length > 0 && (
          <dl className="mt-2.5 flex flex-col gap-1 text-meta-2">
            {t.inputs.map((i) => (
              <div key={i.name} className="flex flex-wrap gap-x-2">
                <dt className="font-mono font-semibold">{i.name}<span className="font-sans font-normal text-muted"> · {i.choices ? i.choices.join(" / ") : i.type}{i.required ? "" : " · optional"}</span></dt>
                <dd className="min-w-0 text-ink-2 [overflow-wrap:anywhere]">{i.description}</dd>
              </div>
            ))}
          </dl>
        )}
        {t.outputs.length > 0 && (
          <p className="mt-2 flex flex-wrap items-center gap-1.5 text-meta-2 text-muted">
            Returns {t.outputs.map((o) => <span key={o} className="rounded-sm bg-well px-1.5 py-0.5 font-mono text-ink-2">{o}</span>)}
          </p>
        )}
        <p className="mt-2 text-meta-2 text-muted">Learned {t.taught ? "from you" : "from a run"} on {t.learned} · replays with no model calls while the app looks as it did</p>
      </div>
    </div>
  );
}

// Settings › Agents: every tool an agent connected to Envoy sees now. The learned ones first, in full; then Envoy's own.
export default function AgentTools() {
  const [info, , error] = useSharing(4000);
  const seen = useRef<Set<string> | null>(null);
  const [added, setAdded] = useState<Record<string, number>>({});  // tool → when it appeared while the list was open
  useEffect(() => {
    if (!info) return;
    const now = new Set(info.tools.map((t) => t.tool));
    if (seen.current) {
      const fresh = [...now].filter((n) => !seen.current!.has(n));
      if (fresh.length) setAdded((a) => ({ ...a, ...Object.fromEntries(fresh.map((n) => [n, Date.now() / 1000])) }));
    }
    seen.current = now;
  }, [info]);
  const newest = Object.entries(added).sort((a, b) => b[1] - a[1])[0]?.[0];
  const section = useRef<HTMLDivElement>(null);
  useEffect(() => {  // a tool that just appeared comes into view (the moment to film), even below the agents' keys
    if (newest) document.getElementById(`agent-tool-${newest}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [newest]);
  const loaded = !!info;
  useEffect(() => {  // #agent-tools: straight to the list
    if (loaded && location.hash === "#agent-tools") section.current?.scrollIntoView({ block: "start" });
  }, [loaded]);
  if (!info) return error ? <p role="alert" className="mx-6 mt-6 rounded-block bg-apricot-tint px-3 py-2 text-meta text-apricot-ink">Couldn&rsquo;t load the agent tools: {error}</p>
    : <p className="px-6 py-6 text-body text-muted">Loading…</p>;
  const n = info.tools.length;
  // A tool that appeared while you watch comes first (the newest at the top), marked New; the rest by name, as agents list them.
  const tools = [...info.tools.filter((t) => added[t.tool]).sort((a, b) => added[b.tool] - added[a.tool]),
    ...info.tools.filter((t) => !added[t.tool])];
  return (
    <div ref={section} id="agent-tools" className="scroll-mt-2">
      <Section title="Agent tools" intro={<>What agents connected to Envoy see right now. Each routine you share from its page becomes a tool of its own: an agent calls it by name, it replays for almost nothing, and anything irreversible still waits for your OK on your phone. Muse sees every tool; an agent with its own key sees the learned ones if its key has &ldquo;run&rdquo;.</>}>
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 border-b border-divider bg-raised px-4 py-3">
            <span aria-hidden className="relative flex h-2.5 w-2.5 shrink-0">  {/* live: it reads the list every few seconds */}
              <span className="absolute -inset-1 rounded-full bg-sage/50" style={{ animation: "evRipple 1.8s ease-out infinite" }} />
              <span className="relative h-2.5 w-2.5 rounded-full bg-sage" />
            </span>
            <span className="shrink-0 text-title font-bold">{n ? `${n} learned ${n === 1 ? "tool" : "tools"}` : "No learned tools yet"}</span>
            <span className="text-meta-2 text-muted">live · updates as you share and Envoy learns</span>
          </div>
          {n ? tools.map((t) => <ToolRow key={t.tool} t={t} added={added[t.tool]} />)
            : <p className="px-4 py-5 text-meta text-ink-2">Open a routine and turn on <b>Share with agents</b>. It shows up here, and in every agent&rsquo;s tool list, at once.</p>}
        </Card>
        <Card className="px-4 py-3">
          <p className="text-meta font-bold">Envoy&rsquo;s own tools <span className="font-normal text-muted">· always there</span></p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {info.builtin.map((b) => <li key={b.name} title={b.title} className="rounded-sm bg-well px-1.5 py-0.5 font-mono text-meta-2 text-ink-2">{b.name}</li>)}
          </ul>
          <p className="mt-2 text-meta-2 text-muted">None of them can approve anything: only you can, on your phone.</p>
        </Card>
      </Section>
    </div>
  );
}
