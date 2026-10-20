package mg.hydria.shared.navigation

import kotlin.math.*

object GeoMath {
    private fun toRadians(value: Double): Double = value / 180.0 * PI
    private fun toDegrees(value: Double): Double = value * 180.0 / PI

    private const val EARTH_RADIUS_M = 6_371_008.8

    fun isValid(latitude: Double, longitude: Double): Boolean =
        latitude.isFinite() && longitude.isFinite() && latitude in -90.0..90.0 && longitude in -180.0..180.0

    fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        require(isValid(lat1, lon1) && isValid(lat2, lon2)) { "Coordonnées invalides" }
        val phi1 = toRadians(lat1)
        val phi2 = toRadians(lat2)
        val dPhi = toRadians(lat2 - lat1)
        val dLambda = toRadians(lon2 - lon1)
        val a = sin(dPhi / 2).pow(2) + cos(phi1) * cos(phi2) * sin(dLambda / 2).pow(2)
        return EARTH_RADIUS_M * 2 * atan2(sqrt(a), sqrt(1 - a))
    }

    fun bearingDegrees(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        require(isValid(lat1, lon1) && isValid(lat2, lon2)) { "Coordonnées invalides" }
        val phi1 = toRadians(lat1)
        val phi2 = toRadians(lat2)
        val lambda = toRadians(lon2 - lon1)
        val y = sin(lambda) * cos(phi2)
        val x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(lambda)
        return normalize360(toDegrees(atan2(y, x)))
    }

    fun relativeDirectionDegrees(targetBearing: Double, referenceBearing: Double): Double {
        var result = normalize360(targetBearing) - normalize360(referenceBearing)
        if (result >= 180.0) result -= 360.0
        if (result < -180.0) result += 360.0
        return result
    }

    fun normalize360(value: Double): Double = ((value % 360.0) + 360.0) % 360.0


    data class EdgePoint(val x: Float, val y: Float, val rotationDegrees: Float)

    fun projectBearingToEdge(
        relativeBearingDegrees: Double,
        width: Float,
        height: Float,
        padding: Float,
    ): EdgePoint {
        require(width > padding * 2 && height > padding * 2)
        val angle = toRadians(relativeBearingDegrees - 90.0)
        val dx = cos(angle).toFloat()
        val dy = sin(angle).toFloat()
        val cx = width / 2f
        val cy = height / 2f
        val maxX = width / 2f - padding
        val maxY = height / 2f - padding
        val tx = if (abs(dx) < 1e-6f) Float.POSITIVE_INFINITY else maxX / abs(dx)
        val ty = if (abs(dy) < 1e-6f) Float.POSITIVE_INFINITY else maxY / abs(dy)
        val scale = min(tx, ty)
        return EdgePoint(
            x = cx + dx * scale,
            y = cy + dy * scale,
            rotationDegrees = relativeBearingDegrees.toFloat(),
        )
    }
}

