"use client";

// The few shared pieces every screen is built from: buttons, cards, chips, list rows, section labels, a segmented
// control, the step marks. Tokens only (globals.css); every touch target is at least 44px.
import type { ButtonHTMLAttributes, ReactNode } from "react";
import {
  AirplaneTiltIcon, CoffeeIcon, DeviceMobileIcon, ForkKnifeIcon, PackageIcon, ShoppingBagIcon, type Icon,
} from "@phosphor-icons/react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "sage" | "secondary" | "ghost";
const VARIANT: Record<Variant, string> = {
  primary: "bg-ink text-on-ink hover:bg-ink/90",
  sage: "bg-sage text-white hover:bg-sage/90",
  secondary: "border border-control bg-surface text-ink hover:border-line-strong",
  ghost: "bg-transparent text-sage-ink hover:bg-sage-tint/60",
};

export function Button({ variant = "secondary", size = "md", className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "md" | "lg" }) {
  return (
    <button {...rest} className={cx("inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-bold transition-colors disabled:pointer-events-none disabled:opacity-50",
      size === "lg" ? "h-[52px] px-6 text-body" : "h-11 px-4 text-[14px]", VARIANT[variant], className)}>
      {children}
    </button>
  );
}

export function IconButton({ label, variant = "plain", className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string; variant?: "plain" | "sage" | "ink" | "surface" }) {
  return (
    <button {...rest} aria-label={label} title={label}
            className={cx("inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-50",
              variant === "sage" ? "bg-sage text-white hover:bg-sage/90" : variant === "ink" ? "bg-ink text-on-ink hover:bg-ink/90" : variant === "surface" ? "border border-control bg-surface text-ink" : "text-ink hover:bg-well", className)}>
      {children}
    </button>
  );
}

export function Card({ tone, className, children, ...rest }: { tone?: "needs"; className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return <div {...rest} className={cx("rounded-card border bg-surface", tone === "needs" ? "border-apricot-line" : "border-line", className)}>{children}</div>;
}

type Tone = "sage" | "apricot" | "neutral";
const TONE: Record<Tone, string> = {
  sage: "bg-sage-tint text-sage-ink",
  apricot: "bg-apricot-tint text-apricot-ink",
  neutral: "bg-well text-ink-2",
};

export function Chip({ tone = "sage", icon: I, className, children }: { tone?: Tone; icon?: Icon; className?: string; children: ReactNode }) {
  return (
    <span className={cx("inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-1 text-meta-2 font-semibold", TONE[tone], className)}>
      {I && <I size={14} className="shrink-0" />}<span className="truncate">{children}</span>
    </span>
  );
}

export function RowIcon({ icon: I, tone = "sage", size = 36 }: { icon: Icon; tone?: Tone; size?: number }) {
  return (
    <span className={cx("flex shrink-0 items-center justify-center rounded-full", TONE[tone])} style={{ width: size, height: size }}>
      <I size={Math.round(size / 2)} />
    </span>
  );
}

// A row in a list card. Clickable when given onClick (a real button); the last row has no divider.
export function Row({ icon, tone, title, meta, trailing, onClick, className }: {
  icon?: Icon; tone?: Tone; title: ReactNode; meta?: ReactNode; trailing?: ReactNode; onClick?: () => void; className?: string;
}) {
  const body = (
    <>
      {icon && <RowIcon icon={icon} tone={tone} />}
      <span className="min-w-0 flex-1">
        <span className="block text-row font-semibold [overflow-wrap:anywhere]">{title}</span>
        {meta && <span className="mt-0.5 block text-meta-2 text-muted [overflow-wrap:anywhere]">{meta}</span>}
      </span>
      {trailing}
    </>
  );
  const cls = cx("flex min-h-[60px] w-full items-center gap-3 border-b border-divider px-4 py-3 text-left last:border-b-0", className);
  return onClick
    ? <button onClick={onClick} className={cx(cls, "transition-colors hover:bg-raised")}>{body}</button>
    : <div className={cls}>{body}</div>;
}

export function SectionLabel({ children, className, id }: { children: ReactNode; className?: string; id?: string }) {
  return <h2 id={id} className={cx("text-meta font-bold text-muted", className)}>{children}</h2>;
}

// A settings section: a title, a line or two about it, then its cards.
export function Section({ title, children, intro }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <section className="px-4 pt-6">
      <h2 className="px-2 text-title font-bold">{title}</h2>
      {intro && <div className="mt-1 px-2 text-meta text-ink-2">{intro}</div>}
      <div className="mt-3 flex flex-col gap-3">{children}</div>
    </section>
  );
}

export function Segmented<T extends string>({ options, value, onChange, label }: { options: readonly T[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-full bg-well p-1">
      {options.map((o) => (
        <button key={o} aria-pressed={value === o} onClick={() => onChange(o)}
                className={cx("h-9 min-w-[44px] rounded-full px-3 text-meta font-bold transition-colors md:px-4",
                  value === o ? "bg-surface text-ink shadow-[0_1px_2px_rgba(31,42,36,0.08)]" : "text-muted hover:text-ink")}>
          {o}
        </button>
      ))}
    </div>
  );
}

// ---- the step marks (the task timeline) ----

export function Done({ size = 24 }: { size?: number }) {
  return (
    <span className="flex shrink-0 items-center justify-center rounded-full bg-sage text-white" style={{ width: size, height: size }}>
      <svg width={size * 0.54} height={size * 0.54} viewBox="0 0 24 24" aria-hidden fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
    </span>
  );
}

export function Spinner({ size = 24, stroke = 3 }: { size?: number; stroke?: number }) {
  const r = 12 - stroke / 2 - 0.5;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden className="shrink-0">
      <circle cx="12" cy="12" r={r} fill="none" stroke="var(--sage-tint)" strokeWidth={stroke} />
      <path className="ev-spin" d={`M12 ${12 - r}a${r} ${r} 0 0 1 ${r} ${r}`} fill="none" stroke="var(--sage)" strokeWidth={stroke} strokeLinecap="round" />
    </svg>
  );
}

// An app's icon in rows and cards, by what the app is for.
const APP_ICON: Record<string, Icon> = {
  "com.skylark.air": AirplaneTiltIcon, "com.dd.doordash": ForkKnifeIcon, "com.chipotle.ordering": ForkKnifeIcon,
  "com.amazon.mShop.android.shopping": PackageIcon, "com.target.ui": ShoppingBagIcon, "com.starbucks.mobilecard": CoffeeIcon,
};
export const appIcon = (pkg?: string | null): Icon => (pkg && APP_ICON[pkg]) || DeviceMobileIcon;

// A short time: "6:12 PM" today, "Tue 6:12 PM" this week, "Oct 21" before that.
export function clock(t: number): string {
  const d = new Date(t * 1000), now = new Date();
  const hm = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (d.toDateString() === now.toDateString()) return hm;
  if (now.getTime() - d.getTime() < 6 * 86400e3) return `${d.toLocaleDateString(undefined, { weekday: "short" })} ${hm}`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export const sentence = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
// A routine step's id ("add_pad_thai_medium") as words.
export const words = (id: string) => sentence(id.replace(/_/g, " "));
