package mg.hydria.shared.terrain

import kotlin.math.abs

object TerrainMeasurementEngine {
    data class TrendSummary(
        val current: Double,
        val previous: Double?,
        val delta: Double?,
        val variationPercent: Double?,
        val recentAverage: Double,
        val trend: String,
    )

    data class HeadMeterSummary(
        val volumeHead: Double,
        val volumeDownstream: Double,
        val gap: Double,
        val gapPercent: Double,
        val dailyAverage: Double,
        val classification: String,
        val recommendation: String,
    )

    fun flowFromVolume(volumeLiters: Double, durationSeconds: Double): Double {
        require(volumeLiters >= 0) { "Le volume ne peut pas être négatif" }
        require(durationSeconds > 0) { "Le temps doit être supérieur à zéro" }
        return volumeLiters / durationSeconds
    }

    fun trend(current: Double, recentNewestFirst: List<Double>): TrendSummary {
        val previous = recentNewestFirst.firstOrNull()
        val delta = previous?.let { current - it }
        val variation = if (previous != null && previous != 0.0) delta!! / previous * 100 else null
        val average = (recentNewestFirst + current).average()
        val label = when {
            variation == null -> "Première mesure"
            variation < -10 -> "Baisse inhabituelle à vérifier"
            variation < -2 -> "Baisse légère"
            variation > 10 -> "Hausse inhabituelle à vérifier"
            variation > 2 -> "Hausse légère"
            else -> "Stable"
        }
        return TrendSummary(current, previous, delta, variation, average, label)
    }

    fun headMeter(previousIndex: Double, newIndex: Double, downstream: Double, days: Long): HeadMeterSummary {
        require(newIndex >= previousIndex) { "Le nouvel index doit être supérieur ou égal au précédent" }
        val volumeHead = newIndex - previousIndex
        val gap = volumeHead - downstream
        val percent = if (volumeHead != 0.0) abs(gap / volumeHead * 100) else 0.0
        val classification = when {
            percent < 5 -> "Bon"
            percent < 10 -> "Acceptable"
            percent < 20 -> "À investiguer"
            else -> "Anormal"
        }
        val recommendation = when (classification) {
            "Bon" -> "Les volumes restent proches."
            "Acceptable" -> "Poursuivre la surveillance."
            "À investiguer" -> "Vérifier les fuites, compteurs et relevés."
            else -> "Un contrôle terrain est recommandé rapidement."
        }
        return HeadMeterSummary(
            volumeHead, downstream, gap, percent,
            if (days > 0) volumeHead / days else volumeHead,
            classification, recommendation,
        )
    }
}
