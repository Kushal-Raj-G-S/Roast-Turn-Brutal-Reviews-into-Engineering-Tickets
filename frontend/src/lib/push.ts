/**
 * Browser Web Push helpers -- self-hosted VAPID keypair, no third-party
 * push service (no Firebase, no OneSignal). The public key is baked in at
 * build time via NEXT_PUBLIC_VAPID_PUBLIC_KEY; the private key never
 * leaves the backend.
 */

export function isPushSupported(): boolean {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window;
}

// PushManager.subscribe() needs the VAPID public key as a raw Uint8Array,
// not the base64url string it's distributed as.
function urlBase64ToUint8Array(base64Url: string): Uint8Array {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const output = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) output[i] = rawData.charCodeAt(i);
  return output;
}

export async function getExistingSubscription(): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null;
  const reg = await navigator.serviceWorker.getRegistration("/sw.js");
  if (!reg) return null;
  return reg.pushManager.getSubscription();
}

/**
 * Requests notification permission, registers the service worker, and
 * subscribes. Throws with a human-readable message on any failure (denied
 * permission, unsupported browser, missing VAPID key) -- the caller is
 * expected to surface that directly rather than fail silently, since this
 * is a deliberate user action (flipping a toggle), not a background task.
 */
export async function subscribeToPush(): Promise<PushSubscription> {
  if (!isPushSupported()) {
    throw new Error("This browser doesn't support push notifications.");
  }
  const vapidKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
  if (!vapidKey) {
    throw new Error("Push isn't configured on this deployment yet.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notification permission was denied.");
  }

  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const existing = await reg.pushManager.getSubscription();
  if (existing) return existing;

  return reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidKey) as BufferSource,
  });
}

export async function unsubscribeFromPush(): Promise<string | null> {
  const sub = await getExistingSubscription();
  if (!sub) return null;
  const endpoint = sub.endpoint;
  await sub.unsubscribe();
  return endpoint;
}
