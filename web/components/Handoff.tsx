"use client";

// Files from your Mac (backend/api/handoff.py): what's in Envoy's outbox folder and where each went. A new file asks
// first ("Put clip.mp4 on your Pixel 5?", an offer, answered on its card); a file waiting or one that didn't go can be
// sent from here. Nothing goes to your phone
// without your tap. The outbox folder is set in Settings › Phones.
import { useEffect, useState } from "react";
import { CheckCircleIcon, FileArrowUpIcon, FolderIcon, ImageIcon, QuestionIcon, VideoIcon, WarningIcon } from "@phosphor-icons/react";
import { Button, Card, Chip, Row, Section, SectionLabel } from "@/components/ui";
import { ago, api, HandoffItem, post } from "@/lib/api";

const STATUS: Record<string, { label: string; tone: "sage" | "apricot" | "neutral" }> = {
  waiting: { label: "Waiting", tone: "neutral" }, offered: { label: "Asked you", tone: "apricot" }, sent: { label: "On the phone", tone: "sage" },
  posted: { label: "Posted", tone: "sage" }, failed: { label: "Didn't go", tone: "apricot" },
};

export function Handoffs({ version = 0 }: { version?: number }) {
  const [items, setItems] = useState<HandoffItem[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api<{ items: HandoffItem[] }>("/api/handoff?limit=8").then((r) => setItems(r.items)).catch(() => setItems([]));
  useEffect(() => { load(); }, [version]);
  if (!items?.length) return null;
  const send = async (h: HandoffItem) => {
    setBusy(h.id);
    setError(null);
    try {
      const got = await post<HandoffItem>(`/api/handoff/${h.id}/send`);
      setItems((xs) => (xs ?? []).map((x) => (x.id === h.id ? got : x)));
      if (got.status === "failed") setError(got.error ?? "It didn't go to the phone");
    } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };
  return (
    <section aria-labelledby="files" className="ev-rise ev-r3">
      <SectionLabel id="files" className="px-6 pb-2.5 pt-6">From your Mac</SectionLabel>
      <Card className="mx-4 overflow-hidden">
        {items.map((h) => {
          const st = STATUS[h.status] ?? STATUS.waiting;
          const where = h.remote_path ? h.remote_path.replace(/^\/sdcard\//, "") : null;
          const meta = [h.device_name ? (h.status === "sent" || h.status === "posted" ? `${h.device_name} · ${where}` : `For ${h.device_name}`) : null,
            h.caption ? `“${h.caption.split("\n")[0]}”` : null, h.status === "failed" ? h.error : h.note, ago(h.updated_at)].filter(Boolean).join(" · ");
          return (
            <Row key={h.id} icon={h.kind === "video" ? VideoIcon : ImageIcon} tone={h.status === "failed" ? "apricot" : "sage"} title={h.name} meta={meta}
                 trailing={h.status === "waiting" || h.status === "failed"
                   ? <Button variant="sage" disabled={busy === h.id} onClick={() => send(h)}>{busy === h.id ? "Sending…" : h.status === "failed" ? "Try again" : "Send to phone"}</Button>
                   : <Chip tone={st.tone} icon={h.status === "offered" ? QuestionIcon : CheckCircleIcon}>{st.label}</Chip>} />
          );
        })}
      </Card>
      {error && <p role="alert" className="flex items-center gap-1.5 px-6 pt-2 text-meta-2 text-apricot-ink"><WarningIcon size={14} />{error}</p>}
    </section>
  );
}

export function Outbox() {
  const [folder, setFolder] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<{ outbox: string }>("/api/settings/handoff").then((r) => { setFolder(r.outbox); setDraft(r.outbox); }).catch(() => {}); }, []);
  if (folder === null) return null;
  const save = async () => {
    setError(null);
    try {
      const r = await post<{ outbox: string }>("/api/settings/handoff", { outbox: draft.trim() });
      setFolder(r.outbox); setDraft(r.outbox); setSaved("Saved");
    } catch (e: any) { setError(e.message); }
  };
  return (
    <Section title="Files from your Mac" intro={<>Put a photo or video in this folder (or ask Muse to) and Envoy asks whether to put it on your phone. A <code>clip.json</code> next to <code>clip.mp4</code> can name the app and the caption. Nothing goes to your phone until you say yes.</>}>
      <Card className="flex flex-col gap-3 px-4 py-4">
        <label className="flex items-center gap-2 text-meta font-semibold text-ink-2" htmlFor="outbox"><FolderIcon size={18} className="text-sage-ink" />Outbox folder</label>
        <div className="flex items-center gap-2">
          <input id="outbox" value={draft} onChange={(e) => { setDraft(e.target.value); setSaved(null); }} spellCheck={false}
                 className="h-11 min-w-0 flex-1 rounded-full border border-control bg-surface px-4 text-meta outline-none focus:border-sage" />
          <Button onClick={save} disabled={!draft.trim() || draft.trim() === folder}>Save</Button>
        </div>
        {(saved || error) && <p role="status" className={error ? "text-meta-2 text-apricot-ink" : "text-meta-2 text-sage-ink"}>{error ?? saved}</p>}
      </Card>
      <p className="flex items-center gap-1.5 px-2 text-meta-2 text-muted"><FileArrowUpIcon size={14} />Photos go to Pictures/Envoy, videos to Movies/Envoy, as the newest items in the phone&rsquo;s gallery.</p>
    </Section>
  );
}
