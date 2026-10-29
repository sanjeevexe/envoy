"use client";

// The iPhone companion's settings (Phase 5): pair a device with a short code, push notifications on this device,
// photos and screenshots, and the "Send to Envoy" Shortcut's token.
import { useCallback, useEffect, useState } from "react";
import { BellRingingIcon, CopyIcon, DeviceMobileIcon, KeyIcon, TrashIcon } from "@phosphor-icons/react";
import { Button, Card, Chip, Section } from "@/components/ui";
import { ago, api, media, post } from "@/lib/api";
import { disablePush, enablePush, isIOS, isStandalone, pushState, PushState } from "@/lib/device";

type Device = { id: string; name: string; scope: string; created_at: number; last_seen?: number | null; user_agent?: string };
type Paired = { devices: Device[]; push: { id: string; device_id: string | null; service: string; last_ok?: number | null; failures: number }[];
  me: { kind: string; device_id: string | null; name: string } | null };

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

  const steps = "flex flex-col gap-1.5 pl-5 text-meta text-ink-2 [list-style:decimal]";
  return (
    <div>
      <Section title="Notifications on this device" intro={push ? PUSH_TEXT[push] : "…"}>
        {isIOS() && !isStandalone() && (
          <Card className="px-4 py-3">
            <ol className={steps}>
              <li>Tap the Share button, then <b>Add to Home Screen</b>.</li>
              <li>Open <b>Envoy</b> from your Home Screen (it keeps its own sign-in, apart from Safari).</li>
              <li>Enter the pairing code from Envoy on your Mac, then turn on notifications there.</li>
            </ol>
          </Card>
        )}
        {(push === "off" || push === "on") && (
          <div className="flex flex-wrap gap-2">
            {push === "off" && <Button variant="primary" onClick={turnOn}><BellRingingIcon size={18} />Turn on notifications</Button>}
            {push === "on" && <Button variant="primary" onClick={test}>Send a test</Button>}
            {push === "on" && <Button onClick={() => disablePush().then(load)}>Turn off</Button>}
          </div>
        )}
        {pushMsg && <p role="status" className="px-2 text-meta text-ink-2">{pushMsg}</p>}
      </Section>

      {owner && (
        <Section title="Pair your iPhone" intro={publicUrl?.startsWith("https://") ? (
          <>Your iPhone reaches Envoy privately over Tailscale at <b className="break-all">{publicUrl}</b>. Open it in Safari on the iPhone (scan the code with the camera), add it to the Home Screen, open it from there, and enter the pairing code.</>
        ) : undefined}>
          {!publicUrl?.startsWith("https://") && (
            <p className="rounded-block bg-apricot-tint px-4 py-3 text-meta text-apricot-ink">
              Envoy isn&rsquo;t on your tailnet yet, so the iPhone can&rsquo;t reach it. Run <code>scripts/serve_tailnet.sh on</code> on the Mac, then restart Envoy.
            </p>
          )}
          <Card className="flex flex-wrap items-center gap-5 p-4">
            {publicUrl?.startsWith("https://") && <img src={media("/api/pair/qr")} alt="QR code for Envoy's address" className="h-36 w-36 rounded-sm border border-line bg-white p-1" />}
            <div className="flex flex-col items-start gap-3">
              {code && left > 0 ? (
                <div>
                  <div className="font-mono text-[34px] font-semibold tracking-[0.3em]">{code.code}</div>
                  <div className="text-meta-2 text-muted">Pairing code · works once · {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} left</div>
                </div>
              ) : (
                <Button variant="primary" onClick={() => post<{ code: string; expires_in: number }>("/api/pair/start").then((r) => { setNow(Date.now()); setCode({ code: r.code, until: Date.now() + r.expires_in * 1000 }); })}>
                  Show a pairing code
                </Button>
              )}
              <Button onClick={() => copy("link", publicUrl ?? "")}><CopyIcon size={16} />{copied === "link" ? "Copied" : "Copy the link"}</Button>
            </div>
          </Card>
        </Section>
      )}

      <Section title="Paired devices">
        <Card className="overflow-hidden">
          {!paired?.devices.length && <p className="px-4 py-4 text-meta text-muted">None yet.</p>}
          {paired?.devices.map((d) => {
            const subs = paired.push.filter((p) => p.device_id === d.id);
            return (
              <div key={d.id} className="flex min-h-[64px] items-center gap-3 border-b border-divider py-2 pl-4 pr-2 last:border-b-0">
                {d.scope === "session" ? <DeviceMobileIcon size={20} className="shrink-0 text-sage-ink" /> : <KeyIcon size={20} className="shrink-0 text-sage-ink" />}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-row font-semibold">{d.name}{paired.me?.device_id === d.id ? " (this device)" : ""}</span>
                  <span className="block text-meta-2 text-muted">
                    {d.scope === "session" ? "Signed in" : d.scope === "photos" ? "Shortcut: can only send images" : d.scope === "siri" ? "Siri shortcut: can ask Envoy and start tasks; can't approve anything" : "Sign-in code test"}
                    {" · paired "}{ago(d.created_at)}{d.last_seen ? ` · seen ${ago(d.last_seen)}` : ""}
                  </span>
                  {subs.length > 0 && <span className="mt-1 block"><Chip icon={BellRingingIcon}>Notifications on ({subs[0].service})</Chip></span>}
                </span>
                {owner && (
                  <button onClick={() => api(`/api/paired/${d.id}`, { method: "DELETE" }).then(load)} aria-label={`Remove ${d.name}`} title="Remove"
                          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full hover:bg-well"><TrashIcon size={18} /></button>
                )}
              </div>
            );
          })}
        </Card>
      </Section>

      <Section title="Photos and screenshots" intro="Only images you pick or share are sent. Envoy reads their text on your Mac, blacks out card numbers and codes before Muse Spark sees the image, keeps only facts it can find in that text (each linked to the photo), and deletes the image.">
        {photos && (
          <Card className="overflow-hidden">
            <label className="flex min-h-[56px] items-center gap-3 border-b border-divider px-4 last:border-b-0">
              <input type="checkbox" checked={photos.enabled} onChange={(e) => post("/api/settings/photos", { ...photos, enabled: e.target.checked }).then(setPhotos)} />
              <span className="text-row font-semibold">Let Envoy read images I send</span>
            </label>
            {photos.enabled && ["screenshots", "photos"].map((sc) => (
              <label key={sc} className="flex min-h-[52px] items-center gap-3 border-b border-divider pl-11 pr-4 last:border-b-0">
                <input type="radio" name="photo-scope" checked={photos.scope === sc} onChange={() => post("/api/settings/photos", { ...photos, scope: sc }).then(setPhotos)} />
                <span className="text-row">{sc === "screenshots" ? "Screenshots only (the default)" : "Screenshots and camera photos"}</span>
              </label>
            ))}
          </Card>
        )}
      </Section>

      <Section title="“Send to Envoy” in the Share Sheet" intro={<>A free iOS Shortcut sends a screenshot from the Share Sheet. It uses its own token, which can only send images: it can&rsquo;t read your memory, approve anything or start tasks.</>}>
        {shortcut ? (
          <Card className="flex flex-col gap-3 p-4">
            <p className="text-meta-2 text-muted">Shown once. Paste it into the Shortcut, then this page can forget it.</p>
            <div className="break-all rounded-sm bg-well p-3 font-mono text-meta-2">{shortcut.token}</div>
            <Button variant="primary" className="self-start" onClick={() => copy("token", shortcut.token)}><CopyIcon size={16} />{copied === "token" ? "Copied" : "Copy the token"}</Button>
            <ol className={steps}>
              <li>In <b>Shortcuts</b>, make a new shortcut named <b>Send to Envoy</b>; in its settings, turn on <b>Show in Share Sheet</b> and accept <b>Images</b>.</li>
              <li>Add <b>Get Contents of URL</b>: URL <span className="break-all font-mono text-meta-2">{shortcut.upload_url}</span>, Method <b>POST</b>,
                Header <b>Authorization</b> = <span className="font-mono text-meta-2">Bearer </span>+ the token, Request Body <b>File</b> = <b>Shortcut Input</b>.</li>
              <li>Add <b>Get Dictionary Value</b> for <b>summary</b>, then <b>Show Notification</b> with it.</li>
            </ol>
          </Card>
        ) : (
          <Button variant="primary" className="self-start" onClick={() => post("/api/tokens", { scope: "photos", name: "Send to Envoy (Shortcut)" }).then(setShortcut).then(load)}>
            Create the Shortcut&rsquo;s token
          </Button>
        )}
      </Section>
    </div>
  );
}
