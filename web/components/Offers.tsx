"use client";

// Offers: Envoy asks "Should I…?" and waits for your yes (backend/api/offers.py). The card says what Envoy will do, word
// for word, and what it checked before starting; Yes starts exactly that, Not now leaves it. Only a tap here answers: a
// push only opens the card. A trigger's "Not now" skips this time; a habit Envoy noticed isn't suggested again.
import { useEffect, useState } from "react";
import {
  ArrowRightIcon, ArrowsClockwiseIcon, ChatCircleDotsIcon, CheckCircleIcon, ClockIcon, FileArrowUpIcon, WarningIcon, XCircleIcon, type Icon,
} from "@phosphor-icons/react";
import Sheet from "@/components/Sheet";
import { Button, Card, cx, Row, RowIcon } from "@/components/ui";
import { ago, api, ApiError, Offer, OfferLine, post } from "@/lib/api";

const KIND_ICON: Record<string, Icon> = { repeat: ArrowsClockwiseIcon, handoff: FileArrowUpIcon };
export const offerIcon = (o: Offer): Icon => KIND_ICON[o.kind] ?? ChatCircleDotsIcon;

// Where a question came from, in a few words (a compact row's meta line): "Your trigger “Morning coffee”", "From your Mac".
export function offerFrom(o: Offer): string {
  if (o.source.startsWith("trigger:")) return `Your trigger “${o.source.slice(8)}”`;
  if (o.kind === "repeat") return "A habit I noticed";
  if (o.kind === "handoff") return "A file from your Mac";
  if (o.source === "mcp") return "An assistant asked";
  if (o.source === "chat" || o.source === "voice") return "You asked me";
  return "Envoy asks";
}

// What the card promises, verbatim: a task's goal, or what a trigger setup will do.
export function whatIllDo(o: Offer): string {
  const a = o.action;
  if (a.type === "task") return a.goal ?? "";
  if (a.type === "create_trigger") return a.summary ?? `Set up “${a.name ?? "a trigger"}”`;
  if (a.type === "enable_trigger") return a.summary ?? "Turn this trigger on";
  if (a.type === "handoff") return `Send ${a.file ?? "the file"} to your phone${a.then?.goal ? `, then: ${a.then.goal}` : ""}`;
  return a.summary ?? o.body;
}

// "Accepted", "Not now", "Expired", in Envoy's words.
export function outcome(o: Offer): string {
  if (o.status === "pending") return "Waiting for your answer";
  if (o.status === "accepted") {
    const by = o.decided_by && o.decided_by !== "you" ? ` (${o.decided_by})` : "";
    if ((o.action.type === "create_trigger" || o.action.type === "enable_trigger") && o.action.setup) return `Set up: ${o.action.setup}`;
    return o.action.type === "task" || o.action.type === "handoff" ? `You said yes${by}: started` : `You said yes${by}: set up`;
  }
  if (o.status === "declined") return o.kind === "repeat" ? "Not now: I won't suggest it again" : o.kind === "trigger" ? "Not now: skipped this time" : "Not now";
  if (o.status === "withdrawn") return `No longer needed${o.note ? `: ${o.note}` : ""}`;  // Envoy took the question back
  return "Expired: no answer in time";
}

const LEVEL: Record<string, { icon: Icon; cls: string }> = {
  info: { icon: CheckCircleIcon, cls: "text-sage-ink" },
  warn: { icon: WarningIcon, cls: "text-apricot-ink" },
  stop: { icon: XCircleIcon, cls: "text-brick" },
};

function Preflight({ lines }: { lines: OfferLine[] }) {
  return (
    <div className="mt-3">
      <div className="text-meta-2 font-bold text-muted">Before I start</div>
      <ul className="mt-1.5 flex flex-col gap-1.5">
        {lines.map((l, i) => {
          const { icon: I, cls } = LEVEL[l.level] ?? LEVEL.info;
          return (
            <li key={i} className="flex items-start gap-2 text-meta text-ink-2">
              <I size={16} weight="fill" className={cx("mt-0.5 shrink-0", cls)} aria-label={l.level === "info" ? undefined : l.level === "warn" ? "Heads up" : "Blocked"} />
              <span className="[overflow-wrap:anywhere]">{l.text}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function OfferCard({ o, openTask, onDecided }: { o: Offer; openTask?: (id: string) => void; onDecided?: (o: Offer) => void }) {
  const [cur, setCur] = useState(o);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setCur(o), [o]);
  const answer = (decision: "accept" | "decline") => {
    setBusy(true);
    setError(null);
    post<Offer>(`/api/offers/${cur.id}`, { decision })
      .then((x) => { setCur(x); onDecided?.(x); })
      .catch((e) => setError(e instanceof ApiError && e.status === 409 && /already/.test(e.message) ? `This was ${e.message.replace("already ", "")} already.` : e.message))
      .finally(() => setBusy(false));
  };
  const pending = cur.status === "pending";
  // a habit's trigger, and one asked for in chat or by an assistant, ask each time they run (both are made in ask mode)
  const asksEachTime = (cur.action.type === "create_trigger" && cur.action.action?.ask) || cur.action.type === "enable_trigger";
  const blocked = cur.preflight.some((l) => l.level === "stop");
  return (
    <Card tone={pending ? "needs" : undefined} className="p-4" aria-label={cur.title}>
      <div className="flex items-start gap-3">
        <RowIcon icon={offerIcon(cur)} tone={pending ? "apricot" : "sage"} size={40} />
        <div className="min-w-0 flex-1">
          <div className="text-body font-bold [overflow-wrap:anywhere]">{cur.title}</div>
          <div className="mt-0.5 text-meta text-muted [overflow-wrap:anywhere]">{cur.body ? `${cur.body} · ` : ""}{ago(cur.created_at)}</div>
        </div>
      </div>
      <div className="mt-3 rounded-block bg-well px-3.5 py-3">
        <div className="text-meta-2 font-bold text-muted">What I&rsquo;ll do</div>
        <p className="mt-0.5 text-body [overflow-wrap:anywhere]">{whatIllDo(cur)}</p>
        {asksEachTime && <p className="mt-1 text-meta-2 text-ink-2">It asks you each time before it runs. Nothing happens without your yes.</p>}
        {cur.action.phone && cur.action.phone !== "emulator" && <p className="mt-1 text-meta-2 text-ink-2">On your Android phone: your yes covers using it.</p>}
      </div>
      {cur.preflight.length > 0 && <Preflight lines={cur.preflight} />}
      {pending ? (
        <>
          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={busy} onClick={() => answer("accept")}>{blocked ? "Try anyway" : "Yes"}</Button>
            <Button disabled={busy} onClick={() => answer("decline")}>Not now</Button>
            {cur.expires_at && <span className="flex items-center gap-1 text-meta-2 text-muted"><ClockIcon size={14} />Until {new Date(cur.expires_at * 1000).toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" })}</span>}
          </div>
          {cur.note && !error && <p role="alert" className="mt-2 text-meta text-apricot-ink">{cur.note}</p>}
        </>
      ) : (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <span className={cx("flex items-center gap-1.5 text-meta font-semibold", cur.status === "accepted" ? "text-sage-ink" : "text-muted")}>
            {cur.status === "accepted" && <CheckCircleIcon size={16} weight="fill" />}{outcome(cur)}
          </span>
          {cur.status === "accepted" && cur.task_id && openTask && (
            <Button variant="ghost" onClick={() => openTask(cur.task_id!)}>Open the task <ArrowRightIcon size={16} /></Button>
          )}
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-meta text-apricot-ink">{error}</p>}
    </Card>
  );
}

// A past offer in Activity: what it was and what happened to it.
export function OfferRow({ o, onOpen }: { o: Offer; onOpen: (o: Offer) => void }) {
  return (
    <Row icon={offerIcon(o)} tone={o.status === "accepted" ? "sage" : o.status === "pending" ? "apricot" : "neutral"}
         title={o.title} meta={`${outcome(o)} · ${ago(o.decided_at ?? o.created_at)}`} onClick={() => onOpen(o)} />
  );
}

// The card on its own: from a push or a link (/?offer=<id>), or Review on a compact row (components/Waiting.tsx).
export function OfferSheet({ id, onClose, openTask, onDecided }: { id: string; onClose: () => void; openTask: (id: string) => void; onDecided?: (o: Offer) => void }) {
  const [o, setO] = useState<Offer | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => { api<Offer>(`/api/offers/${id}`).then(setO).catch(() => setMissing(true)); }, [id]);
  return (
    <Sheet label="Envoy asks" onClose={onClose}>
      {o ? <OfferCard o={o} openTask={(t) => { onClose(); openTask(t); }} onDecided={onDecided} />
        : missing ? <p className="py-4 text-body text-ink-2">This question is gone: it was answered or removed.</p>
        : <div aria-hidden className="h-40 rounded-card bg-well" />}
      <Button className="mt-4 self-center" variant="ghost" onClick={onClose}>Close</Button>
    </Sheet>
  );
}
