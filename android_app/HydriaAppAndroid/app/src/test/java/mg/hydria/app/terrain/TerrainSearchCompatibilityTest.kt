package mg.hydria.app.terrain

import mg.hydria.shared.rules.terrain.TerrainRules
import mg.hydria.shared.rules.search.SearchRules
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class TerrainSearchCompatibilityTest {
    @Test fun terrainJsonKeepsCoercionsAndOriginalObjectIdentity() {
        val point = JSONObject("""{"has_coordinates":"true","has_photo":true}""")
        val work = JSONObject().put("points_eau", JSONArray().put(point))
        val tasks = TerrainRules.buildTourTasks(JSONObject().put("ouvrages", JSONArray().put(work)))
        assertEquals(1, tasks.size)
        assertEquals("subscriber", tasks.single().category)
        assertSame(point, tasks.single().item)
        assertSame(work, tasks.single().work)
        assertEquals(3, TerrainRules.remainingTasks(JSONObject("""{"points_sans_photo":"3","captages_sans_mesure":-2,"unknown":99}""")))
        assertEquals(0, TerrainRules.ouvrageAgeYears(JSONObject("""{"age_annees":"0","annee_realisation":2000}""")))
        assertEquals(LocalDate.now().year - 2000, TerrainRules.ouvrageAgeYears(JSONObject("""{"annee_realisation":" 2000 ","annee_realisation_avant":1990}""")))
    }
    @Test fun downstreamJsonPreservesDateWindowAndMeterSelection() {
        val work = JSONObject("""{"points_eau":[{"compteur_tete_id":"m","historique_recent":[{"date":"2024-02-28","consommation":100},{"date":"2024-02-29","consommation":"2.5"},{"date":"2024-03-01","consommation":3},{"date":"invalid","consommation":999}]},{"compteur_tete_id":"other","historique_recent":[{"date":"2024-03-01","consommation":999}]}]}""")
        assertEquals(5.5, TerrainRules.localDownstream(work, "m", LocalDate.of(2024, 2, 28), LocalDate.of(2024, 3, 1)), 0.0)
    }
    @Test fun perimeterKeepsDirectWorksOrPromotesExtendedStats() {
        val terrain = JSONObject("""
            {"stats":{"completion_score":40},"stats_perimetre_etendu":{"completion_score":90},
             "ouvrages":[{"id":"a","responsable_direct":true},{"id":"b","responsable_direct":false},{"id":"c"}]}
        """)
        val direct = TerrainRules.perimeter(terrain, etendu = false)
        assertEquals(listOf("a", "c"),
            (0 until direct.getJSONArray("ouvrages").length()).map { direct.getJSONArray("ouvrages").getJSONObject(it).getString("id") })
        assertEquals(40, direct.getJSONObject("stats").getInt("completion_score"))
        // l'original n'est pas muté
        assertEquals(3, terrain.getJSONArray("ouvrages").length())

        val extended = TerrainRules.perimeter(terrain, etendu = true)
        assertEquals(3, extended.getJSONArray("ouvrages").length())
        assertEquals(90, extended.getJSONObject("stats").getInt("completion_score"))
    }

    @Test fun worksGroupKeySplitsIntoThreeLevelsWithFallbackLabels() {
        val key = SearchRules.worksGroupKey(JSONObject("""{"region":"Boeny","commune":"Mahajanga I"}"""))
        assertEquals(listOf("Boeny", "District non renseigné", "Mahajanga I"),
            key.split(SearchRules.GROUP_KEY_SEPARATOR))
        assertEquals(listOf("Région non renseignée", "District non renseigné", "Commune non renseignée"),
            SearchRules.worksGroupKey(JSONObject()).split(SearchRules.GROUP_KEY_SEPARATOR))
    }

    @Test fun searchResultRetainsApiShapeAndDetailsReference() {
        val work = JSONObject("""{"id":12,"nom":"Source École","type":"AEP","commune":"Nord"}""")
        val results = SearchRules.offlineWorksResults(JSONArray().put(work), "école")
        assertTrue(results.getBoolean("success"))
        assertFalse(results.getBoolean("has_next"))
        assertEquals(1, results.getInt("total"))
        val item = results.getJSONArray("results").getJSONObject(0)
        assertEquals("12", item.getString("id"))
        assertEquals("ouvrage", item.getString("type"))
        assertEquals("Source École", item.getString("name"))
        assertEquals(item.getString("name"), item.getString("title"))
        assertEquals("AEP · Nord", item.getString("subtitle"))
        assertSame(work, item.getJSONObject("details"))
        assertEquals(0, SearchRules.offlineWorksResults(JSONArray().put(work), "ecole").getInt("total"))
    }
}
