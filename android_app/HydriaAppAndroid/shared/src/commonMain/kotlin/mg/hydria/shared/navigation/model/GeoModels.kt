package mg.hydria.shared.navigation.model


enum class GeoCategory(val storageKey: String, val label: String, val shortLabel: String) {
    VILLAGE("village", "Village", "V"),
    WATER_POINT("water_point", "Point d’eau", "P"),
    EQUIPMENT("equipment", "Équipement", "E"),
    LANDMARK("landmark", "Repère", "R");

    companion object {
        fun fromStorage(value: String): GeoCategory = entries.firstOrNull { it.storageKey == value } ?: LANDMARK
    }
}

data class GeoEntity(
    val id: String,
    val category: GeoCategory,
    val name: String,
    val typeLabel: String = "",
    val code: String = "",
    val ouvrageId: String = "",
    val latitude: Double,
    val longitude: Double,
    val altitude: Double? = null,
    val accuracyMeters: Double? = null,
    val syncState: String = "synced",
    val serverUpdatedAt: String = "",
    val isFieldMarker: Boolean = false,
)

data class CapturedPosition(
    val latitude: Double,
    val longitude: Double,
    val altitude: Double?,
    val accuracyMeters: Double?,
    val capturedAt: String,
    val method: String,
)

data class PlacementCandidate(
    val id: String,
    val category: GeoCategory,
    val name: String,
    val code: String = "",
    val villageName: String = "",
    val referenceLatitude: Double? = null,
    val referenceLongitude: Double? = null,
    val hasPhoto: Boolean = false,
    val servedVillageIds: Set<String> = emptySet(),
    val ouvrageId: String = "",
    val serverUpdatedAt: String = "",
)

enum class NavigationMode { FOLLOW_GPS, EXPLORE, NAVIGATE }

data class NavigationTarget(val entity: GeoEntity, val arrivalRadiusMeters: Double = 25.0)

data class NavigationConfig(
    val arrivalRadiusMeters: Double = 25.0,
    val accuracyWarningMeters: Double = 30.0,
    val maxEdgeIndicators: Int = 6,
    val canModifyPositions: Boolean = true,
    val canCreateLandmarks: Boolean = true,
) {
    companion object {
        fun fromServerValues(
            arrivalRadiusMeters: Double = 25.0,
            accuracyWarningMeters: Double = 30.0,
            maxEdgeIndicators: Int = 6,
            canModifyPositions: Boolean = true,
            canCreateLandmarks: Boolean = true,
        ) = NavigationConfig(
            arrivalRadiusMeters.coerceIn(5.0, 200.0),
            accuracyWarningMeters.coerceIn(5.0, 500.0),
            maxEdgeIndicators.coerceIn(1, 12),
            canModifyPositions,
            canCreateLandmarks,
        )
    }
}
