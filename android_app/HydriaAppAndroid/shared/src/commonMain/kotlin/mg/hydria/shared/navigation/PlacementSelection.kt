package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.PlacementCandidate

data class PlacementSelectionResult(
    val candidates: List<Pair<PlacementCandidate, Double?>>,
    val usesNearbyCoordinates: Boolean,
)

object PlacementSelection {
    fun distance(candidate: PlacementCandidate, latitude: Double, longitude: Double): Double? {
        val lat = candidate.referenceLatitude ?: return null
        val lon = candidate.referenceLongitude ?: return null
        return GeoMath.distanceMeters(latitude, longitude, lat, lon)
    }

    fun select(
        candidates: List<PlacementCandidate>,
        latitude: Double,
        longitude: Double,
        hasCoordinates: Boolean,
        nearbyCandidateIds: Set<String>,
        sortKey: (String) -> String = { it.lowercase() },
    ): PlacementSelectionResult {
        val sorted = candidates.filter { candidate ->
            val positioned = candidate.referenceLatitude != null && candidate.referenceLongitude != null
            positioned == hasCoordinates && (hasCoordinates || candidate.id in nearbyCandidateIds)
        }.map { it to distance(it, latitude, longitude) }
            .sortedWith(
                if (hasCoordinates) compareBy<Pair<PlacementCandidate, Double?>> { it.second ?: Double.MAX_VALUE }
                else compareBy<Pair<PlacementCandidate, Double?>> { sortKey(it.first.villageName) }
                    .thenBy { sortKey(it.first.name) }
            )
        val close = if (hasCoordinates) sorted.filter { (_, distance) ->
            (distance ?: Double.MAX_VALUE) <= 25_000.0
        } else emptyList()
        return PlacementSelectionResult(
            (if (close.isNotEmpty()) close else sorted).take(200),
            close.isNotEmpty(),
        )
    }
}
