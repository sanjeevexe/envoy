"use client";

// Activity: what's waiting for you on top (approvals as cards, offers, a phone ask, a task that needs you on the phone),
// then every task, then the recent offers and what happened to each. Selecting one opens it.
import { useEffect, useState } from "react";
import { HandIcon } from "@phosphor-icons/react";
import type { Mood } from "@/components/Avatar";
import { ApprovalCard } from "@/components/Approvals";
import { Handoffs } from "@/components/Handoff";
import { OfferCard, OfferRow, OfferSheet } from "@/components/Offers";
import PhoneAsk from "@/components/PhoneAsk";
import { TaskDetail, TaskList } from "@/components/Tasks";
import { Button, Card, RowIcon, SectionLabel } from "@/components/ui";
import { ago, api, Approval, Lease, Offer, Step, Task } from "@/lib/api";

export default function Activity({ tasks, all, steps, approvals, openTask, setOpenTask, review, watch, leases, goPhone, version = 0 }: {
  tasks: Task[]; all: Record<string, Task>; steps: Record<string, Step[]>; approvals: Approval[]; openTask: string | null; setOpenTask: (id: string | null) => void;
  review: (id: string) => void; watch: (device?: string) => void; leases: Record<string, Lease>; mood: Mood; goPhone: () => void; version?: number;
}) {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [shown, setShown] = useState<string | null>(null); // a past offer, in its sheet
  useEffect(() => { api<Offer[]>("/api/offers?status=all&limit=12").then(setOffers).catch(() => {}); }, [version]);
  if (openTask) {
    return <TaskDetail id={openTask} task={all[openTask]} liveSteps={steps[openTask] ?? []} back={() => setOpenTask(null)} all={all} open={setOpenTask}
                       review={review} watch={watch} deviceName={(d) => (d ? leases[d]?.name : undefined)} />;
  }
  const pending = approvals.filter((a) => a.status === "pending").sort((a, b) => b.created_at - a.created_at)
    .map((a) => ({ ...a, goal: a.goal ?? all[a.task_id]?.goal }));
  const asks = tasks.filter((t) => t.status === "needs_you" && t.waiting_for === "phone");
  const stuck = tasks.filter((t) => t.status === "needs_you" && t.waiting_for !== "phone");
  const asking = offers.filter((o) => o.status === "pending");
  const past = offers.filter((o) => o.status !== "pending");
  const waiting = pending.length + asking.length + asks.length + stuck.length;
  return (
    <div className="mx-auto w-full max-w-[720px] pb-8 md:pt-6">
      {waiting > 0 && (
        <section aria-labelledby="waiting" className="ev-rise">
          <SectionLabel id="waiting" className="px-6 pb-2.5 pt-4">Needs you</SectionLabel>
          <div className="flex flex-col gap-3 px-4">
            {pending.map((a) => <ApprovalCard key={a.id} a={a} review={review} />)}
            {asking.map((o) => <OfferCard key={o.id} o={o} openTask={setOpenTask} />)}
            {asks.map((t) => <PhoneAsk key={t.id} task={t} />)}
            {stuck.map((t) => (
              <Card key={t.id} tone="needs" className="flex items-center gap-3 py-3.5 pl-4 pr-3.5">
                <RowIcon icon={HandIcon} tone="apricot" size={40} />
                <button onClick={() => setOpenTask(t.id)} className="min-w-0 flex-1 text-left">
                  <span className="block text-body font-bold [overflow-wrap:anywhere]">{t.detail ?? "Envoy needs you on the phone"}</span>
                  <span className="mt-0.5 block truncate text-meta text-muted">{t.goal} · {ago(t.updated_at)}</span>
                </button>
                <Button variant="sage" onClick={() => { watch(t.device); goPhone(); }}>Take over</Button>
              </Card>
            ))}
          </div>
        </section>
      )}
      <section aria-labelledby="tasks" className="ev-rise ev-r2">
        <SectionLabel id="tasks" className="px-6 pb-2.5 pt-6">Tasks</SectionLabel>
        <Card className="mx-4 overflow-hidden"><TaskList tasks={tasks} open={setOpenTask} /></Card>
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
      {shown && <OfferSheet id={shown} onClose={() => setShown(null)} openTask={(id) => { setShown(null); setOpenTask(id); }} />}
    </div>
  );
}
