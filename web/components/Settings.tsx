"use client";

// When Envoy asks before an irreversible step: for everything, per app, or per routine (the most specific wins).
import { useEffect, useState } from "react";
import { api, post } from "@/lib/api";

type Rules = { default: string; apps: Record<string, string>; routines: Record<string, string> };
type Info = { rules: Rules; apps: string[]; routines: { name: string; app: string; intent: string; irreversible: boolean }[] };

const LABEL: Record<string, string> = {
  always: "Always ask",
  unless_requested: "Ask unless I asked for it",
  never: "Never ask (standing approval)",
};

export default function Settings() {
  const [info, setInfo] = useState<Info | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => { api<Info>("/api/settings/approvals").then((i) => { setInfo(i); setRules(i.rules); }); }, []);
  if (!info || !rules) return <p className="p-4 text-sm">Loading…</p>;

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
    <div className="max-w-2xl space-y-6 p-4 text-sm">
      <section>
        <h2 className="text-base font-semibold">Approvals</h2>
        <p className="mt-1 text-stone-600">
          Before an irreversible step (checking in, sending, cancelling), Envoy can ask you first. With
          <b> Ask unless I asked for it</b>, &ldquo;check me in&rdquo; is your OK to tap &ldquo;Confirm check-in&rdquo; for that trip: Envoy does it and tells you.
        </p>
        <div className="mt-3 flex flex-col gap-2">
          {["unless_requested", "always"].map((m) => (
            <label key={m} className="flex items-center gap-2">
              <input type="radio" name="default" checked={rules.default === m} onChange={() => save({ ...rules, default: m })} />
              {LABEL[m]}{m === "unless_requested" && <span className="text-xs text-stone-500">(default)</span>}
            </label>
          ))}
        </div>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-stone-600">
          <li>Anything that costs money (pay, buy, order, subscribe) always asks.</li>
          <li>Envoy still asks when the step isn&rsquo;t what you asked for, or its details differ (another flight, another seat).</li>
          <li>Requests from triggers, emails or other assistants (Muse, Claude, over MCP) ask, unless a routine has a standing approval.</li>
        </ul>
      </section>

      <section>
        <h3 className="font-semibold">Per app</h3>
        <div className="mt-2 divide-y divide-stone-100 rounded-xl bg-white shadow-sm">
          {info.apps.map((app) => (
            <div key={app} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="truncate text-stone-700">{app}</span>
              <select value={rules.apps[app] ?? ""} onChange={(e) => setApp(app, e.target.value)} className="rounded border border-stone-300 px-2 py-1">
                <option value="">Same as above</option>
                <option value="unless_requested">{LABEL.unless_requested}</option>
                <option value="always">{LABEL.always}</option>
              </select>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="font-semibold">Per routine</h3>
        <p className="mt-1 text-xs text-stone-600">A standing approval lets a routine&rsquo;s own irreversible step run without asking, even when a trigger starts it, e.g. checking in 24 hours before every flight. Never for money.</p>
        <div className="mt-2 divide-y divide-stone-100 rounded-xl bg-white shadow-sm">
          {info.routines.filter((r) => r.irreversible).map((r) => (
            <div key={r.name} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="min-w-0"><span className="block truncate text-stone-800">{r.intent}</span><span className="block truncate text-xs text-stone-500">{r.name}</span></span>
              <select value={rules.routines[r.name] ?? ""} onChange={(e) => setRoutine(r.name, e.target.value)} className="rounded border border-stone-300 px-2 py-1">
                <option value="">Same as app</option>
                <option value="unless_requested">{LABEL.unless_requested}</option>
                <option value="always">{LABEL.always}</option>
                <option value="never">{LABEL.never}</option>
              </select>
            </div>
          ))}
        </div>
      </section>
      <Phones />
      {saved && <div className="text-emerald-700">{saved}</div>}
    </div>
  );
}

type PhoneInfo = { phone_apps: string[]; apps: string[]; emulator_refused: Record<string, string>;
  learned?: Record<string, { name?: string; why?: string; at?: number }>; names?: Record<string, string>;
  phones: { avd: string; name?: string; android?: string; state?: string }[] };

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
    <section>
      <h2 className="text-base font-semibold">Phones</h2>
      <p className="mt-1 text-stone-600">
        Tasks run on an emulator unless you say &ldquo;on my phone&rdquo;, an app below is set to your phone, or the app blocks emulators.
        When an app shows a bot check on an emulator, Envoy sets it to your phone itself; untick it to undo.
        Envoy asks before every task on your phone, shows a banner there while it works, and stops the moment you touch the phone.
      </p>
      <div className="mt-2 text-xs text-stone-600">
        {info.phones.length ? info.phones.map((p) => (
          <div key={p.avd}>📱 {p.name ?? "Android phone"}{p.android ? ` · Android ${p.android}` : ""} · {p.state === "device" ? "connected" : p.state === "unauthorized" ? "allow USB debugging on the phone" : "not connected"}</div>
        )) : "No Android phone connected (USB, or wireless debugging)."}
      </div>
      <div className="mt-2 divide-y divide-stone-100 rounded-xl bg-white shadow-sm">
        {[...info.apps].sort((a, b) => (info.names?.[a] ?? a).localeCompare(info.names?.[b] ?? b)).map((app) => (
          <label key={app} className="flex items-center justify-between gap-3 px-3 py-2">
            <span className="min-w-0 truncate text-stone-700">
              {info.names?.[app] ?? app}
              {info.names?.[app] ? <span className="ml-1 text-xs text-stone-400">{app}</span> : null}
              {info.emulator_refused[app] ? <span className="ml-1 text-xs text-stone-500">(blocks emulators)</span> : null}
              {info.learned?.[app] && info.phone_apps.includes(app) ? (
                <span className="block truncate text-xs text-amber-700">
                  Set by Envoy: it {info.learned[app].why ?? "blocked the emulator"}
                  {info.learned[app].at ? ` (${new Date(info.learned[app].at! * 1000).toLocaleDateString()})` : ""}
                </span>
              ) : null}
            </span>
            <span className="flex items-center gap-2 text-xs text-stone-600">
              Runs on my phone
              <input type="checkbox" checked={info.phone_apps.includes(app) || !!info.emulator_refused[app]} disabled={!!info.emulator_refused[app]}
                     onChange={(e) => toggle(app, e.target.checked)} />
            </span>
          </label>
        ))}
      </div>
      <p className="mt-2 text-xs text-stone-500">
        Always on your phone (known to block emulators): {Object.values(info.emulator_refused).join(", ")}.
      </p>
    </section>
  );
}
