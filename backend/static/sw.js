// Service Worker pour Hydria PWA
// Version du cache - à incrémenter à chaque mise à jour importante
const CACHE_VERSION = 'hydria-v1.2.1';
const CACHE_STATIC = `${CACHE_VERSION}-static`;
const CACHE_DYNAMIC = `${CACHE_VERSION}-dynamic`;
const CACHE_API = `${CACHE_VERSION}-api`;

// Fichiers à mettre en cache immédiatement lors de l'installation
const STATIC_FILES = [
    '/',
    '/recherche/',
    '/plannings/',
    '/plannings/reparations/',
    '/facturation/releves/',
    '/facturation/cartes-sociales/',
    '/facturation/cartes-sociales/encaissement/',
    '/geography/capture-donnees/',
    '/organisations/ouvrages/',
    '/organisations/points-eau/',
    '/organisations/equipements/',
    '/feed/',
    '/comptabilite/',
    '/employes/',
    '/static/css/hydria.css',
    '/static/js/offline-db.js',
    '/static/js/pwa-manager.js',
    '/static/js/tournee-manager.js',
    '/static/images/icons/icon-192x192.png',
    '/static/images/icons/icon-512x512.png',
    '/offline/',
];

// Taille maximale du cache dynamique
const DYNAMIC_CACHE_LIMIT = 50;

// Installation du Service Worker
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installation en cours...');

    event.waitUntil(
        caches.open(CACHE_STATIC)
            .then((cache) => {
                console.log('[Service Worker] Mise en cache des fichiers statiques');
                return Promise.allSettled(
                    STATIC_FILES.map(async (url) => {
                        try {
                            await cache.add(url);
                        } catch (error) {
                            console.warn(`[Service Worker] Fichier ignoré lors du précache : ${url}`, error);
                        }
                    })
                );
            })
            .catch((err) => {
                console.error('[Service Worker] Erreur lors de la mise en cache:', err);
            })
    );

    // Force l'activation immédiate
    self.skipWaiting();
});

// Activation du Service Worker
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activation en cours...');

    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    // Supprimer les anciens caches
                    if (cacheName !== CACHE_STATIC &&
                        cacheName !== CACHE_DYNAMIC &&
                        cacheName !== CACHE_API &&
                        cacheName.startsWith('hydria-')) {
                        console.log('[Service Worker] Suppression ancien cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );

    // Prendre le contrôle immédiatement
    return self.clients.claim();
});

// Limiter la taille du cache dynamique
function limitCacheSize(cacheName, maxItems) {
    caches.open(cacheName).then((cache) => {
        cache.keys().then((keys) => {
            if (keys.length > maxItems) {
                cache.delete(keys[0]).then(() => {
                    limitCacheSize(cacheName, maxItems);
                });
            }
        });
    });
}

// Stratégie de cache selon le type de requête
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    const isLocalhost = url.hostname === 'localhost' || url.hostname === '127.0.0.1';

    // Ignorer les requêtes non-HTTP/HTTPS
    if (!request.url.startsWith('http')) {
        return;
    }

    if (isLocalhost && request.method === 'GET') {
        event.respondWith(
            fetch(request).catch(() => caches.match(request))
        );
        return;
    }

    // Ignorer les requêtes vers des domaines externes (sauf CDN)
    if (url.origin !== location.origin &&
        !url.hostname.includes('cdnjs.cloudflare.com') &&
        !url.hostname.includes('fonts.googleapis.com')) {
        return;
    }

    // **Stratégie 1: Cache-First pour fichiers statiques**
    if (request.destination === 'style' ||
        request.destination === 'script' ||
        request.destination === 'font' ||
        request.destination === 'image') {

        event.respondWith(
            caches.match(request).then((response) => {
                if (response) {
                    // Fichier trouvé dans le cache
                    return response;
                }

                // Sinon, récupérer depuis le réseau et mettre en cache
                return fetch(request).then((networkResponse) => {
                    return caches.open(CACHE_STATIC).then((cache) => {
                        cache.put(request, networkResponse.clone());
                        return networkResponse;
                    });
                }).catch(() => {
                    // Fichier statique introuvable en cache et hors ligne :
                    // pas de fallback pertinent pour un style/script/image.
                });
            })
        );
        return;
    }

    // **Stratégie 2: Network-First pour pages HTML (documents)**
    // DOIT être testée avant la stratégie API (ci-dessous) : une navigation
    // vers /plannings/... ou /comptabilite/... a request.destination ===
    // 'document', et ne doit jamais être interceptée comme un appel API
    // (sinon fallback direct vers /offline/ sans jamais tenter le cache
    // dynamique ni un app shell minimal).
    if (request.destination === 'document') {
        event.respondWith(
            fetch(request).then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200) {
                    const cacheResponse = networkResponse.clone();
                    caches.open(CACHE_DYNAMIC).then((cache) => {
                        cache.put(request, cacheResponse);
                        limitCacheSize(CACHE_DYNAMIC, DYNAMIC_CACHE_LIMIT);
                    });
                }
                return networkResponse;
            }).catch(() => offlineDocumentFallback(request))
        );
        return;
    }

    // **Stratégie 3: Network-First pour APIs JSON (avec cache fallback)**
    // request.destination === '' ici (fetch/XHR) : la stratégie 2 ci-dessus
    // a déjà intercepté toute navigation de page, donc plus de risque de
    // confondre une page HTML avec un appel API.
    if (url.pathname.startsWith('/api/') ||
        url.pathname.includes('/plannings/') ||
        url.pathname.includes('/comptabilite/')) {

        event.respondWith(
            fetch(request).then((networkResponse) => {
                // Mettre en cache seulement les GET requests réussies
                if (request.method === 'GET' && networkResponse.status === 200) {
                    return caches.open(CACHE_API).then((cache) => {
                        cache.put(request, networkResponse.clone());
                        limitCacheSize(CACHE_API, DYNAMIC_CACHE_LIMIT);
                        return networkResponse;
                    });
                }
                return networkResponse;
            }).catch(() => {
                // Si offline, essayer de retourner depuis le cache
                return caches.match(request).then((cachedResponse) => {
                    if (cachedResponse) {
                        console.log('[Service Worker] Données servies depuis le cache (mode offline)');
                        return cachedResponse;
                    }

                    // Erreur JSON explicite (jamais de cas 'document' ici,
                    // structurellement impossible depuis la stratégie 2).
                    return new Response(
                        JSON.stringify({
                            error: 'offline',
                            message: 'Vous êtes hors ligne. Cette donnée n\'est pas disponible en cache.'
                        }),
                        {
                            status: 503,
                            headers: { 'Content-Type': 'application/json' }
                        }
                    );
                });
            })
        );
        return;
    }

    // **Stratégie 4: Network-Only pour tout le reste (POST, PUT, DELETE)**
    event.respondWith(fetch(request));
});

// Fallback pour une navigation de page échouée hors ligne : essaie
// d'abord la page elle-même (déjà visitée -> en cache dynamique), sinon
// la page d'accueil déjà précachée en tant que quasi app-shell (Hydria
// est du Django rendu serveur, pas une SPA - ce n'est pas un vrai app
// shell générique, juste la page la plus susceptible d'être en cache),
// sinon en dernier recours la page /offline/ dédiée.
async function offlineDocumentFallback(request) {
    const cachedResponse = await caches.match(request, { ignoreSearch: false });
    if (cachedResponse) return cachedResponse;

    const appShell = await caches.match('/');
    if (appShell) return appShell;

    return caches.match('/offline/');
}

// Gestion des messages du client
self.addEventListener('message', (event) => {
    if (event.data.action === 'skipWaiting') {
        self.skipWaiting();
    }

    if (event.data.action === 'clearCache') {
        event.waitUntil(
            caches.keys().then((cacheNames) => {
                return Promise.all(
                    cacheNames.map((cacheName) => {
                        if (cacheName.startsWith('hydria-')) {
                            return caches.delete(cacheName);
                        }
                    })
                );
            }).then(() => {
                event.ports[0].postMessage({ success: true });
            })
        );
    }
});

// Synchronisation en arrière-plan (Background Sync)
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-data') {
        event.waitUntil(syncData());
    }
});

async function syncData() {
    console.log('[Service Worker] Synchronisation des données...');
    // TODO: Implémenter la logique de synchronisation
    // - Récupérer les données en attente depuis IndexedDB
    // - Envoyer au serveur
    // - Marquer comme synchronisées
}
