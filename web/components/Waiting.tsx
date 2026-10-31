"use client";

// What's waiting on you, on Home and in Activity's "Needs you". One item is shown in full (an offer's card, a phone ask,
// an approval). More than one: a compact row each (icon, title, where it came from · when) and Review, which opens its
// sheet: an approval's ApprovalSheet, an offer's card (OfferSheet), a phone ask's or a stuck task's card. No row answers
// anything itself: Yes on an offer is only ever pressed on its card, under "What I'll do" word for word.
import { useState } from "react";
import { DeviceMobileIcon, HandIcon, LockIcon, type Icon } from "@phosphor-icons/react";
import { ApprovalCard, readable } from "@/components/Approvals";
import { OfferCard, offerFrom, offerIcon } from "@/components/Offers";
import PhoneAsk from "@/components/PhoneAsk";
import Sheet from "@/components/Sheet";
import { appName } from "@/components/Tasks";
import { Button, Card, RowIcon } from "@/components/ui";
import { ago, Approval, Offer, Task } from "@/lib/api";

export type WaitingItem =
  | { kind: "approval"; approval: Approval }
  | { kind: "offer"; offer: Offer }
  | { kind: "phone"; task: Task }  // "Use your Android phone for this task?"
  | { kind: "task"; task: Task };  // Envoy needs you on the phone (a sign-in, a bot check)

const key = (w: WaitingItem) => (w.kind === "approval" ? w.approval.id : w.kind === "offer" ? w.offer.id : w.task.id);

// A task Envoy is stuck on: what it needs, and Take over.
export function StuckCard({ task, onOpen, takeOver }: { task: Task; onOpen?: () => void; takeOver: () => void }) {
  return (
    <Card tone="needs" className="flex items-center gap-3 py-3.5 pl-4 pr-3.5">
      <RowIcon icon={HandIcon} tone="apricot" size={40} />
      <button onClick={onOpen} className="min-w-0 flex-1 text-left">
        <span className="block text-body font-bold [overflow-wrap:anywhere]">{task.detail || "Envoy needs you on the phone"}</span>
        <span className="mt-0.5 block truncate text-meta text-muted">{task.goal} · {ago(task.updated_at)}</span>
      </button>
      <Button variant="sage" onClick={takeOver}>Take over</Button>
    </Card>
  );
}

export default function Waiting({ items, review, openOffer, onDecided, openTask, takeOver }: {
  items: WaitingItem[]; review: (approvalId: string) => void; openOffer: (offerId: string) => void; onDecided?: (o: Offer) => void;
  openTask: (id: string) => void; takeOver: (task: Task) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);  // a phone ask's or a stuck task's card, in a sheet
  if (!items.length) return null;
  const full = (w: WaitingItem) =>
    w.kind === "approval" ? <ApprovalCard key={key(w)} a={w.approval} review={review} />
      : w.kind === "offer" ? <OfferCard key={key(w)} o={w.offer} openTask={openTask} onDecided={onDecided} />
      : w.kind === "phone" ? <PhoneAsk key={key(w)} task={w.task} />
      : <StuckCard key={key(w)} task={w.task} onOpen={() => { setOpen(null); openTask(w.task.id); }} takeOver={() => { setOpen(null); takeOver(w.task); }} />;
  if (items.length === 1) return full(items[0]);

  const shown = items.find((w) => key(w) === open && (w.kind === "phone" || w.kind === "task"));  // gone once it's answered
  return (
    <>
      <Card tone="needs" className="overflow-hidden">
        <ul aria-label={`${items.length} things waiting on you`}>
          {items.map((w) => <Row key={key(w)} w={w} review={() => (w.kind === "approval" ? review(w.approval.id) : w.kind === "offer" ? openOffer(w.offer.id) : setOpen(key(w)))} />)}
        </ul>
      </Card>
      {shown && (
        <Sheet label={shown.kind === "phone" ? "Use your phone?" : "Envoy needs you"} onClose={() => setOpen(null)}>
          {full(shown)}
          <Button className="mt-4 self-center" variant="ghost" onClick={() => setOpen(null)}>Close</Button>
        </Sheet>
      )}
    </>
  );
}

function Row({ w, review }: { w: WaitingItem; review: () => void }) {
  let icon: Icon, title: string, meta: string;
  if (w.kind === "approval") {
    const a = w.approval;
    [icon, title, meta] = [LockIcon, readable(a.description), `${a.goal ?? appName(a.app)} · ${ago(a.created_at)}`];
  } else if (w.kind === "offer") {
    [icon, title, meta] = [offerIcon(w.offer), w.offer.title, `${offerFrom(w.offer)} · ${ago(w.offer.created_at)}`];
  } else {
    const t = w.task;
    [icon, title, meta] = [w.kind === "phone" ? DeviceMobileIcon : HandIcon, t.detail || (w.kind === "phone" ? "Use your Android phone for this task?" : "Envoy needs you on the phone"),
      `${t.goal} · ${ago(t.updated_at)}`];
  }
  return (
    <li className="flex min-h-[64px] items-center gap-3 border-b border-divider py-2.5 pl-4 pr-3 last:border-b-0">
      <RowIcon icon={icon} tone="apricot" size={36} />
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 text-row font-semibold [overflow-wrap:anywhere]">{title}</span>
        <span className="mt-0.5 block truncate text-meta-2 text-muted">{meta}</span>
      </span>
      <Button variant="sage" onClick={review} aria-label={`Review: ${title}`}>Review</Button>
    </li>
  );
}
