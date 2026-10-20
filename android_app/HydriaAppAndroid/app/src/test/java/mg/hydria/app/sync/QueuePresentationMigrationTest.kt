package mg.hydria.app.sync

import mg.hydria.shared.sync.*
import org.json.*
import org.junit.Assert.*
import org.junit.Test

class QueuePresentationMigrationTest {
    @Test fun overviewSkipsMalformedRowsAndKeepsOriginalJsonObjects() {
        val reading = JSONObject().put("type","reading")
        val conflict = JSONObject().put("type","terrain_photo")
            .put("payload",JSONObject().put("_sync_conflict",JSONObject.NULL))
        val photo = JSONObject().put("type","terrain_photo").put("last_error","network")
        val result = QueueOverviewGateway.summarize(JSONArray().put("bad").put(reading).put(conflict).put(photo))
        assertEquals(3,result.items.size)
        assertSame(reading,result.items[0])
        assertSame(conflict,result.conflicts.single())
        assertSame(photo,result.ordinary[1])
        assertEquals(1,result.photoCount)
        assertEquals(1,result.readingCount)
    }
    @Test fun allJournalBranchesMatchLegacyIncludingMalformedSocialCards() {
        val items = mutableListOf<JSONObject>()
        for (type in listOf("reading","terrain_photo","terrain_data","save_repair","save_planning","unknown")) {
            for (operation in listOf("photo_point","photo_equipment","update_point","flow_measure","head_meter_reading","unknown")) {
                for (cards in listOf("[]","[{},{}]","broken")) {
                    val payload = JSONObject().put("operation_type",operation).put("point_eau_id","p")
                        .put("date_releve","2026-09-09").put("nouvel_index","12").put("cartes_sociales",cards)
                        .put("equipment_id","e").put("photo_data","encoded").put("point_id","")
                        .put("subscriber_name",JSONObject.NULL).put("telephone","").put("latitude","1.2")
                        .put("longitude","2.3").put("ouvrage_id","w").put("date","d")
                        .put("debit_l_s","5").put("meter_id","m").put("new_index","6")
                    val item = JSONObject().put("type",type).put("payload",payload).put("local_uuid","u")
                        .put("last_error","error").put("retry_count",3)
                    assertEquals(LegacyQueueJournal.payloadDetails(item),QueueJournalGateway.payloadDetails(item))
                    items += item
                }
            }
        }
        assertEquals(LegacyQueueJournal.journal(items),QueueJournalGateway.journal(items))
        assertEquals(LegacyQueueJournal.journal(emptyList()),QueueJournalGateway.journal(emptyList()))
    }
    @Test fun serverComparisonPreservesAbsentAndExplicitEmptyFields() {
        val bodies = listOf(JSONObject(),JSONObject().put("server_updated_at","date"),
            JSONObject().put("server_value",JSONObject()),
            JSONObject().put("server_value",JSONObject().put("subscriber_name"," ").put("telephone","")
                .put("has_coordinates",false).put("has_photo",false)),
            JSONObject().put("server_updated_at","date").put("server_value",JSONObject()
                .put("has_coordinates",true).put("latitude",1).put("longitude",2).put("has_photo",true)))
        bodies.forEach { assertEquals(LegacyQueueJournal.serverConflictDetails(it),QueueJournalGateway.serverConflictDetails(it)) }
    }
}
