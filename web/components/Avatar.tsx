// Envoy's avatar: one face in seven moods, drawn exactly as on the approved canvas,
// cheeks included. SVG plus the CSS keyframes in globals.css; no motion under prefers-reduced-motion.
// The page picks the mood from real state (lib/mood.ts): offline, needs, listening, working, thinking, done, idle.

export type Mood = "idle" | "listening" | "thinking" | "working" | "needs" | "done" | "offline";

export const MOOD_LABEL: Record<Mood, string> = {
  idle: "Envoy is resting",
  listening: "Envoy is listening",
  thinking: "Envoy is thinking",
  working: "Envoy is working on your phone",
  needs: "Envoy needs you",
  done: "Envoy finished",
  offline: "Envoy can't reach your Mac",
};

const BODY = "M58 14C86 12 106 32 106 61C106 91 86 108 58 106C31 104 14 87 14 60C14 33 31 16 58 14Z";

const Cheeks = ({ r = 5.5, cy = 74, opacity = 0.55, one }: { r?: number; cy?: number; opacity?: number; one?: boolean }) => (
  <>
    <circle cx="35" cy={cy} r={r} fill="var(--apricot)" opacity={opacity} />
    {!one && <circle cx="85" cy={cy} r={r} fill="var(--apricot)" opacity={opacity} />}
  </>
);
const Eyes = ({ rx = 5.5, ry = 7.5, cy = 58 }: { rx?: number; ry?: number; cy?: number }) => (
  <>
    <ellipse className="ev-eye" cx="47" cy={cy} rx={rx} ry={ry} fill="var(--face)" />
    <ellipse className="ev-eye" cx="73" cy={cy} rx={rx} ry={ry} fill="var(--face)" />
  </>
);

function Face({ mood }: { mood: Mood }) {
  switch (mood) {
    case "listening":
      return (
        <>
          <circle className="ev-ring" cx="60" cy="60" r="50" />
          <circle className="ev-ring ev-late" cx="60" cy="60" r="50" />
          <g className="ev-body"><path d={BODY} fill="var(--sage)" /><Cheeks /><Eyes rx={6} ry={9} cy={57} /></g>
        </>
      );
    case "thinking":
      return (
        <>
          <g className="ev-body"><path d={BODY} fill="var(--sage)" /><Cheeks /><g transform="translate(3 -4)"><Eyes /></g></g>
          <circle className="ev-dot" cx="86" cy="6" r="4" fill="var(--sage)" />
          <circle className="ev-dot ev-d2" cx="98" cy="2" r="4" fill="var(--sage)" />
          <circle className="ev-dot ev-d3" cx="110" cy="-1" r="4" fill="var(--sage)" />
        </>
      );
    case "working":
      return (
        <>
          <g className="ev-body"><path d={BODY} fill="var(--sage)" /><Cheeks one /><g transform="translate(4 5)"><Eyes /></g></g>
          <rect className="ev-phone" x="84" y="64" width="30" height="48" rx="7" />
          <rect x="90" y="72" width="18" height="3.5" rx="1.75" fill="var(--phone-line)" />
          <rect x="90" y="79" width="12" height="3.5" rx="1.75" fill="var(--phone-line)" />
          <circle className="ev-tap" cx="99" cy="96" r="5" />
          <circle cx="99" cy="96" r="2.5" fill="var(--sage)" />
        </>
      );
    case "needs":
      return (
        <>
          <circle className="ev-halo" cx="60" cy="60" r="54" fill="var(--apricot)" />
          <g className="ev-body">
            <path d={BODY} fill="var(--sage)" /><Cheeks />
            <path className="ev-line" d="M40 44q7-5 14 0" /><path className="ev-line" d="M66 44q7-5 14 0" />
            <Eyes rx={6} ry={8.5} />
          </g>
        </>
      );
    case "done":
      return (
        <>
          <g className="ev-body">
            <path d={BODY} fill="var(--sage)" /><Cheeks r={6} cy={73} opacity={0.8} />
            <path className="ev-line" d="M41 61q6-8 12 0" /><path className="ev-line" d="M67 61q6-8 12 0" />
          </g>
          <g className="ev-pop"><circle cx="102" cy="22" r="14" fill="var(--ink)" /><path className="ev-check" d="M95.5 22.5l4.5 4.5 8-9" /></g>
        </>
      );
    case "offline":
      return (
        <>
          <g className="ev-slow"><path d={BODY} fill="var(--offline)" /><path className="ev-line" d="M41 61h12" /><path className="ev-line" d="M67 61h12" /></g>
          <text className="ev-z" x="98" y="24">z</text>
          <text className="ev-z ev-z2" x="110" y="10">z</text>
        </>
      );
    default:
      return <g className="ev-body"><path d={BODY} fill="var(--sage)" /><Cheeks /><Eyes /></g>;
  }
}

// `label`: say the mood to screen readers (when no text nearby says it); otherwise the avatar is decoration.
export default function Avatar({ mood = "idle", size = 44, label, className = "" }: { mood?: Mood; size?: number; label?: boolean; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="-12 -12 144 144" className={`shrink-0 overflow-visible ${className}`}
         {...(label ? { role: "img", "aria-label": MOOD_LABEL[mood] } : { "aria-hidden": true })}>
      <Face mood={mood} />
    </svg>
  );
}

// The mark: the avatar's resting face on a sage tile (the Home Screen icon), or the bare face beside the wordmark.
export function Mark({ size = 34, tile = false }: { size?: number; tile?: boolean }) {
  if (tile) {
    return (
      <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden className="shrink-0">
        <rect width="120" height="120" rx="28" fill="var(--sage)" />
        <g transform="translate(19 19) scale(0.68)">
          <path d={BODY} fill="var(--face)" />
          <ellipse cx="47" cy="58" rx="6" ry="8" fill="var(--sage)" /><ellipse cx="73" cy="58" rx="6" ry="8" fill="var(--sage)" />
        </g>
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="8 8 104 104" aria-hidden className="shrink-0">
      <g className="ev-body">
        <path d={BODY} fill="var(--sage)" />
        <ellipse className="ev-eye" cx="47" cy="58" rx="6" ry="8" fill="var(--face)" /><ellipse className="ev-eye" cx="73" cy="58" rx="6" ry="8" fill="var(--face)" />
      </g>
    </svg>
  );
}

export function Wordmark({ size = 24 }: { size?: number }) {
  return <span className="font-serif font-medium tracking-[-0.02em]" style={{ fontSize: size, lineHeight: 1 }}>envoy</span>;
}
