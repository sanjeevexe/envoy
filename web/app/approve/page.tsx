"use client";

// The approval page an approval link or a notification opens. Opening it decides nothing: only pressing Approve, in
// your signed-in app or browser, does (a POST with the approval's nonce; link previews and pushes can't).
import { useEffect, useState } from "react";
import { ApprovalCard } from "@/components/Approvals";
import { api, ApiError, Approval } from "@/lib/api";
import { isIOS, isStandalone } from "@/lib/device";

export default function ApprovePage() {
  const [a, setA] = useState<Approval | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    const id = new URLSearchParams(location.search).get("id");
    if (!id) { setErr("No approval in this link."); return; }
    api<Approval>(`/api/approvals/${id}`).then(setA).catch((e) =>
      setErr(e instanceof ApiError && e.status === 401
        ? isIOS() && !isStandalone()
          ? "Open Envoy from your Home Screen: the approval is waiting there (Safari isn't signed in)."
          : "Sign in to Envoy here first: pair this device, or on the Mac open the link the Envoy server printed."
        : e.message));
  };
  useEffect(load, []);
  return (
    <main className="mx-auto max-w-lg p-4 pt-[max(1rem,env(safe-area-inset-top))]">
      <h1 className="mb-1 text-xl font-semibold">Envoy approval</h1>
      <p className="mb-4 text-sm text-stone-600">Envoy is about to do something that can&rsquo;t be undone. Check the screen and decide.</p>
      {err && <p className="rounded bg-rose-50 p-3 text-sm text-rose-800">{err}</p>}
      {a && <ApprovalCard a={a} onDone={load} large />}
      <a href="/" className="mt-6 block text-center text-sm text-stone-500">Open Envoy</a>
    </main>
  );
}
