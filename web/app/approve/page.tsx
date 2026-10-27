"use client";

// The approval page an approval link opens (from MCP clients like Muse, or a notification). Opening it decides
// nothing: only pressing Approve, in your signed-in browser, does.
import { useEffect, useState } from "react";
import { ApprovalCard } from "@/components/Approvals";
import { api, ApiError, Approval } from "@/lib/api";

export default function ApprovePage() {
  const [a, setA] = useState<Approval | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => {
    const id = new URLSearchParams(location.search).get("id");
    if (!id) { setErr("No approval in this link."); return; }
    api<Approval>(`/api/approvals/${id}`).then(setA).catch((e) =>
      setErr(e instanceof ApiError && e.status === 401 ? "Sign in to Envoy in this browser first (open the link the Envoy server printed)." : e.message));
  };
  useEffect(load, []);
  return (
    <main className="mx-auto max-w-lg p-4">
      <h1 className="mb-1 text-lg font-semibold">Envoy approval</h1>
      <p className="mb-4 text-sm text-stone-600">Envoy is about to do something that can't be undone. Check the screen and decide.</p>
      {err && <p className="rounded bg-rose-50 p-3 text-sm text-rose-800">{err}</p>}
      {a && <ApprovalCard a={a} onDone={load} />}
      <a href="/" className="mt-4 block text-sm text-stone-500">Open Envoy</a>
    </main>
  );
}
