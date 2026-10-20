package mg.hydria.shared.navigation


data class IndicatorCandidate<T>(
    val entity: T,
    val distanceMeters: Double,
    val relativeBearingDegrees: Double,
    val isDestination: Boolean = false,
)

object EdgeIndicatorEngine {
    fun <T> prioritize(candidates: List<IndicatorCandidate<T>>, limit: Int = 6): List<IndicatorCandidate<T>> =
        candidates.sortedWith(
            compareByDescending<IndicatorCandidate<T>> { it.isDestination }.thenBy { it.distanceMeters }
        ).take(limit.coerceAtLeast(1))

    fun <T> groupByDirection(
        candidates: List<IndicatorCandidate<T>>,
        thresholdDegrees: Double = 12.0,
    ): List<List<IndicatorCandidate<T>>> {
        val groups = mutableListOf<MutableList<IndicatorCandidate<T>>>()
        prioritize(candidates, candidates.size.coerceAtLeast(1)).forEach { candidate ->
            val group = groups.firstOrNull { existing ->
                existing.none { it.isDestination } && !candidate.isDestination &&
                    kotlin.math.abs(
                        GeoMath.relativeDirectionDegrees(candidate.relativeBearingDegrees, existing.first().relativeBearingDegrees)
                    ) <= thresholdDegrees
            }
            if (group == null) groups += mutableListOf(candidate) else group += candidate
        }
        return groups
    }
}

