"use client";

// "Use your Android phone for this task?" Envoy waits for your answer before it touches your own phone (Phase 6).
// Only your session answers; no answer is never a yes.
import { useState } from "react";
import { post, Task } from "@/lib/api";

export default function PhoneAsk({ task, large }: { task: Task; large?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answer = (allow: boolean) => {
    setBusy(true);
    post(`/api/tasks/${task.id}/phone`, { allow }).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };
  return (
    <div className={`rounded-xl border border-amber-300 bg-amber-50 ${large ? "p-4" : "p-3"} text-sm text-amber-950`}>
      <div className="font-medium">{task.detail ?? "Envoy wants to use your Android phone"}</div>
      <div className="mt-0.5 text-amber-900/80">{task.goal}</div>
      <div className="mt-1 text-xs text-amber-900/70">While it works, a banner on the phone says so; touch the phone or press Pause there to take it back.</div>
      <div className="mt-3 flex gap-2">
        <button disabled={busy} onClick={() => answer(true)} className="h-10 rounded-lg bg-stone-900 px-4 font-medium text-white disabled:opacity-50">Use my phone</button>
        <button disabled={busy} onClick={() => answer(false)} className="h-10 rounded-lg bg-white px-4 font-medium ring-1 ring-stone-300 disabled:opacity-50">
          {/* an app that blocks emulators has no emulator to fall back to */}
          {(task.detail ?? "").includes("blocks emulators") ? "Not my phone" : "Use an emulator"}
        </button>
      </div>
      {error && <div className="mt-2 text-rose-700">{error}</div>}
    </div>
  );
}
