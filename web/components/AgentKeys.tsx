"use client";

// Settings › Agents (phone-layer contract 2): AI agents that use Envoy over MCP, each with its own key and only the tool
// groups you give it. Muse's key is the one in Envoy's .env and has every tool. Each agent's card lists the tools it sees
// right now, as its tools/list gives them (GET /api/agents `sees`): its groups' tools, and the routines you share with
// agents (AgentTools, beside it) while it has Run. A new key is shown once; a new key stops the old one at once, and
// revoking cuts that agent off without touching the others. Keys are made and changed on the Mac; any of your devices can
// revoke one.
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowsClockwiseIcon, CopyIcon, KeyIcon, PlugsConnectedIcon, PlusIcon, RobotIcon, TrashIcon } from "@phosphor-icons/react";
import { Button, Card, Chip, cx, IconButton, RowIcon, Section } from "@/components/ui";
import { ago, api, post } from "@/lib/api";

export type AgentKey = { id: string; name: string; tools: string[]; created_at: number; last_seen?: number | null; sees?: string[] };
export type AgentGroup = { id: string; label: string; detail: string; tools: string[] };
export type AgentsInfo = {
  agents: AgentKey[]; learned?: string[]; muse: { name: string; key: boolean; last_seen?: number | null; sees?: string[] };
  groups: AgentGroup[]; default: string[]; per_minute: number; mcp_url: string; can_manage: boolean;
};

// The page reloads when a routine is shared or unshared here (AgentTools fires this), and every few seconds while it shows.
export const SHARING_EVENT = "envoy:sharing";

export default function AgentKeys() {
  const [info, setInfo] = useState<AgentsInfo | null>(null);
  const [shown, setShown] = useState<{ name: string; secret: string; rotated: boolean } | null>(null);  // a key, until you press Done
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => { api<AgentsInfo>("/api/agents").then(setInfo).catch((e) => setMsg(e.message)); }, []);
  useEffect(() => {
    load();
    const t = setInterval(() => { if (document.visibilityState === "visible") load(); }, 4000);
    window.addEventListener(SHARING_EVENT, load);
    return () => { clearInterval(t); window.removeEventListener(SHARING_EVENT, load); };
  }, [load]);
  if (!info) return <p className="px-6 py-6 text-body text-muted">{msg ?? "Loading…"}</p>;

  const learned = new Set(info.learned ?? []);
  const rotate = async (a: AgentKey) => {
    if (!confirm(`Make a new key for ${a.name}? Its current key stops working at once.`)) return;
    try { const r = await post<{ key: string }>(`/api/agents/${a.id}/rotate`); setShown({ name: a.name, secret: r.key, rotated: true }); load(); }
    catch (e: any) { setMsg(e.message); }
  };
  const revoke = async (a: AgentKey) => {
    if (!confirm(`Revoke ${a.name}'s key? It can't use Envoy until you make it a new one.`)) return;
    try { await api(`/api/agents/${a.id}`, { method: "DELETE" }); if (shown?.name === a.name) setShown(null); load(); }
    catch (e: any) { setMsg(e.message); }
  };
  const setGroups = async (a: AgentKey, tools: string[]) => {
    if (!tools.length) return setMsg(`${a.name} needs at least one group; revoke its key to stop it.`);
    try { await post(`/api/agents/${a.id}`, { tools }); setMsg(null); load(); } catch (e: any) { setMsg(e.message); }
  };

  return (
    <Section title="Agents" intro={<>Muse and your other agents use Envoy over MCP. Each sees only the tools you give it, and none can approve anything: every irreversible step waits for your OK. Each can start at most {info.per_minute} tasks a minute.</>}>
      <AgentCard name={info.muse.name} icon={RobotIcon} sees={info.muse.sees} learned={learned} seen={info.muse.last_seen}
                 meta={info.muse.key ? "Its key is MCP_BEARER_TOKEN in Envoy's .env" : "No key yet: add MCP_BEARER_TOKEN to Envoy's .env"}>
        <span className="mt-3 flex flex-wrap gap-1.5"><Chip>Every tool</Chip></span>
      </AgentCard>
      {info.agents.map((a) => (
        <AgentCard key={a.id} name={a.name} icon={KeyIcon} sees={a.sees} learned={learned} seen={a.last_seen} meta={`Key made ${ago(a.created_at)}`}
                   missing={!a.tools.includes("run") && learned.size > 0 ? learned.size : 0}
                   actions={<>
                     {info.can_manage && <IconButton label={`New key for ${a.name}`} onClick={() => rotate(a)}><ArrowsClockwiseIcon size={18} /></IconButton>}
                     <IconButton label={`Revoke ${a.name}'s key`} onClick={() => revoke(a)}><TrashIcon size={18} /></IconButton>
                   </>}>
          {info.can_manage ? <Groups groups={info.groups} value={a.tools} onChange={(tools) => setGroups(a, tools)} name={a.name} />
            : <span className="mt-3 flex flex-wrap gap-1.5">{a.tools.map((g) => <Chip key={g} tone="neutral">{info.groups.find((x) => x.id === g)?.label ?? g}</Chip>)}</span>}
        </AgentCard>
      ))}
      {shown && <ShownKey {...shown} url={info.mcp_url} onDone={() => setShown(null)} />}
      {!info.can_manage ? <p className="px-2 text-meta-2 text-muted">Make or change an agent&rsquo;s key in Envoy on your Mac. You can revoke one from here.</p>
        : adding ? <NewAgent info={info} onCancel={() => setAdding(false)} onMade={(name, key) => { setAdding(false); setShown({ name, secret: key, rotated: false }); load(); }} />
        : <Button className="self-start" onClick={() => { setAdding(true); setShown(null); }}><PlusIcon size={16} />Add an agent</Button>}
      {msg && <p role="status" className="px-2 text-meta text-apricot-ink">{msg}</p>}
    </Section>
  );
}

// One agent: who it is, when it last called, what it may do, and the tools it sees now (learned ones first, in sage). A
// tool that appears while you watch (you shared a routine) rises in.
function AgentCard({ name, icon, meta, seen, sees, learned, missing = 0, actions, children }: {
  name: string; icon: typeof KeyIcon; meta: string; seen?: number | null; sees?: string[]; learned: Set<string>; missing?: number;
  actions?: React.ReactNode; children?: React.ReactNode;
}) {
  const before = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const key = (sees ?? []).join(",");
  useEffect(() => {
    const now = new Set(sees ?? []);
    if (before.current) {
      const added = [...now].filter((t) => !before.current!.has(t));
      if (added.length) setFresh((f) => new Set([...f, ...added]));
    }
    before.current = now;
  }, [key]);  // eslint-disable-line react-hooks/exhaustive-deps
  const tools = sees ?? [];
  return (
    <Card className="p-4">
      <div className="flex items-start gap-3">
        <RowIcon icon={icon} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-row font-semibold">{name}</p>
          <p className="text-meta-2 text-muted">{meta} · {seen ? `seen ${ago(seen)}` : "not used yet"}</p>
        </div>
        {actions && <div className="-mr-2 -mt-1 flex shrink-0">{actions}</div>}
      </div>
      {children}
      {sees && (
        <div className="mt-3 border-t border-divider pt-3">
          <p className="text-meta-2 font-bold text-muted">Sees {tools.length} {tools.length === 1 ? "tool" : "tools"}</p>
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={`Tools ${name} sees`}>
            {tools.map((t) => (
              <li key={t} className={cx("inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-mono text-meta-2 [overflow-wrap:anywhere]",
                learned.has(t) ? "bg-sage-tint font-semibold text-sage-ink" : "bg-well text-ink-2", fresh.has(t) && "ev-rise")}>
                {learned.has(t) && <PlugsConnectedIcon size={13} className="shrink-0" aria-label="learned" />}{t}
              </li>
            ))}
          </ul>
          {missing > 0 && <p className="mt-2 text-meta-2 text-muted">Doesn&rsquo;t see the {missing} learned {missing === 1 ? "tool: it needs" : "tools: they need"} Run.</p>}
        </div>
      )}
    </Card>
  );
}

// The tool groups as toggles. Each says what it lets the agent do (title text), and which tools it is.
function Groups({ groups, value, onChange, name }: { groups: AgentGroup[]; value: string[]; onChange: (v: string[]) => void; name: string }) {
  return (
    <span role="group" aria-label={`What ${name} may do`} className="mt-3 flex flex-wrap gap-1.5">
      {groups.map((g) => {
        const on = value.includes(g.id);
        return (
          <button key={g.id} aria-pressed={on} aria-label={g.label} title={`${g.detail} (${g.tools.join(", ")})`}
                  onClick={() => onChange(on ? value.filter((x) => x !== g.id) : [...value, g.id])}
                  className={cx("h-11 rounded-full border px-3.5 text-meta-2 font-semibold transition-colors",
                    on ? "border-sage bg-sage-tint text-sage-ink" : "border-control bg-surface text-muted hover:text-ink")}>
            {g.label}
          </button>
        );
      })}
    </span>
  );
}

function NewAgent({ info, onMade, onCancel }: { info: AgentsInfo; onMade: (name: string, key: string) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [tools, setTools] = useState<string[]>(info.default);
  const [err, setErr] = useState<string | null>(null);
  const make = async () => {
    try {
      const r = await post<{ agent: AgentKey; key: string }>("/api/agents", { name: name.trim(), tools });
      setName(""); setTools(info.default); setErr(null); onMade(r.agent.name, r.key);
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Card className="flex flex-col gap-3 p-4">
      <span className="text-row font-semibold">Add an agent</span>
      <input value={name} onChange={(e) => { setName(e.target.value); setErr(null); }} maxLength={40} spellCheck={false} autoFocus
             placeholder="Its name, such as Claude" aria-label="The agent's name"
             className="h-11 min-w-0 rounded-full border border-control bg-surface px-4 text-meta outline-none focus:border-sage" />
      <div>
        <span className="text-meta-2 text-muted">What it may do</span>
        <Groups groups={info.groups} value={tools} onChange={setTools} name="the new agent" />
        <ul className="mt-2 flex flex-col gap-0.5 text-meta-2 text-ink-2">
          {info.groups.filter((g) => tools.includes(g.id)).map((g) => <li key={g.id}><b>{g.label}</b>: {g.detail}</li>)}
        </ul>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={!name.trim() || !tools.length} onClick={make}><KeyIcon size={16} />Make its key</Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
      {err && <p role="status" className="text-meta text-apricot-ink">{err}</p>}
    </Card>
  );
}

function ShownKey({ name, secret, rotated, url, onDone }: { name: string; secret: string; rotated: boolean; url: string; onDone: () => void }) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = (what: string, text: string) => navigator.clipboard.writeText(text).then(() => { setCopied(what); setTimeout(() => setCopied(null), 2000); });
  return (
    <Card className="flex flex-col gap-3 p-4">
      <span className="text-row font-semibold">{rotated ? `${name}'s new key` : `${name}'s key`}</span>
      <p className="text-meta-2 text-muted">Shown once: Envoy keeps only a fingerprint of it.{rotated ? " The old key has stopped working." : ""} Paste it into {name}&rsquo;s MCP settings, then this page can forget it.</p>
      <div className="break-all rounded-sm bg-well p-3 font-mono text-meta-2">{secret}</div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => copy("key", secret)}><CopyIcon size={16} />{copied === "key" ? "Copied" : "Copy the key"}</Button>
        <Button onClick={() => copy("url", url)}><CopyIcon size={16} />{copied === "url" ? "Copied" : "Copy the address"}</Button>
        <Button variant="ghost" onClick={onDone}>Done</Button>
      </div>
      <p className="text-meta-2 text-ink-2">
        Server address <span className="break-all font-mono">{url}</span> (Streamable HTTP), with the header <span className="font-mono">Authorization: Bearer</span> and the key.
      </p>
    </Card>
  );
}
