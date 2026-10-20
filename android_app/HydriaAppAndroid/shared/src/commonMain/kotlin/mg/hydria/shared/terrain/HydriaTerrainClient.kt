package mg.hydria.shared.terrain

import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.http.HttpHeaders
import kotlinx.serialization.json.JsonObject
import mg.hydria.shared.network.HydriaHttpClient
import mg.hydria.shared.network.HydriaResult
import mg.hydria.shared.network.toHydriaResult
import mg.hydria.shared.network.toSyncForm

/**
 * Client Ktor du domaine Terrain (endpoints apps/planning/views_preparation_tournee.py) :
 *
 *  - [prepareTour]  GET  /plannings/api/preparer-tournee/  : prechargement hors
 *    ligne (plannings a venir, reparations echues, ouvrages + points d'eau +
 *    historique + tarifs du perimetre de l'utilisateur). Miroir de
 *    HydriaApi.prepareTour() : meme horizon fixe (14 j) et meme parametre
 *    conditionnel snapshot_version (le serveur repond alors { not_modified: true }
 *    si le snapshot n'a pas change).
 *  - [saveItem]     POST /plannings/api/mobile/terrain/sync-item/  : envoi d'une
 *    action Terrain legere ou d'une photo. Miroir de HydriaApi.saveTerrainItem() :
 *    formulaire x-www-form-urlencoded, toutes les cles du payload sauf celles
 *    prefixees "_sync_" (metadonnees de file locale) et les valeurs nulles
 *    (regles de toSyncForm(), partagees avec les autres clients Ktor).
 *
 * Branche sur l'app derriere le flag de session OfflineStore.useNewTerrainNetwork,
 * via la facade bloquante HydriaOperationsGateway (jvmCommonMain). HydriaApi reste
 * le repli si le transport Ktor jette.
 */
object HydriaTerrainClient {
    suspend fun prepareTour(client: HttpClient, token: String, snapshotVersion: String?): HydriaResult {
        val response = client.get("/plannings/api/preparer-tournee/") {
            header(HttpHeaders.Authorization, "Token $token")
            parameter("horizon_jours", 14)
            snapshotVersion?.takeIf { it.isNotBlank() }?.let { parameter("snapshot_version", it) }
        }
        return response.toHydriaResult()
    }

    suspend fun saveItem(client: HttpClient, token: String, payload: JsonObject): HydriaResult {
        val response = HydriaHttpClient.postForm(
            client, "/plannings/api/mobile/terrain/sync-item/", token, payload.toSyncForm(),
        )
        return response.toHydriaResult()
    }
}
