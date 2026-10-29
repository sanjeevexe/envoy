"use client";

// The conversation with Envoy's assistant (Muse Spark): answers from memory with where each fact was seen, or starts a
// task. Home's greeting sits in front of it; typing or speaking moves into the thread.
// Phase 5: tap the mic to dictate into the message box (Muse Voice Transcribe), check it, then send; replies to a
// dictated message are spoken. Screenshots and photos go into memory.
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpIcon, CaretLeftIcon, CaretRightIcon, GraphIcon, ImageSquareIcon, MicrophoneIcon, StopIcon } from "@phosphor-icons/react";
import Avatar, { type Mood } from "@/components/Avatar";
import { StatusChip } from "@/components/Tasks";
import { Chip, cx, IconButton } from "@/components/ui";
import { post, Task } from "@/lib/api";
import { metric, uploadPhotos } from "@/lib/device";
import { speak, Turn, useDictation } from "@/lib/voice";

type Msg = { from: "you" | "envoy"; text: string; task?: Task; memory?: boolean; stale?: boolean; voice?: boolean; photo?: boolean; error?: boolean };

const SPOKEN_END: Record<string, string> = { done: "Done.", failed: "That didn't work.", declined: "Declined.", needs_you: "I need you." };

// Dictated words go after whatever is already in the box.
const joinText = (before: string, words: string) => (before.trim() ? `${before.trimEnd()} ${words}` : words);

export default function Chat({ tasks, openTask, intro, suggestions = [], onListening, mood }: {
  tasks: Record<string, Task>; openTask: (id: string) => void; intro?: ReactNode; suggestions?: string[]; onListening?: (on: boolean) => void; mood: Mood;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [thread, setThread] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const spokenTasks = useRef<Record<string, string>>({});
  const before = useRef(""); // the box's text when dictation started
  const dictated = useRef<string | null>(null); // the box's text right after the last transcript landed

  useEffect(() => { if (thread) end.current?.scrollIntoView({ block: "end" }); }, [msgs.length, busy, thread]);

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

  // `dictation`: the message was dictated (and whether you changed the transcript before sending).
  const ask = useCallback(async (message: string, dictation?: { edited: boolean }) => {
    setThread(true);
    setMsgs((m) => [...m, { from: "you", text: message, voice: !!dictation }]);
    setBusy(true);
    const t0 = performance.now();
    try {
      const r = await post("/api/chat", { message, source: dictation ? "voice" : "chat" });
      setMsgs((m) => [...m, { from: "envoy", text: r.reply, task: r.task, memory: r.from_memory, stale: r.stale }]);
      if (dictation) {
        const chatMs = Math.round(performance.now() - t0);
        if (r.task?.id) spokenTasks.current[r.task.id] = r.task.status;
        speak(r.spoken || r.reply, () => metric({ kind: "voice_sent", edited: dictation.edited, chat_ms: chatMs,
          send_to_speech_ms: Math.round(performance.now() - t0), reply_kind: r.kind }));
      }
    } catch (err: any) {
      setMsgs((m) => [...m, { from: "envoy", text: `Sorry, that didn't work: ${err.message}`, error: true }]);
    } finally {
      setBusy(false);
    }
  }, []);

  const onText = useCallback((turn: Turn) => {
    const value = joinText(before.current, turn.text);
    setText(value);
    dictated.current = value;
    box.current?.focus();
    metric({ kind: "voice_turn", source: turn.source, audio_ms: turn.audio_ms, connect_ms: turn.connect_ms, finalize_ms: turn.finalize_ms,
      stop_to_text_ms: turn.stop_to_text_ms, cost_usd: turn.cost_usd });
  }, []);
  const voice = useDictation(onText, useCallback((msg: string) => setError(msg), []));
  const listening = voice.state === "listening" || voice.state === "starting";
  useEffect(() => onListening?.(listening), [listening, onListening]);

  const send = (e: React.FormEvent) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy || voice.state !== "idle") return;
    const wasDictated = dictated.current;
    dictated.current = null;
    setText("");
    ask(message, wasDictated === null ? undefined : { edited: wasDictated.trim() !== message });
  };

  const onPhotos = async (files: FileList | null) => {
    if (!files?.length) return;
    const list = Array.from(files);
    setThread(true);
    setMsgs((m) => [...m, { from: "you", text: list.length === 1 ? "Sent a screenshot" : `Sent ${list.length} images`, photo: true }]);
    setBusy(true);
    try {
      const r = await uploadPhotos(list);
      setMsgs((m) => [...m, { from: "envoy", text: `${r.summary} The image${list.length > 1 ? "s were" : " was"} deleted from your Mac.`, memory: true }]);
    } catch (err: any) {
      setMsgs((m) => [...m, { from: "envoy", text: err.status === 403 ? `${err.message} (Settings › Devices › Photos)` : `That didn't work: ${err.message}`, error: true }]);
    } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  };

  // Tap to start dictating, tap again to stop; the transcript lands in the box.
  const mic = () => {
    if (voice.state === "idle") {
      setError(null);
      before.current = text;
      voice.start();
    } else if (voice.state !== "finishing") voice.stop();
  };

  const shown = voice.state !== "idle" && voice.partial ? joinText(before.current, voice.partial) : text;
  const canSend = !!text.trim() && voice.state === "idle";
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {!thread ? intro : (
          <div className="mx-auto flex w-full max-w-[680px] flex-col gap-4 px-4 pb-4 pt-2">
            <button onClick={() => setThread(false)} className="-ml-2 flex h-11 items-center gap-1 self-start rounded-full pl-2 pr-3 text-meta font-bold text-sage-ink hover:bg-sage-tint/60">
              <CaretLeftIcon size={18} /> Home
            </button>
            {msgs.map((m, i) => m.from === "you" ? (
              <div key={i} className="ev-rise max-w-[78%] self-end rounded-[20px_20px_6px_20px] bg-ink px-4 py-3 text-body text-white [overflow-wrap:anywhere]">
                {m.voice && <MicrophoneIcon size={15} className="mr-1.5 inline -translate-y-px opacity-75" aria-label="Dictated" />}
                {m.photo && <ImageSquareIcon size={15} className="mr-1.5 inline -translate-y-px opacity-75" aria-hidden />}
                {m.text}
              </div>
            ) : (
              <Reply key={i} m={m} task={m.task ? tasks[m.task.id] ?? m.task : undefined} openTask={openTask}
                     mood={i === msgs.length - 1 && m.task && ["queued", "running"].includes((tasks[m.task.id] ?? m.task).status) ? mood : "idle"} />
            ))}
            {busy && (
              <div className="ev-rise flex items-center gap-2.5" role="status">
                <Avatar mood="thinking" size={44} /><span className="font-serif text-voice-2 text-ink-2">Thinking…</span>
              </div>
            )}
            <div ref={end} />
          </div>
        )}
      </div>
      {!thread && suggestions.length > 0 && (
        <div className="ev-rise ev-r4 scroll-none flex shrink-0 gap-2 overflow-x-auto px-4 pt-3 md:mx-auto md:w-full md:max-w-[680px]">
          {msgs.length > 0 && (
            <button onClick={() => setThread(true)} className="flex h-11 shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-sage-tint pl-4 pr-3 text-[14px] font-semibold text-sage-ink">
              Back to the conversation <CaretRightIcon size={16} />
            </button>
          )}
          {suggestions.map((s) => (
            <button key={s} onClick={() => ask(s)} disabled={busy}
                    className="h-11 shrink-0 whitespace-nowrap rounded-full border border-control bg-surface px-4 text-[14px] font-semibold hover:border-line-strong">
              {s}
            </button>
          ))}
        </div>
      )}
      {(listening || voice.state === "finishing" || error) && (
        <p role="status" className={cx("mx-4 mt-3 shrink-0 text-meta md:mx-auto md:w-full md:max-w-[648px]", error ? "text-apricot-ink" : "text-sage-ink")}>
          {error ?? (voice.state === "finishing" ? "Writing down what you said…" : voice.state === "starting" ? "Starting the microphone…" : "Listening. Tap stop when you're done.")}
        </p>
      )}
      <form onSubmit={send} className={cx("ev-rise ev-r5 shrink-0 px-4 pb-3 pt-3 md:mx-auto md:w-full md:max-w-[680px] md:pb-6")}>
        <div className={cx("flex h-14 items-center gap-1 rounded-full border bg-surface pl-1.5 pr-1.5 transition-colors focus-within:border-sage",
          listening ? "border-sage" : "border-control")}>
          <input ref={file} type="file" accept="image/*" multiple hidden onChange={(e) => onPhotos(e.target.files)} />
          <IconButton type="button" label="Send a screenshot or photo" onClick={() => file.current?.click()} className="text-muted"><ImageSquareIcon size={22} /></IconButton>
          <input ref={box} value={shown} readOnly={voice.state !== "idle"} enterKeyHint="send" aria-label={thread ? "Reply to Envoy" : "Ask Envoy"}
                 onChange={(e) => { setText(e.target.value); if (!e.target.value.trim()) dictated.current = null; }}
                 placeholder={listening ? "Listening…" : thread ? "Reply to Envoy" : "Ask Envoy anything"}
                 className="min-w-0 flex-1 bg-transparent px-1 text-[16px] font-medium outline-none placeholder:text-muted md:text-body" />
          {canSend ? (
            <IconButton label="Send" variant="ink" disabled={busy}><ArrowUpIcon size={20} weight="bold" /></IconButton>
          ) : (
            <IconButton type="button" variant="sage" onClick={mic} disabled={voice.state === "finishing"}
                        label={voice.state === "idle" ? "Talk to Envoy" : voice.state === "finishing" ? "Writing it down" : "Stop and write it down"}>
              {listening ? <StopIcon size={20} weight="fill" /> : <MicrophoneIcon size={22} />}
            </IconButton>
          )}
        </div>
      </form>
    </div>
  );
}

// "Order Thai Basil usual (items): DoorDash app, Oct 21" → "DoorDash · Oct 21"
export function rememberedFrom(where: string): string {
  const w = where.includes("): ") ? where.slice(where.lastIndexOf("): ") + 3) : where;
  const [what, ...when] = w.split(", ");
  const from = what.replace(/ app$/, "").replace(/^email from (.+)$/, "$1 email");
  return when.length ? `${from} · ${when.join(", ")}` : from;
}

function Reply({ m, task, openTask, mood }: { m: Msg; task?: Task; openTask: (id: string) => void; mood: Mood }) {
  return (
    <div className="ev-rise flex items-start gap-2.5">
      <Avatar mood={m.error ? "idle" : mood} size={44} />
      <div className="flex min-w-0 flex-1 flex-col gap-2 pt-1.5">
        <p className="font-serif text-voice-2 [overflow-wrap:anywhere]">{m.text}</p>
        {m.memory && (
          <span className="flex flex-wrap gap-1.5">
            <Chip icon={GraphIcon}>From memory</Chip>
            {m.stale && <Chip tone="apricot">May have changed since</Chip>}
          </span>
        )}
        {task && (
          <button onClick={() => openTask(task.id)} className="flex min-h-[60px] items-center gap-3 rounded-block border border-line bg-surface px-4 py-3 text-left hover:border-line-strong">
            <span className="min-w-0 flex-1">
              <span className="block truncate text-row font-semibold">{task.goal}</span>
              {task.result && <span className="mt-0.5 block truncate text-meta-2 text-muted">{task.result}</span>}
            </span>
            <StatusChip status={task.status} />
            <CaretRightIcon size={18} className="shrink-0 text-muted" />
          </button>
        )}
      </div>
    </div>
  );
}
