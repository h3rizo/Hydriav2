package mg.hydria.app.repairs

import mg.hydria.shared.rules.repairs.RepairOverviewGateway
import mg.hydria.shared.rules.repairs.RepairRules
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.util.Locale

class RepairOverviewCompatibilityTest {
    @Test fun jsonGatewayMatchesFormerAndroidGroupingAndFiltering() {
        val items = listOf(
            JSONObject("""{"id":"1","ouvrage_nom":" Puits ","priorite":"Urgente","date_prevue":"2026-09-08","titre":"B"}"""),
            JSONObject("""{"id":"2","ouvrage_nom":"puits","priorite_code":"critique","date_prevue":"2026-09-09","titre":"A","statut":"Terminée"}"""),
            JSONObject("""{"id":"3","ouvrage_id":7,"ouvrage_nom":"Source","priorite":"Haute","hors_perimetre":true}"""),
            JSONObject("""{"id":"4","ouvrage_id":8,"ouvrage_nom":"Borne","priorite":"Normale","date_prevue":"bad"}"""))
        val pending = setOf("4")
        for (showCompleted in listOf(false, true)) for (showOutside in listOf(false, true)) {
            val expected = items.filter {
                (showCompleted || !(RepairRules.isCompleted(it) || it.optString("id") in pending)) &&
                    (showOutside || !it.optBoolean("hors_perimetre"))
            }
            val visible = RepairOverviewGateway.visible(items, pending, showCompleted, showOutside)
            assertEquals(expected, visible)
            val groups = expected.groupBy(RepairRules::workKey).entries.sortedWith(
                compareByDescending<Map.Entry<String, List<JSONObject>>> { it.value.maxOf(RepairRules::criticality) }
                    .thenBy { it.value.minOf(RepairRules::dateKey) }
                    .thenBy { it.value.first().optString("ouvrage_nom").lowercase(Locale.FRANCE) })
            val actual = RepairOverviewGateway.prepare(visible, pending)
            assertEquals(groups.map { it.key }, actual.groups.map { it.workKey })
            assertEquals(groups.map { group -> group.value.sortedWith(compareByDescending<JSONObject>(RepairRules::criticality)
                .thenBy(RepairRules::dateKey).thenBy { RepairRules.activityLabel(it).lowercase(Locale.FRANCE) }) }, actual.groups.map { it.items })
            assertEquals(expected.count { RepairRules.isCompleted(it) || it.optString("id") in pending }, actual.completedCount)
        }
    }
}
