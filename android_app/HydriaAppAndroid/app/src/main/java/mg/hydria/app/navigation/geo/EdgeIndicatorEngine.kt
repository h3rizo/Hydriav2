package mg.hydria.app.navigation.geo

import mg.hydria.app.navigation.model.GeoEntity

data class IndicatorCandidate(
    val entity: GeoEntity,
    val distanceMeters: Double,
    val relativeBearingDegrees: Double,
    val isDestination: Boolean = false,
)

object EdgeIndicatorEngine {
    private fun IndicatorCandidate.shared() = mg.hydria.shared.navigation.IndicatorCandidate(
        this, distanceMeters, relativeBearingDegrees, isDestination,
    )

    fun prioritize(candidates: List<IndicatorCandidate>, limit: Int = 6): List<IndicatorCandidate> =
        mg.hydria.shared.navigation.EdgeIndicatorEngine.prioritize(candidates.map { it.shared() }, limit)
            .map { it.entity }

    fun groupByDirection(candidates: List<IndicatorCandidate>, thresholdDegrees: Double = 12.0): List<List<IndicatorCandidate>> =
        mg.hydria.shared.navigation.EdgeIndicatorEngine.groupByDirection(candidates.map { it.shared() }, thresholdDegrees)
            .map { group -> group.map { it.entity } }
}
