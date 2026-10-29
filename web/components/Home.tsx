"use client";

// Home: Envoy's greeting. The avatar, a short briefing in Envoy's words (GET /api/briefing: built from what the stores
// hold, no model call), what needs your OK, what happened today, what's next, your routines as suggestions, and the
// composer. Typing or speaking moves into the conversation (components/Chat.tsx). An offer ("Should I check you in?")
// is a card with Yes and Not now; once answered it stays, saying what happened, until Home reloads.
import { useEffect, useState } from "react";
import { ClockIcon, GraphIcon, HandIcon, LockIcon, RepeatIcon } from "@phosphor-icons/react";
import Avatar, { type Mood } from "@/components/Avatar";
import { readable } from "@/components/Approvals";
import Chat from "@/components/Chat";
import PhoneAsk from "@/components/PhoneAsk";
import { appName } from "@/components/Tasks";
import { OfferCard } from "@/components/Offers";
import { appIcon, Button, Card, clock, Row, RowIcon, SectionLabel } from "@/components/ui";
import { ago, api, Lease, Offer, Task } from "@/lib/api";

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

export default function Home({ tasks, openTask, review, mood, connected, version, onListening, goPhone }: {
  tasks: Record<string, Task>; openTask: (id: string) => void; review: (approvalId: string) => void; mood: Mood; connected: boolean; version: number;
  compact?: boolean; onListening: (on: boolean) => void; goPhone: () => void; device?: Lease;
}) {
  const [b, setB] = useState<Briefing | null>(null);
  const [failed, setFailed] = useState(false);
  const [answered, setAnswered] = useState<Offer[]>([]); // offers you just answered: they stay, saying what happened
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
          {b.needs.filter((n) => n.kind === "approval").map((n) => <NeedCard key={n.id} n={n} task={tasks[n.task_id]} review={review} goPhone={goPhone} openTask={openTask} />)}
          {[...answered.filter((o) => !b.needs.some((n) => n.id === o.id)), ...b.needs.filter((n) => n.kind === "offer" && n.offer).map((n) => n.offer!)]
            .sort((x, y) => y.created_at - x.created_at)  // the briefing's order, so an answered card stays where it was
            .map((o) => <OfferCard key={o.id} o={o} openTask={openTask} onDecided={(d) => setAnswered((xs) => [d, ...xs.filter((x) => x.id !== d.id)])} />)}
          {b.needs.filter((n) => n.kind !== "approval" && n.kind !== "offer").map((n) => <NeedCard key={n.id} n={n} task={tasks[n.task_id]} review={review} goPhone={goPhone} openTask={openTask} />)}
        </section>
      )}

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

function NeedCard({ n, task, review, goPhone, openTask }: { n: Need; task?: Task; review: (id: string) => void; goPhone: () => void; openTask: (id: string) => void }) {
  if (n.kind === "phone" && (task?.waiting_for ?? "phone") === "phone" && (task?.status ?? "needs_you") === "needs_you") {
    return <PhoneAsk task={task ?? { id: n.task_id, goal: n.detail, detail: n.title, app: n.app } as Task} />;
  }
  const approval = n.kind === "approval";
  return (
    <Card tone="needs" className="flex items-center gap-3 py-3.5 pl-4 pr-3.5">
      <RowIcon icon={approval ? LockIcon : HandIcon} tone="apricot" size={40} />
      <button onClick={() => openTask(n.task_id)} className="min-w-0 flex-1 text-left">
        <span className="block text-body font-bold [overflow-wrap:anywhere]">{approval ? readable(n.title) : n.title}</span>
        <span className="mt-0.5 block truncate text-meta text-muted">{n.detail || appName(n.app)} · {ago(n.time)}</span>
      </button>
      {approval
        ? <Button variant="sage" onClick={() => review(n.id)}>Review</Button>
        : <Button variant="sage" onClick={goPhone}>Take over</Button>}
    </Card>
  );
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
