// Roast push service worker.
// Two jobs only: show a notification when a push arrives, and focus/open
// the app when the user clicks it. No caching, no offline support -- this
// is not a PWA shell, just the minimum a browser requires to deliver Web
// Push to a page that isn't currently open.

self.addEventListener("push", (event) => {
  let payload = { title: "Roast", body: "You have a new notification.", url: "/dashboard" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch (e) {
    // Malformed payload -- fall back to the generic message above rather
    // than showing nothing at all.
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/logo.png",
      badge: "/logo.png",
      data: { url: payload.url || "/dashboard" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || "/dashboard";

  event.waitUntil(
    (async () => {
      const allClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
      // Reuse an already-open Roast tab if there is one, rather than
      // always spawning a new one.
      for (const client of allClients) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      return clients.openWindow(targetUrl);
    })()
  );
});
