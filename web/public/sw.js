// Envoy's service worker (Phase 5, the iPhone companion):
// - push: show the notification, and send a receipt so Envoy can measure delivery time;
// - tapping a notification opens its page (an approval, a task, the phone) in the app;
// - the app's pages are kept for when the Mac can't be reached, so the app still opens and says so.
// It never caches anything under /api/: approvals, memory and tasks always come fresh from your Mac.

const SHELL = "envoy-shell-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (/^\/(api|mcp|login)(\/|$)/.test(url.pathname)) return;
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }).then((hit) => hit || caches.match("/"))),
  );
});

self.addEventListener("push", (event) => {
  let p = {};
  try {
    p = event.data ? event.data.json() : {};
  } catch {
    p = { title: "Envoy", body: event.data ? event.data.text() : "" };
  }
  const shown = self.registration.showNotification(p.title || "Envoy", {
    body: p.body || "",
    tag: p.tag,
    renotify: true,
    requireInteraction: p.kind === "approval",
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",
    data: { url: p.url || "/", id: p.id },
  });
  const receipt = p.id
    ? fetch("/api/push/receipt", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Envoy": "1" },
        body: JSON.stringify({ id: p.id, shown_at: Date.now() }),
      }).catch(() => {})
    : Promise.resolve();
  event.waitUntil(Promise.all([shown, receipt]));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const w of windows) {
        if (!("focus" in w)) continue;
        await w.focus();
        if ("navigate" in w) {
          try {
            return await w.navigate(url);
          } catch {}
        }
        w.postMessage({ type: "open", url });
        return;
      }
      return self.clients.openWindow(url);
    })(),
  );
});
