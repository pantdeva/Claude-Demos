// Stock Finder service worker: shows push notifications sent by this computer and opens
// the dashboard page they point to. Messages are JSON: {id, type, title, body, path, sent}.
const ICON = "icon-192.png", BADGE = "badge-72.png";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", e => {
  let d;
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = {title: "Stock Finder", body: e.data ? e.data.text() : ""}; }
  const title = d.title || "Stock Finder";
  e.waitUntil(self.registration.showNotification(title, {
    body: d.body || "", icon: ICON, badge: BADGE, tag: d.id || undefined,
    timestamp: Date.parse(d.sent) || Date.now(), data: {path: d.path || "#alerts"},
    requireInteraction: d.type === "alert",
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data && e.notification.data.path || "#alerts", self.registration.scope).href;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({type: "window", includeUncontrolled: true});
    for (const w of wins) {
      if (w.url.startsWith(self.registration.scope)) {
        await w.focus();
        try { await w.navigate(url); } catch (_) { w.postMessage({open: url}); }
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});

// The browser rotated the subscription: subscribe again and tell the dashboard.
self.addEventListener("pushsubscriptionchange", e => {
  e.waitUntil((async () => {
    const {publicKey} = await (await fetch("api/push/key")).json();
    const key = Uint8Array.from(atob(publicKey.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
    const sub = await self.registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: key});
    await fetch("api/push/subscribe", {method: "POST", headers: {"Content-Type": "application/json", "X-SFA": "1"},
      body: JSON.stringify({subscription: sub.toJSON(), replaces: e.oldSubscription && e.oldSubscription.endpoint})});
  })());
});
