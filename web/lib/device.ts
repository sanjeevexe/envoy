"use client";

// The iPhone companion's plumbing (Phase 5): the service worker, push notifications, photo uploads, and what kind of
// screen and app this is.
import { useEffect, useState } from "react";
import { api, ApiError, loadMock, mockMode, post } from "@/lib/api";

export const isIOS = () => typeof navigator !== "undefined" && /iPhone|iPad|iPod/.test(navigator.userAgent);
export const isStandalone = () =>
  typeof window !== "undefined" && (window.matchMedia("(display-mode: standalone)").matches || (navigator as any).standalone === true);

export function useMedia(query: string): boolean {
  const [match, setMatch] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    setMatch(m.matches);
    const on = () => setMatch(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return match;
}

// The service worker shows pushes and opens the page a notification points at.
export function registerServiceWorker(onOpen: (url: string) => void): void {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {});
  navigator.serviceWorker.addEventListener("message", (e) => {
    if (e.data?.type === "open" && typeof e.data.url === "string") onOpen(e.data.url);
  });
}

const fromB64 = (s: string) => {
  const raw = atob((s + "=".repeat((4 - (s.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

export type PushState = "unsupported" | "needs_home_screen" | "denied" | "off" | "on";

export async function pushState(): Promise<PushState> {
  if (isIOS() && !isStandalone()) return "needs_home_screen";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  return sub && Notification.permission === "granted" ? "on" : "off";
}

// Must run straight from a tap: iOS only asks for permission inside a user gesture.
export async function enablePush(): Promise<void> {
  if (isIOS() && !isStandalone()) throw new Error("Add Envoy to your Home Screen first (Share → Add to Home Screen), then open it from there.");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) throw new Error("This browser can't receive push notifications.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications are off for Envoy. Turn them on in Settings → Notifications → Envoy.");
  const reg = await navigator.serviceWorker.ready;
  const { key } = await api<{ key: string }>("/api/push/key");
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: fromB64(key) }));
  await post("/api/push/subscribe", { subscription: sub.toJSON() });
}

export async function disablePush(): Promise<void> {
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = await reg?.pushManager.getSubscription();
  if (sub) {
    await post("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
    await sub.unsubscribe();
  }
}

export type PhotoResult = { photo_id: string; summary?: string; error?: string; deleted?: boolean; facts?: Record<string, number>; total_ms?: number };

// Only the images you pick are sent; Envoy reads them on your Mac and deletes them once their facts are saved.
export async function uploadPhotos(files: File[]): Promise<{ results: PhotoResult[]; summary: string }> {
  if (mockMode()) return (await loadMock()).photos(files.length);
  const form = new FormData();
  files.slice(0, 10).forEach((f) => form.append("file", f, f.name));
  const r = await fetch("/api/photos", { method: "POST", body: form, credentials: "same-origin", headers: { "X-Envoy": "1" } });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail ?? msg; } catch {}
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

export const metric = (body: Record<string, unknown>) => post("/api/metrics", body).catch(() => {});
