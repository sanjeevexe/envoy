"use client";

// Settings › Agents (phone-layer contract 2): AI agents that use Envoy over MCP, each with its own key and only the tool
// groups you give it. Muse's key is the one in Envoy's .env and has every tool. A new key is shown once; rotating one stops
// the old key at once, and revoking cuts that agent off without touching the others. Keys are made and changed on the Mac;
// any of your devices can revoke one.
import { useCallback, useEffect, useState } from "react";
import { ArrowsClockwiseIcon, CopyIcon, KeyIcon, RobotIcon, TrashIcon } from "@phosphor-icons/react";
import { Button, Card, Chip, cx, IconButton, Section } from "@/components/ui";
import { ago, api, post } from "@/lib/api";

export type AgentKey = { id: string; name: string; tools: string[]; created_at: number; last_seen?: number | null };
export type AgentGroup = { id: string; label: string; detail: string; tools: string[] };
export type AgentsInfo = {
  agents: AgentKey[]; muse: { name: string; key: boolean; last_seen?: number | null }; groups: AgentGroup[]; default: string[];
  per_minute: number; mcp_url: string; can_manage: boolean;
};

export default function Agents() {
  const [info, setInfo] = useState<AgentsInfo | null>(null);
  const [shown, setShown] = useState<{ name: string; secret: string; rotated: boolean } | null>(null);  // a key, until you press Done
  const [msg, setMsg] = useState<string | null>(null);
  const load = useCallback(() => { api<AgentsInfo>("/api/agents").then(setInfo).catch((e) => setMsg(e.message)); }, []);
  useEffect(load, [load]);
  if (!info) return msg ? <p className="px-6 py-6 text-body text-muted">{msg}</p> : null;

  const label = (g: string) => info.groups.find((x) => x.id === g)?.label ?? g;
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
    <div>
      <Section title="Agents" intro={<>AI agents such as Muse and Claude use Envoy over MCP. Each has its own key and sees only the tools you give it. None of them can approve anything: every irreversible step still waits for your OK. Each agent can start at most {info.per_minute} tasks a minute.</>}>
        <Card className="overflow-hidden">
          <Row icon={RobotIcon} name={info.muse.name} seen={info.muse.last_seen}
               meta={info.muse.key ? "Every tool · its key is MCP_BEARER_TOKEN in Envoy's .env" : "No key set: add MCP_BEARER_TOKEN to Envoy's .env"} />
          {info.agents.map((a) => (
            <Row key={a.id} icon={KeyIcon} name={a.name} seen={a.last_seen} meta={`Key made ${ago(a.created_at)}`}
                 actions={<>
                   {info.can_manage && <IconButton label={`New key for ${a.name}`} onClick={() => rotate(a)}><ArrowsClockwiseIcon size={18} /></IconButton>}
                   <IconButton label={`Revoke ${a.name}'s key`} onClick={() => revoke(a)}><TrashIcon size={18} /></IconButton>
                 </>}>
              {info.can_manage ? (
                <Groups groups={info.groups} value={a.tools} onChange={(tools) => setGroups(a, tools)} name={a.name} />
              ) : (
                <span className="mt-1.5 flex flex-wrap gap-1.5">{a.tools.map((g) => <Chip key={g} tone="neutral">{label(g)}</Chip>)}</span>
              )}
            </Row>
          ))}
        </Card>
        {shown && <ShownKey {...shown} url={info.mcp_url} onDone={() => setShown(null)} />}
        {info.can_manage
          ? <NewAgent info={info} onMade={(name, key) => { setShown({ name, secret: key, rotated: false }); load(); }} />
          : <p className="px-2 text-meta-2 text-muted">Make or change an agent&rsquo;s key in Envoy on your Mac. You can revoke one from here.</p>}
        {msg && <p role="status" className="px-2 text-meta text-apricot-ink">{msg}</p>}
      </Section>
    </div>
  );
}

function Row({ icon: I, name, meta, seen, actions, children }: {
  icon: typeof KeyIcon; name: string; meta: string; seen?: number | null; actions?: React.ReactNode; children?: React.ReactNode;
}) {
  return (
    <div className="min-h-[64px] border-b border-divider py-3 pl-4 pr-2 last:border-b-0">
      <div className="flex items-start gap-3">
        <I size={20} className="mt-0.5 shrink-0 text-sage-ink" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-row font-semibold">{name}</span>
          <span className="block text-meta-2 text-muted">{meta} · {seen ? `seen ${ago(seen)}` : "not used yet"}</span>
        </span>
        {actions && <span className="-mt-1.5 flex shrink-0">{actions}</span>}
      </div>
      {children && <div className="pl-8 pr-2">{children}</div>}
    </div>
  );
}

// The tool groups as toggles. Each says what it lets the agent do (title text), and which tools it is.
function Groups({ groups, value, onChange, name }: { groups: AgentGroup[]; value: string[]; onChange: (v: string[]) => void; name: string }) {
  return (
    <span role="group" aria-label={`What ${name} may do`} className="mt-2 flex flex-wrap gap-1.5">
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

function NewAgent({ info, onMade }: { info: AgentsInfo; onMade: (name: string, key: string) => void }) {
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
      <input value={name} onChange={(e) => { setName(e.target.value); setErr(null); }} maxLength={40} spellCheck={false}
             placeholder="Its name, such as Claude" aria-label="The agent's name"
             className="h-11 min-w-0 rounded-full border border-control bg-surface px-4 text-meta outline-none focus:border-sage" />
      <div>
        <span className="text-meta-2 text-muted">What it may do</span>
        <Groups groups={info.groups} value={tools} onChange={setTools} name="the new agent" />
        <ul className="mt-2 flex flex-col gap-0.5 text-meta-2 text-ink-2">
          {info.groups.filter((g) => tools.includes(g.id)).map((g) => <li key={g.id}><b>{g.label}</b>: {g.detail}</li>)}
        </ul>
      </div>
      <Button variant="primary" className="self-start" disabled={!name.trim() || !tools.length} onClick={make}>
        <KeyIcon size={16} />Make its key
      </Button>
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
