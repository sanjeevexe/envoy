"use client";

// Settings: how proactive Envoy is (which of its offers notify you), when Envoy asks before an irreversible step (for
// everything, per app, or per routine: the most specific wins), which apps run on your own Android phone and which
// apps' notifications Envoy may watch there, this device and the others paired with Envoy, the AI agents that use Envoy,
// what each may do and the tools they see (the learned routines you share), and how Envoy looks on this device (light or
// dark).
import { useEffect, useState } from "react";
import { CheckCircleIcon, DeviceMobileIcon } from "@phosphor-icons/react";
import AgentKeys from "@/components/AgentKeys";
import AgentTools from "@/components/AgentTools";
import Companion from "@/components/Companion";
import { Outbox } from "@/components/Handoff";
import NotificationWatch from "@/components/NotificationWatch";
import SavedLogins from "@/components/SavedLogins";
import { appName } from "@/components/Tasks";
import { Button, Card, cx, Section, Segmented } from "@/components/ui";
import { api, post } from "@/lib/api";
import { setThemeChoice, themeChoice, type ThemeChoice } from "@/lib/theme";

const SECTIONS = ["Approvals", "Phones", "Devices", "Agents", "Appearance"] as const;
export default function SettingsPage({ publicUrl, profile }: { publicUrl?: string; profile?: string }) {
  // `/?settings=agents` (any section's name) opens that section; Approvals otherwise.
  const [section, setSection] = useState<(typeof SECTIONS)[number]>(() => {
    const asked = typeof location === "undefined" ? null : new URLSearchParams(location.search).get("settings");
    return SECTIONS.find((x) => x.toLowerCase() === asked?.toLowerCase()) ?? "Approvals";
  });
  return (
    // Agents is wider: on a big screen (filmed at 1080p) the agents and the tools they see sit side by side.
    <div className={cx("@container mx-auto w-full pb-10 md:pt-6", section === "Agents" ? "max-w-[1180px]" : "max-w-[720px]")}>
      {/* On a phone the five sections are wider than the screen: the row scrolls sideways, the page doesn't. */}
      <div className="overflow-x-auto px-4 pt-3 [scrollbar-width:none]"><Segmented options={SECTIONS} value={section} onChange={setSection} label="Settings" /></div>
      {profile && <p className="px-6 pt-2 text-meta-2 text-muted">Using {profile === "demo" ? "the demo memory (SkyLark test data)" : "your memory"}</p>}
      <div className="ev-fade" key={section}>
        {section === "Approvals" && <><Proactivity /><Settings /></>}
        {section === "Phones" && <><Phones /><NotificationWatch /><SavedLogins /><Outbox /></>}
        {section === "Devices" && <Companion publicUrl={publicUrl} />}
        {section === "Agents" && <div className="grid grid-cols-1 items-start @5xl:grid-cols-2"><AgentKeys /><AgentTools /></div>}
        {section === "Appearance" && <Appearance />}
      </div>
    </div>
  );
}

// Appearance, per device (lib/theme.ts): Light is the default whatever the device's setting; Match device follows it.
const LOOKS: { choice: ThemeChoice; label: string; detail: string }[] = [
  { choice: "light", label: "Light", detail: "The cream look." },
  { choice: "dark", label: "Dark", detail: "Deep green, easier on the eyes at night." },
  { choice: "system", label: "Match device", detail: "Light or dark, following this device\u2019s own setting." },
];

function Appearance() {
  const [choice, setChoice] = useState<ThemeChoice | null>(null);
  useEffect(() => setChoice(themeChoice()), []);
  if (!choice) return null;
  return (
    <Section title="Appearance" intro="How Envoy looks on this device. Each device keeps its own choice.">
      <Card className="overflow-hidden" role="radiogroup" aria-label="Appearance">
        {LOOKS.map((l) => (
          <label key={l.choice} className="flex min-h-[64px] cursor-pointer items-center gap-3 border-b border-divider px-4 py-3 last:border-b-0">
            <input type="radio" name="appearance" checked={choice === l.choice} onChange={() => { setThemeChoice(l.choice); setChoice(l.choice); }} />
            <Swatch choice={l.choice} />
            <span className="min-w-0">
              <span className="block text-row font-semibold">{l.label}{l.choice === "light" && <span className="font-normal text-muted"> · the default</span>}</span>
              <span className="mt-0.5 block text-meta-2 text-muted">{l.detail}</span>
            </span>
          </label>
        ))}
      </Card>
    </Section>
  );
}

// A tiny picture of a theme, in that theme's own tokens (globals.css applies either set inside any data-theme element;
// the raw tokens, since Tailwind's color utilities resolve once on :root); Match device is half of each.
function Swatch({ choice }: { choice: ThemeChoice }) {
  const pic = (theme: "light" | "dark", cls?: string) => (
    <span data-theme={theme} className={cx("absolute inset-0 flex items-center gap-1.5 bg-[var(--page)] pl-2", cls)}>
      <span className="h-3.5 w-3.5 shrink-0 rounded-full bg-[var(--sage)]" />
      <span className="flex flex-col gap-1"><span className="h-1 w-6 rounded-full bg-[var(--ink)]" /><span className="h-1 w-4 rounded-full bg-[var(--muted)]" /></span>
    </span>
  );
  return (
    <span aria-hidden className="relative h-9 w-[56px] shrink-0 overflow-hidden rounded-sm border border-line">
      {pic(choice === "dark" ? "dark" : "light")}
      {choice === "system" && pic("dark", "[clip-path:inset(0_0_0_50%)]")}
    </span>
  );
}

const select = "h-11 max-w-[55%] shrink-0 rounded-full border border-control bg-surface pl-3 pr-2 text-meta font-semibold outline-none focus:border-sage";


// Proactivity: offers always wait in the app; this decides which ones also notify you. Approvals and takeovers aren't
// offers: they always notify.
const LEVELS: { level: string; label: string; detail: string }[] = [
  { level: "off", label: "Off", detail: "Questions wait in the app. No notifications for them." },
  { level: "important", label: "Important only", detail: "When a trigger asks first, a file arrives from your Mac, or an assistant wants to set something up." },
  { level: "all", label: "Everything", detail: "Also when I notice something you do often and could make a habit." },
];

function Proactivity() {
  const [level, setLevel] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { api<{ level: string }>("/api/settings/proactivity").then((r) => setLevel(r.level)).catch(() => {}); }, []);
  if (!level) return null;
  const save = (next: string) => {
    setLevel(next);
    post<{ level: string }>("/api/settings/proactivity", { level: next }).then((r) => { setLevel(r.level); setSaved(true); setTimeout(() => setSaved(false), 2500); }).catch(() => {});
  };
  return (
    <Section title="Proactivity" intro={<>Envoy can ask &ldquo;Should I&hellip;?&rdquo; when a trigger set to ask fires, or when it notices a habit. Nothing starts until you tap Yes. Choose which questions notify you.</>}>
      <Card className="overflow-hidden" role="radiogroup" aria-label="Which questions notify you">
        {LEVELS.map((l) => (
          <label key={l.level} className="flex min-h-[60px] cursor-pointer items-start gap-3 border-b border-divider px-4 py-3 last:border-b-0">
            <input type="radio" name="proactivity" className="mt-1" checked={level === l.level} onChange={() => save(l.level)} />
            <span className="min-w-0">
              <span className="block text-row font-semibold">{l.label}{l.level === "important" && <span className="font-normal text-muted"> · the default</span>}</span>
              <span className="mt-0.5 block text-meta-2 text-muted">{l.detail}</span>
            </span>
          </label>
        ))}
      </Card>
      <p className="px-2 text-meta-2 text-muted">Approvals and &ldquo;take over the phone&rdquo; always notify you, whatever this says.</p>
      {saved && <p role="status" className="flex items-center gap-1.5 px-2 text-meta font-semibold text-sage-ink"><CheckCircleIcon size={16} weight="fill" />Saved</p>}
    </Section>
  );
}

type Rules = { default: string; apps: Record<string, string>; routines: Record<string, string> };
// `money`: the routine's irreversible step spends money, so it always asks (approval_rules.decide checks money first)
type Info = { rules: Rules; apps: string[]; routines: { name: string; app: string; intent: string; irreversible: boolean; money?: boolean }[] };

const LABEL: Record<string, string> = {
  always: "Always ask",
  unless_requested: "Ask unless I asked for it",
  never: "Never ask (standing approval)",
};

function Settings() {
  const [info, setInfo] = useState<Info | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => { api<Info>("/api/settings/approvals").then((i) => { setInfo(i); setRules(i.rules); }); }, []);
  if (!info || !rules) return <p className="px-6 py-6 text-body text-muted">Loading…</p>;

  const save = async (next: Rules) => {
    setRules(next);
    const r = await post<Rules>("/api/settings/approvals", next);
    setRules(r);
    setSaved("Saved: applies to the next approval");
    setTimeout(() => setSaved(null), 2500);
  };
  const setApp = (app: string, mode: string) => {
    const apps = { ...rules.apps };
    if (mode) apps[app] = mode; else delete apps[app];
    save({ ...rules, apps });
  };
  const setRoutine = (name: string, mode: string) => {
    const routines = { ...rules.routines };
    if (mode) routines[name] = mode; else delete routines[name];
    save({ ...rules, routines });
  };

  return (
    <div>
      <Section title="Approvals" intro={<>Before a step that can&rsquo;t be undone (checking in, sending, cancelling), Envoy can ask you first. With <b>Ask unless I asked for it</b>, &ldquo;check me in&rdquo; is your OK to tap &ldquo;Confirm check-in&rdquo; for that trip: Envoy does it and tells you.</>}>
        <Card className="overflow-hidden" role="radiogroup" aria-label="When to ask">
          {["unless_requested", "always"].map((m) => (
            <label key={m} className="flex min-h-[56px] cursor-pointer items-center gap-3 border-b border-divider px-4 py-3 last:border-b-0">
              <input type="radio" name="default" checked={rules.default === m} onChange={() => save({ ...rules, default: m })} />
              <span className="text-row font-semibold">{LABEL[m]}</span>
              {m === "unless_requested" && <span className="text-meta-2 text-muted">the default</span>}
            </label>
          ))}
        </Card>
        <ul className="flex flex-col gap-1.5 px-2 text-meta text-ink-2">
          <li>Anything that costs money (pay, buy, order, subscribe) always asks.</li>
          <li>Envoy still asks when the step isn&rsquo;t what you asked for, or its details differ (another flight, another seat).</li>
          <li>Requests from triggers, emails or other assistants (Muse, Claude, over MCP) ask, unless a routine has a standing approval.</li>
        </ul>
      </Section>

      <Section title="Per app">
        <Card className="overflow-hidden">
          {info.apps.map((app) => (
            <label key={app} className="flex min-h-[56px] items-center justify-between gap-3 border-b border-divider px-4 py-2 last:border-b-0">
              <span className="min-w-0 truncate text-row font-semibold">{appName(app)}</span>
              <select value={rules.apps[app] ?? ""} onChange={(e) => setApp(app, e.target.value)} className={select} aria-label={`When to ask in ${appName(app)}`}>
                <option value="">Same as above</option>
                <option value="unless_requested">{LABEL.unless_requested}</option>
                <option value="always">{LABEL.always}</option>
              </select>
            </label>
          ))}
        </Card>
      </Section>

      <Section title="Per routine" intro="A standing approval lets a routine's own irreversible step run without asking, even when a trigger starts it: checking in 24 hours before every flight, say. Never for money.">
        <Card className="overflow-hidden">
          {info.routines.filter((r) => r.irreversible).map((r) => (
            <label key={r.name} className="flex min-h-[60px] items-center justify-between gap-3 border-b border-divider px-4 py-2 last:border-b-0">
              <span className="min-w-0">
                <span className="block truncate text-row font-semibold">{r.intent}</span>
                <span className="block truncate text-meta-2 text-muted">{appName(r.app)}{r.money ? " · Payments always ask" : ""}</span>
              </span>
              <select value={rules.routines[r.name] ?? ""} onChange={(e) => setRoutine(r.name, e.target.value)} className={select} aria-label={`When to ask for ${r.intent}`}>
                <option value="">Same as app</option>
                <option value="unless_requested">{LABEL.unless_requested}</option>
                <option value="always">{LABEL.always}</option>
                {r.money
                  ? rules.routines[r.name] === "never" && <option value="never" disabled>Always asks: it spends money</option>  // set before money was checked here
                  : <option value="never">{LABEL.never}</option>}
              </select>
            </label>
          ))}
        </Card>
      </Section>
      {saved && <p role="status" className="mx-6 mt-4 flex items-center gap-1.5 text-meta font-semibold text-sage-ink"><CheckCircleIcon size={16} weight="fill" />{saved}</p>}
    </div>
  );
}

type PhoneInfo = { phone_apps: string[]; apps: string[]; emulator_refused: Record<string, string>;
  learned?: Record<string, { name?: string; why?: string; at?: number }>; names?: Record<string, string>;
  phones: { avd: string; name?: string; model?: string; android?: string; state?: string }[] };

// What Envoy calls a phone in its offers, "Before I start" and its notes, word for word ("Envoy's phone"). Empty: "your Pixel 5".
function PhoneName({ phone, onSaved }: { phone: PhoneInfo["phones"][number]; onSaved: (name: string | null) => void }) {
  const current = phone.model && phone.name !== phone.model ? phone.name ?? "" : "";
  const [draft, setDraft] = useState(current);
  const [saved, setSaved] = useState<string | null>(null);
  const save = async () => {
    try {
      const r = await post<{ name: string | null }>("/api/settings/phones/name", { id: phone.avd, name: draft.trim() });
      onSaved(r.name); setDraft(r.name ?? ""); setSaved(r.name ? `Offers now say \u201c${r.name}\u201d` : `Offers now say \u201cyour ${phone.model ?? "phone"}\u201d`);
    } catch (e: any) { setSaved(e.message); }
  };
  return (
    <span className="mt-2 flex items-center gap-2">
      <input value={draft} onChange={(e) => { setDraft(e.target.value); setSaved(null); }} maxLength={40} spellCheck={false}
             placeholder={`your ${phone.model ?? "phone"}`} aria-label="What Envoy calls this phone"
             className="h-9 min-w-0 flex-1 rounded-full border border-control bg-surface px-3 text-meta outline-none focus:border-sage" />
      <Button onClick={save} disabled={draft.trim() === current}>Save</Button>
      {saved && <span role="status" className="text-meta-2 text-sage-ink">{saved}</span>}
    </span>
  );
}

// Which apps run on your own Android phone instead of an emulator (Phase 6). Envoy still asks each time before using it.
// Apps that block emulators always do: the starting list, and apps Envoy found itself (a bot check), which you can untick.
function Phones() {
  const [info, setInfo] = useState<PhoneInfo | null>(null);
  useEffect(() => { api<PhoneInfo>("/api/settings/phones").then(setInfo).catch(() => {}); }, []);
  if (!info) return null;
  const toggle = async (app: string, on: boolean) => {
    const next = on ? [...info.phone_apps, app] : info.phone_apps.filter((a) => a !== app);
    const r = await post<{ phone_apps: string[]; learned?: PhoneInfo["learned"] }>("/api/settings/phones", { phone_apps: next });
    setInfo({ ...info, phone_apps: r.phone_apps, learned: r.learned ?? info.learned });
  };
  return (
    <Section title="Phones" intro={<>Tasks run on an emulator unless you say &ldquo;on my phone&rdquo;, an app below is set to your phone, or the app blocks emulators. When an app shows a bot check on an emulator, Envoy sets it to your phone itself; untick it to undo. Envoy asks before every task on your phone, shows a banner there while it works, and stops the moment you touch the phone.</>}>
      <Card className="overflow-hidden">
        {info.phones.length ? info.phones.map((p) => (
          <div key={p.avd} className="flex min-h-[60px] items-center gap-3 border-b border-divider px-4 py-3 last:border-b-0">
            <DeviceMobileIcon size={20} className="shrink-0 text-sage-ink" />
            <span className="min-w-0 flex-1">
              <span className="block text-row font-semibold">{p.name ?? "Android phone"}{p.android ? ` · Android ${p.android}` : ""}</span>
              <span className={cx("block text-meta-2", p.state === "device" ? "text-sage-ink" : "text-apricot-ink")}>
                {p.state === "device" ? "Connected" : p.state === "unauthorized" ? "Allow USB debugging on the phone" : "Not connected"}
                {p.model && p.name !== p.model ? <span className="text-muted"> · {p.model}</span> : null}
              </span>
              <PhoneName phone={p} onSaved={(name) => setInfo({ ...info, phones: info.phones.map((x) => x.avd === p.avd ? { ...x, name: name ?? x.model } : x) })} />
            </span>
          </div>
        )) : <p className="px-4 py-4 text-meta text-ink-2">No Android phone connected (USB, or wireless debugging).</p>}
      </Card>
      <Card className="overflow-hidden">
        {[...info.apps].sort((a, b) => (info.names?.[a] ?? a).localeCompare(info.names?.[b] ?? b)).map((app) => (
          <label key={app} className="flex min-h-[60px] items-center justify-between gap-3 border-b border-divider px-4 py-2 last:border-b-0">
            <span className="min-w-0">
              <span className="block truncate text-row font-semibold">{info.names?.[app] ?? appName(app)}</span>
              {info.emulator_refused[app] && <span className="block truncate text-meta-2 text-muted">Blocks emulators</span>}
              {info.learned?.[app] && info.phone_apps.includes(app) ? (
                <span className="block text-meta-2 text-apricot-ink">
                  Set by Envoy: it {info.learned[app].why ?? "blocked the emulator"}{info.learned[app].at ? ` (${new Date(info.learned[app].at! * 1000).toLocaleDateString()})` : ""}
                </span>
              ) : null}
            </span>
            <span className="flex shrink-0 items-center gap-2.5 text-meta text-ink-2">
              On my phone
              <input type="checkbox" checked={info.phone_apps.includes(app) || !!info.emulator_refused[app]} disabled={!!info.emulator_refused[app]}
                     onChange={(e) => toggle(app, e.target.checked)} />
            </span>
          </label>
        ))}
      </Card>
      <p className="px-2 text-meta-2 text-muted">Always on your phone (known to block emulators): {Object.values(info.emulator_refused).join(", ")}.</p>
    </Section>
  );
}
