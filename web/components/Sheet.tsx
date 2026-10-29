"use client";

// A sheet: from the bottom on a phone (28px top corners, a grabber), a centered dialog on a wider screen. Escape and the
// scrim close it when it can be closed; focus moves in when it opens and back when it closes.
import { ReactNode, useEffect, useRef } from "react";
import { cx } from "@/components/ui";

export default function Sheet({ label, onClose, children, wide }: { label: string; onClose?: () => void; children: ReactNode; wide?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const first = box.current?.querySelector<HTMLElement>("[data-autofocus], button, a[href], input");
    (first ?? box.current)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && close.current) { e.preventDefault(); close.current(); }
      if (e.key === "Tab" && box.current) {  // keep Tab inside the sheet
        const all = [...box.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input, select, textarea, [tabindex='0']")];
        if (!all.length) return;
        const [a, z] = [all[0], all[all.length - 1]];
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
        else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; before?.focus?.(); };
  }, []);

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center md:items-center md:p-6">
      <div className="ev-scrim absolute inset-0 bg-scrim" onClick={onClose} aria-hidden />
      <div ref={box} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}
           className={cx("ev-sheet relative flex max-h-[calc(100dvh-48px)] w-full flex-col overflow-y-auto rounded-t-sheet bg-raised px-5 pb-[max(24px,env(safe-area-inset-bottom))] pt-2.5 shadow-sheet outline-none",
             "md:max-h-[calc(100dvh-48px)] md:rounded-sheet md:px-7 md:pb-7 md:pt-7 md:shadow-dialog", wide ? "md:max-w-[560px]" : "md:max-w-[480px]")}>
        <div aria-hidden className="mx-auto mb-4 h-[5px] w-10 shrink-0 rounded-full bg-line-strong md:hidden" />
        {children}
      </div>
    </div>
  );
}
