"use client";

// The approval page an approval link or a notification opens: the same sheet as in the app. Opening it decides nothing:
// only pressing Approve, in your signed-in app or browser, does (a POST with the approval's nonce; link previews and
// pushes can't).
import { useEffect, useState } from "react";
import { ApprovalBody } from "@/components/Approvals";
import Avatar, { Wordmark } from "@/components/Avatar";
import Sheet from "@/components/Sheet";
import { api, ApiError } from "@/lib/api";
import { isIOS, isStandalone } from "@/lib/device";

export default function ApprovePage() {
  const [id, setId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(location.search).get("id");
    if (!q) { setErr("No approval in this link."); return; }
    api(`/api/approvals/${q}`).then(() => setId(q)).catch((e) =>
      setErr(e instanceof ApiError && e.status === 401
        ? isIOS() && !isStandalone()
          ? "Open Envoy from your Home Screen: the approval is waiting there (Safari isn't signed in)."
          : "Sign in to Envoy here first: pair this device, or on the Mac open the link the Envoy server printed."
        : e.message));
  }, []);
  return (
    <main className="min-h-[100dvh] bg-page">
      <header className="flex h-[calc(64px+env(safe-area-inset-top))] items-center gap-2.5 px-5 pt-[env(safe-area-inset-top)]">
        <Avatar mood={id ? "needs" : "idle"} size={34} /><Wordmark size={24} />
      </header>
      {err && (
        <div className="mx-auto max-w-[480px] px-6 pt-6">
          <h1 className="font-serif text-display-2 font-normal">This approval can&rsquo;t open here</h1>
          <p className="mt-3 text-body text-ink-2">{err}</p>
          <a href="/" className="mt-6 inline-flex h-11 items-center rounded-full border border-control bg-surface px-4 text-[14px] font-bold text-ink hover:text-ink">Open Envoy</a>
        </div>
      )}
      {id && <Sheet label="Approve this step"><ApprovalBody id={id} standalone /></Sheet>}
    </main>
  );
}
