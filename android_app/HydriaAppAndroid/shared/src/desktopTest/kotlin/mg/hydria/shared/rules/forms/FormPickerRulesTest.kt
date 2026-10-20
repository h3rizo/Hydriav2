package mg.hydria.shared.rules.forms

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class FormPickerRulesTest {
    private val terrain = JSONArray().put(JSONObject().put("id", "w1")
        .put("points_eau", JSONArray().put(JSONObject().put("id", "p1").put("code", "BF1").put("nom", "Rakoto").put("type_id", "tp")))
        .put("equipements", JSONArray().put(JSONObject().put("id", "e1").put("nom", "Réservoir").put("type", "Stockage").put("type_id", "te"))))
    private val catalog = JSONObject()
        .put("point_eau", JSONObject().put("tp", JSONArray().put(JSONObject().put("id", "c1").put("nom", "Robinet"))))
        .put("equipement", JSONObject().put("te", JSONArray().put(JSONObject().put("id", "c2").put("nom", "Vanne"))))

    @Test fun ciblesEtComposantsDeLOuvrage() {
        val targets = WorkTargetRules.targets(terrain, "w1")
        assertEquals(listOf("pe:p1", "eq:e1"), targets.map { it.key })
        assertEquals("Point d'eau · BF1 — Rakoto", targets[0].label)
        assertEquals(listOf("Vanne"), WorkTargetRules.components(catalog, targets[1]).map { it.optString("nom") })
        assertTrue(WorkTargetRules.targets(terrain, "inconnu").isEmpty())
        assertEquals("eq:e9", WorkTargetRules.existingKey(JSONObject().put("equipement_id", "e9")))
        assertNull(WorkTargetRules.existingKey(JSONObject()))
    }

    @Test fun autocompletionEtCascadePartagees() {
        assertEquals(listOf(0), AutocompleteMatch.filter(listOf("Ambanja BP", "Vohipeno"), "amb bp"))
        val tree = ActivityCascadeTree.buildWithoutGroups(listOf(
            JSONObject().put("id", "a").put("nom", "Fuite").put("type_activite", "Maintenance").put("groupe", "Opérations sur les ouvrages")))
        assertEquals(1, tree.size)
        assertEquals(Triple(0, 0, 0), ActivityCascadeTree.pathOf(tree, "a"))
    }
}
