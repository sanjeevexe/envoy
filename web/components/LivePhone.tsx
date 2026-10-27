"use client";

// The phone's screen, live. Take over pauses Envoy; then your taps, swipes and typing go straight to the phone
// (never logged, never shown to a model). Hand back lets Envoy look again and continue.
// Phase 5: touch (tap, swipe, long press; the page doesn't scroll while you're in control), typing with the iPhone's
// keyboard, and latency measured against the Mac's clock (ping/pong), reported back so it can be compared over the tailnet.
import { useEffect, useRef, useState } from "react";
import { Lease, post } from "@/lib/api";
import { isStandalone, metric } from "@/lib/device";

type Props = { avd: string; lease?: Lease; needsYou?: string | null; mobile?: boolean };
const SENTINEL = "  ";

const median = (xs: number[]) => (xs.length ? [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] : 0);

export default function LivePhone({ avd, lease, needsYou, mobile }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const kb = useRef<HTMLInputElement>(null);
  const ws = useRef<WebSocket | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 1080, h: 2400 });
  const [control, setControl] = useState<Lease | undefined>(lease);
  const [stats, setStats] = useState<{ fps: number; frame: number; rtt: number; tap: number }>({ fps: 0, frame: 0, rtt: 0, tap: 0 });
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [keyboard, setKeyboard] = useState(false);
  const down = useRef<{ x: number; y: number; t: number; timer?: ReturnType<typeof setTimeout>; long?: boolean } | null>(null);
  const clock = useRef<{ offset: number; bestRtt: number }>({ offset: 0, bestRtt: Infinity });
  const sent = useRef<Record<number, number>>({});
  const nextId = useRef(1);
  const samples = useRef<{ frame: number[]; rtt: number[]; tap: number[]; bytes: number; frames: number }>({ frame: [], rtt: [], tap: [], bytes: 0, frames: 0 });

  useEffect(() => setControl(lease), [lease]);

  useEffect(() => {
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
          if (msg.type === "hello") { setSize({ w: msg.width, h: msg.height }); setControl(msg.control); setError(null); }
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
    if (!mobile) canvas.current?.focus();
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

  return (
    <div className="flex flex-col gap-2">
      {inControl ? (
        <div className="rounded-lg bg-violet-600 px-3 py-2 text-sm text-white">
          <div className="font-semibold">You are in control. Envoy is paused.</div>
          <div className="opacity-90">What you type goes straight to the phone and is never logged or shown to a model.</div>
          <button onClick={handBack} className="mt-2 rounded-md bg-white px-4 py-2 font-medium text-violet-700">Hand back</button>
        </div>
      ) : needsYou ? (
        <div className="rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-950">
          <div className="font-semibold">Envoy needs you</div>
          <div>{needsYou}</div>
          <button onClick={takeOver} className="mt-2 rounded-md bg-amber-600 px-4 py-2 font-medium text-white">Take over</button>
        </div>
      ) : (
        <div className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-sm shadow-sm">
          <span className="text-stone-600">{control?.task_id ? "Envoy is using the phone" : "Phone idle"}</span>
          <button onClick={takeOver} className="rounded-md bg-stone-800 px-4 py-1.5 font-medium text-white">Take over</button>
        </div>
      )}
      <div className={`relative mx-auto w-full overflow-hidden rounded-[28px] border-[6px] ${inControl ? "border-violet-500" : "border-stone-800"} bg-black shadow-lg`}
           style={{ aspectRatio: `${size.w} / ${size.h}`, maxWidth: mobile ? `min(100%, calc((100dvh - ${inControl ? 300 : 220}px) * ${size.w / size.h}))` : 300 }}>
        <canvas ref={canvas} tabIndex={0} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => { if (down.current?.timer) clearTimeout(down.current.timer); down.current = null; }}
                onKeyDown={onKey} onContextMenu={(e) => e.preventDefault()}
                onPaste={(e) => { const text = e.clipboardData.getData("text"); if (inControl && text) { send({ type: "text", text }); e.preventDefault(); } }}
                className={`h-full w-full select-none outline-none [-webkit-touch-callout:none] ${inControl ? "cursor-pointer [touch-action:none]" : "cursor-not-allowed [touch-action:pan-y]"}`} />
        {error && <div className="absolute inset-x-2 top-2 rounded bg-rose-600/90 px-2 py-1 text-xs text-white">{error}</div>}
      </div>
      <input ref={kb} aria-label="Type into the phone" autoCapitalize="off" autoCorrect="off" autoComplete="off" spellCheck={false} enterKeyHint="send"
             onInput={(e) => { (e.target as HTMLInputElement).value = SENTINEL; }} onBlur={() => setKeyboard(false)}
             className="pointer-events-none fixed left-0 top-0 h-px w-px opacity-0" style={{ fontSize: 16 }} />
      {inControl && (
        <div className="flex flex-col gap-2">
          <div className="flex justify-center gap-2 text-sm">
            {mobile && (
              <button onClick={() => (keyboard ? kb.current?.blur() : openKeyboard())} className={`rounded-md px-3 py-2 shadow-sm ${keyboard ? "bg-stone-800 text-white" : "bg-white"}`}>
                ⌨︎ Keyboard
              </button>
            )}
            {["Back", "Home", "Enter", "Backspace"].map((k) => (
              <button key={k} onClick={() => send({ type: "key", key: k }, true)} className="rounded-md bg-white px-3 py-2 shadow-sm">{k === "Backspace" ? "⌫" : k}</button>
            ))}
          </div>
          {!mobile && (
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (typed) send({ type: "text", text: typed }); setTyped(""); }}>
              <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type into the phone" autoComplete="off"
                     className="min-w-0 flex-1 rounded-md border border-stone-300 bg-white px-2 py-1 text-sm" />
              <button className="rounded-md bg-stone-800 px-3 py-1 text-sm text-white">Send</button>
            </form>
          )}
          <p className="text-center text-xs text-stone-500">
            {mobile ? "Tap, swipe, or hold for a long press. Keyboard types straight into the phone." : "Click the screen to tap, drag to swipe; with the screen focused, typing goes to the phone."}
          </p>
        </div>
      )}
      <div className="text-center text-xs text-stone-400">
        {avd} · {stats.fps} fps · frame {stats.frame} ms · rtt {stats.rtt} ms{stats.tap ? ` · tap ${stats.tap} ms` : ""}
      </div>
    </div>
  );
}
