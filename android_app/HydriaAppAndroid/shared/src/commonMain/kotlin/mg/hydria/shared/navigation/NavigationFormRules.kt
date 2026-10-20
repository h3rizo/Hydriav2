package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.PlacementCandidate

data class CoordinateAvailability(val withoutCoordinates: Int, val nearbyWithoutCoordinates: Int, val withCoordinates: Int)

object NavigationFormRules {
    fun landmarkName(input: String, typeLabel: String): String = input.trim().ifBlank { typeLabel }

    fun coordinates(candidates: List<PlacementCandidate>, nearbyIds: Set<String>): CoordinateAvailability {
        val missing = candidates.filter { it.referenceLatitude == null || it.referenceLongitude == null }
        return CoordinateAvailability(missing.size, missing.count { it.id in nearbyIds },
            candidates.count { it.referenceLatitude != null && it.referenceLongitude != null })
    }
}
