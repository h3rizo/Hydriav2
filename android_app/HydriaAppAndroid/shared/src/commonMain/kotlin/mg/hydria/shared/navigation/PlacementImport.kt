package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.GeoCategory

/** Null village links mean preserve the local value; an empty string means clear it. */
data class PlacementImport(
    val entityId: String,
    val category: GeoCategory,
    val name: String,
    val code: String,
    val villageName: String,
    val referenceLatitude: Double?,
    val referenceLongitude: Double?,
    val hasPhoto: Boolean,
    val servedVillageIds: String?,
    val ouvrageId: String,
    val serverUpdatedAt: String,
)
