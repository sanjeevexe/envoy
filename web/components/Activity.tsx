"use client";

// Activity: what's waiting for you on top (approvals, offers, a phone ask, a task that needs you on the phone: in full
// when there's one, compact rows with Review when there are more; components/Waiting.tsx), then every task, then the
// recent offers and what happened to each. Selecting one opens it.
import { useEffect, useState } from "react";
import type { Mood } from "@/components/Avatar";
import { Handoffs } from "@/components/Handoff";
import { OfferRow, OfferSheet } from "@/components/Offers";
import { TaskDetail, TaskList } from "@/components/Tasks";
import Waiting, { type WaitingItem } from "@/components/Waiting";
import { Card, SectionLabel } from "@/components/ui";
import { api, Approval, Lease, Offer, Step, Task } from "@/lib/api";

export default function Activity({ tasks, all, steps, approvals, openTask, setOpenTask, review, watch, leases, goPhone, version = 0, showMe }: {
  tasks: Task[]; all: Record<string, Task>; steps: Record<string, Step[]>; approvals: Approval[]; openTask: string | null; setOpenTask: (id: string | null) => void;
  review: (id: string) => void; watch: (device?: string) => void; leases: Record<string, Lease>; mood: Mood; goPhone: () => void; version?: number;
  showMe?: (goal: string, device?: string) => void;
}) {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [shown, setShown] = useState<string | null>(null); // an offer, in its sheet (Review on its row, or a past one)
  const decided = (d: Offer) => setOffers((xs) => xs.map((x) => (x.id === d.id ? d : x)));
  useEffect(() => { api<Offer[]>("/api/offers?status=all&limit=12").then(setOffers).catch(() => {}); }, [version]);
  if (openTask) {
    return <TaskDetail id={openTask} task={all[openTask]} liveSteps={steps[openTask] ?? []} back={() => setOpenTask(null)} all={all} open={setOpenTask}
                       review={review} watch={watch} deviceName={(d) => (d ? leases[d]?.name : undefined)} showMe={showMe} />;
  }
  const pending = approvals.filter((a) => a.status === "pending").sort((a, b) => b.created_at - a.created_at)
    .map((a) => ({ ...a, goal: a.goal ?? all[a.task_id]?.goal }));
  const asks = tasks.filter((t) => t.status === "needs_you" && t.waiting_for === "phone");
  const stuck = tasks.filter((t) => t.status === "needs_you" && t.waiting_for !== "phone");
  const asking = offers.filter((o) => o.status === "pending" && (!o.expires_at || o.expires_at > Date.now() / 1000));
  const past = offers.filter((o) => o.status !== "pending");
  const waiting: WaitingItem[] = [
    ...pending.map((a) => ({ kind: "approval" as const, approval: a })), ...asking.map((o) => ({ kind: "offer" as const, offer: o })),
    ...asks.map((t) => ({ kind: "phone" as const, task: t })), ...stuck.map((t) => ({ kind: "task" as const, task: t })),
  ];
  return (
    <div className="mx-auto w-full max-w-[720px] pb-8 md:pt-6">
      {waiting.length > 0 && (
        <section aria-labelledby="waiting" className="ev-rise">
          <SectionLabel id="waiting" className="px-6 pb-2.5 pt-4">Needs you</SectionLabel>
          <div className="flex flex-col gap-3 px-4">
            <Waiting items={waiting} review={review} openOffer={setShown} openTask={setOpenTask} takeOver={(t) => { watch(t.device); goPhone(); }}
                     onDecided={decided} />
          </div>
        </section>
      )}
      <section aria-labelledby="tasks" className="ev-rise ev-r2">
        <SectionLabel id="tasks" className="px-6 pb-2.5 pt-6">Tasks</SectionLabel>
        <Card className="mx-4 overflow-hidden"><TaskList tasks={tasks} open={setOpenTask} deviceName={(d) => (d ? leases[d]?.name : undefined)} /></Card>
      </section>
      <Handoffs version={version} />
      {past.length > 0 && (
        <section aria-labelledby="offers" className="ev-rise ev-r3">
          <SectionLabel id="offers" className="px-6 pb-2.5 pt-6">Envoy asked</SectionLabel>
          <Card className="mx-4 overflow-hidden">
            {past.map((o) => <OfferRow key={o.id} o={o} onOpen={(x) => (x.task_id ? setOpenTask(x.task_id) : setShown(x.id))} />)}
          </Card>
        </section>
      )}
      {shown && <OfferSheet id={shown} onClose={() => setShown(null)} openTask={(id) => { setShown(null); setOpenTask(id); }} onDecided={decided} />}
    </div>
  );
}
