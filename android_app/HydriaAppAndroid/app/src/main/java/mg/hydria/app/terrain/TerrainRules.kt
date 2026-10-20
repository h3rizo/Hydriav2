package mg.hydria.app.terrain

import org.json.JSONObject
import java.time.LocalDate

/**
 * Relais fin vers le module partage `shared` (Phase 0 de la migration
 * KMP). Le code metier reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/rules/terrain/TerrainRules.kt ;
 * ce fichier ne fait plus que le pointer.
 */
typealias TerrainBatchTask = mg.hydria.shared.rules.terrain.TerrainBatchTask

object TerrainRules {
    fun remainingTasks(stats: JSONObject): Int =
        mg.hydria.shared.rules.terrain.TerrainRules.remainingTasks(stats)

    fun ouvrageAgeYears(work: JSONObject): Int? =
        mg.hydria.shared.rules.terrain.TerrainRules.ouvrageAgeYears(work)

    fun ouvrageAgeLabel(work: JSONObject): String =
        mg.hydria.shared.rules.terrain.TerrainRules.ouvrageAgeLabel(work)

    fun buildTourTasks(terrain: JSONObject): List<TerrainBatchTask> =
        mg.hydria.shared.rules.terrain.TerrainRules.buildTourTasks(terrain)

    fun localDownstream(work: JSONObject, meterId: String, after: LocalDate?, until: LocalDate): Double =
        mg.hydria.shared.rules.terrain.TerrainRules.localDownstream(work, meterId, after, until)

    fun perimeter(terrain: JSONObject, etendu: Boolean): JSONObject =
        mg.hydria.shared.rules.terrain.TerrainRules.perimeter(terrain, etendu)
}
