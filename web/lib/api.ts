"use client";

// Talking to Envoy's API: same origin, session cookie. POSTs carry X-Envoy so no other site can make them.
import { useEffect, useRef, useState } from "react";

export type Task = {
  id: string; goal: string; source: string; status: string; created_at: number; updated_at: number;
  app?: string; device?: string; kind?: string; routine?: string; inputs?: Record<string, string>;
  result?: string; detail?: string; waiting_for?: string | null; model_calls?: number; cost_usd?: number;
  parent?: string | null; // the cross-app task this one is a part of
  request?: string | null; // what you asked, when the goal was reworded
};
export type Step = {
  seq: number; time: number; kind: string; text?: string; reason?: string; risk?: string | null; status?: string;
  rung?: number; detail?: string; shot?: string; approval?: { approved: boolean; by: string }; error?: string;
  entities?: string[]; sources?: Record<string, string>;
  // a "change" step: a remembered fact changed during this task (api/alerts.py)
  entity_label?: string; old?: string; new?: string; source?: string; pushed?: boolean; why_not?: string | null; alerted_for?: string;
};
export type Approval = {
  id: string; task_id: string; created_at: number; status: string; description: string; reasons: string[];
  app: string; screen: string; screenshot?: string | null; decided_by?: string; note?: string; nonce?: string; goal?: string;
};
export type Lease = {
  avd: string; task_id: string | null; user_control: boolean; since: number; reason: string; running?: boolean;
  kind?: "emulator" | "phone"; name?: string; android?: string; state?: string;
};
export type EnvoyEvent = { seq: number; time: number; type: string; [k: string]: any };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

// Mock mode (lib/mock.ts): `?mock=1` (or another scenario), kept for the tab's session; `?mock=0` ends it. The fixtures
// load only then, in their own chunk.
let scenario: string | null | undefined;
let mockLib: typeof import("@/lib/mock") | null = null;
export function mockMode(): string | null {
  if (scenario !== undefined) return scenario;
  if (typeof window === "undefined") return null;
  const asked = new URLSearchParams(location.search).get("mock");
  let kept: string | null = null;
  try {
    if (asked === "0") sessionStorage.removeItem("envoy-mock");
    else if (asked) sessionStorage.setItem("envoy-mock", asked);
    kept = sessionStorage.getItem("envoy-mock");
  } catch {}
  const env = process.env.NEXT_PUBLIC_ENVOY_MOCK;
  scenario = asked === "0" ? null : asked || kept || (env && env !== "0" ? env : null);
  return scenario;
}
async function mock() {
  if (!mockLib) {
    mockLib = await import("@/lib/mock");
    mockLib.start(mockMode());
  }
  return mockLib;
}
export const loadMock = mock;

// Where an <img> for an API path points: the API itself, or a placeholder picture in mock mode.
export const media = (path: string): string => (mockLib ? mockLib.media(path) : path);

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  if (mockMode()) {
    try { return await (await mock()).handle(path, init); } catch (e: any) { throw new ApiError(e.status ?? 500, e.message); }
  }
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (init.method && init.method !== "GET") {
    headers["X-Envoy"] = "1";
    if (init.body && typeof init.body === "string") headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail ?? msg; } catch {}
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { method: "POST", body: JSON.stringify(body) });

// The live event stream, with reconnects that pick up where it left off.
export function useEvents(onEvent: (e: EnvoyEvent) => void): boolean {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => {
    if (mockMode()) {
      let off = () => {};
      let gone = false;
      mock().then((m) => { if (!gone) off = m.subscribe((e) => handler.current(e), setConnected); });
      return () => { gone = true; off(); };
    }
    let ws: WebSocket | null = null;
    let last = 0;
    let stop = false;
    let retry: ReturnType<typeof setTimeout>;
    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/api/events?after=${last}`);
      ws.onopen = () => setConnected(true);
      ws.onmessage = (m) => {
        const e = JSON.parse(m.data) as EnvoyEvent;
        last = Math.max(last, e.seq);
        handler.current(e);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!stop) retry = setTimeout(open, 1500);
      };
    };
    open();
    return () => { stop = true; clearTimeout(retry); ws?.close(); };
  }, []);
  return connected;
}

export const ago = (t: number) => {
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(t * 1000).toLocaleDateString();
};
