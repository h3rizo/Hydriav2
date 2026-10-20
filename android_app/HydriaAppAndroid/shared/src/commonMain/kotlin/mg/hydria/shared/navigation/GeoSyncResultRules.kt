package mg.hydria.shared.navigation

data class GeoSyncOperation(
    val type: String,
    val localCategory: String = "",
    val entityKind: String = "",
    val entityId: String = "",
    val localUuid: String = "",
    val markerCategory: String = "landmark",
    val markerId: String = "",
)

enum class GeoSyncChangeKind { ENTITY_SYNCED, HISTORY_SYNCED, ENTITY_ARCHIVED, ENTITY_CONFLICT }

data class GeoSyncChange(
    val kind: GeoSyncChangeKind,
    val category: String = "",
    val id: String,
)

object GeoSyncResultRules {
    fun changes(operation: GeoSyncOperation, conflict: Boolean): List<GeoSyncChange> {
        val synced = if (conflict) GeoSyncChangeKind.ENTITY_CONFLICT else GeoSyncChangeKind.ENTITY_SYNCED
        return when (operation.type) {
            "geo_position_upsert" -> buildList {
                add(GeoSyncChange(synced, operation.localCategory.ifBlank { operation.entityKind }, operation.entityId))
                if (!conflict) add(GeoSyncChange(GeoSyncChangeKind.HISTORY_SYNCED, id = operation.localUuid))
            }
            "landmark_upsert" -> listOf(GeoSyncChange(synced, operation.markerCategory, operation.markerId))
            "landmark_archive" -> listOf(GeoSyncChange(
                if (conflict) GeoSyncChangeKind.ENTITY_CONFLICT else GeoSyncChangeKind.ENTITY_ARCHIVED,
                operation.markerCategory, operation.markerId,
            ))
            else -> emptyList()
        }
    }
}
