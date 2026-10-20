package mg.hydria.shared.rules.forms

import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ActivityTargetRulesTest {
    private fun activity(rules: JSONObject?) = JSONObject().put("id", "a1").put("nom", "Anti-rouille")
        .apply { if (rules != null) put("regles", rules) }
    private val pe = WorkTarget("pe", "p1", "Point d'eau · BF1", "tp")
    private val eq = WorkTarget("eq", "e1", "Équipement · Réservoir", "te")

    @Test fun snapshotAncienToutFacultatif() {
        val rules = ActivityTargetRules.of(activity(null))
        assertNull(rules.error("x", null, emptyList(), 0))
        assertTrue(rules.allowsTarget("eq") && rules.allowsTarget("pe"))
    }

    @Test fun cibleEtComposantsObligatoires() {
        val rules = ActivityTargetRules.of(activity(JSONObject()
            .put("cible_mode", "obligatoire").put("cible_types", "equipement").put("composants_mode", "obligatoire")))
        assertEquals("Précisez l'équipement concerné pour « Anti-rouille »", rules.error("Anti-rouille", null, emptyList(), 0))
        assertFalse(rules.allowsTarget("pe"))
        assertNotNull(rules.error("Anti-rouille", pe, emptyList(), 0))
        assertNotNull(rules.error("Anti-rouille", eq, emptyList(), 2))
        assertNull(rules.error("Anti-rouille", eq, emptyList(), 0))   // catalogue vide : rien d'exigible
        assertNull(rules.error("Anti-rouille", eq, listOf("c1"), 2))
    }

    @Test fun composantsAdmisSansAccentsNiCasse() {
        val rules = ActivityTargetRules.of(activity(JSONObject().put("composants_multiple", false)
            .put("composants_admis", JSONArray().put("Boîte métallique").put("Fer plat").put("Cadenas vita gasy"))))
        val catalog = listOf("Boite metallique", "Robinet", "FER PLAT", "Cadenas-vita gasy").map { JSONObject().put("nom", it) }
        assertEquals(listOf("Boite metallique", "FER PLAT", "Cadenas-vita gasy"), rules.filterComponents(catalog).map { it.optString("nom") })
        assertNotNull(rules.error("Anti-rouille", eq, listOf("c1", "c2"), 3))
    }
}
