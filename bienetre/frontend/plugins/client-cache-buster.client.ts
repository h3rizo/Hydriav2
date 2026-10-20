const APP_STORAGE_VERSION = "2026-06-24-cache-buster-1"
const APP_STORAGE_KEY = "hydria-app-version"

async function clearBrowserCaches() {
  if ("caches" in window) {
    try {
      const cacheKeys = await window.caches.keys()
      await Promise.all(cacheKeys.map((key) => window.caches.delete(key)))
    } catch {
      // Ignore cache API failures and continue with the app boot.
    }
  }

  if ("serviceWorker" in navigator) {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrations.map((registration) => registration.unregister()))
    } catch {
      // Ignore service worker cleanup failures.
    }
  }
}

export default defineNuxtPlugin(async () => {
  if (!import.meta.client) {
    return
  }

  const storedVersion = window.localStorage.getItem(APP_STORAGE_KEY)
  if (storedVersion === APP_STORAGE_VERSION) {
    return
  }

  window.localStorage.setItem(APP_STORAGE_KEY, APP_STORAGE_VERSION)

  try {
    window.sessionStorage.clear()
  } catch {
    // Session storage may be blocked; this is non-fatal.
  }

  await clearBrowserCaches()

  // One clean reload removes stale chunks from normal browser sessions.
  window.location.reload()
})
