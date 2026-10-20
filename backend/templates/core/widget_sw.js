// Service Worker dédié au widget météo Hydria.
// Scope volontairement limité à /widget/ (voir header Service-Worker-Allowed
// envoyé par la vue Django) — n'interfère pas avec le reste du site.

const CACHE_NAME = 'hydria-widgets-v2';
const APP_SHELL = [
  '/widget/',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Page principale du widget : network-first, repli sur le cache si hors-ligne.
  if (url.pathname === '/widget/') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Tout le reste (API météo externe, géocodage, API Hydria) : passe au
  // réseau directement, pas de cache — ce sont des données temps réel.
});
