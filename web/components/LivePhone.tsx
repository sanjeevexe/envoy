"use client";

// The phone's screen, live. Take over pauses Envoy; then your taps, swipes and typing go straight to the phone
// (never logged, never shown to a model). Hand back lets Envoy look again and continue.
import { useEffect, useRef, useState } from "react";
import { Lease, post } from "@/lib/api";

type Props = { avd: string; lease?: Lease; needsYou?: string | null };

export default function LivePhone({ avd, lease, needsYou }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const ws = useRef<WebSocket | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 1080, h: 2400 });
  const [control, setControl] = useState<Lease | undefined>(lease);
  const [stats, setStats] = useState<{ fps: number; latency: number }>({ fps: 0, latency: 0 });
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const down = useRef<{ x: number; y: number; t: number } | null>(null);

  useEffect(() => setControl(lease), [lease]);

  useEffect(() => {
    let stop = false;
    let frames = 0;
    let lat = 0;
    let retry: ReturnType<typeof setTimeout>;
    const tick = setInterval(() => { setStats({ fps: frames, latency: Math.round(lat) }); frames = 0; }, 1000);
    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(`${proto}://${location.host}/api/live/${avd}?fps=12&width=540`);
      sock.binaryType = "arraybuffer";
      ws.current = sock;
      sock.onmessage = async (m) => {
        if (typeof m.data === "string") {
          const msg = JSON.parse(m.data);
          if (msg.type === "hello") { setSize({ w: msg.width, h: msg.height }); setControl(msg.control); setError(null); }
          else if (msg.type === "control") setControl(msg.control);
          else if (msg.type === "error") setError(msg.error);
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
        lat = lat ? lat * 0.8 + (Date.now() - ts * 1000) * 0.2 : Date.now() - ts * 1000;
      };
      sock.onclose = () => { if (!stop) retry = setTimeout(open, 1500); };
    };
    open();
    return () => { stop = true; clearTimeout(retry); clearInterval(tick); ws.current?.close(); };
  }, [avd]);

  const inControl = !!control?.user_control;
  const send = (msg: object) => ws.current?.readyState === WebSocket.OPEN && ws.current.send(JSON.stringify(msg));
  const frac = (e: React.PointerEvent) => {
    const r = (e.target as HTMLElement).getBoundingClientRect();
    return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
  };

  const onDown = (e: React.PointerEvent) => {
    if (!inControl) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    down.current = { ...frac(e), t: performance.now() };
  };
  const onUp = (e: React.PointerEvent) => {
    if (!inControl || !down.current) return;
    const p = frac(e);
    const d = down.current;
    down.current = null;
    if (Math.hypot(p.x - d.x, (p.y - d.y) * (size.h / size.w)) < 0.02) send({ type: "tap", x: p.x, y: p.y });
    else send({ type: "swipe", x1: d.x, y1: d.y, x2: p.x, y2: p.y, ms: Math.max(120, performance.now() - d.t) });
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (!inControl) return;
    const named: Record<string, string> = { Backspace: "Backspace", Enter: "Enter", Tab: "Tab", Escape: "Back" };
    if (named[e.key]) { send({ type: "key", key: named[e.key] }); e.preventDefault(); }
    else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey) { send({ type: "text", text: e.key }); e.preventDefault(); }
  };

  const takeOver = () => post(`/api/devices/${avd}/takeover`).then(setControl).catch((e) => setError(e.message));
  const handBack = () => post(`/api/devices/${avd}/handback`).then(setControl).catch((e) => setError(e.message));

  return (
    <div className="flex flex-col gap-2">
      {inControl ? (
        <div className="rounded-lg bg-violet-600 px-3 py-2 text-sm text-white">
          <div className="font-semibold">You are in control. Envoy is paused.</div>
          <div className="opacity-90">What you type here goes straight to the phone and is never logged or shown to a model.</div>
          <button onClick={handBack} className="mt-2 rounded-md bg-white px-3 py-1 font-medium text-violet-700">Hand back</button>
        </div>
      ) : needsYou ? (
        <div className="rounded-lg bg-amber-100 px-3 py-2 text-sm text-amber-950">
          <div className="font-semibold">Envoy needs you</div>
          <div>{needsYou}</div>
          <button onClick={takeOver} className="mt-2 rounded-md bg-amber-600 px-3 py-1 font-medium text-white">Take over</button>
        </div>
      ) : (
        <div className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-sm shadow-sm">
          <span className="text-stone-600">{control?.task_id ? "Envoy is using the phone" : "Phone idle"}</span>
          <button onClick={takeOver} className="rounded-md bg-stone-800 px-3 py-1 font-medium text-white">Take over</button>
        </div>
      )}
      <div className={`relative mx-auto w-full max-w-[300px] overflow-hidden rounded-[28px] border-[6px] ${inControl ? "border-violet-500" : "border-stone-800"} bg-black shadow-lg`}
           style={{ aspectRatio: `${size.w} / ${size.h}` }}>
        <canvas ref={canvas} tabIndex={0} onPointerDown={onDown} onPointerUp={onUp} onKeyDown={onKey}
                onPaste={(e) => { const text = e.clipboardData.getData("text"); if (inControl && text) { send({ type: "text", text }); e.preventDefault(); } }}
                className={`h-full w-full touch-none outline-none ${inControl ? "cursor-pointer" : "cursor-not-allowed"}`} />
        {error && <div className="absolute inset-x-2 top-2 rounded bg-rose-600/90 px-2 py-1 text-xs text-white">{error}</div>}
      </div>
      {inControl && (
        <div className="flex flex-col gap-2">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (typed) send({ type: "text", text: typed }); setTyped(""); }}>
            <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type into the phone" autoComplete="off"
                   className="min-w-0 flex-1 rounded-md border border-stone-300 bg-white px-2 py-1 text-sm" />
            <button className="rounded-md bg-stone-800 px-3 py-1 text-sm text-white">Send</button>
          </form>
          <div className="flex justify-center gap-2 text-sm">
            {["Back", "Home", "Enter", "Backspace"].map((k) => (
              <button key={k} onClick={() => send({ type: "key", key: k })} className="rounded-md bg-white px-2 py-1 shadow-sm">{k === "Backspace" ? "⌫" : k}</button>
            ))}
          </div>
          <p className="text-center text-xs text-stone-500">Click the screen to tap, drag to swipe; with the screen focused, typing goes to the phone.</p>
        </div>
      )}
      <div className="text-center text-xs text-stone-400">{avd} · {stats.fps} fps · {stats.latency} ms</div>
    </div>
  );
}
