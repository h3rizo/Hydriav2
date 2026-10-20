package mg.hydria.shared.navigation

import kotlin.math.ceil

class HeadingSmoother {
    private var smoothed: Double? = null

    fun update(bearingDegrees: Double): Double {
        val raw = GeoMath.normalize360(bearingDegrees)
        val previous = smoothed
        val delta = if (previous == null) 0.0 else GeoMath.relativeDirectionDegrees(raw, previous)
        val next = if (previous == null) raw else GeoMath.normalize360(previous + delta * 0.2)
        smoothed = next
        return next
    }
}

data class NavigationProgress(
    val distanceMeters: Double,
    val bearingDegrees: Double,
    val relativeDirectionDegrees: Double,
    val estimatedMinutes: Int?,
    val hasArrived: Boolean,
)

object NavigationProgressRules {
    fun acceptsLocation(nowMillis: Long, capturedAtMillis: Long): Boolean =
        nowMillis - capturedAtMillis <= 120_000L

    fun calculate(
        latitude: Double,
        longitude: Double,
        destinationLatitude: Double,
        destinationLongitude: Double,
        referenceBearing: Double,
        speedMetersPerSecond: Float?,
        arrivalRadiusMeters: Double,
    ): NavigationProgress {
        val distance = GeoMath.distanceMeters(latitude, longitude, destinationLatitude, destinationLongitude)
        val bearing = GeoMath.bearingDegrees(latitude, longitude, destinationLatitude, destinationLongitude)
        return NavigationProgress(
            distance,
            bearing,
            GeoMath.relativeDirectionDegrees(bearing, referenceBearing),
            if (speedMetersPerSecond != null && speedMetersPerSecond > 0.8f)
                ceil(distance / speedMetersPerSecond / 60.0).toInt() else null,
            distance <= arrivalRadiusMeters,
        )
    }
}
