package mg.hydria.app.navigation.geo

import mg.hydria.shared.navigation.GeoMath as SharedGeoMath
import kotlin.math.roundToInt

object GeoMath {
    fun isValid(latitude: Double, longitude: Double) = SharedGeoMath.isValid(latitude, longitude)
    fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double) =
        SharedGeoMath.distanceMeters(lat1, lon1, lat2, lon2)
    fun bearingDegrees(lat1: Double, lon1: Double, lat2: Double, lon2: Double) =
        SharedGeoMath.bearingDegrees(lat1, lon1, lat2, lon2)
    fun relativeDirectionDegrees(targetBearing: Double, referenceBearing: Double) =
        SharedGeoMath.relativeDirectionDegrees(targetBearing, referenceBearing)
    fun normalize360(value: Double) = SharedGeoMath.normalize360(value)

    fun formatDistance(meters: Double): String = if (meters < 1000) {
        "${meters.roundToInt()} m (direct)"
    } else {
        String.format(java.util.Locale.FRANCE, "%.1f km (direct)", meters / 1000.0)
    }

    data class EdgePoint(val x: Float, val y: Float, val rotationDegrees: Float)

    fun projectBearingToEdge(relativeBearingDegrees: Double, width: Float, height: Float, padding: Float): EdgePoint =
        SharedGeoMath.projectBearingToEdge(relativeBearingDegrees, width, height, padding).let {
            EdgePoint(it.x, it.y, it.rotationDegrees)
        }
}
