package mg.hydria.compta.sync

import androidx.room.withTransaction
import mg.hydria.compta.core.AppResult
import mg.hydria.compta.core.MutationStatus
import mg.hydria.compta.data.db.ComptaDatabase
import mg.hydria.compta.data.db.entity.SyncStateEntity
import mg.hydria.compta.data.db.entity.SyncStateKeys
import mg.hydria.compta.data.prefs.SessionStore
import mg.hydria.compta.data.remote.BootstrapMapper
import mg.hydria.compta.data.remote.ComptaApi
import mg.hydria.compta.data.repository.ConflictRepository
import mg.hydria.compta.data.repository.OutboxRepository
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/**
 * Orchestration de la synchronisation, appelée par les workers. Aucune logique
 * de planification ici — uniquement les échanges réseau + écriture Room.
 */
class SyncRepository(
    private val db: ComptaDatabase,
    private val api: ComptaApi,
    private val session: SessionStore,
    private val outbox: OutboxRepository,
    private val conflicts: ConflictRepository,
) {

    private val syncState = db.syncStateDao()

    val besoinSyncInitiale: suspend () -> Boolean = {
        syncState.get(SyncStateKeys.LAST_FULL_SYNC).isNullOrBlank()
    }

    /**
     * Laisse entrer l'utilisateur avec une réplique vide quand le serveur ne
     * fournit pas encore les endpoints compta (404). L'app reste utilisable
     * hors ligne ; un nouveau `runInitialSync` sera tenté aux prochains pulls.
     */
    suspend fun forcerModeHorsLigne() {
        syncState.put(SyncStateEntity(SyncStateKeys.LAST_FULL_SYNC, Instant.now().toString()))
    }

    /** Efface les jalons pour forcer un bootstrap complet au prochain appel. */
    suspend fun reinitialiser() {
        syncState.put(SyncStateEntity(SyncStateKeys.LAST_FULL_SYNC, ""))
        syncState.put(SyncStateEntity(SyncStateKeys.CURSOR, ""))
    }

    suspend fun runResyncComplete(progress: (String) -> Unit = {}): AppResult<Unit> {
        reinitialiser()
        return runInitialSync(progress)
    }

    // ---- 1. Sync initiale complète (bloquante, écran d'attente) ----

    suspend fun runInitialSync(progress: (String) -> Unit = {}): AppResult<Unit> {
        progress("Connexion au serveur…")
        val response = withAuthRetry { api.bootstrap() }
        if (!response.successful) return erreurReseau(response)

        val payload = response.body.optJSONObject("payload")
            ?: return AppResult.Err(AppResult.ErrorKind.SERVER, "Charge utile bootstrap absente")

        db.withTransaction {
            progress("Exercices…")
            db.referentielDao().upsertExercices(BootstrapMapper.exercices(payload.optJSONArray("exercices")))
            progress("Plan de comptes…")
            db.referentielDao().upsertComptes(BootstrapMapper.comptes(payload.optJSONArray("comptes")))
            progress("Journaux…")
            db.referentielDao().upsertJournaux(BootstrapMapper.journaux(payload.optJSONArray("journaux")))
            progress("Tiers…")
            db.tiersDao().upsert(BootstrapMapper.tiers(payload.optJSONArray("tiers")))
            progress("Grand livre…")
            db.grandLivreDao().upsert(BootstrapMapper.grandLivre(payload.optJSONArray("grand_livre")))
            // TODO soldes_reels, caisses, baremes, employes_paie — même modèle.

            val cursor = response.body.optString("cursor", Instant.now().toString())
            syncState.put(SyncStateEntity(SyncStateKeys.CURSOR, cursor))
            syncState.put(SyncStateEntity(SyncStateKeys.LAST_FULL_SYNC, Instant.now().toString()))
            syncState.put(SyncStateEntity(SyncStateKeys.LAST_PULL_OK, Instant.now().toString()))
        }
        progress("Soldes…")
        rafraichirSoldes()
        progress("Vérification des scans…")
        rafraichirVerificationScans()
        progress("Terminé")
        return AppResult.Ok(Unit)
    }

    /** Soldes caisses / banques / financements — calcul serveur, stocké tel quel en JSON. */
    suspend fun rafraichirSoldes() {
        val r = withAuthRetry { api.soldes() }
        if (r.successful) {
            syncState.put(SyncStateEntity(SyncStateKeys.SOLDES_JSON, r.body.toString()))
        }
    }

    /**
     * Récapitulatif de vérification des scans (fichiers x mois, statut du cache
     * ScanVerificationCache) — calcul serveur, stocké tel quel en JSON. Rafraîchi
     * à la synchronisation initiale et manuellement (bouton), PAS à chaque pull
     * incrémental : cette donnée n'évolue qu'après une vérification lancée depuis
     * le site web/desktop (accès au lecteur réseau des scans).
     */
    suspend fun rafraichirVerificationScans(): AppResult<Unit> {
        val r = withAuthRetry { api.verificationScansRecap() }
        if (!r.successful) return erreurReseau(r)
        syncState.put(SyncStateEntity(SyncStateKeys.VERIFICATION_SCANS_JSON, r.body.toString()))
        return AppResult.Ok(Unit)
    }

    /** Détail paginé pour un mois/fichier — appel réseau à la demande, non répliqué. */
    suspend fun chargerDetailVerificationScans(
        mois: String, fichier: String, statut: String, page: Int,
    ): AppResult<JSONObject> {
        val r = withAuthRetry { api.verificationScansDetail(mois, fichier, statut, page) }
        if (!r.successful) return erreurReseau(r)
        return AppResult.Ok(r.body)
    }

    // ---- 2. Pull incrémental ----

    suspend fun runPull(): AppResult<Unit> {
        val cursor = syncState.get(SyncStateKeys.CURSOR)?.takeIf { it.isNotBlank() }
            ?: return runInitialSync()

        val response = withAuthRetry { api.changes(cursor) }
        if (!response.successful) return erreurReseau(response)

        if (response.body.optBoolean("full_refresh_required", false)) {
            syncState.put(SyncStateEntity(SyncStateKeys.LAST_FULL_SYNC, ""))
            return runInitialSync()
        }

        val changes = response.body.optJSONObject("changes") ?: JSONObject()
        db.withTransaction {
            appliquerUpserts(changes)
            appliquerTombstones(changes.optJSONObject("deleted"))
            val next = response.body.optString("cursor", cursor)
            syncState.put(SyncStateEntity(SyncStateKeys.CURSOR, next))
            syncState.put(SyncStateEntity(SyncStateKeys.LAST_PULL_OK, Instant.now().toString()))
        }
        rafraichirSoldes()
        return AppResult.Ok(Unit)
    }

    private suspend fun appliquerUpserts(changes: JSONObject) {
        BootstrapMapper.comptes(changes.optJSONArray("comptes")).takeIf { it.isNotEmpty() }
            ?.let { db.referentielDao().upsertComptes(it) }
        BootstrapMapper.journaux(changes.optJSONArray("journaux")).takeIf { it.isNotEmpty() }
            ?.let { db.referentielDao().upsertJournaux(it) }
        BootstrapMapper.tiers(changes.optJSONArray("tiers")).takeIf { it.isNotEmpty() }
            ?.let { db.tiersDao().upsert(it) }
        BootstrapMapper.grandLivre(changes.optJSONArray("grand_livre")).takeIf { it.isNotEmpty() }
            ?.let { db.grandLivreDao().upsert(it) }
    }

    private suspend fun appliquerTombstones(deleted: JSONObject?) {
        if (deleted == null) return
        deleted.optJSONArray("comptes")?.toIdList()?.let { db.referentielDao().deleteComptes(it) }
        deleted.optJSONArray("journaux")?.toIdList()?.let { db.referentielDao().deleteJournaux(it) }
        deleted.optJSONArray("tiers")?.toIdList()?.let { db.tiersDao().delete(it) }
        deleted.optJSONArray("grand_livre")?.toIdList()?.let { db.grandLivreDao().delete(it) }
    }

    // ---- 3. Push de l'outbox ----

    data class PushOutcome(val acceptes: Int, val conflits: Int, val rejetes: Int, val differes: Int)

    suspend fun runPush(): AppResult<PushOutcome> {
        reconcilierEnVol()

        val prochaines = outbox.prochaines()
        if (prochaines.isEmpty()) return AppResult.Ok(PushOutcome(0, 0, 0, 0))

        prochaines.forEach { outbox.marquerEnVol(it.localUuid) }

        val batch = JSONObject().put("mutations", JSONArray().apply {
            prochaines.forEach { m ->
                put(JSONObject().apply {
                    put("local_uuid", m.localUuid)
                    put("type", m.operation.wire)
                    put("base_revision", m.baseRevision)
                    put("client_created_at", m.createdAt.toString())
                    m.dependsOnLocalUuid?.let { put("depends_on", it) }
                    put("payload", JSONObject(m.payloadJson))
                })
            }
        })

        val response = withAuthRetry { api.pushMutations(batch) }
        if (!response.successful) {
            prochaines.forEach { outbox.marquerEchec(it.localUuid, MutationStatus.QUEUED, response.error) }
            return erreurReseau(response)
        }

        var acceptes = 0; var conflits = 0; var rejetes = 0
        val results = response.body.optJSONArray("results") ?: JSONArray()
        for (i in 0 until results.length()) {
            val r = results.getJSONObject(i)
            val localUuid = r.getString("local_uuid")
            val mutation = prochaines.first { it.localUuid == localUuid }
            when (r.optString("status")) {
                "accepted" -> {
                    val serverId = r.optString("server_id").ifBlank { null }
                    outbox.marquerAcked(localUuid, serverId)
                    appliquerAcceptation(mutation.aggregateType, mutation.aggregateLocalUuid, serverId, r.optJSONObject("assigned"))
                    acceptes++
                }
                "conflict" -> {
                    outbox.marquerEchec(localUuid, MutationStatus.CONFLICT, "Version serveur plus récente")
                    conflicts.enregistrer(
                        aggregateType = mutation.aggregateType,
                        aggregateLocalUuid = mutation.aggregateLocalUuid,
                        localSnapshot = JSONObject(mutation.payloadJson),
                        serverSnapshot = r.optJSONObject("server") ?: JSONObject(),
                    )
                    conflits++
                }
                "rejected" -> {
                    outbox.marquerEchec(localUuid, MutationStatus.FAILED, r.optString("errors"))
                    appliquerRejet(mutation.aggregateType, mutation.aggregateLocalUuid, r.optString("errors"))
                    rejetes++
                }
                else -> outbox.marquerEchec(localUuid, MutationStatus.QUEUED, "Statut inconnu")
            }
        }
        return AppResult.Ok(PushOutcome(acceptes, conflits, rejetes, 0))
    }

    private suspend fun reconcilierEnVol() {
        outbox.enVol().forEach { m ->
            val response = runCatching { api.mutationStatus(m.localUuid) }.getOrNull() ?: return@forEach
            when {
                response.status == 404 -> outbox.marquerEchec(m.localUuid, MutationStatus.QUEUED, null)
                response.successful && response.body.optString("status") == "accepted" ->
                    outbox.marquerAcked(m.localUuid, response.body.optString("server_id").ifBlank { null })
                else -> outbox.marquerEchec(m.localUuid, MutationStatus.QUEUED, null)
            }
        }
    }

    private suspend fun appliquerAcceptation(type: String, localUuid: String, serverId: String?, assigned: JSONObject?) {
        when (type) {
            "piece_comptable" -> serverId?.let { db.pieceComptableDao().marquerSynced(localUuid, it) }
            // TODO facture (+ consommer numéro), mouvement_caisse, reglement, tiers…
        }
    }

    private suspend fun appliquerRejet(type: String, localUuid: String, erreurs: String) {
        when (type) {
            "piece_comptable" ->
                db.pieceComptableDao().marquer(localUuid, mg.hydria.compta.core.SyncStatus.REJECTED, erreurs)
        }
    }

    // ---- utilitaires ----

    private inline fun withAuthRetry(call: () -> ComptaApi.Response): ComptaApi.Response {
        val first = call()
        if (first.status != 401) return first
        val refresh = session.session.value?.refreshToken ?: return first
        val refreshed = api.refresh(refresh)
        if (refreshed.successful) {
            session.updateAccessToken(
                refreshed.body.optString("access_token"),
                refreshed.body.optString("refresh_token", refresh),
            )
            return call()
        }
        return first
    }

    private fun <T> erreurReseau(response: ComptaApi.Response): AppResult<T> {
        val kind = when {
            response.status == -1 -> AppResult.ErrorKind.NETWORK
            response.isAuthError -> AppResult.ErrorKind.AUTH
            else -> AppResult.ErrorKind.SERVER
        }
        return AppResult.Err(kind, response.error)
    }

    private fun JSONArray.toIdList(): List<String> = (0 until length()).map { getString(it) }
}
