"use client";

// The phone's screen, live. Take over pauses Envoy; then your taps, swipes and typing go straight to the phone
// (never logged, never shown to a model). Hand back lets Envoy look again and continue.
// Phase 5: touch (tap, swipe, long press; the page doesn't scroll while you're in control), typing with the iPhone's
// keyboard, and latency measured against the Mac's clock (ping/pong), reported back so it can be compared over the tailnet.
// Teach: you take over with a goal and do the task once while Envoy records it (the only time input is kept), then say it
// worked; Envoy turns it into a routine and replays it once to show it runs. Sign-in and secure screens pause the recording.
// While Envoy works, the bar above the screen says what it's doing: the task's goal and its latest step, worded as in the
// task view ("Step 3 of 6 · Open trip"), with a link to the task.
import { useEffect, useRef, useState } from "react";
import { ArrowUpRightIcon, ArrowUUpLeftIcon, BackspaceIcon, ChalkboardTeacherIcon, CircleIcon, DeviceMobileIcon, HandIcon, KeyboardIcon, KeyReturnIcon } from "@phosphor-icons/react";
import { stepLine } from "@/components/Tasks";
import { cx, IconButton } from "@/components/ui";
import { api, Lease, loadMock, mockMode, post, Step, Task, TeachResult } from "@/lib/api";
import { isStandalone, metric } from "@/lib/device";

// `teachAsk`: open the Teach form with this goal ("Show me once" on a task that failed; empty from Routines).
// `task`: what Envoy is doing on this phone, and `steps` its steps as they stream in (page.tsx). `ended`: whether a task
// has finished, for a lease that still names it (leases are refreshed every 10 s).
type Props = { avd: string; lease?: Lease; needsYou?: string | null; mobile?: boolean; teachAsk?: { goal: string } | null;
  task?: Task; steps?: Step[]; openTask?: (id: string) => void; ended?: (taskId: string) => boolean };
const SENTINEL = "  ";
const QUESTION = /\?\s*$|^(what|how|when|where|which|who|is|are|do|does|did|can)\b/i;  // as the compiler tells a question goal
const LEARNING: Record<string, string> = { compiling: "Turning what you showed into a routine…", replaying: "Running it once on its own to check it works…" };

const median = (xs: number[]) => (xs.length ? [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] : 0);

// "Step 3 of 6 · Open trip": the latest step a person would count (a routine's steps, the agent's actions), in the task
// view's words. "of 6" only for a routine, while the count fits (a repair can add steps).
function stepCaption(t: Task, steps: Step[], total: number | null): string {
  if (t.status === "queued") return "Getting ready";
  const counted = steps.filter((s) => s.kind === (t.routine ? "routine_step" : "action"));
  const last = counted.length ? stepLine(counted[counted.length - 1]) : null;
  if (!last) return "Looking at the screen";
  const n = counted.length;
  return `Step ${n}${t.routine && total && n <= total ? ` of ${total}` : ""} · ${last.text}`;
}

export default function LivePhone({ avd, lease, needsYou, mobile, teachAsk, task, steps: liveSteps, openTask, ended }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const kb = useRef<HTMLInputElement>(null);
  const ws = useRef<WebSocket | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 1080, h: 2400 });
  const [control, setControl] = useState<Lease | undefined>(lease);
  const [stats, setStats] = useState<{ fps: number; frame: number; rtt: number; tap: number }>({ fps: 0, frame: 0, rtt: 0, tap: 0 });
  const [error, setError] = useState<string | null>(null);
  const [secure, setSecure] = useState(false);  // a real phone shows protected screens black: say so instead
  const [isPhone, setIsPhone] = useState(false);
  const [typed, setTyped] = useState("");
  const [keyboard, setKeyboard] = useState(false);
  const [goal, setGoal] = useState<string | null>(teachAsk?.goal ?? null);  // the Teach form, open while not null
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [taught, setTaught] = useState<TeachResult | null>(null);  // the last teach session's outcome
  const down = useRef<{ x: number; y: number; t: number; timer?: ReturnType<typeof setTimeout>; long?: boolean } | null>(null);
  const clock = useRef<{ offset: number; bestRtt: number }>({ offset: 0, bestRtt: Infinity });
  const sent = useRef<Record<number, number>>({});
  const nextId = useRef(1);
  const samples = useRef<{ frame: number[]; rtt: number[]; tap: number[]; bytes: number; frames: number }>({ frame: [], rtt: [], tap: [], bytes: 0, frames: 0 });
  const [debug] = useState(() => typeof location !== "undefined" && new URLSearchParams(location.search).get("debug") === "1");  // the stream's numbers

  // The task's steps so far (the page may have opened mid-task), plus those streaming in; a routine's step count.
  const [stored, setStored] = useState<Step[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  useEffect(() => {
    setStored([]);
    if (task?.id) api<{ steps: Step[] }>(`/api/tasks/${task.id}`).then((d) => setStored(d.steps ?? [])).catch(() => {});
  }, [task?.id]);
  useEffect(() => {
    setTotal(null);
    if (task?.routine) api<{ name: string; steps: number }[]>("/api/routines").then((rs) => setTotal(rs.find((r) => r.name === task.routine)?.steps ?? null)).catch(() => {});
  }, [task?.routine]);
  const taskSteps = [...stored, ...(liveSteps ?? []).filter((s) => s.seq > (stored[stored.length - 1]?.seq ?? 0))];

  useEffect(() => setControl(lease), [lease]);
  useEffect(() => { if (teachAsk) { setTaught(null); setGoal(teachAsk.goal); } }, [teachAsk]);

  // After Finish the phone is handed back and Envoy learns in the background: follow it until it's saved or failed.
  const teachStatus = control?.teach?.status;
  const [following, setFollowing] = useState(false);
  useEffect(() => {
    if (!following || mockMode()) return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api<TeachResult>(`/api/teach/${avd}`);
        if (stop) return;
        setTaught(r);
        if (!["compiling", "replaying", "recording"].includes(r.status)) { setFollowing(false); return; }
      } catch { /* the next tick tries again */ }
      if (!stop) setTimeout(tick, 1500);
    };
    tick();
    return () => { stop = true; };
  }, [following, avd]);

  useEffect(() => {
    if (mockMode()) {  // mock mode: a still picture of the phone, and no socket
      let gone = false;
      loadMock().then((m) => {
        const img = new Image();
        img.onload = () => {
          const c = canvas.current;
          if (gone || !c) return;
          c.width = img.width; c.height = img.height;
          c.getContext("2d")?.drawImage(img, 0, 0);
          setSize({ w: img.width, h: img.height });
          setIsPhone(avd === "pixel-5");
        };
        img.src = m.liveFrame(avd);
      });
      return () => { gone = true; };
    }
    let stop = false;
    let frames = 0;
    let retry: ReturnType<typeof setTimeout>;
    const quality = mobile ? 60 : 70;
    const width = mobile ? 720 : 540;
    const tick = setInterval(() => {
      const s = samples.current;
      setStats({ fps: frames, frame: Math.round(median(s.frame.slice(-30))), rtt: Math.round(median(s.rtt.slice(-10))), tap: Math.round(median(s.tap.slice(-10))) });
      frames = 0;
      if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify({ type: "ping", t: Date.now() }));
    }, 1000);
    const report = setInterval(() => {
      const s = samples.current;
      if (!s.frames) return;
      metric({ kind: "live", avd, width, quality, frames: s.frames, frame_ms_p50: Math.round(median(s.frame)), rtt_ms_p50: Math.round(median(s.rtt)),
        tap_ack_ms_p50: s.tap.length ? Math.round(median(s.tap)) : null, kb_per_frame: Math.round(s.bytes / s.frames / 1024),
        standalone: isStandalone(), host: location.host, net: (navigator as any).connection?.effectiveType ?? null });
      samples.current = { frame: [], rtt: [], tap: [], bytes: 0, frames: 0 };
    }, 20000);
    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(`${proto}://${location.host}/api/live/${avd}?fps=${mobile ? 10 : 12}&width=${width}&quality=${quality}`);
      sock.binaryType = "arraybuffer";
      ws.current = sock;
      sock.onopen = () => sock.send(JSON.stringify({ type: "ping", t: Date.now() }));
      sock.onmessage = async (m) => {
        if (typeof m.data === "string") {
          const msg = JSON.parse(m.data);
          if (msg.type === "hello") { setSize({ w: msg.width, h: msg.height }); setControl(msg.control); setError(null); setIsPhone(msg.kind === "phone"); }
          else if (msg.type === "secure") setSecure(!!msg.secure);
          else if (msg.type === "control") setControl(msg.control);
          else if (msg.type === "error") setError(msg.error);
          else if (msg.type === "pong") {
            const now = Date.now();
            const rtt = now - msg.t;
            samples.current.rtt.push(rtt);
            if (rtt <= clock.current.bestRtt * 1.2) {  // the offset from the tightest round trips
              clock.current.bestRtt = Math.min(clock.current.bestRtt, rtt);
              clock.current.offset = msg.server * 1000 - (msg.t + now) / 2;
            }
          } else if (msg.type === "ack" && sent.current[msg.id]) {
            samples.current.tap.push(performance.now() - sent.current[msg.id]);
            delete sent.current[msg.id];
          }
          return;
        }
        const buf = m.data as ArrayBuffer;
        const ts = new DataView(buf).getFloat64(0);
        const bmp = await createImageBitmap(new Blob([buf.slice(8)], { type: "image/jpeg" }));
        const c = canvas.current;
        if (!c) return;
        if (c.width !== bmp.width) { c.width = bmp.width; c.height = bmp.height; }
        c.getContext("2d")?.drawImage(bmp, 0, 0);
        frames += 1;
        samples.current.frames += 1;
        samples.current.bytes += buf.byteLength;
        if (clock.current.bestRtt < Infinity) samples.current.frame.push(Date.now() + clock.current.offset - ts * 1000);
      };
      sock.onclose = () => { if (!stop) retry = setTimeout(open, 1500); };
    };
    open();
    return () => { stop = true; clearTimeout(retry); clearInterval(tick); clearInterval(report); ws.current?.close(); };
  }, [avd, mobile]);

  const inControl = !!control?.user_control;
  const send = (msg: Record<string, unknown>, ack = false) => {
    if (ws.current?.readyState !== WebSocket.OPEN) return;
    if (ack) { const id = nextId.current++; sent.current[id] = performance.now(); msg = { ...msg, id }; }
    ws.current.send(JSON.stringify(msg));
  };
  const frac = (e: React.PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) };
  };

  const onDown = (e: React.PointerEvent) => {
    if (!inControl) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = frac(e);
    const d = { ...p, t: performance.now() } as NonNullable<typeof down.current>;
    d.timer = setTimeout(() => { d.long = true; send({ type: "long_press", x: d.x, y: d.y }, true); navigator.vibrate?.(10); }, 550);
    down.current = d;
    if (!mobile) canvas.current?.focus({ preventScroll: true });
  };
  const onMove = (e: React.PointerEvent) => {
    const d = down.current;
    if (!d || !d.timer) return;
    const p = frac(e);
    if (Math.hypot(p.x - d.x, (p.y - d.y) * (size.h / size.w)) > 0.02) { clearTimeout(d.timer); d.timer = undefined; }
  };
  const onUp = (e: React.PointerEvent) => {
    const d = down.current;
    down.current = null;
    if (!inControl || !d) return;
    if (d.timer) clearTimeout(d.timer);
    if (d.long) return;
    const p = frac(e);
    if (Math.hypot(p.x - d.x, (p.y - d.y) * (size.h / size.w)) < 0.02) send({ type: "tap", x: p.x, y: p.y }, true);
    else send({ type: "swipe", x1: d.x, y1: d.y, x2: p.x, y2: p.y, ms: Math.max(120, performance.now() - d.t) }, true);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (!inControl) return;
    const named: Record<string, string> = { Backspace: "Backspace", Enter: "Enter", Tab: "Tab", Escape: "Back" };
    if (named[e.key]) { send({ type: "key", key: named[e.key] }); e.preventDefault(); }
    else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) { send({ type: "text", text: e.key }); e.preventDefault(); }
  };

  // The iPhone's keyboard: a hidden field that always holds a little text, so Backspace has something to delete;
  // every edit is forwarded to the phone and cancelled here (the native beforeinput event: React's doesn't see deletes).
  const live = useRef({ inControl, send });
  live.current = { inControl, send };
  useEffect(() => {
    const k = kb.current;
    if (!k) return;
    const onBeforeInput = (ev: InputEvent) => {
      ev.preventDefault();
      if (!live.current.inControl) return;
      if (ev.inputType === "deleteContentBackward") live.current.send({ type: "key", key: "Backspace" });
      else if (ev.inputType === "insertLineBreak" || ev.inputType === "insertParagraph") live.current.send({ type: "key", key: "Enter" });
      else if (ev.data) live.current.send({ type: "text", text: ev.data });
    };
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Enter") { ev.preventDefault(); if (live.current.inControl) live.current.send({ type: "key", key: "Enter" }); }
    };
    k.addEventListener("beforeinput", onBeforeInput);
    k.addEventListener("keydown", onKeyDown);
    return () => { k.removeEventListener("beforeinput", onBeforeInput); k.removeEventListener("keydown", onKeyDown); };
  }, []);
  const openKeyboard = () => {
    const k = kb.current;
    if (!k) return;
    k.value = SENTINEL;
    k.focus();
    k.setSelectionRange(SENTINEL.length, SENTINEL.length);
    setKeyboard(true);
  };

  const takeOver = () => post(`/api/devices/${avd}/takeover`).then(setControl).catch((e) => setError(e.message));
  const handBack = () => { kb.current?.blur(); post(`/api/devices/${avd}/handback`).then(setControl).catch((e) => setError(e.message)); };
  const teach = async (path: "start" | "finish" | "cancel", body: Record<string, unknown> = {}) => {
    setBusy(true);
    setError(null);
    try {
      const r = await post<TeachResult>(`/api/teach/${path}`, { device: avd, ...body });
      setTaught(r);
      if (path === "start") { setGoal(null); setAnswer(""); }
      if (path === "finish") { kb.current?.blur(); setFollowing(true); }
      if (path === "cancel") kb.current?.blur();
      api<Lease[]>("/api/devices").then((ds) => { const me = ds.find((d) => d.avd === avd); if (me) setControl(me); }).catch(() => {});
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const recording = !!control?.teach && control.teach.status === "recording" && inControl;
  const working = !!task || (!!control?.task_id && !ended?.(control.task_id));
  const free = !working && !inControl && !needsYou;  // the Teach form only opens on a phone nobody is using
  const paused = recording && control?.teach?.recording === "paused";
  const asking = recording && QUESTION.test(control?.teach?.goal ?? "");

  const keys: { k: string; label: string; icon: React.ReactNode }[] = [
    { k: "Back", label: "Back", icon: <ArrowUUpLeftIcon size={20} /> }, { k: "Home", label: "Home", icon: <CircleIcon size={20} /> },
    { k: "Enter", label: "Enter", icon: <KeyReturnIcon size={20} /> }, { k: "Backspace", label: "Delete", icon: <BackspaceIcon size={20} /> },
  ];
  return (
    <div className="flex flex-col gap-3">
      {recording ? (
        <div className={`rounded-block px-4 py-3 ${paused ? "border border-apricot-line bg-surface" : "bg-ink text-on-ink"}`} role="status" aria-live="polite">
          <div className="flex items-center gap-2 text-body font-bold">
            <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${paused ? "bg-apricot" : "animate-pulse bg-apricot"}`} />
            {paused ? <span className="text-apricot-ink">Recording paused</span> : "Recording"}
            <span className={`ml-auto text-meta font-normal tabular-nums ${paused ? "text-ink-2" : "opacity-85"}`}>{control?.teach?.steps ?? 0} step{control?.teach?.steps === 1 ? "" : "s"}</span>
          </div>
          <div className={`mt-0.5 text-meta ${paused ? "text-ink-2" : "opacity-85"}`}>
            {paused ? `On ${control?.teach?.why || "a sign-in screen"}: nothing here is kept. It records again on the next screen.`
              : <>Show Envoy: <span className="font-semibold">{control?.teach?.goal}</span>. Each tap and what you type is kept; sign-in screens and passwords never are.</>}
          </div>
          {asking && (
            <input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="The answer you found" aria-label="The answer you found"
                   className={`mt-3 h-11 w-full rounded-full border px-4 text-meta outline-none ${paused ? "border-control bg-surface" : "border-transparent bg-surface text-ink"} focus:border-sage`} />
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button disabled={busy} onClick={() => teach("finish", { ok: true, answer })}
                    className={`h-11 rounded-full px-5 text-[14px] font-bold disabled:opacity-60 ${paused ? "bg-sage text-white" : "bg-surface text-ink"}`}>Done, it worked</button>
            <button disabled={busy} onClick={() => teach("cancel")}
                    className={`h-11 rounded-full border px-4 text-[14px] font-bold disabled:opacity-60 ${paused ? "border-control bg-surface" : "border-on-ink/40"}`}>Cancel</button>
          </div>
        </div>
      ) : teachStatus && LEARNING[teachStatus] ? (
        <div className="rounded-block border border-line bg-surface px-4 py-3" role="status" aria-live="polite">
          <div className="text-body font-bold">Learning it</div>
          <div className="mt-0.5 text-meta text-ink-2">
            {teachStatus === "compiling" && control?.teach?.source_task ? "Turning a finished task’s run into a routine…" : LEARNING[teachStatus]}
          </div>
        </div>
      ) : inControl ? (
        <div className="rounded-block bg-ink px-4 py-3 text-on-ink">
          <div className="text-body font-bold">You&rsquo;re in control. Envoy is paused.</div>
          <div className="mt-0.5 text-meta opacity-85">What you type goes straight to the phone and is never logged or shown to a model.</div>
          <button onClick={handBack} className="mt-3 h-11 rounded-full bg-surface px-5 text-[14px] font-bold text-ink">Hand back</button>
        </div>
      ) : needsYou ? (
        <div className="flex items-center gap-3 rounded-block border border-apricot-line bg-surface py-3 pl-4 pr-3">
          <span className="min-w-0 flex-1">
            <span className="block text-body font-bold text-apricot-ink">Envoy needs you</span>
            <span className="mt-0.5 block text-meta text-ink-2">{needsYou}</span>
          </span>
          <button onClick={takeOver} className="h-11 shrink-0 rounded-full bg-sage px-4 text-[14px] font-bold text-white">Take over</button>
        </div>
      ) : goal !== null && free ? (
        <form className="rounded-block border border-line bg-surface p-3" onSubmit={(e) => { e.preventDefault(); if (goal.trim()) teach("start", { goal }); }}>
          <label htmlFor={`teach-${avd}`} className="block px-1 text-body font-bold">Show Envoy once</label>
          <p className="mt-0.5 px-1 text-meta text-ink-2">Say what you&rsquo;ll do, then do it on the phone. Envoy records it and learns it as a routine.</p>
          <input id={`teach-${avd}`} value={goal} onChange={(e) => setGoal(e.target.value)} autoFocus placeholder="Add a Calendar event called Dentist tomorrow at 3pm"
                 className="mt-2 h-11 w-full rounded-full border border-control bg-surface px-4 text-meta outline-none focus:border-sage" />
          <div className="mt-2 flex gap-2">
            <button disabled={busy || !goal.trim()} className="h-11 rounded-full bg-sage px-5 text-[14px] font-bold text-white disabled:opacity-60">Start recording</button>
            <button type="button" onClick={() => setGoal(null)} className="h-11 rounded-full border border-control bg-surface px-4 text-[14px] font-bold">Not now</button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-2 rounded-block border border-line bg-surface py-2 pl-4 pr-2">
          {task ? (
            <span className="min-w-0 flex-1">
              {openTask ? (  // the goal is the link to the task
                <button onClick={() => openTask(task.id)} title="Open task" aria-label={`Open task: ${task.goal}`}
                        className="flex max-w-full items-center gap-1 text-left text-meta font-bold hover:text-sage-ink">
                  <span className="truncate">{task.goal}</span><ArrowUpRightIcon size={14} className="shrink-0 text-sage-ink" />
                </button>
              ) : <span className="block truncate text-meta font-bold">{task.goal}</span>}
              <span className={cx("block truncate text-meta-2", task.status === "waiting_approval" ? "font-semibold text-apricot-ink" : "text-ink-2")}>
                {task.status === "waiting_approval" ? "Waiting for your OK" : stepCaption(task, taskSteps, total)}
              </span>
            </span>
          ) : <span className="min-w-[8.5rem] flex-1 text-meta text-ink-2">{working ? "Envoy is using the phone" : "The phone is idle"}</span>}
          {task ? (  // while Envoy works, what it's doing gets the room: Take over is its icon
            <IconButton label="Take over" variant="surface" onClick={takeOver}><HandIcon size={18} /></IconButton>
          ) : <span className="flex gap-2">
            {!working && (
              <button onClick={() => { setTaught(null); setGoal(""); }} className="flex h-11 shrink-0 items-center gap-1.5 rounded-full border border-control bg-surface px-4 text-[14px] font-bold">
                <ChalkboardTeacherIcon size={18} />Teach</button>
            )}
            <button onClick={takeOver} className="flex h-11 shrink-0 items-center gap-1.5 rounded-full border border-control bg-surface px-4 text-[14px] font-bold"><HandIcon size={18} />Take over</button>
          </span>}
        </div>
      )}
      {goal !== null && !free && !recording && !(teachStatus && LEARNING[teachStatus]) && (
        <div className="flex items-center gap-2 rounded-block bg-raised py-2 pl-4 pr-2 text-meta text-ink-2" role="status">
          <ChalkboardTeacherIcon size={18} className="shrink-0" />
          <span className="min-w-0 flex-1">The phone is busy. Teach when it&rsquo;s free.</span>
          <button onClick={() => setGoal(null)} className="h-11 shrink-0 rounded-full px-3 text-meta font-bold text-sage-ink hover:bg-sage-tint/60">Not now</button>
        </div>
      )}
      {taught && !recording && !(teachStatus && LEARNING[teachStatus]) && ["saved", "failed", "discarded"].includes(taught.status) && (
        <div className={`rounded-block px-4 py-3 text-meta ${taught.status === "saved" ? "bg-sage-tint text-sage-ink" : taught.status === "failed" ? "bg-apricot-tint text-apricot-ink" : "bg-raised text-ink-2"}`} role="status">
          <div className="font-bold">{taught.status === "saved" ? "Learned it" : taught.status === "failed" ? "Couldn't learn it this time" : "Nothing was kept"}</div>
          <div className="mt-0.5">{taught.detail}</div>
          {taught.status === "saved" && <div className="mt-1 text-meta-2">It&rsquo;s in Routines, marked taught. Next time, just ask.</div>}
          {taught.status === "failed" && taught.notes.length > 0 && <ul className="mt-1 list-disc pl-4 text-meta-2">{taught.notes.slice(0, 3).map((n) => <li key={n}>{n}</li>)}</ul>}
          <button onClick={() => setTaught(null)} className="mt-2 h-9 rounded-full border border-current/30 px-3 text-meta-2 font-bold">OK</button>
        </div>
      )}
      <div className={`relative mx-auto w-full overflow-hidden rounded-[30px] border-[6px] ${recording && !paused ? "border-apricot" : inControl ? "border-sage" : "border-ink"} bg-ink shadow-phone`}
           style={{ aspectRatio: `${size.w} / ${size.h}`, maxWidth: mobile ? `min(100%, calc((100dvh - ${recording ? (asking ? 530 : 470) : inControl ? 430 : 350}px) * ${size.w / size.h}))` : 300 }}>
        <canvas ref={canvas} tabIndex={0} aria-label={inControl ? "The phone's screen: tap, swipe, or type" : "The phone's screen, live"}
                onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => { if (down.current?.timer) clearTimeout(down.current.timer); down.current = null; }}
                onKeyDown={onKey} onContextMenu={(e) => e.preventDefault()}
                onPaste={(e) => { const text = e.clipboardData.getData("text"); if (inControl && text) { send({ type: "text", text }); e.preventDefault(); } }}
                className={`h-full w-full select-none outline-none [-webkit-touch-callout:none] ${inControl ? "cursor-pointer [touch-action:none]" : "cursor-not-allowed [touch-action:pan-y]"}`} />
        {secure && (
          <div className="absolute inset-0 flex items-center justify-center bg-ink/95 p-5 text-center text-meta text-on-ink">
            This screen is protected (a sign-in or a payment): your phone won&rsquo;t share it. Use the phone itself, then press Resume on its banner.
          </div>
        )}
        {error && <div role="alert" className="absolute inset-x-2 top-2 rounded-sm bg-apricot-tint px-2 py-1 text-meta-2 text-apricot-ink">{error}</div>}
      </div>
      <input ref={kb} aria-label="Type into the phone" autoCapitalize="off" autoCorrect="off" autoComplete="off" spellCheck={false} enterKeyHint="send"
             onInput={(e) => { (e.target as HTMLInputElement).value = SENTINEL; }} onBlur={() => setKeyboard(false)}
             className="pointer-events-none fixed left-0 top-0 h-px w-px opacity-0" style={{ fontSize: 16 }} />
      {inControl && (
        <div className="flex flex-col gap-2">
          <div className="flex justify-center gap-2">
            {mobile && (
              <button onClick={() => (keyboard ? kb.current?.blur() : openKeyboard())} aria-pressed={keyboard}
                      className={`flex h-11 items-center gap-1.5 rounded-full px-4 text-meta font-bold ${keyboard ? "bg-ink text-on-ink" : "border border-control bg-surface"}`}>
                <KeyboardIcon size={18} /> Keyboard
              </button>
            )}
            {keys.map(({ k, label, icon }) => (
              <button key={k} onClick={() => send({ type: "key", key: k }, true)} aria-label={label} title={label}
                      className="flex h-11 w-11 items-center justify-center rounded-full border border-control bg-surface">{icon}</button>
            ))}
          </div>
          {!mobile && (
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (typed) send({ type: "text", text: typed }); setTyped(""); }}>
              <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type into the phone" autoComplete="off" aria-label="Type into the phone"
                     className="h-11 min-w-0 flex-1 rounded-full border border-control bg-surface px-4 text-meta outline-none focus:border-sage" />
              <button className="h-11 rounded-full bg-ink px-4 text-meta font-bold text-on-ink">Send</button>
            </form>
          )}
          <p className="text-center text-meta-2 text-muted">
            {mobile ? "Tap, swipe, or hold for a long press. Keyboard types straight into the phone." : "Click the screen to tap, drag to swipe. With the screen focused, typing goes to the phone."}
          </p>
        </div>
      )}
      <div className="text-center text-meta-2 tabular-nums text-muted">
        {lease?.name ?? (isPhone ? "Your phone" : "Emulator")}
        {debug && <> · {stats.fps} fps · frame {stats.frame} ms · rtt {stats.rtt} ms{stats.tap ? ` · tap ${stats.tap} ms` : ""}</>}
      </div>
    </div>
  );
}

// Which phone the live view shows: the emulators, and your own Android phone when it's connected.
export function PhoneSwitch({ phones, avd, onChange }: { phones: Lease[]; avd: string; onChange: (avd: string) => void }) {
  if (phones.length < 2) return null;
  return (
    <div role="group" aria-label="Phones" className="scroll-none flex gap-2 overflow-x-auto">
      {phones.map((d) => {
        const on = avd === d.avd;
        const note = d.kind === "phone" && d.state === "unauthorized" ? "allow USB debugging" : d.running === false ? "off" : "";
        return (
          <button key={d.avd} onClick={() => onChange(d.avd)} aria-pressed={on}
                  className={`flex h-11 shrink-0 items-center gap-2 rounded-full px-4 text-meta font-semibold transition-colors ${on ? "bg-ink text-on-ink" : "border border-control bg-surface text-ink"}`}>
            <DeviceMobileIcon size={16} />{d.name ?? (d.kind === "phone" ? "Your phone" : "Emulator")}{note && <span className={on ? "opacity-80" : "text-muted"}>· {note}</span>}
          </button>
        );
      })}
    </div>
  );
}
