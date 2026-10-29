"use client";

// Mock mode (`?mock=1`, or NEXT_PUBLIC_ENVOY_MOCK=1): the API and the event stream are answered here, in the page, from
// fixtures that cover every state, so each screen can be designed, checked and captured without a Mac, a phone or a
// model. Nothing in this file touches the network. Scenarios (`?mock=<name>`):
// - `1` / `full`: a task streaming steps, a payment waiting for your OK, a phone ask, an offer ("Check in for SL 482?")
//   with its "Before I start" lines, a habit Envoy noticed ("Make this a habit?"), a filled memory, routines, triggers
//   (one asks first, one weekly), past offers in each state, and files from the Mac: one Envoy is asking about
//   ("Put pier-sunset.mp4 on your Pixel 5 and post it to Instagram?"), one waiting, one on the phone, one posted, one
//   that didn't go
// - `quiet`: nothing needs you; a watcher reruns the gate routine every so often (working, thinking, done)
// - `idle`: nothing running and nothing waiting
// - `offline`: the event stream never connects, and Home can't load its briefing
// - `pair`: a device that isn't paired yet (the pairing screen)
// `?mock=0` turns it off again (it's kept for the tab's session, so /approve links stay in mock mode).
import type { Approval, EnvoyEvent, HandoffItem, Lease, Step, Task } from "@/lib/api";

export type Scenario = "full" | "quiet" | "idle" | "offline" | "pair";

const T = Date.now() / 1000;
const now = () => Date.now() / 1000;
const ago = (s: number) => T - s;
const midnight = new Date(new Date().setHours(0, 0, 0, 0)).getTime() / 1000;
const todayAt = (h: number, m = 0) => midnight + h * 3600 + m * 60;
// "Today" in the fixtures: since midnight, or the last 18 hours when it's early in the morning, so Home always has a day.
const dayStart = Math.min(midnight, T - 18 * 3600);
const earlier = (h: number, m: number, fallback: number) => (todayAt(h, m) < T - 600 ? todayAt(h, m) : ago(fallback));
const fmtDay = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });

let scenario: Scenario = "full";
const listeners = new Set<(e: EnvoyEvent) => void>();
let seq = 1000;
const emit = (type: string, body: Record<string, unknown>) => {
  const e = { seq: ++seq, time: now(), type, ...body } as EnvoyEvent;
  listeners.forEach((fn) => fn(e));
};

// ---- the phone screens (placeholders: an app's header, a few rows, the button Envoy is about to press) ----------------

const APP_LOOK: Record<string, { name: string; color: string }> = {
  "com.dd.doordash": { name: "DoorDash", color: "#E8573A" },
  "com.skylark.air": { name: "SkyLark", color: "#2F5DA8" },
  "com.amazon.mShop.android.shopping": { name: "Amazon", color: "#232F3E" },
  "com.starbucks.mobilecard": { name: "Starbucks", color: "#1E6B4F" },
  "com.target.ui": { name: "Target", color: "#C4262E" },
};

function screen(app: string, title: string, rows: string[], button?: string): string {
  const look = APP_LOOK[app] ?? { name: "App", color: "#4E5A53" };
  const row = (t: string, i: number) =>
    `<rect x="24" y="${236 + i * 92}" width="492" height="76" rx="14" fill="#F4F2EE"/>` +
    `<rect x="40" y="${252 + i * 92}" width="44" height="44" rx="10" fill="#E2DED6"/>` +
    `<text x="100" y="${280 + i * 92}" font-family="system-ui,sans-serif" font-size="22" fill="#2A2A2A">${t}</text>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="540" height="1200" viewBox="0 0 540 1200">
<rect width="540" height="1200" fill="#FFFFFF"/>
<rect width="540" height="44" fill="#F6F6F6"/><text x="24" y="30" font-family="system-ui,sans-serif" font-size="18" fill="#555">7:41</text>
<rect y="44" width="540" height="120" fill="${look.color}"/>
<text x="24" y="118" font-family="system-ui,sans-serif" font-weight="700" font-size="34" fill="#FFFFFF">${look.name}</text>
<text x="24" y="210" font-family="system-ui,sans-serif" font-weight="700" font-size="28" fill="#1A1A1A">${title}</text>
${rows.map(row).join("")}
${button ? `<rect x="24" y="1060" width="492" height="84" rx="42" fill="${look.color}"/><text x="270" y="1112" text-anchor="middle" font-family="system-ui,sans-serif" font-weight="700" font-size="28" fill="#FFFFFF">${button}</text>` : ""}
</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

const SHOTS: Record<string, string> = {
  "dd-1": screen("com.dd.doordash", "Your recent orders", ["Thai Basil · Oct 21", "Sushi Zen · Oct 14", "Taqueria Sol · Oct 9"]),
  "dd-2": screen("com.dd.doordash", "Thai Basil", ["Pad thai · $13.50", "Spring rolls · $6.00", "Green curry · $14.25"]),
  "dd-3": screen("com.dd.doordash", "Pad thai", ["Spice: medium", "No peanuts", "Quantity: 1"], "Add to cart"),
  "dd-4": screen("com.dd.doordash", "Checkout", ["Pad thai, medium, no peanuts", "Subtotal $13.50 · fees $1.92", "Tip $3.00 · total $18.42"], "Place order"),
  "sl-1": screen("com.skylark.air", "Your trips", ["Chicago · Fri, Oct 30", "Denver · Nov 12"]),
  "sl-2": screen("com.skylark.air", "Chicago · SL 482", ["Departs 6:05 AM", "Gate B22 (was B14)", "Seat 14C · Group 3"]),
  "amz-1": screen("com.amazon.mShop.android.shopping", "Your orders", ["AirPods Pro · arriving Thursday", "Phone case · delivered"]),
  "sb-1": screen("com.starbucks.mobilecard", "Order", ["Grande oat latte", "Pick up at 5th & Pine"], "Checkout"),
  "tgt-1": screen("com.target.ui", "AirPods Pro", ["$189.99 · in stock nearby"]),
};
export const liveFrame = (avd: string): string => (avd === "pixel-5" ? SHOTS["dd-4"] : SHOTS["sl-2"]);

// What an <img> shows for an API path in mock mode.
export function media(path: string): string {
  const key = (path.split("?")[0].split("/").pop() ?? "").replace(/\.\w+$/, "");
  if (SHOTS[key]) return SHOTS[key];
  if (path.includes("/api/pair/qr")) return qr();
  if (path.includes("/history/")) return key === "before" ? SHOTS["sl-1"] : SHOTS["sl-2"];
  return path.includes("/api/approvals/") ? SHOTS["dd-4"] : SHOTS["sl-2"];
}

function qr(): string {
  let cells = "";
  const finder = (x: number, y: number) => `<path d="M${x} ${y}h7v7h-7zM${x + 1} ${y + 1}v5h5v-5zM${x + 2} ${y + 2}h3v3h-3z" fill-rule="evenodd"/>`;
  for (let y = 0; y < 21; y++) for (let x = 0; x < 21; x++) {
    const inFinder = (x < 8 && y < 8) || (x > 12 && y < 8) || (x < 8 && y > 12);
    if (!inFinder && (x * 7 + y * 13 + x * y) % 5 < 2) cells += `<rect x="${x}" y="${y}" width="1" height="1"/>`;
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 23 23"><rect x="-1" y="-1" width="23" height="23" fill="#fff"/><g fill="#1F2A24">${finder(0, 0)}${finder(14, 0)}${finder(0, 14)}${cells}</g></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// ---- the fixtures -----------------------------------------------------------------------------------------------------

type DB = {
  tasks: Record<string, Task>; steps: Record<string, Step[]>; approvals: Record<string, Approval & { nonce: string }>;
  leases: Record<string, Lease>; triggers: any[]; changes: any[]; rules: { default: string; apps: Record<string, string>; routines: Record<string, string> };
  photos: { enabled: boolean; scope: string }; phoneApps: string[]; notes: any[]; offers: any[]; proactivity: string;
  handoffs: HandoffItem[]; outbox: string;
};
let db: DB;

const task = (t: Partial<Task> & Pick<Task, "id" | "goal">): Task => ({
  source: "chat", status: "done", created_at: ago(3600), updated_at: ago(3590), model_calls: 0, cost_usd: 0, ...t,
});
const step = (n: number, s: Omit<Step, "seq" | "time"> & { time?: number }): Step => ({ seq: n, time: s.time ?? ago(100 - n * 10), ...s });

function seed(): DB {
  const tasks: Record<string, Task> = {};
  const steps: Record<string, Step[]> = {};
  const approvals: DB["approvals"] = {};
  const add = (t: Task, s: Step[] = []) => { tasks[t.id] = t; steps[t.id] = s; };

  if (scenario === "full" || scenario === "offline") {
    add(task({ id: "task-dd", goal: "Get my usual from Thai Basil on DoorDash", status: "waiting_approval", app: "com.dd.doordash", device: "pixel-5",
      kind: "routine", routine: "doordash_reorder_usual", inputs: { restaurant: "Thai Basil" }, created_at: ago(140), updated_at: ago(30),
      model_calls: 1, cost_usd: 0.002, waiting_for: "approval" }), [
      step(1, { kind: "preflight", time: ago(139), lines: [
        { kind: "device", text: "DoorDash is set to run on your phone: I'll ask before using your Pixel 5.", level: "warn" },
        { kind: "signin", text: "DoorDash asked you to sign in on your Pixel 5 last time (Oct 27).", level: "warn" },
        { kind: "approval", text: "The payment step will need your OK.", level: "info" },
        { kind: "routine", text: "Using routine doordash_reorder_usual v3: usually 41 s, about 1 model call.", level: "info" },
        { kind: "app_note", text: "From earlier runs: A pop-up offering DashPass can appear before checkout", level: "info" },
      ] }),
      step(2, { kind: "note", text: "using routine doordash_reorder_usual v3 with restaurant = Thai Basil", time: ago(138),
        sources: { usual_order: "Order Thai Basil usual (items): DoorDash app, Oct 21" } }),
      step(3, { kind: "routine_step", text: "open_recent_orders", status: "done", rung: 0, shot: "dd-1", time: ago(120) }),
      step(4, { kind: "routine_step", text: "find_thai_basil", status: "done", rung: 0, shot: "dd-2", time: ago(96) }),
      step(5, { kind: "routine_step", text: "add_pad_thai_medium_no_peanuts", status: "done", rung: 2, detail: "relaxed match: the button now says Add", shot: "dd-3", time: ago(70) }),
      step(6, { kind: "routine_step", text: "go_to_checkout", status: "running", rung: 0, shot: "dd-4", risk: "irreversible", time: ago(32) }),
    ]);
    approvals["appr-dd"] = { id: "appr-dd", task_id: "task-dd", created_at: ago(30), status: "pending", description: "Pay $18.42 at DoorDash",
      reasons: ["Order: Pad thai, medium, no peanuts", "From: Thai Basil", "Total: $18.42 with tip", "rule: it costs money"],
      app: "com.dd.doordash", screen: "Checkout", screenshot: "dd-4.jpg", nonce: "mock-nonce" };
    add(task({ id: "task-tgt", goal: "Check the price of AirPods Pro at Target", status: "needs_you", app: "com.target.ui", waiting_for: "phone",
      detail: "Target blocks emulators: use your Android phone for this task?", created_at: ago(400), updated_at: ago(380) }), [
      step(1, { kind: "preflight", time: ago(399), lines: [
        { kind: "device", text: "Target blocks emulators: I'll ask to use your Pixel 5.", level: "warn" },
        { kind: "app_note", text: "From earlier runs: A store must be chosen before prices show", level: "info" },
      ] }),
    ]);
  }
  // the task that streams (full: on load; quiet: a watcher every so often)
  add(task({ id: "task-amz", goal: "When does my Amazon package arrive?", app: "com.amazon.mShop.android.shopping", device: "envoy-test", kind: "agent",
    result: "Your AirPods Pro arrive Thursday", created_at: earlier(17, 29, 3 * 3600 + 60), updated_at: earlier(17, 30, 3 * 3600), model_calls: 6, cost_usd: 0.011 }), [
    step(1, { kind: "plan", text: "Open Your Orders; Read the delivery date of the newest order", time: earlier(17, 29, 3 * 3600 + 60) }),
    step(2, { kind: "action", text: 'tap "Your Orders"', reason: "The orders list has the delivery dates", risk: "read", shot: "amz-1", time: earlier(17, 29, 3 * 3600 + 40) }),
    step(3, { kind: "memory", text: "memory updated: 3 same, 1 replaced", entities: ["Order AirPods Pro"], time: earlier(17, 30, 3 * 3600) }),
    step(4, { kind: "finish", text: "Your AirPods Pro arrive Thursday", status: "done", time: earlier(17, 30, 3 * 3600) }),
  ]);
  add(task({ id: "task-sb", goal: "Order my morning coffee", source: "trigger:Morning coffee", app: "com.starbucks.mobilecard", device: "envoy-test",
    kind: "routine", routine: "starbucks_order_usual", result: "Ordered a grande oat latte for pickup at 5th & Pine", created_at: earlier(7, 30, 9 * 3600), updated_at: earlier(7, 30, 9 * 3600) + 9 }), [
    step(1, { kind: "note", text: "using routine starbucks_order_usual v2", time: earlier(7, 30, 9 * 3600) }),
    step(2, { kind: "routine_step", text: "open_order", status: "done", rung: 0, shot: "sb-1", time: earlier(7, 30, 9 * 3600) + 3 }),
    step(3, { kind: "approval", text: "Checkout: done without asking (standing approval)", reason: "you set routine starbucks_order_usual to run without asking", time: earlier(7, 30, 9 * 3600) + 7 }),
    step(4, { kind: "finish", text: "all steps and checks passed", status: "done", time: earlier(7, 30, 9 * 3600) + 9 }),
  ]);
  add(task({ id: "task-cmp", goal: "Is AirPods Pro cheaper at Amazon or Target?", kind: "crossapp", result: "Amazon: $179.99 · Target: $189.99",
    detail: "Amazon is $10 cheaper", created_at: ago(86400 + 4000), updated_at: ago(86400 + 3900), model_calls: 4, cost_usd: 0.009 }));
  add(task({ id: "task-cmp-a", goal: "Price of AirPods Pro at Amazon", parent: "task-cmp", app: "com.amazon.mShop.android.shopping", device: "envoy-test",
    result: "$179.99", created_at: ago(86400 + 3990), updated_at: ago(86400 + 3950) }));
  add(task({ id: "task-cmp-t", goal: "Price of AirPods Pro at Target", parent: "task-cmp", app: "com.target.ui", device: "pixel-5",
    result: "$189.99", created_at: ago(86400 + 3990), updated_at: ago(86400 + 3920) }));
  add(task({ id: "task-ck", goal: "Check me in for my flight", app: "com.skylark.air", device: "envoy-test", kind: "routine", routine: "skylark_check_in_flight",
    status: "declined", detail: "you declined Confirm check-in", created_at: ago(2 * 86400), updated_at: ago(2 * 86400 - 40) }), [
    step(1, { kind: "preflight", time: ago(2 * 86400), lines: [
      { kind: "approval", text: "Confirming check-in will need your OK.", level: "info" },
      { kind: "routine", text: "Using routine skylark_check_in_flight v1: usually 9 s, no model calls.", level: "info" },
    ] }),
    step(2, { kind: "note", text: "using routine skylark_check_in_flight v1 with trip_city = Chicago", time: ago(2 * 86400 - 1) }),
    step(3, { kind: "routine_step", text: "open_trips", status: "done", rung: 0, shot: "sl-1", time: ago(2 * 86400 - 6) }),
    step(4, { kind: "routine_step", text: "confirm_check_in", status: "failed", rung: 0, detail: "you declined it", risk: "irreversible", time: ago(2 * 86400 - 40) }),
  ]);
  add(task({ id: "task-siri", goal: "Check me in for my flight", source: "siri", request: "Check me in for my flight", app: "com.skylark.air",
    device: "envoy-test", kind: "routine", routine: "skylark_check_in_flight", status: "declined", detail: "you declined Confirm check-in",
    created_at: ago(26 * 60), updated_at: ago(25 * 60), model_calls: 2, cost_usd: 0.003 }), [
    step(1, { kind: "preflight", time: ago(26 * 60 - 3), lines: [
      { kind: "approval", text: "Confirming check-in will wait for your OK.", level: "info" },
      { kind: "routine", text: "Using routine skylark_check_in_flight v1: usually 9 s, no model calls.", level: "info" },
    ] }),
    step(2, { kind: "note", text: "using routine skylark_check_in_flight v1 with trip_city = Chicago", time: ago(26 * 60 - 4) }),
    step(3, { kind: "routine_step", text: "open_trips", status: "done", rung: 0, shot: "sl-1", time: ago(26 * 60 - 9) }),
    step(4, { kind: "routine_step", text: "confirm_check_in", status: "failed", rung: 0, detail: "you declined it", risk: "irreversible", time: ago(25 * 60) }),
  ]);
  add(task({ id: "task-chase", goal: "What's my checking balance in Chase?", app: "com.chase.sig.android", status: "failed",
    detail: "Chase blocks emulators; it needs a real Android phone. Connect your Android phone (USB, or wireless debugging) and ask again.",
    created_at: ago(2 * 86400 + 600), updated_at: ago(2 * 86400 + 598) }), [
    step(1, { kind: "preflight", time: ago(2 * 86400 + 599), lines: [
      { kind: "blocked", text: "Chase needs your Android phone, and it isn't connected.", level: "stop" },
      { kind: "signin", text: "Chase asked you to sign in on your Pixel 5 last time (Oct 24).", level: "warn" },
    ] }),
    step(2, { kind: "error", text: "Chase blocks emulators; it needs a real Android phone. Connect your Android phone (USB, or wireless debugging) and ask again.", time: ago(2 * 86400 + 598) }),
  ]);
  add(task({ id: "task-old", goal: "What's my seat on the Chicago flight?", status: "failed", detail: "envoy-test is not running",
    created_at: ago(3 * 86400), updated_at: ago(3 * 86400 - 5) }));

  const leases: Record<string, Lease> = {
    "envoy-test": { avd: "envoy-test", task_id: null, user_control: false, since: 0, reason: "", running: true, kind: "emulator", name: "Pixel 8 emulator" },
    "pixel-5": { avd: "pixel-5", task_id: scenario === "full" || scenario === "offline" ? "task-dd" : null, user_control: false, since: ago(140), reason: "",
      running: true, kind: "phone", name: "Pixel 5", android: "13", state: "device" },
  };
  const triggers = [
    { id: "trig-gate", kind: "watch", name: "Watch my gate", spec: { every_minutes: 10, alert: true }, action: { routine: "skylark_get_flight_gate", inputs_from: {} },
      enabled: true, last_fired: ago(420), next: [{ at: ago(420) + 600 }], alerts: { on: true, attributes: ["gate"] } },
    { id: "trig-checkin", kind: "before_fact", name: "Ask me to check in when check-in opens", spec: { entity_type: "Flight", date_attr: "date", time_attr: "depart_time", minutes_before: 1440 },
      action: { goal: "Check me in for my flight {number} to {trip.destination}", routine: "skylark_check_in_flight", inputs_from: { trip_city: "trip.destination" },
        ask: true, offer_title: "Check in for {number}?" }, enabled: true, last_fired: ago(1500),
      next: [{ at: todayAt(21) > T ? todayAt(21) : todayAt(33), for: "SL 1190" }], alerts: { on: false, attributes: ["*"] } },
    { id: "trig-coffee", kind: "time", name: "Morning coffee", spec: { daily_at: "7:30" }, action: { routine: "starbucks_order_usual", inputs_from: {} },
      enabled: true, last_fired: earlier(7, 30, 9 * 3600), next: [{ at: todayAt(31, 30) > T + 86400 ? todayAt(7, 30) : todayAt(31, 30) }], alerts: { on: false, attributes: ["*"] } },
    { id: "trig-dep", kind: "fact_changed", name: "Departure changed: look up the gate", spec: { entity_type: "Flight", attributes: ["depart_time"] },
      action: { routine: "skylark_get_flight_gate", inputs_from: { trip_city: "trip.destination" } }, enabled: false, last_fired: null, next: [],
      alerts: { on: false, attributes: ["*"] } },
  ];
  const changes = [
    { id: 41, time: todayAt(18, 12) > T ? ago(1800) : todayAt(18, 12), task_id: "task-gate-0", entity_label: "Flight SL 482", attribute: "gate", old: "B14", new: "B22",
      title: "Gate changed: B14 → B22", pushed: 1, why_not: null, source: "SkyLark" },
    { id: 38, time: ago(86400 + 2000), task_id: "task-gate-0", entity_label: "Flight SL 482", attribute: "boarding_group", old: "3", new: "Group 3",
      title: "Boarding group changed: 3 → Group 3", pushed: 0, why_not: "you started this task", source: "SkyLark" },
  ];
  // Offers: one waiting (with its "Before I start" lines), a habit, and one of each answer in the history.
  const lastMondays = [3, 2, 1].map((w) => { const d = new Date(T * 1000); d.setDate(d.getDate() - ((d.getDay() + 6) % 7 || 7) - (w - 1) * 7); d.setHours(8, 0, 0, 0); return d.getTime() / 1000; });
  const checkIn = { type: "task", goal: "Check me in for my flight SL 482 to Chicago", request: "Check me in for my flight to", routine: "skylark_check_in_flight",
    inputs: { trip_city: "Chicago" }, app: null };
  const offer = (o: any) => ({ source: "trigger:Ask me to check in when check-in opens", expires_at: null, decided_at: null, decided_by: null, task_id: null,
    preflight: [], origin: { trigger_id: "trig-checkin" }, note: null, result: null, kind: "trigger", ...o });
  // Files from the Mac (api/handoff.py), and the offer the newest one raised.
  const full = scenario === "full" || scenario === "offline";
  const file = (h: Partial<HandoffItem> & Pick<HandoffItem, "id" | "name">): HandoffItem => ({ size: 18_400_000, kind: "video", app: null, caption: null,
    status: "waiting", device: "envoy-test", device_name: "Test phone", remote_path: null, media_uri: null, offer_id: null, task_id: null,
    created_at: ago(600), updated_at: ago(600), error: null, note: null, origin: "outbox", ...h });
  const handoffs = full ? [
    file({ id: "handoff-pier", name: "pier-sunset.mp4", app: "instagram", caption: "Golden hour at the pier 🌅\nShot on the 14th", status: "offered",
      device: "pixel-5", device_name: "Pixel 5", offer_id: "offer-clip", created_at: ago(240), updated_at: ago(238) }),
    file({ id: "handoff-listing", name: "listing-412-elm.jpg", kind: "image", size: 2_300_000, created_at: ago(3 * 3600), updated_at: ago(3 * 3600),
      note: "you said not now" }),
    file({ id: "handoff-pass", name: "boarding-pass.png", kind: "image", size: 640_000, status: "sent", remote_path: "/sdcard/Pictures/Envoy/boarding-pass.png",
      media_uri: "content://media/external/images/media/1000000021", created_at: ago(26 * 3600), updated_at: ago(26 * 3600), origin: "mcp" }),
    file({ id: "handoff-teaser", name: "teaser.mp4", app: "instagram", caption: "New week, new walk", status: "posted", device: "pixel-5", device_name: "Pixel 5",
      remote_path: "/sdcard/Movies/Envoy/teaser.mp4", task_id: "task-ig-1", created_at: ago(2 * 86400), updated_at: ago(2 * 86400 - 300) }),
    file({ id: "handoff-big", name: "full-cut-4k.mov", size: 2_100_000_000, status: "failed", error: "full-cut-4k.mov is over 500 MB",
      created_at: ago(3 * 86400), updated_at: ago(3 * 86400) }),
  ] : [];
  const offers = [
    ...(full ? [offer({ id: "offer-clip", kind: "handoff", source: "outbox", origin: null, created_at: ago(238), status: "pending",
      title: "Put pier-sunset.mp4 on your Pixel 5 and post it to Instagram?", body: "Golden hour at the pier 🌅",
      action: { type: "handoff", handoff_id: "handoff-pier", file: "pier-sunset.mp4", device: "pixel-5", then: {
        goal: "Post the newest video in my phone's gallery to Instagram as a reel with this caption: \"Golden hour at the pier 🌅 Shot on the 14th\"",
        request: "the newest video in my phone's gallery to Instagram as a reel with this caption", app: "com.instagram.android",
        inputs: { caption: "Golden hour at the pier 🌅\nShot on the 14th" } } },
      preflight: [{ kind: "device", text: "On your Pixel 5 (Instagram is set to your phone)", level: "info" },
        { kind: "approval", text: "Sharing the reel will wait for your OK", level: "info" }] }),
      offer({ id: "offer-muse", kind: "trigger_request", source: "mcp", origin: null, created_at: ago(5 * 3600), status: "accepted", decided_at: ago(5 * 3600 - 120),
        decided_by: "you", title: "Muse wants to set this up: every day at 08:00, \"Check my gate for today's flight\". Turn it on?",
        body: "Each time it fires, Envoy asks you before it does anything. Asked through Envoy's connector by Muse.",
        action: { type: "enable_trigger", trigger_id: "trig-gate-am" }, result: { trigger_id: "trig-gate-am" } })] : []),
    ...(scenario === "full" || scenario === "offline" ? [offer({ id: "offer-ck", created_at: ago(1500), title: "Check in for SL 482?", status: "pending",
      body: "From your trigger “Ask me to check in when check-in opens”, which asks you first.", action: checkIn, key: "trig-checkin:flight@1",
      expires_at: todayAt(30, 10) > T ? todayAt(30, 10) : T + 18 * 3600, preflight: [
        { kind: "device", text: "On the Pixel 8 emulator, where SkyLark runs", level: "info" },
        { kind: "routine", text: "From your routine: check-in took 21 s the last 4 times, no model calls", level: "info" },
        { kind: "approval", text: "Confirming check-in will go ahead: you asked for it", level: "info" },
        { kind: "signin", text: "SkyLark signed you out 2 days ago: you may need to sign in", level: "warn" },
      ] })] : []),
    ...(scenario === "full" || scenario === "offline" ? [offer({ id: "offer-habit", kind: "repeat", created_at: ago(5400), title: "Make this a habit?", status: "pending",
      source: "repeats", origin: null, key: "repeat:mock",
      body: `You asked me to check the status of your flight SL 1190 on your last 3 Mondays (${lastMondays.map(fmtDay).join(", ").replace(/, ([^,]*)$/, " and $1")}), around 8:00 AM.`,
      action: { type: "create_trigger", kind: "time", name: "Every Monday at 8:00 AM: check the status of your flight SL 1190",
        spec: { weekly_on: { days: ["mon"], at: "08:00" } }, pattern: "weekly", evidence: lastMondays.map(fmtDay),
        action: { goal: "Check the status of my flight SL 1190", routine: "skylark_check_flight_status", inputs: { flight_number: "SL 1190" }, ask: true },
        summary: "Every Monday at 8:00 AM, I'll ask you: “Should I check the status of your flight SL 1190?”", setup: "asks you every Monday at 8:00 AM" } })] : []),
    offer({ id: "offer-ck-old", created_at: ago(2 * 86400 + 600), title: "Check in for SL 1213?", status: "accepted", decided_at: ago(2 * 86400 + 300), decided_by: "you on Maya's iPhone",
      task_id: "task-ck", body: "From your trigger “Ask me to check in when check-in opens”, which asks you first.",
      action: { ...checkIn, goal: "Check me in for my flight SL 1213 to Louisville", inputs: { trip_city: "Louisville" } } }),
    offer({ id: "offer-chat-thai", kind: "trigger_request", created_at: ago(3 * 86400 + 900), title: "Set this up? Every Friday at 6:00 PM: order your usual from Thai Basil",
      status: "accepted", decided_at: ago(3 * 86400 + 840), decided_by: "you", source: "chat", origin: null,
      body: "It stays off until you say yes, and each time it runs I'll ask you first.",
      action: { type: "enable_trigger", trigger_id: "trig-thai", summary: "Every Friday at 6:00 PM, I'll ask you: “Should I order your usual from Thai Basil?”",
        setup: "asks you every Friday at 6:00 PM" }, result: { trigger_id: "trig-thai" } }),
    offer({ id: "offer-recap", kind: "handoff", created_at: ago(5 * 3600), title: "Send trip-recap.mp4 to your Pixel 5?", status: "withdrawn",
      decided_at: ago(5 * 3600 - 43), decided_by: "envoy", note: "Muse already sent it to your phone", source: "handoff", origin: null,
      body: "A video from your Mac's Envoy Outbox.", action: { type: "handoff", file: "trip-recap.mp4", device: "phone-pixel5", then: null } }),
    offer({ id: "offer-coffee", created_at: earlier(7, 30, 9 * 3600) - 86400, title: "Should I order your morning coffee?", status: "declined", decided_at: earlier(7, 32, 9 * 3600) - 86400,
      decided_by: "you", body: "From your trigger “Morning coffee”, which asks you first.", source: "trigger:Morning coffee", origin: { trigger_id: "trig-coffee" },
      action: { type: "task", goal: "Order my morning coffee", request: "Order my morning coffee", routine: "starbucks_order_usual", inputs: {} } }),
    offer({ id: "offer-seat", created_at: ago(3 * 86400), title: "Check in for SL 1585?", status: "expired", decided_at: ago(3 * 86400 - 7200), decided_by: "time",
      body: "From your trigger “Ask me to check in when check-in opens”, which asks you first.",
      action: { ...checkIn, goal: "Check me in for my flight SL 1585 to Savannah", inputs: { trip_city: "Savannah" } } }),
  ];
  return {
    tasks, steps, approvals, leases, triggers, changes, offers, proactivity: "important", handoffs, outbox: "/Users/maya/Envoy Outbox",
    rules: { default: "unless_requested", apps: { "com.dd.doordash": "always" }, routines: { starbucks_order_usual: "never" } },
    photos: { enabled: true, scope: "screenshots" }, phoneApps: ["com.target.ui"],
    notes: [
      { id: "note-1", app: "com.skylark.air", text: "A SkyLark Miles promo can cover the trip list; Not now closes it.", status: "active", confirmations: 4,
        first_seen: ago(5 * 86400), last_confirmed: ago(7200), sources: [{ task_id: "task-amz", step: 2, kind: "routine" }] },
      { id: "note-2", app: "com.skylark.air", text: "The gate shows on the trip's details, not on the trip list.", status: "active", confirmations: 7,
        first_seen: ago(6 * 86400), last_confirmed: ago(3600), sources: [{ task_id: "task-amz", step: 3, kind: "agent" }] },
      { id: "note-3", app: "com.dd.doordash", text: "Reorder lives under Orders, not on the restaurant's page.", status: "active", confirmations: 2,
        first_seen: ago(8 * 86400), last_confirmed: ago(140), sources: [{ task_id: "task-dd", step: 2, kind: "agent" }] },
    ],
  };
}

// ---- memory -------------------------------------------------------------------------------------------------------------

type MemNode = { id: string; type: string; name: string; facts: number; stale: boolean; user_edited: boolean };
const NODES: MemNode[] = [
  { id: "person-maya", type: "Person", name: "Maya Patel", facts: 4, stale: false, user_edited: false },
  { id: "trip-chi", type: "Trip", name: "Chicago · Fri, Oct 30", facts: 5, stale: false, user_edited: false },
  { id: "flight-482", type: "Flight", name: "SL 482 · Fri, Oct 30", facts: 7, stale: false, user_edited: false },
  { id: "trip-den", type: "Trip", name: "Denver · Nov 12", facts: 3, stale: true, user_edited: false },
  { id: "flight-910", type: "Flight", name: "SL 910 · Nov 12", facts: 4, stale: true, user_edited: false },
  { id: "res-hotel", type: "Reservation", name: "The Drake, Chicago", facts: 4, stale: false, user_edited: false },
  { id: "order-airpods", type: "Order", name: "AirPods Pro", facts: 3, stale: false, user_edited: false },
  { id: "order-dd", type: "Order", name: "Thai Basil usual", facts: 3, stale: false, user_edited: true },
  { id: "place-thai", type: "Place", name: "Thai Basil", facts: 2, stale: false, user_edited: false },
  { id: "loyalty-sb", type: "Loyalty program", name: "Starbucks Rewards", facts: 2, stale: false, user_edited: false },
  { id: "loyalty-sl", type: "Loyalty program", name: "SkyLark Miles", facts: 2, stale: false, user_edited: false },
];
const EDGES = [
  ["trip-chi", "includes", "flight-482"], ["trip-chi", "stays_at", "res-hotel"], ["trip-den", "includes", "flight-910"],
  ["person-maya", "travels_on", "trip-chi"], ["person-maya", "travels_on", "trip-den"], ["person-maya", "ordered", "order-airpods"],
  ["person-maya", "ordered", "order-dd"], ["order-dd", "from", "place-thai"], ["person-maya", "member_of", "loyalty-sb"], ["person-maya", "member_of", "loyalty-sl"],
].map(([source, relation, target], i) => ({ id: `edge-${i}`, source, target, relation }));

const src = (id: string, where: string) => ({ id, where });
const fact = (attribute: string, value: string, sources: { id: string; where: string }[], extra: Record<string, unknown> = {}) => ({
  id: `fact-${attribute}-${value}`.replace(/\W+/g, "-"), attribute, value, current: true, stale: false, conflict: 0, recorded_at: ago(3600), sources, ...extra,
});
const ENTITY: Record<string, { facts: any[] }> = {
  "flight-482": { facts: [
    fact("number", "SL 482", [src("s-email", "email from SkyLark Air, Oct 12")]),
    fact("date", "Fri, Oct 30, 2026", [src("s-email", "email from SkyLark Air, Oct 12")]),
    fact("depart_time", "6:05 AM", [src("s-sl", "SkyLark app, 1 h ago")]),
    fact("gate", "B22", [src("s-sl", "SkyLark app, 1 h ago")]),
    fact("gate", "B14", [src("s-sl-old", "SkyLark app, yesterday")], { current: false, valid_to: ago(3600) }),
    fact("seat", "14C", [src("s-sl", "SkyLark app, 1 h ago")]),
    fact("boarding_group", "Group 3", [src("s-sl", "SkyLark app, 1 h ago")]),
    fact("terminal", "B", [src("s-email", "email from SkyLark Air, Oct 12")], { stale: true }),
  ] },
  "order-dd": { facts: [
    fact("items", "Pad thai, medium spice, no peanuts", [src("s-dd", `DoorDash app, ${fmtDay(ago(8 * 86400))}`)], { author: "user" }),
    fact("restaurant", "Thai Basil", [src("s-dd", `DoorDash app, ${fmtDay(ago(8 * 86400))}`)]),
    fact("total", "$18.42", [src("s-dd", `DoorDash app, ${fmtDay(ago(8 * 86400))}`)]),
  ] },
};
const entityOf = (id: string) => {
  const n = NODES.find((x) => x.id === id) ?? NODES[0];
  const facts = ENTITY[id]?.facts ?? [
    fact("name", n.name.split(" · ")[0], [src("s-gen", "email from SkyLark Air, Oct 12")]),
    ...(n.type === "Trip" ? [fact("destination", n.name.split(" · ")[0], [src("s-gen", "email from SkyLark Air, Oct 12")])] : []),
  ];
  const links = EDGES.filter((e) => e.source === id || e.target === id).map((e) => {
    const other = NODES.find((x) => x.id === (e.source === id ? e.target : e.source))!;
    return { relation: e.relation, id: other.id, type: other.type, name: other.name };
  });
  return { entity: { id: n.id, type: n.type, name: n.name }, facts, links };
};

// ---- routines -----------------------------------------------------------------------------------------------------------

const ROUTINES = [
  { name: "skylark_get_flight_gate", app: "com.skylark.air", intent: "Look up my flight's gate", active: 3, steps: 4, runs: 23, success: 0.96, recompile: false,
    inputs: { trip_city: "The trip's destination city" }, outputs: ["gate", "terminal", "boarding_time"],
    versions: [{ version: 1, status: "retired" }, { version: 2, status: "retired", source_task: "task-1021" }, { version: 3, status: "active", source_task: "task-1026" }] },
  { name: "doordash_reorder_usual", app: "com.dd.doordash", intent: "Reorder my usual on DoorDash", active: 3, steps: 6, runs: 9, success: 0.89, recompile: false,
    inputs: { restaurant: "Which restaurant" }, outputs: ["total"], versions: [{ version: 1, status: "retired" }, { version: 2, status: "retired", source_task: "t" }, { version: 3, status: "active" }] },
  { name: "skylark_check_in_flight", app: "com.skylark.air", intent: "Check me in for my flight", active: 1, steps: 7, runs: 6, success: 0.67, recompile: false,
    inputs: { trip_city: "The trip's destination city" }, outputs: ["seat", "gate", "boarding_group"], versions: [{ version: 1, status: "active" }, { version: 2, status: "trial", source_task: "t" }] },
  { name: "starbucks_order_usual", app: "com.starbucks.mobilecard", intent: "Order my morning coffee", active: 2, steps: 5, runs: 14, success: 1, recompile: false,
    inputs: {}, outputs: ["pickup_time"], versions: [{ version: 1, status: "retired" }, { version: 2, status: "active" }] },
  { name: "amazon_track_package", app: "com.amazon.mShop.android.shopping", intent: "Track my Amazon package", active: 1, steps: 3, runs: 2, success: 0.5, recompile: true,
    inputs: {}, outputs: ["delivery_eta"], versions: [{ version: 1, status: "active" }] },
];

function routineDetail(name: string) {
  const r = ROUTINES.find((x) => x.name === name) ?? ROUTINES[0];
  const loc = (text: string, extra: Record<string, unknown> = {}) => ({ text, kind: "button", ...extra });
  const stepsByName: Record<string, any[]> = {
    skylark_get_flight_gate: [
      { id: "open_trips", intent: "Open My trips", risk: "read", optional: false, action: { kind: "tap", verb: "Tap", target: loc("My trips") }, pre: [], post: [{ kind: "text", text: "Your trips", locator: null }], outputs: [] },
      { id: "dismiss_promo", intent: "Close the miles promo if it shows", risk: "read", optional: true, action: { kind: "tap", verb: "Tap", target: loc("Not now", { desc: "Close" }) }, pre: [], post: [], outputs: [], changed_in: [{ version: 3, kind: "inserted" }] },
      { id: "open_trip", intent: "Open the trip to {{trip_city}}", risk: "read", optional: false, action: { kind: "tap", verb: "Tap", target: loc("{{trip_city}}", { in_list: true }) }, pre: [{ kind: "text", text: "Your trips", locator: null }], post: [{ kind: "text", text: "Gate", locator: null }], outputs: [], changed_in: [{ version: 2, kind: "locator" }] },
      { id: "read_gate", intent: "Read the gate, terminal and boarding time", risk: "read", optional: false, action: { kind: "read", verb: "Read", target: null }, pre: [], post: [], outputs: ["gate", "terminal", "boarding_time"] },
    ],
  };
  const steps = stepsByName[name] ?? [
    { id: "open", intent: `Open ${r.intent.toLowerCase()}`, risk: "read", optional: false, action: { kind: "tap", verb: "Tap", target: loc("Orders") }, pre: [], post: [], outputs: [] },
    { id: "act", intent: "Do the step that matters", risk: name.includes("check_in") || name.includes("order") || name.includes("reorder") ? "irreversible" : "reversible",
      optional: false, action: { kind: "tap", verb: "Tap", target: loc(name.includes("check_in") ? "Confirm check-in" : "Place order") }, pre: [], post: [], outputs: r.outputs },
  ];
  const versions = r.versions.map((v, i) => ({
    version: v.version, status: v.status, created: new Date((ago((r.versions.length - i) * 2 * 86400)) * 1000).toISOString().slice(0, 16).replace("T", " "),
    parent: i ? v.version - 1 : null, origin: i ? "repaired" : "compiled", notes: i ? ["relaxed match on 'Chicago' row", "inserted optional step dismiss_promo"] : [],
    changes: i && name === "skylark_get_flight_gate" ? (v.version === 2
      ? [{ step: "open_trip", intent: "Open the trip to {{trip_city}}", kind: "locator", what: "how the trip row is found", before: loc("{{trip_city}} · SL 482"), after: loc("{{trip_city}}", { in_list: true }),
        why: "The trip row's label changed after an app update.", score: 0.64 }]
      : [{ step: "dismiss_promo", intent: "Close the miles promo if it shows", kind: "inserted", what: "a new step", before: null, after: steps[1], follows: "Open My trips",
        reasons: ["A SkyLark Miles promo covered the trip list; closing it with Not now shows the list again."] }]) : [],
    shots: i && name === "skylark_get_flight_gate" && v.version === 3 ? [{ label: "step 2", intent: "Close the miles promo if it shows", before: `/api/routines/${name}/history/3/before.png`, after: `/api/routines/${name}/history/3/after.png` }] : [],
    replaced_by: v.status === "retired" ? v.version + 1 : null,
    repair: i ? { task_id: `task-repair-${v.version}`, rung: v.version === 2 ? 2 : 4, how: v.version === 2 ? "relaxed match" : "local repair", model_calls: v.version === 2 ? 0 : 1, run_rung: null, duration_s: 14.2, time: null } : undefined,
    compiled: i ? undefined : { task_id: "task-1019-agent", goal: r.intent, compiler: "Muse Spark", usd: 0.021, source: { task_id: "task-1019-agent", steps: 9, model_calls: 11, duration_s: 74, usd: 0.034 },
      verification: [{ case: "same-inputs", passed: true, duration_s: 8.1, inputs: {} }, { case: "other-inputs", passed: true, duration_s: 7.6, inputs: {} }] },
    trial: v.status === "active" && i ? { passed: true, task_id: "task-trial", status: "done", model_calls: 0, duration_s: 7.9 } : undefined,
  }));
  const runs = Array.from({ length: Math.min(r.runs, 6) }, (_, i) => ({
    time: new Date((ago((6 - i) * 43200)) * 1000).toISOString().slice(0, 16).replace("T", " "), kind: "run", version: r.active, task_id: `task-run-${i}`,
    status: i === 2 && r.success < 1 ? "agent_done" : "done", ok: true, rung: i === 2 ? 2 : 0, how: i === 2 ? "relaxed match" : "clean replay", model_calls: i === 2 ? 1 : 0,
    duration_s: 7 + (i % 3), usd: i === 2 ? 0.003 : 0, usd_estimated: i === 2, patches: 0, device: i % 2 ? "pixel-5" : "envoy-test", app_task: i === 5 ? "task-amz" : null,
    saved: { calls: 11, seconds: 66, usd: 0.034 }, event: null,
  }));
  return {
    name: r.name, app: APP_LOOK[r.app]?.name ?? r.app, intent: r.intent, description: `Learned from one agent run. Replays ${r.intent.toLowerCase()} with no model calls while the app looks as expected.`,
    inputs: Object.fromEntries(Object.entries(r.inputs).map(([k, d]) => [k, { type: "string", description: d, example: k === "trip_city" ? "Chicago" : "Thai Basil" }])),
    outputs: r.outputs, active: r.active, shown: r.active, shown_status: "active", trial: r.versions.find((v) => v.status === "trial")?.version ?? null,
    needs_recompile: r.recompile, steps, done: [{ kind: "text", text: "Gate", locator: null }], versions, runs,
    savings: { source: { task_id: "task-1019-agent", steps: 9, model_calls: 11, duration_s: 74, usd: 0.034 }, runs: r.runs, finished: r.runs - 1, compared: r.runs - 1, failed: 1,
      model_calls: 2, saved: { calls: 11 * (r.runs - 1) - 2, seconds: 66 * (r.runs - 1), usd: 0.034 * (r.runs - 1) }, compile_usd: 0.021, net_usd: 0.034 * (r.runs - 1) - 0.021,
      paid_back_after: 1, median_s: 8.2 },
  };
}

// ---- the briefing (the same rules as backend/api/briefing.py) -----------------------------------------------------------

function briefing() {
  const all = Object.values(db.tasks);
  const pending = Object.values(db.approvals).filter((a) => a.status === "pending");
  const waiting = new Set(pending.map((a) => a.task_id));
  const needs: any[] = pending.map((a) => ({ kind: "approval", id: a.id, task_id: a.task_id, title: a.description, detail: db.tasks[a.task_id]?.goal ?? "",
    app: a.app, time: a.created_at, money: /\$|\bpay/i.test(a.description) }));
  const asks = all.filter((t) => t.status === "needs_you" && t.waiting_for === "phone");
  asks.forEach((t) => needs.push({ kind: "phone", id: t.id, task_id: t.id, title: t.detail ?? "Use your Android phone for this task?", detail: t.goal, app: t.app, time: t.updated_at }));
  const stuck = all.filter((t) => ["needs_you", "waiting_approval"].includes(t.status) && t.waiting_for !== "phone" && !waiting.has(t.id));
  stuck.forEach((t) => needs.push({ kind: "task", id: t.id, task_id: t.id, title: t.goal, detail: t.detail ?? "", status: t.status, app: t.app, device: t.device, time: t.updated_at }));
  const changes = db.changes.filter((c) => c.time >= now() - 86400);
  const today: any[] = changes.map((c) => ({ kind: "change", id: `change-${c.id}`, task_id: c.task_id, title: `${c.attribute === "gate" ? "Gate" : c.attribute} changed to ${c.new}`,
    label: c.attribute === "gate" ? "Gate" : c.attribute.replace(/_/g, " "), attribute: c.attribute, old: c.old, new: c.new, entity: c.entity_label, source: c.source, time: c.time }));
  const finished = all.filter((t) => ["done", "failed", "declined"].includes(t.status) && t.updated_at >= dayStart && !t.parent);
  finished.forEach((t) => today.push({ kind: t.routine ? "routine" : "task", id: t.id, task_id: t.id, title: t.goal, result: t.result ?? "", status: t.status, app: t.app,
    routine: t.routine, seconds: Math.round((t.updated_at - t.created_at) * 10) / 10, time: t.updated_at }));
  today.sort((a, b) => b.time - a.time);
  const upcoming = db.triggers.filter((t) => t.enabled && t.kind !== "watch" && t.next[0] && t.next[0].at >= now() && t.next[0].at <= now() + 86400)
    .map((t) => ({ id: t.id, name: t.name, kind: t.kind, at: t.next[0].at, for: t.next[0].for, ask: !!t.action.ask })).sort((a, b) => a.at - b.at);
  const asking = db.offers.filter((o) => o.status === "pending" && (!o.expires_at || o.expires_at > now()));
  asking.forEach((o) => needs.push({ kind: "offer", id: o.id, offer_id: o.id, task_id: null, title: o.title, detail: o.body, goal: o.action.goal ?? "",
    action: o.action.type, offer_kind: o.kind, preflight: o.preflight, time: o.created_at, expires_at: o.expires_at, offer: o }));
  const said: string[] = [];
  const c = today.find((x) => x.kind === "change");
  if (c) said.push(`Your ${c.label.toLowerCase()} for flight SL 482 changed to ${c.new}.`);
  if (upcoming[0]) {
    const at = new Date(upcoming[0].at * 1000);
    const tomorrow = at.getDate() !== new Date().getDate() ? " tomorrow" : "";
    said.push(`Next up at ${at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}${tomorrow}: ${upcoming[0].name}${upcoming[0].ask ? ", and I'll ask you first." : "."}`);
  }
  const ap = needs.filter((n) => n.kind === "approval");
  if (ap.length) said.push(ap.length === 1 ? (ap[0].money ? "One payment is waiting for your OK." : "One action is waiting for your OK.") : `${ap.length} actions are waiting for your OK.`);
  if (asking.length) said.push(asking.length === 1 ? `I have a question for you: ${asking[0].title}` : `I have ${asking.length} questions for you.`);
  if (asks.length) said.push(asks.length === 1 ? "One task asks to use your Android phone." : `${asks.length} tasks ask to use your Android phone.`);
  const done = finished.filter((t) => t.status === "done");
  if (done.length && said.length < 3) said.push(done.length > 1 ? `I finished ${done.length} tasks today.` : "I finished one task today.");
  if (!said.length) said.push("All quiet. Nothing needs you right now.");
  return { time: now(), name: "Maya", text: said.slice(0, 3).join(" "), needs, today: today.slice(0, 8), upcoming,
    suggestions: [...ROUTINES].sort((a, b) => b.runs - a.runs).slice(0, 4).map((r) => ({ label: r.intent, routine: r.name, app: r.app })) };
}

// ---- the running task --------------------------------------------------------------------------------------------------

const timers = new Set<ReturnType<typeof setTimeout>>();
const later = (ms: number, fn: () => void) => { const t = setTimeout(() => { timers.delete(t); fn(); }, ms); timers.add(t); };

function setTask(id: string, patch: Partial<Task>) {
  db.tasks[id] = { ...db.tasks[id], ...patch, updated_at: now() };
  emit("task", { task: db.tasks[id] });
}
function addStep(id: string, s: Omit<Step, "seq" | "time">) {
  const list = (db.steps[id] ??= []);
  const st = { ...s, seq: list.length + 1, time: now() } as Step;
  list.push(st);
  emit("step", { task_id: id, step: st });
}

let runs = 0;
// A watcher's run of the gate routine: plan, a few steps a second or so apart, a pause (thinking), then done.
function gateRun(source = "trigger:Watch my gate") {
  const id = `task-gate-${++runs}`;
  db.tasks[id] = task({ id, goal: "What's my gate for SL 482?", source, status: "queued", app: "com.skylark.air", device: "envoy-test", kind: "routine",
    routine: "skylark_get_flight_gate", created_at: now(), updated_at: now() });
  db.steps[id] = [];
  emit("task", { task: db.tasks[id] });
  db.leases["envoy-test"] = { ...db.leases["envoy-test"], task_id: id };
  const script: [number, () => void][] = [
    [1000, () => { setTask(id, { status: "running" });
      addStep(id, { kind: "preflight", lines: [{ kind: "routine", text: "Using routine skylark_get_flight_gate v3: usually 7 s, no model calls.", level: "info" }] }); }],
    [200, () => { addStep(id, { kind: "note", text: "using routine skylark_get_flight_gate v3 with trip_city = Chicago",
      sources: { trip_city: "Trip Chicago · Fri, Oct 30 (destination): email from SkyLark Air, Oct 12" } }); }],
    [1400, () => addStep(id, { kind: "routine_step", text: "open_trips", status: "done", rung: 0, shot: "sl-1" })],
    [1300, () => addStep(id, { kind: "routine_step", text: "dismiss_promo", status: "skipped", rung: 0, detail: "its screen didn't appear" })],
    [1500, () => addStep(id, { kind: "routine_step", text: "open_trip", status: "done", rung: 0, shot: "sl-2" })],
    [3200, () => addStep(id, { kind: "routine_step", text: "read_gate", status: "done", rung: 0, shot: "sl-2" })],
    [1400, () => addStep(id, { kind: "memory", text: "memory updated: 6 same", entities: ["Flight SL 482 · Fri, Oct 30, 2026"] })],
    [800, () => { addStep(id, { kind: "finish", text: "all steps and checks passed", status: "done" });
      setTask(id, { status: "done", result: "gate: B22; terminal: B; boarding time: 5:30 AM", model_calls: 0 });
      db.leases["envoy-test"] = { ...db.leases["envoy-test"], task_id: null };
      for (const old of Object.keys(db.tasks)) if (old.startsWith("task-gate-") && old !== id && +old.split("-")[2] < runs - 1) { delete db.tasks[old]; delete db.steps[old]; }
      if (scenario === "quiet") later(14000, () => gateRun());
    }],
  ];
  let at = 0;
  for (const [ms, fn] of script) { at += ms; later(at, fn); }
  return db.tasks[id];
}

// A task you started from chat, which ends with a payment waiting for your OK (unless there is one already).
function chatTask(goal: string) {
  const id = `task-chat-${++runs}`;
  db.tasks[id] = task({ id, goal, source: "chat", status: "queued", created_at: now(), updated_at: now(), app: "com.starbucks.mobilecard", device: "envoy-test" });
  db.steps[id] = [];
  emit("task", { task: db.tasks[id] });
  const script: [number, () => void][] = [
    [700, () => { setTask(id, { status: "running", kind: "agent" }); addStep(id, { kind: "preflight", lines: [
      { kind: "approval", text: "Any payment will need your OK.", level: "info" },
      { kind: "app_note", text: "From earlier runs: A Rewards pop-up can appear before the menu", level: "info" },
    ] }); }],
    [200, () => addStep(id, { kind: "plan", text: "Open Starbucks; Find your usual; Check out" })],
    [1600, () => addStep(id, { kind: "action", text: 'tap "Order"', reason: "The order tab has your favorites", risk: "read", shot: "sb-1" })],
    [1500, () => addStep(id, { kind: "action", text: 'tap "Grande oat latte"', reason: "That's your usual", risk: "reversible", shot: "sb-1" })],
    [1500, () => { addStep(id, { kind: "finish", text: "Added your usual to the cart", status: "done" }); setTask(id, { status: "done", result: "Your usual is in the cart: a grande oat latte", model_calls: 3, cost_usd: 0.006 }); }],
  ];
  let at = 0;
  for (const [ms, fn] of script) { at += ms; later(at, fn); }
  return db.tasks[id];
}

// Your answer to an offer. Yes starts the check-in from its routine, with "Confirm check-in" done because you asked.
function answerOffer(id: string, decision: string) {
  const o = db.offers.find((x) => x.id === id);
  if (!o) throw err(404, "no such offer");
  if (o.status === "accepted" && decision === "accept") return o;
  if (o.status !== "pending") throw err(409, `already ${o.status}`);
  if (o.action.type === "handoff") return answerHandoff(o, decision);
  if (decision === "decline") Object.assign(o, { status: "declined", decided_at: now(), decided_by: "you" });
  else if (o.action.type === "enable_trigger") {  // chat or an assistant asked for it: the yes turns it on
    const t = db.triggers.find((x) => x.id === o.action.trigger_id);
    if (t) t.enabled = true;
    Object.assign(o, { status: "accepted", decided_at: now(), decided_by: "you", result: { trigger_id: o.action.trigger_id } });
  } else if (o.action.type === "create_trigger") {  // a habit: the trigger it sets up asks each time
    const t = { id: `trig-${++runs}`, kind: o.action.kind, name: o.action.name, spec: o.action.spec, action: o.action.action, enabled: true, last_fired: null,
      next: [{ at: (() => { const d = new Date(); d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7)); d.setHours(8, 0, 0, 0); return d.getTime() / 1000; })() }],
      alerts: { on: false, attributes: ["*"] } };
    db.triggers.push(t);
    Object.assign(o, { status: "accepted", decided_at: now(), decided_by: "you", result: { trigger_id: t.id } });
  } else Object.assign(o, { status: "accepted", decided_at: now(), decided_by: "you", task_id: checkInRun(o.action.goal, o.action.inputs?.trip_city ?? "Chicago") });
  emit("offer", { offer: o, change: o.status });
  return o;
}

// A file from the Mac: yes puts it on the phone, then (for a template with a post) starts the post, which waits for your
// OK on Share like any public post.
function setHandoff(id: string, patch: Partial<HandoffItem>) {
  const i = db.handoffs.findIndex((h) => h.id === id);
  if (i < 0) throw err(404, `no handoff ${id}`);
  db.handoffs[i] = { ...db.handoffs[i], ...patch, updated_at: now() };
  emit("handoff", { item: db.handoffs[i] });
  return db.handoffs[i];
}

function sendHandoff(id: string) {
  const h = db.handoffs.find((x) => x.id === id);
  if (!h) throw err(404, `no handoff ${id}`);
  if (h.status === "sent" || h.status === "posted") return h;
  const dir = h.kind === "video" ? "Movies/Envoy" : "Pictures/Envoy";
  return setHandoff(id, { status: "sent", error: null, note: null, remote_path: `/sdcard/${dir}/${h.name}`, media_uri: `content://media/external/${h.kind === "video" ? "video" : "images"}/media/${1000000030 + runs}` });
}

function answerHandoff(o: any, decision: string) {
  const id = o.action.handoff_id;
  if (decision === "decline") {
    Object.assign(o, { status: "declined", decided_at: now(), decided_by: "you" });
    setHandoff(id, { status: "waiting", note: "you said not now" });
  } else {
    sendHandoff(id);
    const t = o.action.then ? chatTask(o.action.then.goal) : null;
    if (t) setHandoff(id, { task_id: t.id });
    Object.assign(o, { status: "accepted", decided_at: now(), decided_by: "you", task_id: t?.id ?? null });
  }
  emit("offer", { offer: o, change: o.status });
  return o;
}

function checkInRun(goal: string, city: string) {
  const id = `task-offer-${++runs}`;
  db.tasks[id] = task({ id, goal, source: "web", request: "Check me in for my flight to", status: "queued", app: "com.skylark.air", device: "envoy-test", kind: "routine",
    routine: "skylark_check_in_flight", inputs: { trip_city: city }, created_at: now(), updated_at: now() });
  db.steps[id] = [];
  emit("task", { task: db.tasks[id] });
  const script: [number, () => void][] = [
    [900, () => { setTask(id, { status: "running" }); addStep(id, { kind: "note", text: `using routine skylark_check_in_flight v1 with trip_city = ${city}` }); }],
    [1300, () => addStep(id, { kind: "routine_step", text: "tap_check_in", status: "done", rung: 0, shot: "sl-1" })],
    [1200, () => addStep(id, { kind: "routine_step", text: "select_passenger", status: "done", rung: 0, shot: "sl-2" })],
    [1200, () => addStep(id, { kind: "approval", text: "Confirm check-in: done without asking (your request)", reason: `you asked: "Check me in for my flight to"` })],
    [900, () => addStep(id, { kind: "routine_step", text: "confirm_check_in", status: "done", rung: 0, shot: "sl-2", risk: "irreversible" })],
    [900, () => { addStep(id, { kind: "finish", text: "all steps and checks passed", status: "done" });
      setTask(id, { status: "done", result: "You're checked in: seat 14C, group 3, boarding 5:30 AM", model_calls: 0 }); }],
  ];
  let at = 0;
  for (const [ms, fn] of script) { at += ms; later(at, fn); }
  return id;
}

function approve(id: string, approved: boolean) {
  const a = db.approvals[id];
  if (!a || a.status !== "pending") throw Object.assign(new Error("already decided"), { status: 409 });
  db.approvals[id] = { ...a, status: approved ? "approved" : "declined", decided_by: "you" };
  emit("approval_decided", { approval: db.approvals[id], task_id: a.task_id });
  const t = a.task_id;
  if (approved) {
    setTask(t, { status: "running", waiting_for: null });
    later(1400, () => addStep(t, { kind: "routine_step", text: "place_order", status: "done", rung: 0, shot: "dd-4", risk: "irreversible", approval: { approved: true, by: "you" } }));
    later(2600, () => { addStep(t, { kind: "finish", text: "all steps and checks passed", status: "done" }); setTask(t, { status: "done", result: "Ordered: arrives in about 35 min" });
      db.leases["pixel-5"] = { ...db.leases["pixel-5"], task_id: null }; });
  } else {
    later(600, () => { setTask(t, { status: "declined", detail: "you declined the payment", waiting_for: null }); db.leases["pixel-5"] = { ...db.leases["pixel-5"], task_id: null }; });
  }
  return db.approvals[id];
}

// ---- the API ----------------------------------------------------------------------------------------------------------

const err = (status: number, message: string) => Object.assign(new Error(message), { status });

export function start(s: string | null): void {
  scenario = (s === "1" || !s ? "full" : s) as Scenario;
  if (!["full", "quiet", "idle", "offline", "pair"].includes(scenario)) scenario = "full";
  db = seed();
}

export async function handle(path: string, init: RequestInit = {}): Promise<any> {
  await new Promise((r) => setTimeout(r, 120)); // a little latency, so loading states show
  const u = new URL(path, "http://mock");
  const p = u.pathname.replace(/\/$/, "");
  const method = (init.method ?? "GET").toUpperCase();
  const body = typeof init.body === "string" ? JSON.parse(init.body || "{}") : {};
  if (scenario === "pair" && !["/api/pair"].includes(p)) throw err(401, "Not signed in");
  if (scenario === "offline" && p === "/api/briefing") throw err(503, "Can't reach your Mac");
  const pub = (a: any) => { const { nonce, ...rest } = a; return rest; };
  let m: RegExpMatchArray | null;

  if (p === "/api/state") return { profile: "demo", devices: Object.values(db.leases), tasks: Object.values(db.tasks).sort((a, b) => b.created_at - a.created_at).slice(0, 20),
    approvals: Object.values(db.approvals).filter((a) => a.status === "pending").map(pub), routines: ROUTINES.length, memory: { entities: NODES.length },
    public_url: "https://envoy-mac.tail1234.ts.net:8443", me: { kind: "owner", name: "Mac" }, push_key: "mock" };
  if (p === "/api/briefing") return briefing();
  if (p === "/api/tasks" && method === "POST") return body.routine ? gateRun("web") : chatTask(body.goal ?? "A task");
  if (p === "/api/tasks") return Object.values(db.tasks).sort((a, b) => b.created_at - a.created_at);
  if ((m = p.match(/^\/api\/tasks\/([^/]+)\/stop$/))) { setTask(m[1], { status: "stopped", detail: "stopped by you" }); return { stopped: true }; }
  if ((m = p.match(/^\/api\/tasks\/([^/]+)\/phone$/))) {
    setTask(m[1], { status: body.allow ? "running" : "failed", waiting_for: null, device: body.allow ? "pixel-5" : undefined,
      detail: body.allow ? undefined : "you said no: Target blocks emulators" });
    if (body.allow) later(2500, () => { addStep(m![1], { kind: "action", text: 'tap "Search"', reason: "Find AirPods Pro", risk: "read", shot: "tgt-1" });
      setTask(m![1], { status: "done", result: "AirPods Pro: $189.99 at Target, in stock nearby" }); });
    return { ok: true };
  }
  if ((m = p.match(/^\/api\/tasks\/([^/]+)$/))) {
    const t = db.tasks[m[1]];
    if (!t) throw err(404, "Not Found");
    return { task: t, steps: db.steps[m[1]] ?? [], approvals: Object.values(db.approvals).filter((a) => a.task_id === t.id).map(pub) };
  }
  if (p === "/api/approvals") return Object.values(db.approvals).filter((a) => !u.searchParams.get("status") || a.status === u.searchParams.get("status")).map(pub);
  if ((m = p.match(/^\/api\/approvals\/([^/]+)$/))) {
    const a = db.approvals[m[1]];
    if (!a) throw err(404, "Not Found");
    if (method === "POST") return pub(approve(a.id, body.decision === "approve"));
    return { ...a, goal: db.tasks[a.task_id]?.goal, task_status: db.tasks[a.task_id]?.status };
  }
  if (p === "/api/devices") return Object.values(db.leases);
  if ((m = p.match(/^\/api\/devices\/([^/]+)\/(takeover|handback)$/))) {
    const l = { ...db.leases[m[1]], user_control: m[2] === "takeover" };
    db.leases[m[1]] = l;
    emit(m[2] === "takeover" ? "takeover" : "hand_back", { avd: m[1], task_id: l.task_id });
    return l;
  }
  if (p === "/api/chat") {
    const msg = String(body.message ?? "");
    if (/\b(every|each|daily|weekly|whenever)\b/i.test(msg)) {  // a recurring job: a trigger, switched off, and a card to turn it on
      const id = `offer-chat-${++runs}`;
      const t = { id: `trig-${runs}`, kind: "time", name: msg.slice(0, 60), spec: { weekly_on: { days: ["fri"], at: "18:00" } }, action: { goal: msg, ask: true },
        enabled: false, last_fired: null, next: [], alerts: { on: false, attributes: ["*"] } };
      db.triggers.push(t);
      const o = { id, created_at: now(), kind: "trigger_request", title: "Set this up? Every Friday at 6:00 PM: order your usual from Thai Basil", status: "pending",
        body: "It stays off until you say yes, and each time it runs I'll ask you first.", source: "chat", key: `trigger_request:${t.id}`, expires_at: null,
        decided_at: null, decided_by: null, task_id: null, preflight: [], origin: null, note: null, result: null,
        action: { type: "enable_trigger", trigger_id: t.id, summary: "Every Friday at 6:00 PM, I'll ask you: “Should I order your usual from Thai Basil?”",
          setup: "asks you every Friday at 6:00 PM" } };
      db.offers.push(o);
      emit("offer", { offer: o, change: "created" });
      return { kind: "trigger_request", reply: "I can do that: every Friday at 6:00 PM, order your usual from Thai Basil. It's off until you say yes below, and each time it runs I'll ask you first.",
        spoken: "I've drafted it. Say yes on the card to turn it on.", offer: o, trigger: t, model_calls: 1 };
    }
    if (/gate|seat|flight|board/i.test(msg)) return { kind: "memory", reply: "Your gate for SL 482 is B22. It moved from B14 at 6:12 PM; I saw it in SkyLark.", from_memory: true, stale: false,
      spoken: "Your gate is B22." };
    return { kind: "task", reply: "On it. I'll do that on the emulator and tell you when it's done.", task: chatTask(msg) };
  }
  if (p === "/api/memory/graph") return { nodes: NODES, edges: EDGES };
  if ((m = p.match(/^\/api\/memory\/entity\/([^/]+)(\/fact)?$/))) return m[2] ? { ok: true } : entityOf(m[1]);
  if (p.startsWith("/api/memory/source/")) return { deleted: 1 };
  if (p === "/api/memory/search") return { markdown: "**Flight SL 482** (Fri, Oct 30, 2026): gate B22 (SkyLark app, 1 h ago; was B14), departs 6:05 AM, seat 14C, group 3." };
  if (p === "/api/routines") return ROUTINES;
  if ((m = p.match(/^\/api\/routines\/([^/]+)\/detail$/))) return routineDetail(decodeURIComponent(m[1]));
  if ((m = p.match(/^\/api\/routines\/([^/]+)$/))) return { index: {}, yaml: `routine: ${m[1]}\nversion: 3\napp: com.skylark.air\nsteps:\n  - id: open_trips\n    action: tap\n    target: {text: My trips}\n` };
  if (p === "/api/triggers" && method === "POST") { const t = { id: `trig-${++runs}`, enabled: true, last_fired: null, next: [], alerts: { on: false, attributes: ["*"] }, ...body }; db.triggers.push(t); return t; }
  if (p === "/api/triggers") return db.triggers;
  if ((m = p.match(/^\/api\/triggers\/([^/]+)$/))) {
    const i = db.triggers.findIndex((t) => t.id === m![1]);
    if (method === "DELETE") { db.triggers.splice(i, 1); return { deleted: m[1] }; }
    const t = db.triggers[i];
    if ("enabled" in body) t.enabled = body.enabled;
    if ("alert" in body) t.alerts = { ...t.alerts, on: body.alert };
    if ("ask" in body) t.action = { ...t.action, ask: body.ask };
    return t;
  }
  if (p === "/api/alerts") return db.changes;
  if (p === "/api/offers") {
    const st = u.searchParams.get("status") ?? "pending";
    return db.offers.filter((o) => st === "all" || o.status === st).sort((a, b) => b.created_at - a.created_at).slice(0, Number(u.searchParams.get("limit") ?? 50));
  }
  if ((m = p.match(/^\/api\/offers\/([^/]+)$/))) {
    if (method === "POST") return answerOffer(m[1], body.decision);
    const o = db.offers.find((x) => x.id === m![1]);
    if (!o) throw err(404, "no such offer");
    return o;
  }
  if (p === "/api/handoff") return { outbox: db.outbox, items: db.handoffs.slice().sort((a, b) => b.created_at - a.created_at).slice(0, Number(u.searchParams.get("limit") ?? 50)),
    templates: { gallery: { label: "the phone's gallery", package: null }, instagram: { label: "Instagram", package: "com.instagram.android" } } };
  if ((m = p.match(/^\/api\/handoff\/([^/]+)\/send$/))) return sendHandoff(m[1]);
  if (p === "/api/settings/handoff") {
    if (method === "POST") { if (!String(body.outbox ?? "").startsWith("/")) throw err(400, "the outbox is a full path to a folder on this Mac"); db.outbox = body.outbox; }
    return { outbox: db.outbox };
  }
  if (p === "/api/settings/proactivity") {
    if (method === "POST") db.proactivity = body.level;
    return { level: db.proactivity, levels: ["off", "important", "all"] };
  }
  if ((m = p.match(/^\/api\/app-notes\/([^/]+)\/retire$/))) { db.notes = db.notes.filter((n) => n.id !== m![1]); return { retired: m[1] }; }
  if (p === "/api/app-notes") {
    const by: Record<string, any[]> = {};
    db.notes.forEach((n) => (by[n.app] ??= []).push(n));
    return { apps: Object.entries(by).map(([app, notes]) => ({ app, notes })) };
  }
  if (p === "/api/settings/approvals") {
    if (method === "POST") db.rules = body;
    return { rules: db.rules, apps: ["com.skylark.air", "com.dd.doordash", "com.starbucks.mobilecard", "com.amazon.mShop.android.shopping"],
      routines: ROUTINES.map((r) => ({ name: r.name, app: r.app, intent: r.intent, irreversible: !/gate|track/.test(r.name) })) };
  }
  if (p === "/api/settings/phones") {
    if (method === "POST") db.phoneApps = body.phone_apps;
    return { phone_apps: db.phoneApps, apps: Object.keys(APP_LOOK), emulator_refused: { "com.target.ui": "Target" }, learned: {},
      names: Object.fromEntries(Object.entries(APP_LOOK).map(([k, v]) => [k, v.name])), phones: [{ avd: "pixel-5", name: "Pixel 5", android: "13", state: "device" }] };
  }
  if (p === "/api/settings/photos") { if (method === "POST") db.photos = body; return db.photos; }
  if (p === "/api/paired") return { devices: [
    { id: "dev-1", name: "Maya's iPhone (Home Screen app)", scope: "session", created_at: ago(5 * 86400), last_seen: ago(60) },
    { id: "dev-2", name: "Send to Envoy (Shortcut)", scope: "photos", created_at: ago(4 * 86400), last_seen: ago(2 * 86400) },
    { id: "dev-3", name: "Ask Envoy (Siri)", scope: "siri", created_at: ago(2 * 86400), last_seen: ago(26 * 60) },
  ], push: [{ id: "push-1", device_id: "dev-1", service: "Apple", last_ok: ago(1800), failures: 0 }], me: { kind: "owner", device_id: null, name: "Mac" } };
  if (p === "/api/pair/start") return { code: "482917", expires_in: 300 };
  if (p === "/api/pair") { scenario = "full"; db = seed(); return { ok: true }; }
  if (p === "/api/tokens") return { token: "envoy_photos_mock_token_not_real", upload_url: "https://envoy-mac.tail1234.ts.net:8443/api/photos" };
  if (p === "/api/push/test") return { sent: 1, results: [{ status: 201, service: "Apple" }] };
  if (p.startsWith("/api/push") || p === "/api/metrics") return { ok: true };
  throw err(404, `mock: no fixture for ${method} ${p}`);
}

export const photos = async (n: number) => {
  await new Promise((r) => setTimeout(r, 900));
  const summary = n === 1 ? "I read the boarding pass: SL 482, seat 14C, group 3." : `I read ${n} images and saved what they say.`;
  emit("photo", { summary }); // the API tells every open app (a toast), as for a Shortcut upload
  return { results: [], summary };
};

// The event stream: replays what the fixtures do, and what you do (approving, stopping, starting a task).
export function subscribe(onEvent: (e: EnvoyEvent) => void, setConnected: (on: boolean) => void): () => void {
  listeners.add(onEvent);
  if (scenario !== "offline") {
    const t = setTimeout(() => setConnected(true), 250);
    timers.add(t);
    if (scenario === "full") later(2500, () => gateRun());
    if (scenario === "quiet") later(1500, () => gateRun());
  }
  return () => { listeners.delete(onEvent); timers.forEach(clearTimeout); timers.clear(); };
}
