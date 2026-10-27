"use client";

// Chat with Envoy's assistant (Muse Spark): answers from memory with where each fact was seen, or starts a task.
// Phase 5: hold the mic to talk (Muse Voice Transcribe; spoken replies), and send screenshots or photos into memory.
import { useCallback, useEffect, useRef, useState } from "react";
import { post, Task } from "@/lib/api";
import { metric, uploadPhotos } from "@/lib/device";
import { speak, Turn, usePushToTalk } from "@/lib/voice";

type Msg = { from: "you" | "envoy"; text: string; task?: Task; memory?: boolean; stale?: boolean; voice?: boolean; photo?: boolean };

const SPOKEN_END: Record<string, string> = { done: "Done.", failed: "That didn't work.", declined: "Declined.", needs_you: "I need you." };

export default function Chat({ tasks, openTask, compact }: { tasks: Record<string, Task>; openTask: (id: string) => void; compact?: boolean }) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { from: "envoy", text: "Hi! Ask me about your trips (\"What's my gate?\") or ask me to do something (\"Check me in for my flight\"). Hold the mic to talk, or send a screenshot." },
  ]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const spokenTasks = useRef<Record<string, string>>({});
  const held = useRef<{ t: number; latched: boolean }>({ t: 0, latched: false });
  const [latched, setLatched] = useState(false);

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs.length, busy]);

  // A task you started by voice says how it ended, out loud.
  useEffect(() => {
    for (const [id, last] of Object.entries(spokenTasks.current)) {
      const t = tasks[id];
      if (t && t.status !== last && SPOKEN_END[t.status]) {
        spokenTasks.current[id] = t.status;
        speak(`${SPOKEN_END[t.status]} ${t.status === "done" ? (t.result ?? "").replace(/_/g, " ").replace(/;/g, ",") : ""}`.trim());
      }
    }
  }, [tasks]);

  const ask = useCallback(async (message: string, turn?: Turn) => {
    setMsgs((m) => [...m, { from: "you", text: message, voice: !!turn }]);
    setBusy(true);
    const t0 = performance.now();
    try {
      const r = await post("/api/chat", { message, source: turn ? "voice" : "chat" });
      setMsgs((m) => [...m, { from: "envoy", text: r.reply, task: r.task, memory: r.from_memory, stale: r.stale }]);
      if (turn) {
        const chatMs = Math.round(performance.now() - t0);
        if (r.task?.id) spokenTasks.current[r.task.id] = r.task.status;
        speak(r.spoken || r.reply, () => metric({ kind: "voice_turn", source: turn.source, audio_ms: turn.audio_ms, connect_ms: turn.connect_ms,
          finalize_ms: turn.finalize_ms, release_to_text_ms: turn.release_to_text_ms, chat_ms: chatMs,
          release_to_speech_ms: turn.release_to_text_ms + Math.round(performance.now() - t0), cost_usd: turn.cost_usd, reply_kind: r.kind }));
      }
    } catch (err: any) {
      setMsgs((m) => [...m, { from: "envoy", text: `Sorry, that didn't work: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  }, []);

  const ptt = usePushToTalk(useCallback((turn: Turn) => ask(turn.text, turn), [ask]),
    useCallback((msg: string) => { setError(msg); held.current = { t: 0, latched: false }; setLatched(false); }, []));

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    ask(message);
  };

  const onPhotos = async (files: FileList | null) => {
    if (!files?.length) return;
    const list = Array.from(files);
    setMsgs((m) => [...m, { from: "you", text: list.length === 1 ? "📷 Sent a screenshot" : `📷 Sent ${list.length} images`, photo: true }]);
    setBusy(true);
    try {
      const r = await uploadPhotos(list);
      setMsgs((m) => [...m, { from: "envoy", text: `${r.summary} The image${list.length > 1 ? "s were" : " was"} deleted from your Mac.`, memory: true }]);
    } catch (err: any) {
      setMsgs((m) => [...m, { from: "envoy", text: err.status === 403 ? `${err.message} (More → Settings → Photos)` : `That didn't work: ${err.message}` }]);
    } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  };

  // Hold to talk; a quick tap starts listening until the next tap.
  const micDown = (e: React.PointerEvent) => {
    e.preventDefault();
    if (ptt.state === "listening" && held.current.latched) { held.current.latched = false; setLatched(false); ptt.stop(); return; }
    if (ptt.state !== "idle") return;
    setError(null);
    held.current = { t: performance.now(), latched: false };
    ptt.start();
  };
  const micUp = (e: React.PointerEvent) => {
    e.preventDefault();
    if (held.current.latched || held.current.t === 0) return;
    if (performance.now() - held.current.t < 350) { held.current.latched = true; setLatched(true); return; }
    held.current.t = 0;
    ptt.stop();
  };

  const listening = ptt.state === "listening" || ptt.state === "starting";
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {msgs.map((m, i) => {
          const t = m.task ? tasks[m.task.id] ?? m.task : undefined;
          return (
            <div key={i} className={`flex ${m.from === "you" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${m.from === "you" ? "bg-stone-800 text-white" : "bg-white shadow-sm"}`}>
                <div>{m.voice && <span className="mr-1 opacity-70">🎙</span>}{m.text}</div>
                {m.memory && <div className="mt-1 text-xs text-stone-500">From memory{m.stale ? " · may have changed" : ""}</div>}
                {t && (
                  <button onClick={() => openTask(t.id)} className="mt-2 block w-full rounded-lg bg-stone-100 px-3 py-2 text-left text-xs">
                    <div className="font-medium">{t.goal}</div>
                    <div className="text-stone-600">{t.status.replace("_", " ")}{t.result ? ` · ${t.result}` : ""}</div>
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {busy && <div className="text-sm text-stone-400">Envoy is thinking…</div>}
        <div ref={end} />
      </div>
      {(listening || ptt.state === "finishing" || error) && (
        <div className={`mx-3 mb-2 rounded-lg px-3 py-2 text-sm ${error ? "bg-rose-50 text-rose-800" : "bg-emerald-50 text-emerald-900"}`}>
          {error ?? (ptt.state === "finishing" ? `“${ptt.partial || "…"}”` : ptt.partial ? `“${ptt.partial}”` : latched ? "Listening… tap the mic to send" : "Listening… release to send")}
        </div>
      )}
      <form onSubmit={send} className={`flex items-center gap-2 border-t border-stone-200 bg-white p-3 ${compact ? "pb-3" : ""}`}>
        <input ref={file} type="file" accept="image/*" multiple hidden onChange={(e) => onPhotos(e.target.files)} />
        <button type="button" onClick={() => file.current?.click()} aria-label="Send a screenshot or photo"
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-stone-100 text-lg">🖼</button>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Message Envoy" enterKeyHint="send"
               className="min-w-0 flex-1 rounded-full border border-stone-300 px-4 py-2 text-base md:text-sm" />
        {text.trim() ? (
          <button disabled={busy} className="h-11 shrink-0 rounded-full bg-stone-800 px-4 text-sm font-medium text-white disabled:opacity-50">Send</button>
        ) : (
          <button type="button" aria-label="Hold to talk" onPointerDown={micDown} onPointerUp={micUp} onPointerCancel={() => ptt.cancel()}
                  onContextMenu={(e) => e.preventDefault()}
                  className={`flex h-11 w-11 shrink-0 select-none items-center justify-center rounded-full text-lg text-white [touch-action:none] [-webkit-touch-callout:none] ${listening ? "scale-110 bg-emerald-600" : ptt.state === "finishing" ? "bg-emerald-800" : "bg-stone-800"} transition`}>
            🎙
          </button>
        )}
      </form>
    </div>
  );
}
