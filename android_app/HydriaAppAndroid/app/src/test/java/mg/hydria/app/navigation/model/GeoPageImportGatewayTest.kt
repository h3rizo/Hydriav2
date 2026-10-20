package mg.hydria.app.navigation.model

import mg.hydria.shared.navigation.*
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class GeoPageImportGatewayTest {
    @Test fun aliasesUseFirstArrayEvenWhenEmptyAndImportPrecedesDeletion() {
        val events = mutableListOf<String>()
        val entities = JSONObject().put("villages",JSONArray().put("malformed").put(JSONObject()))
            .put("points_eau",JSONArray()).put("water_points",JSONArray().put(JSONObject()))
            .put("equipments",JSONArray().put(JSONObject())).put("landmarks",JSONArray().put(JSONObject()))
            .put("types_reperes",JSONArray())
        val page = JSONObject().put("entities",entities).put("deletions",JSONArray().put(
            JSONObject().put("entity_kind","water_point").put("entity_id","p")))
        val count = GeoPageImportGateway.importPage(JSONObject().put("data",page),
            { values, category, work ->
                assertEquals("",work); events += category.storageKey + ":" + values!!.length()
            },
            { values -> assertSame(entities.getJSONArray("types_reperes"),values); events += "types" },
            { category, id -> events += "delete:$category:$id" },
        )
        assertEquals(4,count)
        assertEquals(listOf("village:2","water_point:0","equipment:1","landmark:1","types","delete:water_point:p"),events)
    }
    @Test fun deletionFallbacksSkipMalformedAndIncompleteEntries() {
        val deleted = mutableListOf<String>()
        val page = JSONObject().put("suppressions",JSONArray().put("bad")
            .put(JSONObject().put("entity_kind"," ").put("category","landmark").put("entity_id","").put("id","m"))
            .put(JSONObject().put("entity_kind","water_point"))
            .put(JSONObject().put("id","orphan")))
        GeoPageImportGateway.importPage(page,{ _, _, _ -> fail("no entities") },{},
            { category,id -> deleted += "$category:$id" })
        assertEquals(listOf("landmark:m"),deleted)
        page.put("deletions",JSONArray())
        deleted.clear()
        GeoPageImportGateway.importPage(page,{ _, _, _ -> },{}, { category,id -> deleted += "$category:$id" })
        assertTrue(deleted.isEmpty())
    }
    @Test fun snapshotPreservesWorkAssociationAndOrder() {
        val events = mutableListOf<String>()
        val work = JSONObject().put("id","w").put("points_eau",JSONArray().put(JSONObject()))
        val snapshot = JSONObject().put("terrain",JSONObject().put("ouvrages",JSONArray().put("bad").put(work)))
            .put("navigation",JSONObject().put("villages",JSONArray()))
        GeoPageImportGateway.importSnapshot(snapshot,
            { values, category, workId -> events += category.storageKey + ":" + workId + ":" + (values?.length() ?: -1) },
            { events += "types" },
        )
        assertEquals(listOf("water_point:w:1","equipment:w:-1","village::0","landmark::-1","types"),events)
        GeoPageImportGateway.importSnapshot(null,{ _, _, _ -> fail("null snapshot") },{ fail("null snapshot") })
    }
    @Test fun importExceptionStopsBeforeTypesAndDeletion() {
        val failure = IllegalStateException("write failed")
        val page = JSONObject().put("villages",JSONArray().put(JSONObject()))
        try {
            GeoPageImportGateway.importPage(page,{ _, _, _ -> throw failure },
                { fail("must not continue") },{ _, _ -> fail("must not delete") })
            fail("exception expected")
        } catch (actual: IllegalStateException) {
            assertSame(failure,actual)
        }
    }
    @Test fun landmarkTypesPreserveDefaultsExplicitValuesAndSkipBlankIds() {
        val saved = mutableListOf<LandmarkTypeImport>()
        val values = JSONArray().put("bad").put(JSONObject().put("id"," "))
            .put(JSONObject().put("id","a"))
            .put(JSONObject().put("id","b").put("nom","B").put("icone","").put("couleur","")
                .put("ordre_affichage",-2).put("actif",false))
        GeoPageImportGateway.importLandmarkTypes(values) { saved += it }
        assertEquals(listOf(
            LandmarkTypeImport("a","","","autre","#58D594",0,true,""),
            LandmarkTypeImport("b","B","","","",-2,false,""),
        ),saved)
    }
}
