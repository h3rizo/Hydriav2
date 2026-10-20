/**
 * Module de gestion de la base de données IndexedDB pour mode hors ligne
 * Permet de stocker et synchroniser les données quand la connexion est rétablie
 */

class OfflineDB {
    constructor() {
        this.dbName = 'HydriaOfflineDB';
        this.version = 2;
        this.db = null;

        // Définition des stores (tables)
        this.stores = {
            releves: 'releves',              // Relevés de compteurs
            plannings: 'plannings',          // Plannings
            paiements: 'paiements',          // Paiements forfaitaires
            reparations: 'reparations',      // Réparations
            sync_queue: 'sync_queue',        // File d'attente de synchronisation
            reference_data: 'reference_data' // Données de référence préchargées (lecture seule)
        };
    }

    /**
     * Initialiser la base de données IndexedDB
     */
    async init() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);

            request.onerror = () => {
                console.error('[OfflineDB] Erreur ouverture DB:', request.error);
                reject(request.error);
            };

            request.onsuccess = () => {
                this.db = request.result;
                console.log('[OfflineDB] Base de données ouverte avec succès');
                resolve(this.db);
            };

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                console.log('[OfflineDB] Mise à niveau de la base de données');

                // Store pour les relevés
                if (!db.objectStoreNames.contains(this.stores.releves)) {
                    const relevesStore = db.createObjectStore(this.stores.releves, {
                        keyPath: 'id',
                        autoIncrement: false
                    });
                    relevesStore.createIndex('point_eau_id', 'point_eau_id', { unique: false });
                    relevesStore.createIndex('datereleve', 'datereleve', { unique: false });
                    relevesStore.createIndex('synced', 'synced', { unique: false });
                }

                // Store pour les plannings
                if (!db.objectStoreNames.contains(this.stores.plannings)) {
                    const planningsStore = db.createObjectStore(this.stores.plannings, {
                        keyPath: 'id',
                        autoIncrement: false
                    });
                    planningsStore.createIndex('employe_id', 'employe_id', { unique: false });
                    planningsStore.createIndex('date', 'date', { unique: false });
                    planningsStore.createIndex('synced', 'synced', { unique: false });
                }

                // Store pour les paiements
                if (!db.objectStoreNames.contains(this.stores.paiements)) {
                    const paiementsStore = db.createObjectStore(this.stores.paiements, {
                        keyPath: 'id',
                        autoIncrement: false
                    });
                    paiementsStore.createIndex('point_eau_id', 'point_eau_id', { unique: false });
                    paiementsStore.createIndex('synced', 'synced', { unique: false });
                }

                // Store pour les réparations
                if (!db.objectStoreNames.contains(this.stores.reparations)) {
                    const reparationsStore = db.createObjectStore(this.stores.reparations, {
                        keyPath: 'id',
                        autoIncrement: false
                    });
                    reparationsStore.createIndex('ouvrage_id', 'ouvrage_id', { unique: false });
                    reparationsStore.createIndex('synced', 'synced', { unique: false });
                }

                // Store pour la file de synchronisation
                if (!db.objectStoreNames.contains(this.stores.sync_queue)) {
                    const syncStore = db.createObjectStore(this.stores.sync_queue, {
                        keyPath: 'id',
                        autoIncrement: true
                    });
                    syncStore.createIndex('timestamp', 'timestamp', { unique: false });
                    syncStore.createIndex('type', 'type', { unique: false });
                    syncStore.createIndex('status', 'status', { unique: false });
                }

                // Store pour les données de référence préchargées (lecture seule,
                // remplacées en bloc à chaque "Préparer ma tournée" - jamais
                // synchronisées en retour, contrairement aux autres stores).
                if (!db.objectStoreNames.contains(this.stores.reference_data)) {
                    const refStore = db.createObjectStore(this.stores.reference_data, {
                        keyPath: 'uid',
                        autoIncrement: false
                    });
                    refStore.createIndex('type', 'type', { unique: false });
                    refStore.createIndex('entity_id', 'entity_id', { unique: false });
                    refStore.createIndex('preloaded_at', 'preloaded_at', { unique: false });
                }
            };
        });
    }

    /**
     * Ajouter ou mettre à jour un enregistrement
     */
    async save(storeName, data) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);

            // Ajouter timestamp et flag synced
            const record = {
                ...data,
                _offline_timestamp: new Date().toISOString(),
                synced: false
            };

            const request = store.put(record);

            request.onsuccess = () => {
                console.log(`[OfflineDB] Enregistrement sauvegardé dans ${storeName}`);
                resolve(request.result);
            };

            request.onerror = () => {
                console.error(`[OfflineDB] Erreur sauvegarde ${storeName}:`, request.error);
                reject(request.error);
            };
        });
    }

    /**
     * Récupérer un enregistrement par ID
     */
    async get(storeName, id) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.get(id);

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Récupérer tous les enregistrements d'un store
     */
    async getAll(storeName, indexName = null, value = null) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readonly');
            const store = transaction.objectStore(storeName);

            let request;
            if (indexName && value !== null) {
                const index = store.index(indexName);
                request = index.getAll(value);
            } else {
                request = store.getAll();
            }

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Supprimer un enregistrement
     */
    async delete(storeName, id) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([storeName], 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.delete(id);

            request.onsuccess = () => resolve(true);
            request.onerror = () => reject(request.error);
        });
    }

    /**
     * Ajouter une opération à la file de synchronisation
     */
    async addToSyncQueue(type, action, data, endpoint) {
        if (!this.db) await this.init();

        const syncItem = {
            type,           // 'releve', 'planning', 'paiement', etc.
            action,         // 'create', 'update', 'delete'
            data,           // Données à synchroniser
            endpoint,       // URL de l'API
            timestamp: new Date().toISOString(),
            status: 'pending',  // 'pending', 'syncing', 'success', 'error'
            attempts: 0,
            lastError: null
        };

        return this.save(this.stores.sync_queue, syncItem);
    }

    /**
     * Récupérer les éléments en attente de synchronisation
     */
    async getPendingSync() {
        return this.getAll(this.stores.sync_queue, 'status', 'pending');
    }

    /**
     * Marquer un élément comme synchronisé
     */
    async markAsSynced(syncId, success = true, error = null) {
        const item = await this.get(this.stores.sync_queue, syncId);
        if (!item) return;

        item.status = success ? 'success' : 'error';
        item.lastError = error;
        item.attempts++;

        if (success && item.type && item.data && item.data.id) {
            // Marquer l'enregistrement original comme synchronisé, si un
            // store dédié existe pour ce type. Certains types (ex.
            // 'livraison_bon', 'avance_bon', 'avance_detail',
            // 'releve_terrain_2steps') n'ont pas de store dédié : sync_queue
            // reste alors la seule source de vérité, on ne tente rien de plus.
            const storeName = this.stores[item.type + 's'];
            if (storeName && this.db.objectStoreNames.contains(storeName)) {
                const originalRecord = await this.get(storeName, item.data.id);
                if (originalRecord) {
                    originalRecord.synced = true;
                    await this.save(storeName, originalRecord);
                }
            }
        }

        return this.save(this.stores.sync_queue, item);
    }

    /**
     * Remplace entièrement les données de référence d'un type donné
     * (préchargement de tournée : remplacement en bloc, pas de merge).
     */
    async replaceReferenceData(type, items) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.stores.reference_data], 'readwrite');
            const store = transaction.objectStore(this.stores.reference_data);
            const index = store.index('type');
            const keysRequest = index.getAllKeys(type);

            keysRequest.onsuccess = () => {
                keysRequest.result.forEach((key) => store.delete(key));

                const now = new Date().toISOString();
                (items || []).forEach((item) => {
                    store.put({
                        uid: `${type}:${item.id}`,
                        type,
                        entity_id: item.id,
                        data: item,
                        preloaded_at: now
                    });
                });
            };
            keysRequest.onerror = () => reject(keysRequest.error);

            transaction.oncomplete = () => resolve(true);
            transaction.onerror = () => reject(transaction.error);
        });
    }

    /**
     * Récupère toutes les entrées de référence d'un type
     * ('point_eau', 'planning', 'reparation', 'tarif').
     */
    async getReferenceData(type) {
        return this.getAll(this.stores.reference_data, 'type', type);
    }

    /**
     * Récupère une entrée de référence précise par type + entity_id.
     */
    async getReferenceItem(type, entityId) {
        return this.get(this.stores.reference_data, `${type}:${entityId}`);
    }

    /**
     * Vider tous les stores
     */
    async clearAll() {
        if (!this.db) await this.init();

        const storeNames = Object.values(this.stores);

        return Promise.all(
            storeNames.map(storeName => {
                return new Promise((resolve, reject) => {
                    const transaction = this.db.transaction([storeName], 'readwrite');
                    const store = transaction.objectStore(storeName);
                    const request = store.clear();

                    request.onsuccess = () => {
                        console.log(`[OfflineDB] Store ${storeName} vidé`);
                        resolve(true);
                    };
                    request.onerror = () => reject(request.error);
                });
            })
        );
    }

    /**
     * Obtenir des statistiques sur les données en cache
     */
    async getStats() {
        if (!this.db) await this.init();

        const stats = {};

        for (const [key, storeName] of Object.entries(this.stores)) {
            const all = await this.getAll(storeName);
            const unsynced = all.filter(item => !item.synced);

            stats[key] = {
                total: all.length,
                unsynced: unsynced.length,
                synced: all.length - unsynced.length
            };
        }

        return stats;
    }
}

// Instance globale
const offlineDB = new OfflineDB();

// Initialiser au chargement
if ('indexedDB' in window) {
    offlineDB.init().catch(err => {
        console.error('[OfflineDB] Erreur initialisation:', err);
    });
}
