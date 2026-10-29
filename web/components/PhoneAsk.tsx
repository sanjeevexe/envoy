"use client";

// "Use your Android phone for this task?" Envoy waits for your answer before it touches your own phone (Phase 6).
// Only your session answers; no answer is never a yes.
import { useState } from "react";
import { DeviceMobileIcon } from "@phosphor-icons/react";
import { Button, Card, RowIcon } from "@/components/ui";
import { post, Task } from "@/lib/api";

export default function PhoneAsk({ task }: { task: Task; large?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answer = (allow: boolean) => {
    setBusy(true);
    post(`/api/tasks/${task.id}/phone`, { allow }).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };
  // an app that blocks emulators has no emulator to fall back to
  const blocked = (task.detail ?? "").includes("blocks emulators");
  return (
    <Card tone="needs" className="p-4">
      <div className="flex items-start gap-3">
        <RowIcon icon={DeviceMobileIcon} tone="apricot" size={40} />
        <div className="min-w-0 flex-1">
          <div className="text-body font-bold">{task.detail ?? "Envoy wants to use your Android phone"}</div>
          <div className="mt-0.5 text-meta text-muted">{task.goal}</div>
        </div>
      </div>
      <p className="mt-3 text-meta text-ink-2">While it works, a banner on the phone says so. Touch the phone or press Pause there to take it back.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" disabled={busy} onClick={() => answer(true)}>Use my phone</Button>
        <Button disabled={busy} onClick={() => answer(false)}>{blocked ? "Not my phone" : "Use an emulator"}</Button>
      </div>
      {error && <p role="alert" className="mt-2 text-meta text-apricot-ink">{error}</p>}
    </Card>
  );
}
