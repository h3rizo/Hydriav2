/**
 * Gestionnaire PWA pour Hydria
 * Gère l'installation, les mises à jour et la synchronisation
 */

class PWAManager {
    constructor() {
        this.deferredPrompt = null;
        this.isOnline = navigator.onLine;
        this.syncInProgress = false;
    }

    isLocalhost() {
        const host = window.location.hostname;
        return host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    }

    /**
     * Initialiser le PWA Manager
     */
    init() {
        // Enregistrer le Service Worker
        const isLocalhost = this.isLocalhost();
        if (!isLocalhost) {
            this.registerServiceWorker();
        } else {
            this.disableServiceWorkerForLocalhost();
        }

        // Gérer le prompt d'installation
        this.handleInstallPrompt();

        // Surveiller l'état de la connexion
        this.monitorConnection();

        // Gérer les mises à jour du Service Worker
        if (!isLocalhost) {
            this.handleServiceWorkerUpdates();
        }

        // Synchroniser automatiquement quand la connexion revient
        window.addEventListener('online', () => {
            this.syncData();
        });
    }

    async disableServiceWorkerForLocalhost() {
        if (!('serviceWorker' in navigator)) {
            return;
        }

        try {
            const registrations = await navigator.serviceWorker.getRegistrations();
            await Promise.all(registrations.map((registration) => registration.unregister()));

            if ('caches' in window) {
                const cacheNames = await caches.keys();
                await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
            }

            console.log('[PWA] Localhost detecte: service worker desactive et caches vides');
        } catch (error) {
            console.warn('[PWA] Impossible de desactiver le service worker:', error);
        }
    }

    /**
     * Enregistrer le Service Worker
     */
    async registerServiceWorker() {
        if (!('serviceWorker' in navigator)) {
            console.warn('[PWA] Service Workers non supportés');
            return;
        }

        try {
            const registration = await navigator.serviceWorker.register('/static/sw.js');
            console.log('[PWA] Service Worker enregistré:', registration.scope);

            // Vérifier les mises à jour toutes les heures
            setInterval(() => {
                registration.update();
            }, 60 * 60 * 1000);

            // Écouter les messages du Service Worker
            navigator.serviceWorker.addEventListener('message', (event) => {
                this.handleServiceWorkerMessage(event.data);
            });

        } catch (error) {
            console.error('[PWA] Erreur enregistrement Service Worker:', error);
        }
    }

    /**
     * Gérer le prompt d'installation
     */
    handleInstallPrompt() {
        window.addEventListener('beforeinstallprompt', (e) => {
            // Empêcher le prompt automatique
            e.preventDefault();

            // Sauvegarder l'événement pour l'utiliser plus tard
            this.deferredPrompt = e;

            // Afficher le bouton d'installation
            this.showInstallButton();

            console.log('[PWA] Prompt d\'installation prêt');
        });

        // Détecter si l'app est installée
        window.addEventListener('appinstalled', () => {
            console.log('[PWA] Application installée avec succès');
            this.hideInstallButton();
            this.showNotification('✓ Hydria installée !', 'success');
        });
    }

    /**
     * Afficher le bouton d'installation
     */
    showInstallButton() {
        const btn = document.getElementById('pwa-install-btn');
        if (btn) {
            btn.classList.remove('hidden');
        }
    }

    /**
     * Cacher le bouton d'installation
     */
    hideInstallButton() {
        const btn = document.getElementById('pwa-install-btn');
        if (btn) {
            btn.classList.add('hidden');
        }
    }

    /**
     * Installer la PWA
     */
    async install() {
        if (!this.deferredPrompt) {
            console.warn('[PWA] Prompt d\'installation non disponible');
            return;
        }

        // Afficher le prompt d'installation
        this.deferredPrompt.prompt();

        // Attendre la réponse de l'utilisateur
        const { outcome } = await this.deferredPrompt.userChoice;

        if (outcome === 'accepted') {
            console.log('[PWA] Installation acceptée');
        } else {
            console.log('[PWA] Installation refusée');
        }

        // Réinitialiser le prompt
        this.deferredPrompt = null;
    }

    /**
     * Surveiller l'état de la connexion
     */
    monitorConnection() {
        const updateOnlineStatus = () => {
            const wasOnline = this.isOnline;
            this.isOnline = navigator.onLine;

            // Mettre à jour l'indicateur visuel
            const indicator = document.getElementById('connection-status');
            if (indicator) {
                if (this.isOnline) {
                    indicator.innerHTML = '<i class="fas fa-wifi text-success"></i> <span>En ligne</span>';
                    indicator.classList.remove('badge-error');
                    indicator.classList.add('badge-success');
                } else {
                    indicator.innerHTML = '<i class="fas fa-wifi-slash text-error"></i> <span>Hors ligne</span>';
                    indicator.classList.remove('badge-success');
                    indicator.classList.add('badge-error');
                }
            }

            // Notifier le changement
            if (this.isOnline && !wasOnline) {
                console.log('[PWA] Connexion rétablie');
                this.showNotification('🌐 Connexion rétablie', 'info');
            } else if (!this.isOnline && wasOnline) {
                console.log('[PWA] Passage en mode hors ligne');
                this.showNotification('📴 Mode hors ligne activé', 'warning');
            }
        };

        // Écouter les changements de connexion
        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);

        // Mise à jour initiale
        updateOnlineStatus();
    }

    /**
     * Gérer les mises à jour du Service Worker
     */
    handleServiceWorkerUpdates() {
        if (!('serviceWorker' in navigator)) return;

        navigator.serviceWorker.ready.then((registration) => {
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;

                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        // Nouvelle version disponible
                        this.showUpdateNotification();
                    }
                });
            });
        });
    }

    /**
     * Afficher notification de mise à jour
     */
    showUpdateNotification() {
        const updateBtn = document.createElement('button');
        updateBtn.className = 'btn btn-primary btn-sm';
        updateBtn.innerHTML = '<i class="fas fa-sync-alt mr-2"></i>Mettre à jour';
        updateBtn.onclick = () => {
            window.location.reload();
        };

        this.showNotification(
            'Une nouvelle version d\'Hydria est disponible !',
            'info',
            updateBtn
        );
    }

    /**
     * Synchroniser les données
     */
    async syncData() {
        if (!this.isOnline || this.syncInProgress) {
            return;
        }

        this.syncInProgress = true;
        console.log('[PWA] Début de la synchronisation...');

        try {
            const pendingItems = await offlineDB.getPendingSync();

            if (pendingItems.length === 0) {
                console.log('[PWA] Aucune donnée à synchroniser');
                this.syncInProgress = false;
                return;
            }

            console.log(`[PWA] ${pendingItems.length} élément(s) à synchroniser`);

            // Afficher indicateur de synchronisation
            this.showSyncIndicator(true);

            let successCount = 0;
            let errorCount = 0;

            for (const item of pendingItems) {
                try {
                    // Marquer comme en cours de synchronisation
                    item.status = 'syncing';
                    await offlineDB.save(offlineDB.stores.sync_queue, item);

                    const ok = item.type === 'releve_terrain_2steps'
                        ? await this.syncReleveTerrainDeuxEtapes(item)
                        : await this.syncItemSimple(item);

                    if (ok) {
                        await offlineDB.markAsSynced(item.id, true);
                        successCount++;
                    } else {
                        await offlineDB.markAsSynced(item.id, false, item._lastError || 'Échec synchronisation');
                        errorCount++;
                    }

                } catch (error) {
                    console.error('[PWA] Erreur synchronisation item:', error);
                    await offlineDB.markAsSynced(item.id, false, error.message);
                    errorCount++;
                }
            }

            // Notification de résultat
            if (successCount > 0) {
                this.showNotification(
                    `✓ ${successCount} élément(s) synchronisé(s)`,
                    'success'
                );
            }

            if (errorCount > 0) {
                this.showNotification(
                    `⚠ ${errorCount} erreur(s) de synchronisation`,
                    'error'
                );
            }

        } catch (error) {
            console.error('[PWA] Erreur lors de la synchronisation:', error);
            this.showNotification('Erreur de synchronisation', 'error');

        } finally {
            this.syncInProgress = false;
            this.showSyncIndicator(false);
        }
    }

    /**
     * Synchronisation "simple" : comportement historique, un seul appel
     * réseau par item (types 'planning', 'paiement', 'reparation',
     * 'livraison_bon', 'avance_bon', 'avance_detail').
     */
    async syncItemSimple(item) {
        const response = await fetch(item.endpoint, {
            method: item.action === 'delete' ? 'DELETE' : 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken')
            },
            body: JSON.stringify(item.data)
        });
        if (response.ok) return true;
        item._lastError = await response.text();
        return false;
    }

    /**
     * Synchronisation en 2 étapes pour un relevé saisi hors ligne : le
     * montant n'a jamais pu être calculé pendant la saisie (moteur
     * tarifaire serveur non reproductible en JS), donc on rejoue d'abord
     * le calcul, puis la sauvegarde avec le montant obtenu à l'instant.
     */
    async syncReleveTerrainDeuxEtapes(item) {
        const d = item.data;

        const calcResponse = await fetch('/facturation/api/calculer-facture-terrain/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken')
            },
            body: JSON.stringify({
                point_eau_id: d.point_eau_id,
                date_releve: d.date_releve,
                nouvel_index: d.nouvel_index,
                volume_facture: d.volume_facture
            })
        });
        const calcData = await calcResponse.json();
        if (!calcData.success) {
            item._lastError = 'Calcul: ' + (calcData.error || 'échec');
            return false;
        }

        const formData = new FormData();
        formData.append('point_eau_id', d.point_eau_id);
        formData.append('date_releve', d.date_releve);
        formData.append('nouvel_index', d.nouvel_index);
        formData.append('volume_non_facture', d.volume_non_facture);
        formData.append('remarque', d.remarque || '');
        formData.append('cartes_sociales', JSON.stringify(d.cartes_sociales || []));
        formData.append('montant', calcData.montant_total);
        // Pas de photo : non gérée en mode hors ligne pour cette version.

        const saveResponse = await fetch('/facturation/api/save-releve-terrain/', {
            method: 'POST',
            body: formData
            // Pas de X-CSRFToken : la route est @csrf_exempt côté serveur,
            // cohérent avec le comportement en ligne existant.
        });
        const saveData = await saveResponse.json();
        if (!saveData.success) {
            item._lastError = 'Enregistrement: ' + (saveData.error || 'échec');
            return false;
        }

        if (saveData.pending_validation) {
            this.showNotification('Relevé synchronisé, en attente de validation Directeur.', 'info');
        }
        return true;
    }

    /**
     * Afficher/cacher l'indicateur de synchronisation
     */
    showSyncIndicator(show) {
        const indicator = document.getElementById('sync-indicator');
        if (indicator) {
            if (show) {
                indicator.classList.remove('hidden');
            } else {
                indicator.classList.add('hidden');
            }
        }
    }

    /**
     * Afficher une notification toast
     */
    showNotification(message, type = 'info', action = null) {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} shadow-lg mb-2`;
        toast.innerHTML = `
            <div class="flex items-center justify-between w-full">
                <span>${message}</span>
                ${action ? '<div class="ml-4"></div>' : ''}
            </div>
        `;

        if (action) {
            toast.querySelector('.ml-4').appendChild(action);
        }

        const container = document.getElementById('toast-container') || this.createToastContainer();
        container.appendChild(toast);

        // Auto-suppression après 5 secondes
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }

    /**
     * Créer le conteneur de toasts
     */
    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed bottom-4 right-4 z-50 flex flex-col-reverse max-w-md';
        document.body.appendChild(container);
        return container;
    }

    /**
     * Récupérer un cookie
     */
    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Gérer les messages du Service Worker
     */
    handleServiceWorkerMessage(data) {
        console.log('[PWA] Message du Service Worker:', data);

        if (data.type === 'cache-updated') {
            this.showNotification('Cache mis à jour', 'success');
        }
    }

    /**
     * Vider le cache
     */
    async clearCache() {
        if (!('serviceWorker' in navigator)) return;

        const registration = await navigator.serviceWorker.ready;
        const messageChannel = new MessageChannel();

        return new Promise((resolve) => {
            messageChannel.port1.onmessage = (event) => {
                if (event.data.success) {
                    this.showNotification('Cache vidé avec succès', 'success');
                    resolve(true);
                }
            };

            registration.active.postMessage(
                { action: 'clearCache' },
                [messageChannel.port2]
            );
        });
    }
}

// Instance globale
const pwaManager = new PWAManager();

// Initialiser au chargement de la page
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => pwaManager.init());
} else {
    pwaManager.init();
}
