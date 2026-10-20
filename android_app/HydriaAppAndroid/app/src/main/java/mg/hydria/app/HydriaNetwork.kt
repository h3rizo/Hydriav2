package mg.hydria.app

import android.util.Log
import mg.hydria.app.network.SessionNetworkRoute
import mg.hydria.shared.network.HydriaOperationsGateway
import org.json.JSONObject

/** Adaptateur de transport uniquement : les files, confirmations et conflits
 * restent geres par leurs repositories actuels. Aucun token/payload dans les traces.
 */
object HydriaNetwork {
    private fun route(domain: String, state: SessionNetworkRoute,
        shared: () -> HydriaOperationsGateway.Result, legacy: () -> HydriaApi.Result,
    ): HydriaApi.Result = state.call(
        shared = {
            Log.d("HydriaNetwork", "$domain: Ktor")
            val result = shared()
            HydriaApi.Result(result.status, result.body)
        },
        legacy = {
            Log.d("HydriaNetwork", "$domain: HydriaApi (repli de session)")
            legacy()
        },
    )

    fun savePlanning(token: String, payload: JSONObject): HydriaApi.Result =
        route("Planning", OfflineStore.planningNetwork,
            { HydriaOperationsGateway.savePlanning(token, payload) },
            { HydriaApi.savePlanning(token, payload) })

    fun saveRepair(token: String, payload: JSONObject): HydriaApi.Result =
        route("Repairs", OfflineStore.repairsNetwork,
            { HydriaOperationsGateway.saveRepair(token, payload) },
            { HydriaApi.saveRepair(token, payload) })

    fun finishRepair(token: String, planningId: String): HydriaApi.Result =
        route("Repairs", OfflineStore.repairsNetwork,
            { HydriaOperationsGateway.finishRepair(token, planningId) },
            { HydriaApi.finishRepair(token, planningId) })

    /** Legacy uniquement pour l'instant : operation encore absente du client
     * Ktor partage (HydriaOperationsGateway/HydriaRepairsClient). A completer
     * si le domaine Repairs bascule un jour entierement sur ce transport. */
    fun saveRepairPhoto(token: String, payload: JSONObject): HydriaApi.Result =
        HydriaApi.saveRepairPhoto(token, payload)

    fun saveReading(token: String, payload: JSONObject): HydriaApi.Result =
        route("Readings", OfflineStore.readingsNetwork,
            { HydriaOperationsGateway.saveReading(token, payload) },
            { HydriaApi.saveReading(token, payload) })

    fun pointInvoices(token: String, pointId: String): HydriaApi.Result =
        route("Readings", OfflineStore.readingsNetwork,
            { HydriaOperationsGateway.pointInvoices(token, pointId) },
            { HydriaApi.pointInvoices(token, pointId) })

    fun interventions(token: String, page: Int = 1, includeOtherBases: Boolean = false, status: String = "", sort: String = "created"): HydriaApi.Result =
        route("Interventions", OfflineStore.interventionsNetwork,
            { HydriaOperationsGateway.interventions(token, page, includeOtherBases, status, sort) },
            { HydriaApi.interventions(token, page, includeOtherBases, status, sort) })

    fun postponeIntervention(token: String, planningId: String, date: String): HydriaApi.Result =
        route("Interventions", OfflineStore.interventionsNetwork,
            { HydriaOperationsGateway.postponeIntervention(token, planningId, date) },
            { HydriaApi.postponeIntervention(token, planningId, date) })

    fun deleteIntervention(token: String, planningId: String): HydriaApi.Result =
        route("Interventions", OfflineStore.interventionsNetwork,
            { HydriaOperationsGateway.deleteIntervention(token, planningId) },
            { HydriaApi.deleteIntervention(token, planningId) })

    fun interventionOptions(token: String, workId: String): HydriaApi.Result =
        route("Interventions", OfflineStore.interventionsNetwork,
            { HydriaOperationsGateway.interventionOptions(token, workId) },
            { HydriaApi.interventionOptions(token, workId) })

    fun updateIntervention(token: String, workId: String, planningId: String, payload: JSONObject): HydriaApi.Result =
        route("Interventions", OfflineStore.interventionsNetwork,
            { HydriaOperationsGateway.updateIntervention(token, workId, planningId, payload) },
            { HydriaApi.updateIntervention(token, workId, planningId, payload) })

    fun volumeBootstrap(token: String, ouvrageId: String = "", month: String = ""): HydriaApi.Result =
        route("Volume", OfflineStore.volumeNetwork,
            { HydriaOperationsGateway.volumeBootstrap(token, ouvrageId, month) },
            { HydriaApi.volumeBootstrap(token, ouvrageId, month) })

    fun volumeOperation(token: String, payload: JSONObject): HydriaApi.Result =
        route("Volume", OfflineStore.volumeNetwork,
            { HydriaOperationsGateway.volumeOperation(token, payload) },
            { HydriaApi.volumeOperation(token, payload) })

    fun navigationConfig(token: String): HydriaApi.Result =
        route("Navigation", OfflineStore.navigationNetwork,
            { HydriaOperationsGateway.navigationConfig(token) },
            { HydriaApi.navigationConfig(token) })

    fun navigationEntities(token: String, cursor: String?, bbox: String?, limit: Int = 500): HydriaApi.Result =
        route("Navigation", OfflineStore.navigationNetwork,
            { HydriaOperationsGateway.navigationEntities(token, cursor, bbox, limit) },
            { HydriaApi.navigationEntities(token, cursor, bbox, limit) })

    fun navigationRoute(
        token: String, fromLat: Double, fromLon: Double, toLat: Double, toLon: Double, profile: String,
    ): HydriaApi.Result =
        route("Navigation", OfflineStore.navigationNetwork,
            { HydriaOperationsGateway.navigationRoute(token, fromLat, fromLon, toLat, toLon, profile) },
            { HydriaApi.navigationRoute(token, fromLat, fromLon, toLat, toLon, profile) })

    fun saveNavigationPosition(token: String, payload: JSONObject): HydriaApi.Result =
        route("Navigation", OfflineStore.navigationNetwork,
            { HydriaOperationsGateway.saveNavigationPosition(token, payload) },
            { HydriaApi.saveNavigationPosition(token, payload) })

    fun saveNavigationLandmark(token: String, payload: JSONObject): HydriaApi.Result =
        route("Navigation", OfflineStore.navigationNetwork,
            { HydriaOperationsGateway.saveNavigationLandmark(token, payload) },
            { HydriaApi.saveNavigationLandmark(token, payload) })

    fun saveNavigationPhoto(token: String, payload: JSONObject): HydriaApi.Result =
        route("Navigation", OfflineStore.navigationNetwork,
            { HydriaOperationsGateway.saveNavigationPhoto(token, payload) },
            { HydriaApi.saveNavigationPhoto(token, payload) })

    fun prepareTour(token: String, snapshotVersion: String? = null): HydriaApi.Result =
        route("Terrain", OfflineStore.terrainNetwork,
            { HydriaOperationsGateway.prepareTour(token, snapshotVersion) },
            { HydriaApi.prepareTour(token, snapshotVersion) })

    fun saveTerrainItem(token: String, payload: JSONObject): HydriaApi.Result =
        route("Terrain", OfflineStore.terrainNetwork,
            { HydriaOperationsGateway.saveTerrainItem(token, payload) },
            { HydriaApi.saveTerrainItem(token, payload) })

    fun finishIntervention(token: String, planningId: String): HydriaApi.Result =
        route("Interventions", OfflineStore.interventionsNetwork,
            { HydriaOperationsGateway.finishRepair(token, planningId) },
            { HydriaApi.finishRepair(token, planningId) })

    fun search(token: String, query: String, types: Set<String>, page: Int = 1): HydriaApi.Result =
        route("Search", OfflineStore.searchNetwork,
            { HydriaOperationsGateway.search(token, query, types, page) },
            { HydriaApi.search(token, query, types, page) })

    fun people(token: String, query: String, type: String, status: String, page: Int = 1): HydriaApi.Result =
        route("Search", OfflineStore.searchNetwork,
            { HydriaOperationsGateway.people(token, query, type, status, page) },
            { HydriaApi.people(token, query, type, status, page) })

    fun works(token: String, query: String, page: Int = 1, region: String = "", district: String = "", commune: String = "", employee: String = ""): HydriaApi.Result =
        route("Search", OfflineStore.searchNetwork,
            { HydriaOperationsGateway.works(token, query, page, region, district, commune, employee) },
            { HydriaApi.works(token, query, page, region, district, commune, employee) })

    fun workFilters(token: String): HydriaApi.Result =
        route("Search", OfflineStore.searchNetwork,
            { HydriaOperationsGateway.workFilters(token) },
            { HydriaApi.workFilters(token) })

    fun searchDetail(token: String, type: String, id: String): HydriaApi.Result =
        route("Search", OfflineStore.searchNetwork,
            { HydriaOperationsGateway.searchDetail(token, type, id) },
            { HydriaApi.searchDetail(token, type, id) })

    fun personDetail(token: String, type: String, id: String): HydriaApi.Result =
        route("Search", OfflineStore.searchNetwork,
            { HydriaOperationsGateway.personDetail(token, type, id) },
            { HydriaApi.personDetail(token, type, id) })

    fun salaryCalculationConfig(token: String, checksum: String = ""): HydriaApi.Result =
        route("Calculator", OfflineStore.calculatorNetwork,
            { HydriaOperationsGateway.salaryCalculationConfig(token, checksum) },
            { HydriaApi.salaryCalculationConfig(token, checksum) })
}
