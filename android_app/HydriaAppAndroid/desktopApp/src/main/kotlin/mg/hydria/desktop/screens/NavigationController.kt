package mg.hydria.desktop.screens

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.storage.DesktopPrefs
import mg.hydria.shared.database.HydriaGeoGateway
import mg.hydria.shared.navigation.GeoImportGateway
import mg.hydria.shared.navigation.GeoMath
import mg.hydria.shared.navigation.GeoPageImportGateway
import mg.hydria.shared.navigation.NavigationDownload
import mg.hydria.shared.navigation.NavigationPage
import mg.hydria.shared.navigation.NavigationPageCursor
import mg.hydria.shared.navigation.model.GeoCategory
import mg.hydria.shared.network.HydriaOperationsGateway
import org.json.JSONArray
import org.json.JSONObject

/**
 * Navigation terrain, version Desktop **dégradée** : pas de carte (MapLibre n'a
 * pas d'équivalent Desktop mûr), pas de GPS. Consultation seule :
 *  - télécharge le périmètre cartographique par pages
 *    (`HydriaOperationsGateway.navigationEntities` + `NavigationDownload.run`)
 *    et l'importe dans SQLDelight via `HydriaGeoGateway` — exactement le même
 *    chemin d'import que l'app Android (`GeoPageImportGateway` / `GeoImportGateway`),
 *  - liste les entités (village / point d'eau / équipement / repère) avec filtre
 *    catégorie + recherche, et, si on saisit une position, la distance / le cap
 *    calculés par `GeoMath`.
 *
 * Le marquage GPS et la création de repères (qui exigent GPS + photo) sont hors
 * périmètre de cette version.
 */
class NavigationController(
    private val session: DesktopSession,
    private val prefs: DesktopPrefs,
) {
    var entities: List<JSONObject> by mutableStateOf(emptyList())
        private set
    var loaded: Boolean by mutableStateOf(false)
        private set
    var busy: Boolean by mutableStateOf(false)
    var message: String? by mutableStateOf(null)

    var category: GeoCategory? by mutableStateOf(null)
    var query: String by mutableStateOf("")
    var originLat: String by mutableStateOf("")
    var originLon: String by mutableStateOf("")

    private val origin: Pair<Double, Double>?
        get() {
            val lat = originLat.replace(',', '.').toDoubleOrNull() ?: return null
            val lon = originLon.replace(',', '.').toDoubleOrNull() ?: return null
            return if (GeoMath.isValid(lat, lon)) lat to lon else null
        }

    data class Row(
        val name: String, val typeLabel: String, val code: String, val category: GeoCategory,
        val latitude: Double, val longitude: Double, val distanceMeters: Double?, val bearingDegrees: Double?,
    )

    val rows: List<Row>
        get() {
            val needle = query.trim().lowercase()
            val here = origin
            return entities.asSequence()
                .filter { category == null || it.optString("category") == category!!.storageKey }
                .filter { row ->
                    needle.isBlank() ||
                        listOf(row.optString("name"), row.optString("code"), row.optString("type_label"))
                            .any { it.lowercase().contains(needle) }
                }
                .map { row ->
                    val lat = row.optDouble("latitude")
                    val lon = row.optDouble("longitude")
                    val valid = here != null && GeoMath.isValid(lat, lon)
                    val dist = if (valid) GeoMath.distanceMeters(here!!.first, here.second, lat, lon) else null
                    val bearing = if (valid) GeoMath.bearingDegrees(here!!.first, here.second, lat, lon) else null
                    Row(
                        name = row.optString("name").ifBlank { "Sans nom" },
                        typeLabel = row.optString("type_label"),
                        code = row.optString("code"),
                        category = GeoCategory.fromStorage(row.optString("category")),
                        latitude = lat, longitude = lon, distanceMeters = dist, bearingDegrees = bearing,
                    )
                }
                .sortedWith(compareBy({ it.distanceMeters ?: Double.MAX_VALUE }, { it.name }))
                .toList()
        }

    fun countByCategory(cat: GeoCategory): Int =
        entities.count { it.optString("category") == cat.storageKey }

    fun loadFromCache() {
        val all = runCatching {
            HydriaGeoGateway.allEntities(GeoCategory.entries.mapTo(mutableSetOf()) { it.storageKey })
        }.getOrNull()
        entities = all ?: emptyList()
        loaded = all != null
    }

    suspend fun syncMap() {
        val token = session.token ?: run { message = "Session expiree."; return }
        busy = true; message = null
        val result = withContext(Dispatchers.IO) {
            runCatching {
                NavigationDownload.run(
                    initialCursor = prefs.getString(CURSOR_KEY),
                    fetch = { cursor ->
                        val r = HydriaOperationsGateway.navigationEntities(token, cursor, null, 500)
                        NavigationPage(
                            body = r.body,
                            successful = r.status in 200..299 && r.body.optBoolean("success", true),
                            error = r.body.optString("error", "Erreur HTTP ${r.status}"),
                        )
                    },
                    importPage = { body -> importNavigationPage(body) },
                    readCursor = { body, cursor ->
                        val page = body.optJSONObject("data") ?: body
                        val next = page.optString("next_cursor").ifBlank { page.optString("cursor") }
                        NavigationPageCursor(next, page.optBoolean("has_more", next.isNotBlank() && next != cursor))
                    },
                    saveCursor = { next -> prefs.putString(CURSOR_KEY, next) },
                )
            }
        }
        busy = false
        result.onSuccess {
            loadFromCache()
            message = it.message
        }.onFailure {
            message = "Synchronisation impossible : ${it.message ?: "reseau indisponible"}"
        }
    }

    fun resetCursor() {
        prefs.clear(CURSOR_KEY)
        message = "Curseur reinitialise : la prochaine synchro repart de zero."
    }

    // ── Import (miroir de GeoRepository.importNavigationPage cote Android) ──

    private fun importNavigationPage(body: JSONObject): Int =
        HydriaGeoGateway.runImportTransaction {
            GeoPageImportGateway.importPage(
                body,
                importItems = { items, cat, ouvrageId -> importItems(items, cat, ouvrageId) },
                importLandmarkTypes = { arr -> importLandmarkTypes(arr) },
                archiveSynced = { kind, id -> HydriaGeoGateway.archiveEntityIfSynced(kind, id) },
            )
        }

    private fun importItems(items: JSONArray?, cat: GeoCategory, ouvrageId: String) {
        if (items == null) return
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            if (cat == GeoCategory.WATER_POINT || cat == GeoCategory.EQUIPMENT) {
                GeoImportGateway.placement(item, cat, ouvrageId)?.let { v ->
                    HydriaGeoGateway.upsertPlacementCandidate(
                        entityId = v.entityId, category = v.category.storageKey, name = v.name, code = v.code,
                        villageName = v.villageName, referenceLatitude = v.referenceLatitude,
                        referenceLongitude = v.referenceLongitude, hasPhoto = v.hasPhoto,
                        servedVillageIds = v.servedVillageIds, ouvrageId = v.ouvrageId, serverUpdatedAt = v.serverUpdatedAt,
                    )
                }
            }
            GeoImportGateway.entity(item, cat, ouvrageId)?.let { v ->
                HydriaGeoGateway.upsertServerEntity(
                    entityId = v.id, category = v.category.storageKey, name = v.name, typeLabel = v.typeLabel,
                    code = v.code, ouvrageId = v.ouvrageId, latitude = v.latitude, longitude = v.longitude,
                    altitude = v.altitude, accuracyM = v.accuracyMeters, serverUpdatedAt = v.serverUpdatedAt,
                    isFieldMarker = v.isFieldMarker,
                )
            }
        }
    }

    private fun importLandmarkTypes(values: JSONArray?) {
        GeoPageImportGateway.importLandmarkTypes(values) { v ->
            HydriaGeoGateway.upsertServerLandmarkType(
                serverId = v.serverId, name = v.name, description = v.description, iconKey = v.iconKey,
                colorHex = v.colorHex, displayOrder = v.displayOrder, isActive = v.isActive,
                serverUpdatedAt = v.serverUpdatedAt,
            )
        }
    }

    private companion object {
        const val CURSOR_KEY = "nav_cursor"
    }
}
