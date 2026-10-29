"use client";

// Pending irreversible actions. Only you can approve, here or on the approval page; Envoy and outside assistants can't.
import { useState } from "react";
import { api, ago, Approval, media, post } from "@/lib/api";

export function ApprovalCard({ a, onDone, large }: { a: Approval; onDone?: () => void; large?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const decide = async (decision: "approve" | "decline") => {
    setBusy(true);
    try {
      const full = await api<Approval>(`/api/approvals/${a.id}`);
      const r = await post<Approval>(`/api/approvals/${a.id}`, { decision, nonce: full.nonce });
      setMsg(r.status === "approved" ? "Approved" : "Declined");
      onDone?.();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };
  if (large) {
    // One-handed on a phone: the screen it's for, what it does, and two big buttons within thumb reach.
    return (
      <div className="space-y-3 rounded-2xl bg-white p-4 shadow-sm">
        <div className="text-lg font-semibold">{a.description}</div>
        {a.goal && <div className="text-sm text-stone-600">Task: {a.goal}</div>}
        {a.screenshot && <img src={media(`/api/approvals/${a.id}/shot`)} alt="The screen this approval is for" className="mx-auto max-h-[45dvh] rounded-lg border border-stone-200" />}
        <ul className="list-disc pl-5 text-xs text-stone-500">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        <div className="text-xs text-stone-400">{a.app} · {ago(a.created_at)}</div>
        {a.status === "pending" && !msg ? (
          <div className="grid grid-cols-2 gap-3">
            <button disabled={busy} onClick={() => decide("decline")} className="h-14 rounded-xl bg-stone-200 text-base font-medium disabled:opacity-50">Decline</button>
            <button disabled={busy} onClick={() => decide("approve")} className="h-14 rounded-xl bg-emerald-600 text-base font-semibold text-white disabled:opacity-50">Approve</button>
          </div>
        ) : (
          <div className="rounded-xl bg-stone-100 p-3 text-center text-base font-medium">{msg ?? `${a.status}${a.decided_by ? ` by ${a.decided_by}` : ""}${a.note ? ` (${a.note})` : ""}`}</div>
        )}
      </div>
    );
  }
  return (
    <div className="flex gap-3 rounded-xl bg-white p-3 shadow-sm">
      {a.screenshot ? <img src={media(`/api/approvals/${a.id}/shot`)} alt="The screen this approval is for" className="w-28 shrink-0 rounded border border-stone-200" />
                    : <div className="w-28 shrink-0 rounded bg-stone-100" />}
      <div className="min-w-0 flex-1 text-sm">
        <div className="font-semibold">{a.description}</div>
        {a.goal && <div className="text-stone-600">Task: {a.goal}</div>}
        <ul className="mt-1 list-disc pl-4 text-xs text-stone-500">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        <div className="mt-1 text-xs text-stone-400">{a.app} · {ago(a.created_at)}</div>
        {a.status === "pending" && !msg ? (
          <div className="mt-3 flex gap-2">
            <button disabled={busy} onClick={() => decide("approve")} className="rounded-md bg-emerald-600 px-4 py-1.5 font-medium text-white disabled:opacity-50">Approve</button>
            <button disabled={busy} onClick={() => decide("decline")} className="rounded-md bg-stone-200 px-4 py-1.5 font-medium disabled:opacity-50">Decline</button>
          </div>
        ) : (
          <div className="mt-3 text-sm font-medium">{msg ?? `${a.status}${a.decided_by ? ` by ${a.decided_by}` : ""}${a.note ? ` (${a.note})` : ""}`}</div>
        )}
      </div>
    </div>
  );
}

export default function Approvals({ approvals }: { approvals: Approval[] }) {
  const pending = approvals.filter((a) => a.status === "pending");
  return (
    <div className="space-y-3 p-4">
      <p className="text-sm text-stone-600">Irreversible actions wait here for you. No answer means Envoy waits: nothing is approved on its own.</p>
      {pending.length === 0 && <p className="text-sm text-stone-500">Nothing waiting for approval.</p>}
      {pending.map((a) => <ApprovalCard key={a.id} a={a} />)}
    </div>
  );
}
