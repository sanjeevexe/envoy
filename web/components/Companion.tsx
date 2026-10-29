"use client";

// The iPhone companion's settings (Phase 5): pair a device with a short code, push notifications on this device,
// photos and screenshots, and the "Send to Envoy" Shortcut's token.
import { useCallback, useEffect, useState } from "react";
import { ago, api, media, post } from "@/lib/api";
import { disablePush, enablePush, isIOS, isStandalone, pushState, PushState } from "@/lib/device";

type Device = { id: string; name: string; scope: string; created_at: number; last_seen?: number | null; user_agent?: string };
type Paired = { devices: Device[]; push: { id: string; device_id: string | null; service: string; last_ok?: number | null; failures: number }[];
  me: { kind: string; device_id: string | null; name: string } | null };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  );
}

const PUSH_TEXT: Record<PushState, string> = {
  unsupported: "This browser can't receive push notifications.",
  needs_home_screen: "On iPhone, notifications work in the Home Screen app: tap Share → Add to Home Screen, open Envoy from there, and pair it.",
  denied: "Notifications are blocked for Envoy in this browser (on iPhone: Settings → Notifications → Envoy).",
  off: "Get a notification when Envoy needs your OK, needs you to take over, or finishes a task.",
  on: "Notifications are on for this device. Approvals, takeovers and finished tasks arrive here.",
};

export default function Companion({ publicUrl }: { publicUrl?: string }) {
  const [paired, setPaired] = useState<Paired | null>(null);
  const [push, setPush] = useState<PushState | null>(null);
  const [pushMsg, setPushMsg] = useState<string | null>(null);
  const [code, setCode] = useState<{ code: string; until: number } | null>(null);
  const [now, setNow] = useState(Date.now());
  const [photos, setPhotos] = useState<{ enabled: boolean; scope: string } | null>(null);
  const [shortcut, setShortcut] = useState<{ token: string; upload_url: string } | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Paired>("/api/paired").then(setPaired).catch(() => {});
    api("/api/settings/photos").then(setPhotos).catch(() => {});
    pushState().then(setPush);
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (!code) return;
    const t = setInterval(() => { setNow(Date.now()); api<Paired>("/api/paired").then(setPaired).catch(() => {}); }, 2000);
    return () => clearInterval(t);
  }, [code]);

  const owner = paired?.me?.kind === "owner";
  const left = code ? Math.max(0, Math.round((code.until - now) / 1000)) : 0;
  const copy = (label: string, text: string) => navigator.clipboard.writeText(text).then(() => { setCopied(label); setTimeout(() => setCopied(null), 2000); });

  const turnOn = async () => {
    setPushMsg(null);
    try { await enablePush(); setPushMsg("Notifications are on."); } catch (e: any) { setPushMsg(e.message); }
    pushState().then(setPush);
    load();
  };
  const test = async () => {
    setPushMsg("Sending…");
    try {
      const r = await post<{ sent: number; results: { status: number; service: string }[] }>("/api/push/test");
      setPushMsg(r.sent ? `Sent to ${r.sent} device${r.sent > 1 ? "s" : ""}: ${r.results.map((x) => `${x.service} ${x.status}`).join(", ")}` : "No device has notifications on yet.");
    } catch (e: any) { setPushMsg(e.message); }
  };

  return (
    <div className="max-w-2xl space-y-6 p-4 text-sm">
      <Section title="Notifications on this device">
        <p className="text-stone-600">{push ? PUSH_TEXT[push] : "…"}</p>
        {isIOS() && !isStandalone() && (
          <ol className="list-decimal space-y-1 rounded-xl bg-white p-3 pl-7 shadow-sm">
            <li>Tap the Share button, then <b>Add to Home Screen</b>.</li>
            <li>Open <b>Envoy</b> from your Home Screen (it keeps its own sign-in, apart from Safari).</li>
            <li>Enter the pairing code from Envoy on your Mac, then turn on notifications there.</li>
          </ol>
        )}
        <div className="flex flex-wrap gap-2">
          {push === "off" && <button onClick={turnOn} className="rounded-lg bg-stone-800 px-4 py-2 font-medium text-white">Turn on notifications</button>}
          {push === "on" && <button onClick={test} className="rounded-lg bg-stone-800 px-4 py-2 font-medium text-white">Send a test</button>}
          {push === "on" && <button onClick={() => disablePush().then(load)} className="rounded-lg bg-stone-200 px-4 py-2 font-medium">Turn off</button>}
        </div>
        {pushMsg && <p className="text-stone-700">{pushMsg}</p>}
      </Section>

      {owner && (
        <Section title="Pair your iPhone">
          {publicUrl?.startsWith("https://") ? (
            <p className="text-stone-600">
              Your iPhone reaches Envoy privately over Tailscale at <b className="break-all">{publicUrl}</b>. Open it in Safari on the iPhone
              (scan the code with the camera), add it to the Home Screen, open it from there, and enter the pairing code.
            </p>
          ) : (
            <p className="rounded-lg bg-amber-50 p-2 text-amber-950">
              Envoy isn&rsquo;t on your tailnet yet, so the iPhone can&rsquo;t reach it. Run <code>scripts/serve_tailnet.sh on</code> on the Mac, then restart Envoy.
            </p>
          )}
          <div className="flex flex-wrap items-start gap-4">
            {publicUrl?.startsWith("https://") && <img src={media("/api/pair/qr")} alt="QR code for Envoy's address" className="h-40 w-40 rounded-lg bg-white p-1 shadow-sm" />}
            <div className="space-y-2">
              <button onClick={() => copy("link", publicUrl ?? "")} className="block rounded-lg bg-stone-200 px-3 py-2">{copied === "link" ? "Copied" : "Copy link"}</button>
              {code && left > 0 ? (
                <div className="rounded-xl bg-white p-3 shadow-sm">
                  <div className="font-mono text-4xl tracking-[0.3em]">{code.code}</div>
                  <div className="text-xs text-stone-500">Pairing code · works once · {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} left</div>
                </div>
              ) : (
                <button onClick={() => post<{ code: string; expires_in: number }>("/api/pair/start").then((r) => { setNow(Date.now()); setCode({ code: r.code, until: Date.now() + r.expires_in * 1000 }); })}
                        className="rounded-lg bg-stone-800 px-4 py-2 font-medium text-white">Show a pairing code</button>
              )}
            </div>
          </div>
        </Section>
      )}

      <Section title="Paired devices">
        {!paired?.devices.length && <p className="text-stone-500">None yet.</p>}
        <div className="divide-y divide-stone-100 rounded-xl bg-white shadow-sm">
          {paired?.devices.map((d) => {
            const subs = paired.push.filter((p) => p.device_id === d.id);
            return (
              <div key={d.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0">
                  <span className="block truncate text-stone-800">{d.name}{paired.me?.device_id === d.id ? " (this device)" : ""}</span>
                  <span className="block truncate text-xs text-stone-500">
                    {d.scope === "session" ? "signed in" : d.scope === "photos" ? "Shortcut: can only send images" : "sign-in code test"}
                    {" · paired "}{ago(d.created_at)}{d.last_seen ? ` · seen ${ago(d.last_seen)}` : ""}
                    {subs.length ? ` · notifications on (${subs[0].service})` : ""}
                  </span>
                </span>
                {owner && <button onClick={() => api(`/api/paired/${d.id}`, { method: "DELETE" }).then(load)} className="text-xs text-rose-700">Remove</button>}
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="Photos and screenshots">
        <p className="text-stone-600">
          Only images you pick or share are sent. Envoy reads their text on your Mac, blacks out card numbers and codes before
          Muse Spark sees the image, keeps only facts it can find in that text (each linked to the photo), and deletes the image.
        </p>
        {photos && (
          <div className="space-y-2 rounded-xl bg-white p-3 shadow-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={photos.enabled} onChange={(e) => post("/api/settings/photos", { ...photos, enabled: e.target.checked }).then(setPhotos)} />
              Let Envoy read images I send
            </label>
            {photos.enabled && ["screenshots", "photos"].map((sc) => (
              <label key={sc} className="ml-6 flex items-center gap-2 text-stone-700">
                <input type="radio" name="photo-scope" checked={photos.scope === sc} onChange={() => post("/api/settings/photos", { ...photos, scope: sc }).then(setPhotos)} />
                {sc === "screenshots" ? "Screenshots only (default)" : "Screenshots and camera photos"}
              </label>
            ))}
          </div>
        )}
      </Section>

      <Section title="“Send to Envoy” in the Share Sheet">
        <p className="text-stone-600">
          A free iOS Shortcut sends a screenshot from the Share Sheet. It uses its own token, which can only send images:
          it can&rsquo;t read your memory, approve anything or start tasks.
        </p>
        {shortcut ? (
          <div className="space-y-2 rounded-xl bg-white p-3 shadow-sm">
            <div className="text-xs text-stone-500">Shown once. Paste it into the Shortcut, then this page can forget it.</div>
            <div className="break-all rounded bg-stone-100 p-2 font-mono text-xs">{shortcut.token}</div>
            <button onClick={() => copy("token", shortcut.token)} className="rounded-lg bg-stone-800 px-3 py-2 text-white">{copied === "token" ? "Copied" : "Copy token"}</button>
            <ol className="list-decimal space-y-1 pl-5 text-stone-700">
              <li>In <b>Shortcuts</b>, make a new shortcut named <b>Send to Envoy</b>; in its settings, turn on <b>Show in Share Sheet</b> and accept <b>Images</b>.</li>
              <li>Add <b>Get Contents of URL</b>: URL <span className="break-all font-mono text-xs">{shortcut.upload_url}</span>, Method <b>POST</b>,
                Header <b>Authorization</b> = <span className="font-mono text-xs">Bearer </span>+ the token, Request Body <b>File</b> = <b>Shortcut Input</b>.</li>
              <li>Add <b>Get Dictionary Value</b> for <b>summary</b>, then <b>Show Notification</b> with it.</li>
            </ol>
          </div>
        ) : (
          <button onClick={() => post("/api/tokens", { scope: "photos", name: "Send to Envoy (Shortcut)" }).then(setShortcut).then(load)}
                  className="rounded-lg bg-stone-800 px-4 py-2 font-medium text-white">Create the Shortcut&rsquo;s token</button>
        )}
      </Section>
    </div>
  );
}
