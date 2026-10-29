"use client";

// Approvals: what Envoy is about to do that can't be undone, waiting for you. Only you approve, in your signed-in app or
// browser: pressing Approve fetches the approval's nonce and POSTs it with your decision. Opening a sheet, the page or a
// link decides nothing, and no answer is never a yes.
import { useCallback, useEffect, useState } from "react";
import { LockIcon } from "@phosphor-icons/react";
import Avatar from "@/components/Avatar";
import Sheet from "@/components/Sheet";
import { appName } from "@/components/Tasks";
import { Button, Card, RowIcon, sentence } from "@/components/ui";
import { api, ago, Approval, media, post } from "@/lib/api";

const MONEY = /\$|\b(pay|payment|buy|purchase|order|subscribe|checkout)\b/i;
// 'tap "Confirm check-in" in com.skylark.air (routine skylark_check_in_flight v1)' → 'Tap “Confirm check-in” in SkyLark'
export const readable = (d: string) => sentence(d.replace(/\s*\(routine [^)]*\)\s*$/, "").replace(/\bin ([a-z][\w]*(\.[\w]+)+)\b/g, (_, pkg) => `in ${appName(pkg)}`)
  .replace(/"([^"]+)"/g, "“$1”"));
const routineOf = (d: string) => d.match(/\(routine ([^)]*)\)\s*$/)?.[1];
const verb = (a: Approval, money: boolean) => {
  if (money) return "Approve and pay";
  const label = a.description.match(/[“"]([^”"]{1,28})[”"]/)?.[1];
  return label ? `Approve: ${label}` : "Approve";
};

// A card for the approval in a list (Activity), opening the sheet.
export function ApprovalCard({ a, review }: { a: Approval; review: (id: string) => void }) {
  return (
    <Card tone="needs" className="flex items-center gap-3 py-3.5 pl-4 pr-3.5">
      <RowIcon icon={LockIcon} tone="apricot" size={40} />
      <span className="min-w-0 flex-1">
        <span className="block text-body font-bold [overflow-wrap:anywhere]">{readable(a.description)}</span>
        <span className="mt-0.5 block truncate text-meta text-muted">{a.goal ?? appName(a.app)} · {ago(a.created_at)}</span>
      </span>
      <Button variant="sage" onClick={() => review(a.id)}>Review</Button>
    </Card>
  );
}

// The sheet's contents: in the app's sheet, and on the approval page.
export function ApprovalBody({ id, device, onClose, standalone }: { id: string; device?: string; onClose?: () => void; standalone?: boolean }) {
  const [a, setA] = useState<Approval | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [decided, setDecided] = useState<"approved" | "declined" | null>(null);
  const load = useCallback(() => api<Approval>(`/api/approvals/${id}`).then(setA).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  const decide = async (decision: "approve" | "decline") => {
    setBusy(true);
    setErr(null);
    try {
      const full = await api<Approval>(`/api/approvals/${id}`);
      const r = await post<Approval>(`/api/approvals/${id}`, { decision, nonce: full.nonce });
      setDecided(r.status === "approved" ? "approved" : "declined");
    } catch (e: any) {
      setErr(e.message);
      load();
    } finally {
      setBusy(false);
    }
  };

  if (!a) return err ? <p className="py-6 text-body text-ink-2">{err}</p> : <p className="py-10 text-center text-body text-muted" aria-busy="true">Loading…</p>;
  const money = MONEY.test(a.description) || a.reasons.some((r) => /money|pay/i.test(r));
  const status = decided ?? (a.status === "pending" ? null : a.status);
  const pairs = a.reasons.map((r) => r.match(/^([a-zA-Z][\w ]{0,14}):\s*(.+)$/));

  if (status) {
    const yes = status === "approved";
    return (
      <div className="flex flex-col items-start gap-3 py-2">
        <Avatar mood={yes ? "done" : "idle"} size={52} />
        <h2 className="font-serif text-display-2 font-normal tracking-[-0.01em]">
          {decided ? (yes ? "Approved. I'll go on." : "Declined. I won't do it.") : `This was ${status}${a.decided_by ? ` by ${a.decided_by}` : ""}.`}
        </h2>
        <p className="text-body text-ink-2">{readable(a.description)}{a.note ? ` · ${a.note}` : ""}</p>
        {onClose && <Button size="lg" onClick={onClose} className="mt-2 w-full">Close</Button>}
        {standalone && <a href="/" className="mt-2 flex h-[52px] w-full items-center justify-center rounded-full bg-ink text-body font-bold text-white hover:text-white">Open Envoy</a>}
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-3">
        <Avatar mood="needs" size={52} />
        <div>
          <div className="text-meta font-bold text-apricot-ink">Envoy needs your OK</div>
          <div className="mt-0.5 text-meta text-muted">{money ? "Payments always come to you" : "Steps that can't be undone come to you"}</div>
        </div>
      </div>
      <h2 className="mt-3.5 font-serif text-display-2 font-normal tracking-[-0.01em] [overflow-wrap:anywhere]">{readable(a.description)}</h2>
      {(a.goal || routineOf(a.description)) && (
        <p className="mt-1 text-meta text-muted">{a.goal ? `For “${a.goal}”` : ""}{a.goal && routineOf(a.description) ? " · " : ""}{routineOf(a.description) ? `routine ${routineOf(a.description)}` : ""}</p>
      )}

      <div className="mt-4 text-meta font-bold text-muted">What Envoy will tap</div>
      {a.screenshot ? (
        <a href={media(`/api/approvals/${a.id}/shot`)} target="_blank" rel="noreferrer" className="mt-2 flex justify-center overflow-hidden rounded-block bg-well px-4 pt-3.5">
          <img src={media(`/api/approvals/${a.id}/shot`)} alt={`The screen Envoy is about to act on, for: ${readable(a.description)}`}
               className="max-h-[min(30dvh,260px)] w-auto max-w-[200px] rounded-t-block object-cover object-top" />
        </a>
      ) : (
        <p className="mt-2 rounded-block bg-well px-4 py-5 text-meta text-ink-2">No picture: the screen was a secure one (a sign-in or a payment), and those aren&rsquo;t kept.</p>
      )}
      <p className="mt-2 text-meta-2 text-muted">{a.screenshot ? `Screenshot ${device ? `from your ${device}` : `in ${appName(a.app)}`} · ` : ""}{ago(a.created_at)}</p>

      {a.reasons.length > 0 && (
        <div className="mt-3.5 rounded-block border border-line bg-surface px-4">
          {a.reasons.map((r, i) => (
            <div key={i} className="flex min-h-[44px] items-center gap-3 border-b border-divider py-2 last:border-b-0">
              {pairs[i] ? <><span className="w-[72px] shrink-0 text-meta text-muted">{sentence(pairs[i]![1])}</span><span className="text-row font-semibold [overflow-wrap:anywhere]">{sentence(pairs[i]![2])}</span></>
                : <span className="text-row [overflow-wrap:anywhere]">{sentence(r)}</span>}
            </div>
          ))}
        </div>
      )}

      <div className="mt-3.5 flex items-center gap-2 text-meta font-semibold text-brick">
        <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-brick" />
        {money ? "Can't be undone once it's paid" : "Can't be undone once it's done"}
      </div>
      {err && <p role="alert" className="mt-3 rounded-block bg-apricot-tint px-3 py-2 text-meta text-apricot-ink">{err}</p>}

      <div className="mt-6 flex gap-3">
        <button disabled={busy} onClick={() => decide("decline")}
                className="h-[52px] flex-1 rounded-full border border-line-strong bg-surface text-body font-bold disabled:opacity-50">Decline</button>
        <button disabled={busy} onClick={() => decide("approve")}
                className="flex h-[52px] flex-[1.6] items-center justify-center gap-2 rounded-full bg-ink px-4 text-body font-bold text-white disabled:opacity-50">
          {money && <LockIcon size={18} />}{busy ? "One moment…" : verb(a, money)}
        </button>
      </div>
      <p className="mt-3 text-center text-meta-2 text-muted">Only you can approve this. Envoy can&rsquo;t approve its own {money ? "payments" : "actions"}.</p>
    </div>
  );
}

export function ApprovalSheet({ id, device, onClose }: { id: string; device?: string; onClose: () => void }) {
  return <Sheet label="Approve this step" onClose={onClose}><ApprovalBody id={id} device={device} onClose={onClose} /></Sheet>;
}
