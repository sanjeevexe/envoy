"use client";

// Home: Envoy's greeting. The avatar, a short briefing in Envoy's words (GET /api/briefing: built from what the stores
// hold, no model call), what needs your OK, what happened today, what's next, your routines as suggestions, and the
// composer. Typing or speaking moves into the conversation (components/Chat.tsx). One thing waiting is shown in full
// (an offer, "Should I check you in?", is a card with Yes and Not now); several are compact rows, each with Review
// (components/Waiting.tsx). An offer you answer here stays as a one-line row saying what happened, until Home reloads.
import { useEffect, useState } from "react";
import { ClockIcon, GraphIcon, RepeatIcon } from "@phosphor-icons/react";
import Avatar, { type Mood } from "@/components/Avatar";
import Chat from "@/components/Chat";
import { appName } from "@/components/Tasks";
import { OfferRow, OfferSheet } from "@/components/Offers";
import Waiting, { type WaitingItem } from "@/components/Waiting";
import { appIcon, Card, clock, Row, SectionLabel } from "@/components/ui";
import { api, Lease, Offer, Task } from "@/lib/api";

type Need = { kind: "approval" | "phone" | "task" | "offer"; id: string; task_id: string; title: string; detail: string; app?: string; time: number;
  status?: string; device?: string; offer?: Offer };
type Today = { kind: "change" | "task" | "routine"; id: string; task_id?: string; title: string; time: number; app?: string; source?: string;
  label?: string; old?: string; new?: string; entity?: string; result?: string; status?: string; routine?: string; seconds?: number };
export type Briefing = { time: number; name: string | null; text: string; needs: Need[]; today: Today[];
  upcoming: { id: string; name: string; kind: string; at: number; for?: string; ask?: boolean }[]; suggestions: { label: string; routine: string; app: string }[] };

const greeting = (name: string | null) => {
  const h = new Date().getHours();
  const part = h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return name ? `${part}, ${name}` : part;
};

export default function Home({ tasks, openTask, review, mood, connected, version, onListening, goPhone, watch }: {
  tasks: Record<string, Task>; openTask: (id: string) => void; review: (approvalId: string) => void; mood: Mood; connected: boolean; version: number;
  compact?: boolean; onListening: (on: boolean) => void; goPhone: () => void; device?: Lease; watch?: (device?: string) => void;
}) {
  const [b, setB] = useState<Briefing | null>(null);
  const [failed, setFailed] = useState(false);
  const [answered, setAnswered] = useState<Offer[]>([]); // offers you just answered: they stay, saying what happened
  const [asking, setAsking] = useState<string | null>(null); // an offer's card, in a sheet (Review on its row)
  const decided = (d: Offer) => setAnswered((xs) => [d, ...xs.filter((x) => x.id !== d.id)]);
  useEffect(() => {
    api<Briefing>("/api/briefing").then((x) => { setB(x); setFailed(false); }).catch(() => setFailed(true));
  }, [version, connected]);

  const offline = mood === "offline" || (failed && !b);
  const intro = (
    <div className="mx-auto w-full max-w-[680px] pb-2 md:pt-6">
      <div className="ev-rise flex flex-col gap-3 px-6 pt-4">
        <Avatar mood={mood} size={68} />
        <h1 className="font-serif text-display font-normal tracking-[-0.01em]">{greeting(b?.name ?? null)}</h1>
        {offline ? (
          <p className="font-serif text-voice text-ink-2">I can&rsquo;t reach your Mac right now. I&rsquo;ll pick up again as soon as it&rsquo;s back.</p>
        ) : b ? (
          <p className="font-serif text-voice text-ink-2">{b.text}</p>
        ) : (
          <div aria-hidden className="flex flex-col gap-2 pt-1"><span className="h-4 w-11/12 rounded-full bg-well" /><span className="h-4 w-2/3 rounded-full bg-well" /></div>
        )}
      </div>

      {b && (b.needs.length > 0 || answered.length > 0) && (
        <section aria-label="Needs your OK" className="ev-rise ev-r2 mt-5 flex flex-col gap-3 px-4">
          <Waiting items={waiting(b.needs, tasks, answered)} review={review} openOffer={setAsking} onDecided={decided} openTask={openTask}
                   takeOver={(t) => { watch?.(t.device); goPhone(); }} />
          {answered.length > 0 && (
            <Card className="overflow-hidden">
              {answered.map((o) => <OfferRow key={o.id} o={o} onOpen={(x) => (x.task_id ? openTask(x.task_id) : setAsking(x.id))} />)}
            </Card>
          )}
        </section>
      )}
      {asking && <OfferSheet id={asking} onClose={() => setAsking(null)} openTask={openTask} onDecided={decided} />}

      {b && b.today.length > 0 && (
        <section aria-labelledby="today" className="ev-rise ev-r3">
          <SectionLabel id="today" className="px-6 pb-2.5 pt-6">Today</SectionLabel>
          <Card className="mx-4 overflow-hidden">
            {b.today.map((x) => <TodayRow key={x.id} x={x} openTask={openTask} />)}
          </Card>
        </section>
      )}

      {b && b.upcoming.length > 0 && (
        <section aria-labelledby="next" className="ev-rise ev-r3">
          <SectionLabel id="next" className="px-6 pb-2.5 pt-6">Coming up</SectionLabel>
          <Card className="mx-4 overflow-hidden">
            {b.upcoming.map((u) => (
              <Row key={u.id} icon={ClockIcon} title={u.name} meta={`${clock(u.at)}${u.for ? ` · for ${u.for}` : ""}${u.ask ? " · will ask you first" : ""}`} />
            ))}
          </Card>
        </section>
      )}
    </div>
  );
  return <Chat tasks={tasks} openTask={openTask} intro={intro} suggestions={b?.suggestions.map((s) => s.label) ?? []} onListening={onListening} mood={mood} />;
}

// The briefing's needs as the waiting list: approvals, then offers (newest first), then phone asks and tasks stuck on
// you. A phone ask or a stuck task that has moved on since the briefing (the live task says so) isn't waiting any more,
// and neither is an offer you just answered here.
function waiting(needs: Need[], tasks: Record<string, Task>, answered: Offer[]): WaitingItem[] {
  const out: WaitingItem[] = needs.filter((n) => n.kind === "approval").map((n) => ({ kind: "approval",
    approval: { id: n.id, task_id: n.task_id, created_at: n.time, status: "pending", description: n.title, goal: n.detail || undefined, reasons: [], app: n.app ?? "", screen: "" } }));
  needs.filter((n) => n.kind === "offer" && n.offer && !answered.some((o) => o.id === n.id)).sort((x, y) => y.time - x.time)
    .forEach((n) => out.push({ kind: "offer", offer: n.offer! }));
  for (const n of needs) {
    if (n.kind !== "phone" && n.kind !== "task") continue;
    const live: Task | undefined = tasks[n.task_id];
    const said = { id: n.task_id, goal: n.kind === "phone" ? n.detail : n.title, detail: n.kind === "phone" ? n.title : n.detail, app: n.app, device: n.device,
      updated_at: n.time } as Task;
    const task = live ? { ...said, ...live } : said;
    if (n.kind === "phone" && (task.status ?? "needs_you") === "needs_you" && (task.waiting_for ?? "phone") === "phone") out.push({ kind: "phone", task });
    else if (n.kind === "task" && ["needs_you", "waiting_approval", undefined].includes(live?.status)) out.push({ kind: "task", task });
  }
  return out;
}

function TodayRow({ x, openTask }: { x: Today; openTask: (id: string) => void }) {
  const open = x.task_id ? () => openTask(x.task_id!) : undefined;
  if (x.kind === "change") {
    return <Row icon={GraphIcon} title={x.title} onClick={open}
                meta={`${x.old ? `Was ${x.old} · ` : ""}seen in ${x.source || "an app"} at ${clock(x.time)}`} />;
  }
  const how = x.status === "failed" ? "Didn't finish · " : x.status === "declined" ? "Declined · " : "";
  return x.kind === "routine"
    ? <Row icon={RepeatIcon} title={x.title} onClick={open} meta={`${how}${appName(x.app)} · your routine, ${x.seconds ?? 0} s`} />
    : <Row icon={appIcon(x.app)} title={x.title} onClick={open} meta={`${how}${appName(x.app)} at ${clock(x.time)}`} />;
}
