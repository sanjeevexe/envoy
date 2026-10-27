"use client";

// Signing in on the iPhone (Phase 5): a 6-digit code from Envoy on the Mac, typed inside the installed app. The Home
// Screen app keeps its own cookies, apart from Safari, so the code is entered here rather than following a link.
import { useState } from "react";
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
    <main className="mx-auto flex min-h-[100dvh] max-w-sm flex-col justify-center gap-5 p-6">
      <div className="flex items-center gap-3">
        <img src="/icons/icon-192.png" alt="" className="h-12 w-12 rounded-xl" />
        <h1 className="text-2xl font-semibold">Envoy</h1>
      </div>
      {ios && !home && (
        <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-950">
          For notifications, add Envoy to your Home Screen first: tap <b>Share</b> → <b>Add to Home Screen</b>, then open Envoy from there and
          pair it. (The Home Screen app keeps its own sign-in.)
        </div>
      )}
      <form onSubmit={submit} className="space-y-3">
        <label className="block text-sm text-stone-700" htmlFor="code">Enter the pairing code shown in Envoy on your Mac (the Devices tab).</label>
        <input id="code" value={code} onChange={(e) => { const v = e.target.value.replace(/\D/g, "").slice(0, 6); setCode(v); if (v.length === 6) submit(undefined, v); }} inputMode="numeric" autoComplete="one-time-code"
               pattern="[0-9]{6}" placeholder="000000" autoFocus
               className="w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-center font-mono text-3xl tracking-[0.4em]" />
        <button disabled={code.length !== 6 || busy} className="w-full rounded-xl bg-stone-800 py-3 text-base font-medium text-white disabled:opacity-40">
          {busy ? "Pairing…" : "Pair"}
        </button>
        {error && <p className="text-sm text-rose-700">{error}</p>}
      </form>
      {!ios && <p className="text-xs text-stone-500">On the Mac itself, open the sign-in link the Envoy server printed when it started.</p>}
    </main>
  );
}
