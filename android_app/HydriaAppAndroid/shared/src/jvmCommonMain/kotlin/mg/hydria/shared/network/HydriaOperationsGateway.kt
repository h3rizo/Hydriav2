package mg.hydria.shared.network

import io.ktor.client.HttpClient
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonObject
import org.json.JSONObject
import mg.hydria.shared.search.HydriaSearchClient
import mg.hydria.shared.calculator.HydriaSalaryConfigClient
import mg.hydria.shared.plannings.HydriaPlanningsClient
import mg.hydria.shared.repairs.HydriaRepairsClient
import mg.hydria.shared.readings.HydriaReadingsClient
import mg.hydria.shared.interventions.HydriaInterventionsClient
import mg.hydria.shared.billing.HydriaVolumeClient
import mg.hydria.shared.navigation.HydriaNavigationClient
import mg.hydria.shared.terrain.HydriaTerrainClient

/** Facade bloquante Android/Desktop. Appeler sur un thread de travail.
 * Les exceptions de transport remontent au routeur de session de l'application.
 */
object HydriaOperationsGateway {
    data class Result(val status: Int, val body: JSONObject)

    fun probe() { HydriaHttpClient.create().close() }

    private fun JSONObject.toSharedJson() = HydriaHttpClient.json.parseToJsonElement(toString()).jsonObject

    private fun request(block: suspend (HttpClient) -> HydriaResult): Result {
        val client = HydriaHttpClient.create()
        return try {
            runBlocking {
                val response = block(client)
                Result(response.status, JSONObject(response.body.toString()))
            }
        } finally { client.close() }
    }

    fun savePlanning(token: String, payload: JSONObject): Result = request { client ->
        HydriaPlanningsClient.savePlanning(client, token, payload.toSharedJson())
    }

    fun saveRepair(token: String, payload: JSONObject): Result = request { client ->
        HydriaPlanningsClient.saveRepair(client, token, payload.toSharedJson())
    }

    fun finishRepair(token: String, planningId: String): Result = request { client ->
        HydriaRepairsClient.finishRepair(client, token, planningId)
    }

    fun saveRepairPhoto(token: String, payload: JSONObject): Result = request { client ->
        HydriaPlanningsClient.saveRepairPhoto(client, token, payload.toSharedJson())
    }

    fun saveReading(token: String, payload: JSONObject): Result = request { client ->
        HydriaReadingsClient.saveReading(client, token, payload.toSharedJson())
    }

    fun pointInvoices(token: String, pointId: String): Result = request { client ->
        HydriaPlanningsClient.pointInvoices(client, token, pointId)
    }

    fun interventions(token: String, page: Int = 1, includeOtherBases: Boolean = false, status: String = "", sort: String = "created"): Result = request { client ->
        HydriaInterventionsClient.list(client, token, page, includeOtherBases, status, sort)
    }

    fun postponeIntervention(token: String, planningId: String, date: String): Result = request { client ->
        HydriaInterventionsClient.postpone(client, token, planningId, date)
    }

    fun deleteIntervention(token: String, planningId: String): Result = request { client ->
        HydriaInterventionsClient.delete(client, token, planningId)
    }

    fun interventionOptions(token: String, workId: String): Result = request { client ->
        HydriaInterventionsClient.options(client, token, workId)
    }

    fun updateIntervention(token: String, workId: String, planningId: String, payload: JSONObject): Result = request { client ->
        HydriaInterventionsClient.update(client, token, workId, planningId, payload.toSharedJson())
    }

    fun volumeBootstrap(token: String, ouvrageId: String = "", month: String = ""): Result = request { client ->
        HydriaVolumeClient.bootstrap(client, token, ouvrageId, month)
    }

    fun volumeOperation(token: String, payload: JSONObject): Result = request { client ->
        HydriaVolumeClient.syncOperation(client, token, payload.toSharedJson())
    }

    fun navigationConfig(token: String): Result = request { client ->
        HydriaNavigationClient.config(client, token)
    }

    fun navigationEntities(token: String, cursor: String?, bbox: String?, limit: Int = 500): Result = request { client ->
        HydriaNavigationClient.entities(client, token, cursor, bbox, limit)
    }

    fun navigationRoute(
        token: String, fromLat: Double, fromLon: Double, toLat: Double, toLon: Double, profile: String,
    ): Result = request { client ->
        HydriaNavigationClient.route(client, token, fromLat, fromLon, toLat, toLon, profile)
    }

    fun saveNavigationPosition(token: String, payload: JSONObject): Result = request { client ->
        HydriaNavigationClient.savePosition(client, token, payload.toSharedJson())
    }

    fun saveNavigationLandmark(token: String, payload: JSONObject): Result = request { client ->
        HydriaNavigationClient.saveLandmark(client, token, payload.toSharedJson())
    }

    fun saveNavigationPhoto(token: String, payload: JSONObject): Result = request { client ->
        HydriaNavigationClient.savePhoto(client, token, payload.toSharedJson())
    }

    fun prepareTour(token: String, snapshotVersion: String? = null): Result = request { client ->
        HydriaTerrainClient.prepareTour(client, token, snapshotVersion)
    }

    fun saveTerrainItem(token: String, payload: JSONObject): Result = request { client ->
        HydriaTerrainClient.saveItem(client, token, payload.toSharedJson())
    }

    fun search(token: String, query: String, types: Set<String>, page: Int = 1): Result = request { client ->
        HydriaSearchClient.search(client, token, query, types, page)
    }

    fun people(token: String, query: String, type: String, status: String, page: Int = 1): Result = request { client ->
        HydriaSearchClient.people(client, token, query, type, status, page)
    }

    fun works(token: String, query: String, page: Int = 1, region: String = "", district: String = "", commune: String = "", employee: String = ""): Result = request { client ->
        HydriaSearchClient.works(client, token, query, page, region, district, commune, employee)
    }

    fun workFilters(token: String): Result = request { client ->
        HydriaSearchClient.workFilters(client, token)
    }

    fun searchDetail(token: String, type: String, id: String): Result = request { client ->
        HydriaSearchClient.searchDetail(client, token, type, id)
    }

    fun personDetail(token: String, type: String, id: String): Result = request { client ->
        HydriaSearchClient.personDetail(client, token, type, id)
    }

    fun salaryCalculationConfig(token: String, checksum: String = ""): Result = request { client ->
        HydriaSalaryConfigClient.fetch(client, token, checksum)
    }
}
