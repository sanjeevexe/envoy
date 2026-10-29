"use client";

// The phone's screen, live. Take over pauses Envoy; then your taps, swipes and typing go straight to the phone
// (never logged, never shown to a model). Hand back lets Envoy look again and continue.
// Phase 5: touch (tap, swipe, long press; the page doesn't scroll while you're in control), typing with the iPhone's
// keyboard, and latency measured against the Mac's clock (ping/pong), reported back so it can be compared over the tailnet.
import { useEffect, useRef, useState } from "react";
import { ArrowUUpLeftIcon, BackspaceIcon, CircleIcon, DeviceMobileIcon, HandIcon, KeyboardIcon, KeyReturnIcon } from "@phosphor-icons/react";
import { Lease, loadMock, mockMode, post } from "@/lib/api";
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
  const [secure, setSecure] = useState(false);  // a real phone shows protected screens black: say so instead
  const [isPhone, setIsPhone] = useState(false);
  const [typed, setTyped] = useState("");
  const [keyboard, setKeyboard] = useState(false);
  const down = useRef<{ x: number; y: number; t: number; timer?: ReturnType<typeof setTimeout>; long?: boolean } | null>(null);
  const clock = useRef<{ offset: number; bestRtt: number }>({ offset: 0, bestRtt: Infinity });
  const sent = useRef<Record<number, number>>({});
  const nextId = useRef(1);
  const samples = useRef<{ frame: number[]; rtt: number[]; tap: number[]; bytes: number; frames: number }>({ frame: [], rtt: [], tap: [], bytes: 0, frames: 0 });

  useEffect(() => setControl(lease), [lease]);

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

  const keys: { k: string; label: string; icon: React.ReactNode }[] = [
    { k: "Back", label: "Back", icon: <ArrowUUpLeftIcon size={20} /> }, { k: "Home", label: "Home", icon: <CircleIcon size={20} /> },
    { k: "Enter", label: "Enter", icon: <KeyReturnIcon size={20} /> }, { k: "Backspace", label: "Delete", icon: <BackspaceIcon size={20} /> },
  ];
  return (
    <div className="flex flex-col gap-3">
      {inControl ? (
        <div className="rounded-block bg-ink px-4 py-3 text-white">
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
      ) : (
        <div className="flex items-center gap-3 rounded-block border border-line bg-surface py-2 pl-4 pr-2">
          <span className="min-w-0 flex-1 text-meta text-ink-2">{control?.task_id ? "Envoy is using the phone" : "The phone is idle"}</span>
          <button onClick={takeOver} className="flex h-11 shrink-0 items-center gap-1.5 rounded-full border border-control bg-surface px-4 text-[14px] font-bold"><HandIcon size={18} />Take over</button>
        </div>
      )}
      <div className={`relative mx-auto w-full overflow-hidden rounded-[30px] border-[6px] ${inControl ? "border-sage" : "border-ink"} bg-ink shadow-phone`}
           style={{ aspectRatio: `${size.w} / ${size.h}`, maxWidth: mobile ? `min(100%, calc((100dvh - ${inControl ? 430 : 350}px) * ${size.w / size.h}))` : 300 }}>
        <canvas ref={canvas} tabIndex={0} aria-label={inControl ? "The phone's screen: tap, swipe, or type" : "The phone's screen, live"}
                onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => { if (down.current?.timer) clearTimeout(down.current.timer); down.current = null; }}
                onKeyDown={onKey} onContextMenu={(e) => e.preventDefault()}
                onPaste={(e) => { const text = e.clipboardData.getData("text"); if (inControl && text) { send({ type: "text", text }); e.preventDefault(); } }}
                className={`h-full w-full select-none outline-none [-webkit-touch-callout:none] ${inControl ? "cursor-pointer [touch-action:none]" : "cursor-not-allowed [touch-action:pan-y]"}`} />
        {secure && (
          <div className="absolute inset-0 flex items-center justify-center bg-ink/95 p-5 text-center text-meta text-white">
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
                      className={`flex h-11 items-center gap-1.5 rounded-full px-4 text-meta font-bold ${keyboard ? "bg-ink text-white" : "border border-control bg-surface"}`}>
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
              <button className="h-11 rounded-full bg-ink px-4 text-meta font-bold text-white">Send</button>
            </form>
          )}
          <p className="text-center text-meta-2 text-muted">
            {mobile ? "Tap, swipe, or hold for a long press. Keyboard types straight into the phone." : "Click the screen to tap, drag to swipe. With the screen focused, typing goes to the phone."}
          </p>
        </div>
      )}
      <div className="text-center text-meta-2 tabular-nums text-muted">
        {isPhone ? lease?.name ?? "your phone" : lease?.name ?? avd} · {stats.fps} fps · frame {stats.frame} ms · rtt {stats.rtt} ms{stats.tap ? ` · tap ${stats.tap} ms` : ""}
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
                  className={`flex h-11 shrink-0 items-center gap-2 rounded-full px-4 text-meta font-semibold transition-colors ${on ? "bg-ink text-white" : "border border-control bg-surface text-ink"}`}>
            <DeviceMobileIcon size={16} />{d.name ?? (d.kind === "phone" ? "Your phone" : d.avd)}{note && <span className={on ? "opacity-80" : "text-muted"}>· {note}</span>}
          </button>
        );
      })}
    </div>
  );
}
