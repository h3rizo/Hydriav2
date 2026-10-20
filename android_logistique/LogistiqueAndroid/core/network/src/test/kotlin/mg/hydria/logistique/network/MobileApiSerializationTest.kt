package mg.hydria.logistique.network

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MobileApiSerializationTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun loginRequestUsesServerFieldNames() {
        val encoded = json.encodeToString(LoginRequest("agent", "secret", "device", "Pixel"))
        assertTrue(encoded.contains("\"device_id\":\"device\""))
        assertTrue(encoded.contains("\"device_label\":\"Pixel\""))
    }

    @Test
    fun bootstrapDecimalsRemainExactStrings() {
        val decoded = json.decodeFromString<BootstrapResponse>(
            """{
              "cursor":"2026-09-05T12:00:00Z",
              "server_time":"2026-09-05T12:00:00Z",
              "payload":{
                "user":{"id":"u","username":"agent","display_name":"Agent","inventory_scope":"base"},
                "capabilities":[],"bases":[],"magasins":[],"article_types":[],"articles":[],
                "stock_positions":[{
                  "id":"p","article_id":"a","base_id":"b","magasin_id":null,
                  "current":"10.25","reserved":"1.10","available":"9.15","status":"OK",
                  "updated_at":"2026-09-05T12:00:00Z","revision":1,"estimated":true
                }]
              }
            }""".trimIndent()
        )
        assertEquals("10.25", decoded.payload.stockPositions.single().current)
        assertEquals("9.15", decoded.payload.stockPositions.single().available)
    }

    @Test
    fun activityDueStatsUseDistinctServerCounters() {
        val decoded = json.decodeFromString<ActivityDueStatsDto>(
            """{"repair_overdue_works":7,"maintenance_only_works":4,"as_of_date":"2026-09-05"}"""
        )
        assertEquals(7, decoded.repairOverdueWorks)
        assertEquals(4, decoded.maintenanceOnlyWorks)
    }
}
