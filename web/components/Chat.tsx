"use client";

// Chat with Envoy's assistant (Muse Spark): answers from memory with where each fact was seen, or starts a task.
import { useState } from "react";
import { post, Task } from "@/lib/api";

type Msg = { from: "you" | "envoy"; text: string; task?: Task; memory?: boolean; stale?: boolean };

export default function Chat({ tasks, openTask }: { tasks: Record<string, Task>; openTask: (id: string) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([
    { from: "envoy", text: "Hi! Ask me about your trips (\"What's my gate?\") or ask me to do something (\"Check me in for my flight\")." },
  ]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setMsgs((m) => [...m, { from: "you", text: message }]);
    setBusy(true);
    try {
      const r = await post("/api/chat", { message });
      setMsgs((m) => [...m, { from: "envoy", text: r.reply, task: r.task, memory: r.from_memory, stale: r.stale }]);
    } catch (err: any) {
      setMsgs((m) => [...m, { from: "envoy", text: `Sorry, that didn't work: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {msgs.map((m, i) => {
          const t = m.task ? tasks[m.task.id] ?? m.task : undefined;
          return (
            <div key={i} className={`flex ${m.from === "you" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${m.from === "you" ? "bg-stone-800 text-white" : "bg-white shadow-sm"}`}>
                <div>{m.text}</div>
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
      </div>
      <form onSubmit={send} className="flex gap-2 border-t border-stone-200 bg-white p-3">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Message Envoy"
               className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm" />
        <button disabled={busy} className="rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">Send</button>
      </form>
    </div>
  );
}
