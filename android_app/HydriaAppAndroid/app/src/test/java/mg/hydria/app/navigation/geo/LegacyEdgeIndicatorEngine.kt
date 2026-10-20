package mg.hydria.app.navigation.geo

object LegacyEdgeIndicatorEngine {
    fun prioritize(candidates: List<IndicatorCandidate>, limit: Int = 6): List<IndicatorCandidate> =
        candidates.sortedWith(
            compareByDescending<IndicatorCandidate> { it.isDestination }.thenBy { it.distanceMeters }
        ).take(limit.coerceAtLeast(1))

    fun groupByDirection(
        candidates: List<IndicatorCandidate>,
        thresholdDegrees: Double = 12.0,
    ): List<List<IndicatorCandidate>> {
        val groups = mutableListOf<MutableList<IndicatorCandidate>>()
        prioritize(candidates, candidates.size.coerceAtLeast(1)).forEach { candidate ->
            val group = groups.firstOrNull { existing ->
                existing.none { it.isDestination } && !candidate.isDestination &&
                    kotlin.math.abs(
                        LegacyGeoMath.relativeDirectionDegrees(candidate.relativeBearingDegrees, existing.first().relativeBearingDegrees)
                    ) <= thresholdDegrees
            }
            if (group == null) groups += mutableListOf(candidate) else group += candidate
        }
        return groups
    }
}

