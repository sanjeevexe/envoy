"use client";

// Signing in on the iPhone (Phase 5): a 6-digit code from Envoy on the Mac, typed inside the installed app. The Home
// Screen app keeps its own cookies, apart from Safari, so the code is entered here rather than following a link.
import { useState } from "react";
import Avatar from "@/components/Avatar";
import { post } from "@/lib/api";
import { isIOS, isStandalone } from "@/lib/device";

export default function Pair({ onPaired }: { onPaired: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ios = isIOS();
  const home = isStandalone();
  const ua = typeof navigator === "undefined" ? "" : navigator.userAgent;
  const name = /iPad/.test(ua) ? "iPad" : ios ? "iPhone" : /Android/.test(ua) ? "Android phone" : "Browser";

  const submit = async (e?: React.FormEvent, value = code) => {
    e?.preventDefault();
    if (value.length !== 6 || busy) return;
    setBusy(true);
    setError(null);
    try {
      await post("/api/pair", { code: value, name: home ? `${name} (Home Screen app)` : `${name} (Safari)` });
      onPaired();
    } catch (err: any) {
      setError(err.message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[100dvh] max-w-[420px] flex-col justify-center gap-6 bg-page px-6 pb-[max(24px,env(safe-area-inset-bottom))] pt-[max(24px,env(safe-area-inset-top))]">
      <div className="ev-rise flex flex-col gap-3">
        <Avatar mood={busy ? "thinking" : error ? "needs" : "idle"} size={84} />
        <h1 className="font-serif text-display font-normal tracking-[-0.01em]">Hi, I&rsquo;m Envoy</h1>
        <p className="font-serif text-voice text-ink-2">I use your phone&rsquo;s apps for you and remember what I see. Let&rsquo;s connect this {name === "Browser" ? "browser" : name} to your Mac.</p>
      </div>
      {ios && !home && (
        <div className="ev-rise ev-r2 rounded-block border border-apricot-line bg-surface p-4 text-meta text-ink-2">
          For notifications, add Envoy to your Home Screen first: tap <b>Share</b>, then <b>Add to Home Screen</b>, then open Envoy from there and
          pair it. (The Home Screen app keeps its own sign-in.)
        </div>
      )}
      <form onSubmit={submit} className="ev-rise ev-r3 flex flex-col gap-3">
        <label className="text-meta text-ink-2" htmlFor="code">Enter the pairing code from Envoy on your Mac (Settings › Devices).</label>
        <input id="code" value={code} onChange={(e) => { const v = e.target.value.replace(/\D/g, "").slice(0, 6); setCode(v); if (v.length === 6) submit(undefined, v); }} inputMode="numeric" autoComplete="one-time-code"
               pattern="[0-9]{6}" placeholder="000000" autoFocus
               className="h-16 w-full rounded-card border border-control bg-surface px-4 text-center font-mono text-[30px] font-semibold tracking-[0.4em] outline-none placeholder:text-line-strong focus:border-sage" />
        <button disabled={code.length !== 6 || busy} className="h-[52px] w-full rounded-full bg-ink text-body font-bold text-on-ink disabled:opacity-40">
          {busy ? "Pairing…" : "Pair"}
        </button>
        {error && <p role="alert" className="text-meta text-apricot-ink">{error}</p>}
      </form>
      {!ios && <p className="text-meta-2 text-muted">On the Mac itself, open the sign-in link the Envoy server printed when it started.</p>}
    </main>
  );
}
