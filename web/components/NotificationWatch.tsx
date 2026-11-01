"use client";

// Settings › Phones › Watch notifications: the apps on Envoy's phone whose notifications Envoy may read, for your
// notification triggers ("tell me when anyone comments on my post"). All off until you turn one on; a trigger, or an
// assistant proposing one, can't turn an app on. Envoy keeps only what a trigger asked for, with codes hidden.
import { useEffect, useState } from "react";
import { BellSimpleRingingIcon } from "@phosphor-icons/react";
import { Card, cx, Section } from "@/components/ui";
import { ago, api, post, type WatchSettings, type Watching } from "@/lib/api";

export function watchingLine(w: Watching, names: Record<string, string>): string {
  const apps = w.packages.map((p) => names[p] ?? p).join(", ");
  if (!w.online) return `${w.name} isn’t answering${w.error ? ` (${w.error})` : ""}: watching ${apps} again when it’s back`;
  return `Watching ${apps} on ${w.name}${w.last_ok ? ` · checked ${ago(w.last_ok)}` : ""}`;
}

export default function NotificationWatch() {
  const [info, setInfo] = useState<WatchSettings | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<WatchSettings>("/api/settings/notifications").then(setInfo).catch(() => {}); }, []);
  if (!info) return null;
  const names = Object.fromEntries(info.apps.map((a) => [a.package, a.name]));
  const toggle = async (pkg: string, on: boolean) => {
    setErr(null);
    const next = on ? [...info.on, pkg] : info.on.filter((p) => p !== pkg);
    try {
      const r = await post<{ on: string[] }>("/api/settings/notifications", { apps: next });
      setInfo({ ...info, on: r.on, apps: info.apps.map((a) => ({ ...a, on: r.on.includes(a.package) })) });
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Section title="Watch notifications" intro={<>Apps whose notifications Envoy may read on Envoy&rsquo;s phone, for your notification triggers (&ldquo;tell me when anyone comments on my post&rdquo;). All off until you turn one on. Envoy keeps only the notifications a trigger asked for, with codes hidden, and reads nothing while no trigger needs it.</>}>
      <Card className="overflow-hidden">
        {info.apps.map((a) => (
          <label key={a.package} className="flex min-h-[60px] items-center justify-between gap-3 border-b border-divider px-4 py-2 last:border-b-0">
            <span className="min-w-0">
              <span className="block truncate text-row font-semibold">{a.name}</span>
              {info.read_from_phone && !a.installed && <span className="block truncate text-meta-2 text-muted">Not on Envoy&rsquo;s phone yet</span>}
            </span>
            <span className="flex shrink-0 items-center gap-2.5 text-meta text-ink-2">
              Watch
              <input type="checkbox" checked={a.on} onChange={(e) => toggle(a.package, e.target.checked)} aria-label={`Watch notifications from ${a.name}`} />
            </span>
          </label>
        ))}
      </Card>
      {info.watching.map((w) => (
        <p key={w.phone} className={cx("flex items-start gap-1.5 px-2 text-meta-2 font-semibold", w.online ? "text-sage-ink" : "text-apricot-ink")}>
          <BellSimpleRingingIcon size={14} className="mt-0.5 shrink-0" />{watchingLine(w, names)}
        </p>
      ))}
      {err && <p role="alert" className="px-2 text-meta text-apricot-ink">{err}</p>}
    </Section>
  );
}
