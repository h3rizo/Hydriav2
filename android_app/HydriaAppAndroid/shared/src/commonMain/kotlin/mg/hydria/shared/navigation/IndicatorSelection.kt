package mg.hydria.shared.navigation

import mg.hydria.shared.navigation.model.GeoCategory
import mg.hydria.shared.navigation.model.GeoEntity
import kotlin.math.hypot

data class ScreenPoint(val x: Float, val y: Float)

object IndicatorSelection {
    fun select(
        entities: List<GeoEntity>,
        visibleCategories: Set<GeoCategory>,
        originLatitude: Double,
        originLongitude: Double,
        cameraBearing: Double,
        destinationId: String?,
        width: Float,
        height: Float,
        limit: Int,
        project: (GeoEntity) -> ScreenPoint,
    ): List<IndicatorCandidate<GeoEntity>> {
        val candidates = entities.asSequence().filter { it.category in visibleCategories }.mapNotNull { entity ->
            val screen = project(entity)
            if (screen.x in 0f..width && screen.y in 0f..height) return@mapNotNull null
            val distance = GeoMath.distanceMeters(originLatitude, originLongitude, entity.latitude, entity.longitude)
            val bearing = GeoMath.bearingDegrees(originLatitude, originLongitude, entity.latitude, entity.longitude)
            IndicatorCandidate(entity, distance, GeoMath.relativeDirectionDegrees(bearing, cameraBearing),
                entity.id == destinationId)
        }.toList()
        return EdgeIndicatorEngine.prioritize(candidates, limit)
    }

    fun <T> nearestHit(
        items: List<T>,
        x: Float,
        y: Float,
        radius: Float,
        position: (T) -> ScreenPoint,
    ): T? {
        fun distance(item: T): Double {
            val point = position(item)
            return hypot((point.x - x).toDouble(), (point.y - y).toDouble())
        }
        return items.minByOrNull(::distance)?.takeIf { distance(it) < radius }
    }
}
