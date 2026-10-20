package mg.hydria.shared.terrain

import kotlinx.datetime.LocalDate

data class TerrainPoint<T>(val item: T, val hasCoordinates: Boolean, val hasSubscriberName: Boolean, val hasPhoto: Boolean)
data class TerrainWork<W, T>(val work: W, val points: List<TerrainPoint<T>>, val equipment: List<TerrainPoint<T>>)
data class TerrainTask<W, T>(val item: T, val work: W, val category: String)
data class DownstreamReading(val date: String, val consumption: Double)
data class DownstreamPoint(val meterId: String, val readings: List<DownstreamReading>)

object TerrainTaskRules {
    val statisticKeys = listOf("captages_sans_mesure", "points_sans_coordonnees", "points_sans_nom_abonne",
        "points_sans_photo", "equipements_sans_photo", "captages_mesure_en_retard")
    fun remainingTasks(counts: List<Int>): Int = counts.sumOf { it.coerceAtLeast(0) }
    fun ageYears(serverAge: Int?, realizationYears: List<Int>, currentYear: Int): Int? {
        if (serverAge != null && serverAge >= 0) return serverAge
        val year = realizationYears.firstOrNull() ?: return null
        return (currentYear - year).takeIf { it >= 0 }
    }
    fun ageLabel(age: Int?): String = if (age == null) "Âge non renseigné" else "Âge : $age an${if (age > 1) "s" else ""}"
    fun <W, T> buildTourTasks(works: List<TerrainWork<W, T>>): List<TerrainTask<W, T>> = buildList {
        listOf("gps", "subscriber", "point_photo", "equipment_photo").forEach { category ->
            works.forEach { work ->
                val items = if (category == "equipment_photo") work.equipment else work.points
                items.forEach { point ->
                    val missing = when (category) {
                        "gps" -> !point.hasCoordinates
                        "subscriber" -> !point.hasSubscriberName
                        else -> !point.hasPhoto
                    }
                    if (missing) add(TerrainTask(point.item, work.work, category))
                }
            }
        }
    }
    fun localDownstream(points: List<DownstreamPoint>, meterId: String, after: String?, until: String): Double {
        val start = after?.let { LocalDate.parse(it) }
        val end = LocalDate.parse(until)
        var total = 0.0
        points.forEach { point ->
            if (point.meterId == meterId) point.readings.forEach { reading ->
                val date = runCatching { LocalDate.parse(reading.date) }.getOrNull()
                if (date != null && (start == null || date > start) && date <= end) total += reading.consumption
            }
        }
        return total
    }
}
