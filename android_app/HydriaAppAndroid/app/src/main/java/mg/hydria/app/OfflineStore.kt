package mg.hydria.app

import android.content.Context
import mg.hydria.shared.database.HydriaAndroidDatabase
import mg.hydria.shared.database.HydriaCalculatorGateway
import mg.hydria.shared.database.HydriaGeoGateway
import mg.hydria.shared.database.HydriaSearchCacheGateway
import mg.hydria.shared.database.HydriaSnapshotGateway
import mg.hydria.shared.database.HydriaSyncQueueGateway
import mg.hydria.shared.database.HydriaVolumeCacheGateway
import mg.hydria.shared.network.HydriaOperationsGateway
import mg.hydria.app.network.SessionNetworkRoute
import org.json.JSONArray
import org.json.JSONObject

class OfflineStore(context: Context) {
    companion object {
        // Initialisation unique au premier store, sans requete reseau.
        internal val searchNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val calculatorNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val terrainNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val planningNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val repairsNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val readingsNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val interventionsNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val volumeNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }
        internal val navigationNetwork = SessionNetworkRoute { HydriaOperationsGateway.probe() }

        // Snapshot décodé gardé en mémoire pour tout le processus : le décoder à chaque
        // lecture (plusieurs Mo de JSON, des dizaines d'appels) bloquait le fil
        // principal au démarrage -> ANR « l'application se ferme ».
        private val snapshotLock = Any()
        private var cachedSnapshot: JSONObject? = null
        private var snapshotLoaded = false

        /** Décode le snapshot hors du fil principal (pendant l'animation d'IntroActivity). */
        fun preloadSnapshot(context: Context) {
            val store = OfflineStore(context)
            Thread({ runCatching { store.snapshot } }, "hydria-snapshot-preload").start()
        }
    }

    private val appContext = context.applicationContext
    private val preferences = context.getSharedPreferences("hydria_terrain", Context.MODE_PRIVATE)
    private val database = TerrainDatabase(context.applicationContext)

    init {
        if (!preferences.getBoolean("sqlite_migrated", false)) {
            preferences.getString("snapshot", null)?.let { raw ->
                runCatching { database.saveSnapshot(JSONObject(raw)) }
            }
            preferences.getString("pending", null)?.let { raw ->
                runCatching {
                    val legacy = JSONArray(raw)
                    for (index in 0 until legacy.length()) {
                        val item = legacy.getJSONObject(index)
                        database.enqueue(item.optString("type"), item.optJSONObject("payload") ?: JSONObject())
                    }
                }
            }
            preferences.edit().remove("snapshot").remove("pending").putBoolean("sqlite_migrated", true).commit()
        }
        database.recoverInterrupted()
    }

    /**
     * Migration unique (au demarrage) de la file de synchronisation depuis
     * TerrainDatabase (SQLite historique, app/) vers HydriaSyncQueueGateway
     * (SQLDelight, shared/) : suit le meme principe que la migration
     * "sqlite_migrated" ci-dessus (flag SharedPreferences + runCatching).
     *
     * Consigne explicite : si la migration echoue pour quelque raison que ce
     * soit, on reste sur l'ancienne base TOUT DU LONG pour cette session -
     * jamais de melange ancienne/nouvelle base en cours de route. D'ou le
     * runCatching global : la moindre exception fait retomber [useNewSyncQueue]
     * a false et TOUTES les operations (pas seulement celle qui a echoue)
     * continuent de passer par [database].
     */
    private fun migrateSyncQueueIfNeeded(): Boolean = runCatching {
        HydriaAndroidDatabase.init(appContext)
        if (!preferences.getBoolean("sync_queue_migrated_v2", false)) {
            val legacy = database.pending()
            for (index in 0 until legacy.length()) {
                val item = legacy.getJSONObject(index)
                val localUuid = item.getString("local_uuid")
                val type = item.optString("type")
                val payload = item.optJSONObject("payload") ?: JSONObject()
                HydriaSyncQueueGateway.enqueueIfAbsent(localUuid, type, payload)
            }
            preferences.edit().putBoolean("sync_queue_migrated_v2", true).commit()
        }
        HydriaSyncQueueGateway.recoverInterrupted()
        true
    }.getOrDefault(false)

    /**
     * true si la migration a reussi et que la file de synchronisation doit
     * desormais passer par HydriaSyncQueueGateway ; false si on reste sur
     * TerrainDatabase (soit parce que la migration a echoue, soit - le cas
     * normal apres une premiere migration reussie - simplement pour retenter
     * l'init/recover a chaque demarrage sans jamais rejouer la copie).
     */
    private val useNewSyncQueue: Boolean = migrateSyncQueueIfNeeded()

    /**
     * Cache de recherche : simple cache jetable, aucune migration de donnees
     * necessaire (contrairement a syncQueue) - un cache vide au demarrage est
     * un etat normal, repeuple au prochain appel reseau. On se contente donc
     * de verifier que le backend partage est utilisable (runCatching), avec
     * le meme principe de repli total sur TerrainDatabase en cas d'echec.
     */
    private val useNewSearchCache: Boolean = runCatching {
        HydriaAndroidDatabase.init(appContext)
        true
    }.getOrDefault(false)

    /**
     * Snapshot de prechargement offline : migration unique au demarrage (une
     * seule valeur a copier, contrairement a la file syncQueue) puis routage
     * get/set vers HydriaSnapshotGateway - meme principe de repli total sur
     * TerrainDatabase pour toute la session en cas d'echec de la migration.
     */
    private fun migrateSnapshotIfNeeded(): Boolean = runCatching {
        HydriaAndroidDatabase.init(appContext)
        if (!preferences.getBoolean("snapshot_migrated_v2", false)) {
            HydriaSnapshotGateway.saveSnapshot(database.snapshot())
            preferences.edit().putBoolean("snapshot_migrated_v2", true).commit()
        }
        true
    }.getOrDefault(false)

    private val useNewSnapshot: Boolean = migrateSnapshotIfNeeded()

    /**
     * Calculatrice de salaire : migration unique du brouillon existant
     * (calculator_state, toutes les cles de compte confondues - contrairement
     * a la migration syncQueue/snapshot qui ne connait qu'un seul compte a la
     * fois, un utilisateur peut avoir bascule entre plusieurs comptes). Le
     * bareme serveur (salary_calculation_config) n'a pas besoin d'etre migre :
     * c'est un cache resynchronise par checksum, jamais des donnees saisies
     * localement. Meme filet de secours que les autres tables.
     */
    private fun migrateCalculatorIfNeeded(): Boolean = runCatching {
        HydriaAndroidDatabase.init(appContext)
        if (!preferences.getBoolean("calculator_migrated_v2", false)) {
            database.readableDatabase.rawQuery("SELECT account_key, payload FROM calculator_state", null).use { cursor ->
                while (cursor.moveToNext()) {
                    val key = cursor.getString(0)
                    val payload = runCatching { JSONObject(cursor.getString(1)) }.getOrNull()
                    if (key.isNullOrBlank() || payload == null) continue
                    HydriaCalculatorGateway.saveState(key, payload)
                }
            }
            preferences.edit().putBoolean("calculator_migrated_v2", true).commit()
        }
        true
    }.getOrDefault(false)

    private val useNewCalculator: Boolean = migrateCalculatorIfNeeded()

    /**
     * Cache volumetrique (packs de factures, recapitulatifs, audit) :
     * migration unique de toutes les entrees existantes (tous comptes
     * confondus, meme raisonnement que pour Calculator). Note d'architecture :
     * VolumeRepository.kt combinait auparavant ces ecritures et
     * store.enqueue()/store.remove() dans une meme transaction SQLite brute
     * pour obtenir une atomicite complete - cette garantie ne tient plus
     * telle quelle des lors que syncQueue et volumeCache peuvent vivre sur
     * des connexions differentes (ancienne base vs base partagee). On accepte
     * cette degradation (deja presente depuis la bascule syncQueue) : les
     * ecritures groupees purement locales (ex: un pack de factures) restent
     * atomiques via [HydriaVolumeCacheGateway.writeBatch], mais la
     * combinaison avec l'enqueue de synchronisation ne l'est plus - sans
     * consequence fonctionnelle grave car ces lectures locales ont toutes un
     * repli gracieux (cf. VolumeRepository.accept/syncOne).
     */
    private fun migrateVolumeCacheIfNeeded(): Boolean = runCatching {
        HydriaAndroidDatabase.init(appContext)
        if (!preferences.getBoolean("volume_cache_migrated_v2", false)) {
            database.readableDatabase.rawQuery("SELECT account, cache_key, payload FROM volume_cache", null).use { cursor ->
                while (cursor.moveToNext()) {
                    val account = cursor.getString(0)
                    val key = cursor.getString(1)
                    val payload = runCatching { JSONObject(cursor.getString(2)) }.getOrNull()
                    if (account.isNullOrBlank() || key.isNullOrBlank() || payload == null) continue
                    HydriaVolumeCacheGateway.write(account, key, payload)
                }
            }
            preferences.edit().putBoolean("volume_cache_migrated_v2", true).commit()
        }
        true
    }.getOrDefault(false)

    private val useNewVolumeCache: Boolean = migrateVolumeCacheIfNeeded()

    /**
     * Navigation/GPS (geo_entities, geo_landmark_types, geo_position_history,
     * geo_placement_candidates) : migration unique de toutes les lignes
     * existantes, copie fidele (etat de sync/archivage preserve via
     * seedEntity/seedPositionHistory - PAS via upsertServerEntity, qui
     * forcerait sync_state='synced' et perdrait une capture GPS en attente
     * de synchronisation). Donnee la plus sensible de toute la migration
     * (positions de terrain, marquage de points d'eau) : filet de secours
     * identique aux autres tables.
     */
    private fun migrateGeoIfNeeded(): Boolean = runCatching {
        HydriaAndroidDatabase.init(appContext)
        if (!preferences.getBoolean("geo_migrated_v2", false)) {
            database.readableDatabase.rawQuery(
                """SELECT entity_id,category,name,type_label,code,ouvrage_id,latitude,longitude,altitude,
                          accuracy_m,capture_method,captured_at,server_updated_at,local_updated_at,
                          sync_state,is_archived,is_field_marker
                   FROM geo_entities""".trimIndent(), null,
            ).use { cursor ->
                while (cursor.moveToNext()) {
                    HydriaGeoGateway.seedEntity(
                        entityId = cursor.getString(0), category = cursor.getString(1), name = cursor.getString(2),
                        typeLabel = cursor.getString(3), code = cursor.getString(4), ouvrageId = cursor.getString(5),
                        latitude = if (cursor.isNull(6)) null else cursor.getDouble(6),
                        longitude = if (cursor.isNull(7)) null else cursor.getDouble(7),
                        altitude = if (cursor.isNull(8)) null else cursor.getDouble(8),
                        accuracyM = if (cursor.isNull(9)) null else cursor.getDouble(9),
                        captureMethod = cursor.getString(10), capturedAt = cursor.getString(11),
                        serverUpdatedAt = cursor.getString(12), localUpdatedAt = cursor.getLong(13),
                        syncState = cursor.getString(14) ?: "synced", isArchived = cursor.getInt(15) == 1,
                        isFieldMarker = cursor.getInt(16) == 1,
                    )
                }
            }
            database.readableDatabase.rawQuery(
                "SELECT id,name,description,icon_key,color_hex,display_order,is_active,server_updated_at FROM geo_landmark_types", null,
            ).use { cursor ->
                while (cursor.moveToNext()) {
                    HydriaGeoGateway.upsertServerLandmarkType(
                        serverId = cursor.getString(0), name = cursor.getString(1), description = cursor.getString(2),
                        iconKey = cursor.getString(3), colorHex = cursor.getString(4), displayOrder = cursor.getLong(5),
                        isActive = cursor.getInt(6) == 1, serverUpdatedAt = cursor.getString(7),
                    )
                }
            }
            database.readableDatabase.rawQuery(
                """SELECT local_uuid,entity_kind,entity_id,old_latitude,old_longitude,new_latitude,new_longitude,
                          altitude,accuracy_m,capture_method,captured_at,sync_state,created_at
                   FROM geo_position_history""".trimIndent(), null,
            ).use { cursor ->
                while (cursor.moveToNext()) {
                    HydriaGeoGateway.seedPositionHistory(
                        localUuid = cursor.getString(0), entityKind = cursor.getString(1), entityId = cursor.getString(2),
                        oldLatitude = if (cursor.isNull(3)) null else cursor.getDouble(3),
                        oldLongitude = if (cursor.isNull(4)) null else cursor.getDouble(4),
                        newLatitude = cursor.getDouble(5), newLongitude = cursor.getDouble(6),
                        altitude = if (cursor.isNull(7)) null else cursor.getDouble(7),
                        accuracyM = if (cursor.isNull(8)) null else cursor.getDouble(8),
                        captureMethod = cursor.getString(9), capturedAt = cursor.getString(10),
                        syncState = cursor.getString(11) ?: "pending", createdAt = cursor.getLong(12),
                    )
                }
            }
            database.readableDatabase.rawQuery(
                """SELECT entity_id,category,name,code,village_name,reference_latitude,reference_longitude,
                          has_photo,served_village_ids,ouvrage_id,server_updated_at
                   FROM geo_placement_candidates""".trimIndent(), null,
            ).use { cursor ->
                while (cursor.moveToNext()) {
                    HydriaGeoGateway.upsertPlacementCandidate(
                        entityId = cursor.getString(0), category = cursor.getString(1), name = cursor.getString(2),
                        code = cursor.getString(3), villageName = cursor.getString(4),
                        referenceLatitude = if (cursor.isNull(5)) null else cursor.getDouble(5),
                        referenceLongitude = if (cursor.isNull(6)) null else cursor.getDouble(6),
                        hasPhoto = cursor.getInt(7) == 1, servedVillageIds = cursor.getString(8),
                        ouvrageId = cursor.getString(9), serverUpdatedAt = cursor.getString(10),
                    )
                }
            }
            preferences.edit().putBoolean("geo_migrated_v2", true).commit()
        }
        true
    }.getOrDefault(false)

    private val useNewGeo: Boolean = migrateGeoIfNeeded()

    /**
     * Transport reseau du domaine Terrain (prepareTour + saveTerrainItem,
     * endpoints apps/planning/views_preparation_tournee.py) : bascule vers le
     * client Ktor partage (HydriaOperationsGateway) au lieu de HydriaApi
     * (HttpURLConnection). Meme discipline que les tables locales ci-dessus -
     * decide UNE fois au demarrage (runCatching + getOrDefault(false)) : ici
     * rien a migrer, une simple sonde (creation/fermeture d'un client Ktor)
     * suffit. Si une exception Ktor survient malgre tout en cours de session,
     * [disableNewTerrainNetwork] l'eteint definitivement et TOUS les appels
     * Terrain repassent par HydriaApi pour le reste de la session - jamais de
     * melange en cours de route. Une simple erreur HTTP non-2xx ne bascule
     * PAS : c'est une condition serveur, identique sur les deux transports.
     */
    val useNewTerrainNetwork: Boolean get() = terrainNetwork.enabled
    fun disableNewTerrainNetwork() = terrainNetwork.disable()

    val useNewPlanningNetwork: Boolean get() = planningNetwork.enabled
    fun disableNewPlanningNetwork() = planningNetwork.disable()

    val useNewRepairsNetwork: Boolean get() = repairsNetwork.enabled
    fun disableNewRepairsNetwork() = repairsNetwork.disable()

    val useNewReadingsNetwork: Boolean get() = readingsNetwork.enabled
    fun disableNewReadingsNetwork() = readingsNetwork.disable()

    val useNewInterventionsNetwork: Boolean get() = interventionsNetwork.enabled
    fun disableNewInterventionsNetwork() = interventionsNetwork.disable()

    val useNewVolumeNetwork: Boolean get() = volumeNetwork.enabled
    fun disableNewVolumeNetwork() = volumeNetwork.disable()

    val useNewNavigationNetwork: Boolean get() = navigationNetwork.enabled
    fun disableNewNavigationNetwork() = navigationNetwork.disable()


    val useNewSearchNetwork: Boolean get() = searchNetwork.enabled
    fun disableNewSearchNetwork() = searchNetwork.disable()

    val useNewCalculatorNetwork: Boolean get() = calculatorNetwork.enabled
    fun disableNewCalculatorNetwork() = calculatorNetwork.disable()

    var token: String?
        get() = preferences.getString("token", null)
        set(value) = preferences.edit().putString("token", value).apply()

    var employeeName: String
        get() = preferences.getString("employee_name", "Agent terrain") ?: "Agent terrain"
        set(value) = preferences.edit().putString("employee_name", value).apply()

    var accountKey: String
        get() = preferences.getString("account_key", "") ?: ""
        set(value) = preferences.edit().putString("account_key", value.trim().lowercase()).apply()

    /** Total de points Terrain (serveur) et dernier total affiche, par compte : sert au compteur animé. */
    var terrainPoints: Int
        get() = preferences.getInt("terrain_points_$accountKey", 0)
        set(value) = preferences.edit().putInt("terrain_points_$accountKey", value).apply()

    var terrainPointsShown: Int
        get() = preferences.getInt("terrain_points_shown_$accountKey", 0)
        set(value) = preferences.edit().putInt("terrain_points_shown_$accountKey", value).apply()

    var terrainRank: Int
        get() = preferences.getInt("terrain_rank_$accountKey", 0)
        set(value) = preferences.edit().putInt("terrain_rank_$accountKey", value).apply()

    var salaryConfigNotice: String
        get() = preferences.getString("salary_config_notice", "") ?: ""
        set(value) = preferences.edit().putString("salary_config_notice", value).apply()

    /**
     * Campagne de relevé en cours (ouvrage, nom, date ISO) : mémorisée pour survivre à la fermeture de
     * l'appli ou à la mort du processus. Propre au compte, effacée à la déconnexion (clearSession).
     * Un ouvrage ou une date vide efface la mémorisation.
     */
    fun saveCampaign(ouvrageId: String?, ouvrageNom: String?, date: String?) {
        val editor = preferences.edit()
        if (ouvrageId.isNullOrBlank() || date.isNullOrBlank()) {
            editor.remove("campaign_ouvrage_id_$accountKey").remove("campaign_ouvrage_nom_$accountKey")
                .remove("campaign_date_$accountKey")
        } else {
            editor.putString("campaign_ouvrage_id_$accountKey", ouvrageId)
                .putString("campaign_ouvrage_nom_$accountKey", ouvrageNom.orEmpty())
                .putString("campaign_date_$accountKey", date)
        }
        editor.apply()
    }

    /** (identifiant de l'ouvrage, nom, date ISO) de la campagne mémorisée, ou null. */
    fun savedCampaign(): Triple<String, String, String>? {
        val id = preferences.getString("campaign_ouvrage_id_$accountKey", null)?.takeIf { it.isNotBlank() } ?: return null
        val date = preferences.getString("campaign_date_$accountKey", null)?.takeIf { it.isNotBlank() } ?: return null
        return Triple(id, preferences.getString("campaign_ouvrage_nom_$accountKey", null).orEmpty(), date)
    }

    private fun readingDraftsKey(campaignKey: String) = "reading_drafts_$accountKey|$campaignKey"

    /**
     * Brouillons de saisie d'une campagne de relevés (JSON de ReadingDraftBook), propres au compte et à la
     * campagne (clé « ouvrage|date »), dans les mêmes préférences que saveCampaign. Le contenu est interprété,
     * purgé et validé par ReadingDraftBook.fromJson : ici ce n'est qu'un texte. Effacés par clearSession().
     */
    fun readingDrafts(campaignKey: String): String? =
        preferences.getString(readingDraftsKey(campaignKey), null)?.takeIf { it.isNotBlank() }

    /** Un JSON vide efface les brouillons de la campagne. */
    fun saveReadingDrafts(campaignKey: String, json: String) {
        if (json.isBlank()) clearReadingDrafts(campaignKey)
        else preferences.edit().putString(readingDraftsKey(campaignKey), json).apply()
    }

    fun clearReadingDrafts(campaignKey: String) {
        preferences.edit().remove(readingDraftsKey(campaignKey)).apply()
    }

    var snapshot: JSONObject?
        get() = synchronized(snapshotLock) {
            if (!snapshotLoaded) {
                cachedSnapshot = if (useNewSnapshot) HydriaSnapshotGateway.snapshot() else database.snapshot()
                snapshotLoaded = true
            }
            cachedSnapshot
        }
        set(value) = synchronized(snapshotLock) {
            if (useNewSnapshot) HydriaSnapshotGateway.saveSnapshot(value) else database.saveSnapshot(value)
            cachedSnapshot = value
            snapshotLoaded = true
        }

    fun pending(): JSONArray = if (useNewSyncQueue) HydriaSyncQueueGateway.pending() else database.pending()

    fun pendingCount(): Int = if (useNewSyncQueue) HydriaSyncQueueGateway.pendingCount() else database.pendingCount()

    @Synchronized
    fun enqueue(type: String, payload: JSONObject) {
        val suppliedUuid = payload.optString("local_uuid")
        val localUuid = suppliedUuid.ifBlank { java.util.UUID.randomUUID().toString() }
        if (useNewSyncQueue) {
            val body = JSONObject(payload.toString()).put("local_uuid", localUuid)
            HydriaSyncQueueGateway.enqueue(localUuid, type, body)
        } else if (suppliedUuid.isBlank()) database.enqueue(type, payload)
        else database.enqueue(type, payload, suppliedUuid)
    }

    @Synchronized
    fun removeFirst() {
        val current = pending()
        if (current.length() > 0) remove(current.getJSONObject(0).getString("local_uuid"))
    }

    fun markSynchronizing(localUuid: String) {
        if (useNewSyncQueue) HydriaSyncQueueGateway.markSynchronizing(localUuid) else database.markSynchronizing(localUuid)
    }

    fun markFailed(localUuid: String, error: String) {
        if (useNewSyncQueue) HydriaSyncQueueGateway.markFailed(localUuid, error) else database.markFailed(localUuid, error)
    }

    fun updatePayload(localUuid: String, payload: JSONObject) {
        if (useNewSyncQueue) HydriaSyncQueueGateway.updatePayload(localUuid, payload) else database.updatePayload(localUuid, payload)
    }

    fun remove(localUuid: String) {
        if (useNewSyncQueue) HydriaSyncQueueGateway.remove(localUuid) else database.remove(localUuid)
    }

    fun pendingPhotoCount(): Int {
        val items = pending()
        var count = 0
        for (index in 0 until items.length()) if (items.getJSONObject(index).optString("type").contains("photo")) count++
        return count
    }

    fun searchCache(key: String): JSONObject? =
        if (useNewSearchCache) HydriaSearchCacheGateway.payload(key) else database.searchCache(key)

    fun saveSearchCache(key: String, payload: JSONObject) {
        if (useNewSearchCache) HydriaSearchCacheGateway.save(key, payload) else database.saveSearchCache(key, payload)
    }

    fun searchCacheUpdatedAt(key: String): Long? =
        if (useNewSearchCache) HydriaSearchCacheGateway.updatedAt(key) else database.searchCacheUpdatedAt(key)

    fun calculatorState(accountKey: String): JSONObject? =
        if (useNewCalculator) HydriaCalculatorGateway.state(accountKey) else database.calculatorState(accountKey)

    fun saveCalculatorState(accountKey: String, payload: JSONObject) {
        if (useNewCalculator) HydriaCalculatorGateway.saveState(accountKey, payload) else database.saveCalculatorState(accountKey, payload)
    }

    fun clearCalculatorMemory(accountKey: String) {
        if (useNewCalculator) HydriaCalculatorGateway.clearState(accountKey) else database.clearCalculatorMemory(accountKey)
    }

    fun activeSalaryConfig(accountKey: String, organisationKey: String = "global"): JSONObject? =
        if (useNewCalculator) HydriaCalculatorGateway.activeSalaryConfig(accountKey, organisationKey)
        else database.activeSalaryConfig(accountKey, organisationKey)

    fun salaryConfigChecksum(accountKey: String, organisationKey: String = "global"): String =
        if (useNewCalculator) HydriaCalculatorGateway.salaryConfigChecksum(accountKey, organisationKey)
        else database.salaryConfigChecksum(accountKey, organisationKey)

    fun replaceActiveSalaryConfig(accountKey: String, configuration: JSONObject) {
        if (useNewCalculator) HydriaCalculatorGateway.replaceActiveSalaryConfig(accountKey, configuration)
        else database.replaceActiveSalaryConfig(accountKey, configuration)
    }

    fun volumeRead(account: String, key: String): JSONObject? =
        if (useNewVolumeCache) HydriaVolumeCacheGateway.read(account, key) else database.volumeRead(account, key)

    fun volumeWrite(account: String, key: String, payload: JSONObject) {
        if (useNewVolumeCache) HydriaVolumeCacheGateway.write(account, key, payload) else database.volumeWrite(account, key, payload)
    }

    fun volumeWriteBatch(entries: List<Triple<String, String, JSONObject>>) {
        if (useNewVolumeCache) HydriaVolumeCacheGateway.writeBatch(entries) else database.volumeWriteBatch(entries)
    }

    fun volumeHistory(account: String): List<JSONObject> =
        if (useNewVolumeCache) HydriaVolumeCacheGateway.history(account) else database.volumeHistory(account)

    fun geoRunImportTransaction(block: () -> Unit) {
        if (useNewGeo) HydriaGeoGateway.runImportTransaction(block) else database.geoRunImportTransaction(block)
    }

    fun geoUpsertServerEntity(
        entityId: String, category: String, name: String, typeLabel: String?, code: String?,
        ouvrageId: String?, latitude: Double, longitude: Double, altitude: Double?,
        accuracyM: Double?, serverUpdatedAt: String?, isFieldMarker: Boolean,
    ) {
        if (useNewGeo) HydriaGeoGateway.upsertServerEntity(
            entityId, category, name, typeLabel, code, ouvrageId, latitude, longitude, altitude, accuracyM, serverUpdatedAt, isFieldMarker,
        ) else database.geoUpsertServerEntity(
            entityId, category, name, typeLabel, code, ouvrageId, latitude, longitude, altitude, accuracyM, serverUpdatedAt, isFieldMarker,
        )
    }

    fun geoUpsertPlacementCandidate(
        entityId: String, category: String, name: String, code: String?, villageName: String?,
        referenceLatitude: Double?, referenceLongitude: Double?, hasPhoto: Boolean,
        servedVillageIds: String?, ouvrageId: String?, serverUpdatedAt: String?,
    ) {
        if (useNewGeo) HydriaGeoGateway.upsertPlacementCandidate(
            entityId, category, name, code, villageName, referenceLatitude, referenceLongitude, hasPhoto, servedVillageIds, ouvrageId, serverUpdatedAt,
        ) else database.geoUpsertPlacementCandidate(
            entityId, category, name, code, villageName, referenceLatitude, referenceLongitude, hasPhoto, servedVillageIds, ouvrageId, serverUpdatedAt,
        )
    }

    fun geoUpsertServerLandmarkType(
        serverId: String, name: String, description: String?, iconKey: String,
        colorHex: String, displayOrder: Long, isActive: Boolean, serverUpdatedAt: String?,
    ) {
        if (useNewGeo) HydriaGeoGateway.upsertServerLandmarkType(serverId, name, description, iconKey, colorHex, displayOrder, isActive, serverUpdatedAt)
        else database.geoUpsertServerLandmarkType(serverId, name, description, iconKey, colorHex, displayOrder.toInt(), isActive, serverUpdatedAt)
    }

    fun geoArchiveEntityIfSynced(category: String, entityId: String) {
        if (useNewGeo) HydriaGeoGateway.archiveEntityIfSynced(category, entityId) else database.geoArchiveEntityIfSynced(category, entityId)
    }

    fun geoMarkEntitySynced(category: String, entityId: String) {
        if (useNewGeo) HydriaGeoGateway.markEntitySynced(category, entityId) else database.geoMarkEntitySynced(category, entityId)
    }

    fun geoMarkEntitySyncedAndArchived(category: String, entityId: String) {
        if (useNewGeo) HydriaGeoGateway.markEntitySyncedAndArchived(category, entityId) else database.geoMarkEntitySyncedAndArchived(category, entityId)
    }

    fun geoMarkEntityConflict(category: String, entityId: String) {
        if (useNewGeo) HydriaGeoGateway.markEntityConflict(category, entityId) else database.geoMarkEntityConflict(category, entityId)
    }

    fun geoMarkPositionHistorySynced(localUuid: String) {
        if (useNewGeo) HydriaGeoGateway.markPositionHistorySynced(localUuid) else database.geoMarkPositionHistorySynced(localUuid)
    }

    fun geoAllEntities(categories: Set<String>, limit: Int? = null): List<JSONObject> =
        if (useNewGeo) {
            // HydriaGeoGateway.allEntities() n'a pas de LIMIT SQL (contrairement a
            // TerrainDatabase.geoAllEntities) : on tronque ici pour un comportement
            // identique (les appelants s'appuient sur `limit` pour ne pas surcharger
            // la carte sur des appareils bas de gamme).
            HydriaGeoGateway.allEntities(categories).let { if (limit != null) it.take(limit) else it }
        } else database.geoAllEntities(categories, limit)

    fun geoNearby(latitude: Double, longitude: Double, radiusMeters: Double, limit: Int = 300): List<JSONObject> =
        if (useNewGeo) HydriaGeoGateway.nearby(latitude, longitude, radiusMeters, limit) else database.geoNearby(latitude, longitude, radiusMeters, limit)

    fun geoWithinBounds(
        north: Double, south: Double, east: Double, west: Double,
        centerLatitude: Double, centerLongitude: Double, limit: Int = 600,
    ): List<JSONObject> =
        if (useNewGeo) HydriaGeoGateway.withinBounds(north, south, east, west, centerLatitude, centerLongitude, limit)
        else database.geoWithinBounds(north, south, east, west, centerLatitude, centerLongitude, limit)

    fun geoLandmarkTypes(): List<Pair<String, String>> =
        if (useNewGeo) HydriaGeoGateway.landmarkTypes() else database.geoLandmarkTypes()

    fun geoPlacementCandidates(category: String): List<JSONObject> =
        if (useNewGeo) HydriaGeoGateway.placementCandidates(category) else database.geoPlacementCandidates(category)

    fun geoPlacementCandidate(category: String, entityId: String): JSONObject? =
        if (useNewGeo) HydriaGeoGateway.placementCandidate(category, entityId) else database.geoPlacementCandidate(category, entityId)

    fun geoMarkCandidatePhotoQueued(category: String, entityId: String) {
        if (useNewGeo) HydriaGeoGateway.markCandidatePhotoQueued(category, entityId) else database.geoMarkCandidatePhotoQueued(category, entityId)
    }

    fun geoNearbyVillageIds(latitude: Double, longitude: Double, radiusMeters: Double = 25_000.0): Set<String> =
        if (useNewGeo) HydriaGeoGateway.nearbyVillageIds(latitude, longitude, radiusMeters) else database.geoNearbyVillageIds(latitude, longitude, radiusMeters)

    fun geoCandidateIdsServingNearbyVillages(category: String, latitude: Double, longitude: Double, radiusMeters: Double = 25_000.0): Set<String> =
        if (useNewGeo) HydriaGeoGateway.candidateIdsServingNearbyVillages(category, latitude, longitude, radiusMeters)
        else database.geoCandidateIdsServingNearbyVillages(category, latitude, longitude, radiusMeters)

    fun geoPlaceCandidate(
        entityId: String, category: String, name: String, code: String?,
        latitude: Double, longitude: Double, altitude: Double?, accuracyM: Double?,
        captureMethod: String, capturedAt: String, serverUpdatedAt: String?,
    ): Pair<JSONObject, String> =
        if (useNewGeo) HydriaGeoGateway.placeCandidate(entityId, category, name, code, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt, serverUpdatedAt)
        else database.geoPlaceCandidate(entityId, category, name, code, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt, serverUpdatedAt)

    fun geoCreateLandmark(
        name: String, typeId: String, latitude: Double, longitude: Double,
        altitude: Double?, accuracyM: Double?, captureMethod: String, capturedAt: String,
        category: String = "landmark",
    ): JSONObject =
        if (useNewGeo) HydriaGeoGateway.createLandmark(name, typeId, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt, category)
        else database.geoCreateLandmark(name, typeId, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt, category)

    fun geoUpdatePosition(
        category: String, entityId: String, latitude: Double, longitude: Double,
        altitude: Double?, accuracyM: Double?, captureMethod: String, capturedAt: String,
    ): String =
        if (useNewGeo) HydriaGeoGateway.updatePosition(category, entityId, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt)
        else database.geoUpdatePosition(category, entityId, latitude, longitude, altitude, accuracyM, captureMethod, capturedAt)

    fun geoArchiveLandmark(category: String, entityId: String): String =
        if (useNewGeo) HydriaGeoGateway.archiveLandmark(category, entityId) else database.geoArchiveLandmark(category, entityId)

    fun terrainDatabase(): TerrainDatabase = database

    fun clearSession() {
        saveCampaign(null, null, null)
        // Brouillons de relevés du compte : avant le retrait de account_key, qui entre dans leurs clés.
        val draftsPrefix = "reading_drafts_$accountKey|"
        val draftsEditor = preferences.edit()
        preferences.all.keys.filter { it.startsWith(draftsPrefix) }.forEach { draftsEditor.remove(it) }
        draftsEditor.apply()
        preferences.edit().remove("token").remove("employee_name").remove("account_key").apply()
        synchronized(snapshotLock) {
            if (useNewSnapshot) HydriaSnapshotGateway.clearSnapshot() else database.clearSnapshot()
            cachedSnapshot = null
            snapshotLoaded = true
        }
    }
}
