package mg.hydria.shared.terrain

import kotlin.test.*

class TerrainTaskRulesTest {
    @Test fun taskCountsIgnoreNegativeValues() {
        assertEquals(7, TerrainTaskRules.remainingTasks(listOf(-2, 0, 3, 4)))
        assertEquals(0, TerrainTaskRules.remainingTasks(emptyList()))
    }
    @Test fun serverAgeWinsAndFirstRealizationYearKeepsPrecedence() {
        assertEquals(0, TerrainTaskRules.ageYears(0, listOf(2000), 2026))
        assertEquals(6, TerrainTaskRules.ageYears(-1, listOf(2020, 2000), 2026))
        assertNull(TerrainTaskRules.ageYears(null, listOf(2030, 2000), 2026))
        assertNull(TerrainTaskRules.ageYears(null, emptyList(), 2026))
        assertEquals("Âge : 0 an", TerrainTaskRules.ageLabel(0))
        assertEquals("Âge : 2 ans", TerrainTaskRules.ageLabel(2))
        assertEquals("Âge non renseigné", TerrainTaskRules.ageLabel(null))
    }
    @Test fun tourKeepsCategoryThenWorkThenItemOrder() {
        val works = listOf(TerrainWork("A", listOf(TerrainPoint("a", false, false, false), TerrainPoint("complete", true, true, true)),
            listOf(TerrainPoint("equip", false, false, false))),
            TerrainWork("B", listOf(TerrainPoint("b", false, true, false)), emptyList()))
        assertEquals(listOf("gps:A:a", "gps:B:b", "subscriber:A:a", "point_photo:A:a", "point_photo:B:b", "equipment_photo:A:equip"),
            TerrainTaskRules.buildTourTasks(works).map { "${it.category}:${it.work}:${it.item}" })
    }
    @Test fun downstreamUsesExclusiveStartInclusiveEndAndMatchingMeter() {
        val points = listOf(DownstreamPoint("m", listOf(DownstreamReading("2024-02-28", 1.0), DownstreamReading("2024-02-29", 2.0),
            DownstreamReading("2024-03-01", 3.0), DownstreamReading("2024-03-02", 4.0), DownstreamReading("bad", 99.0))),
            DownstreamPoint("other", listOf(DownstreamReading("2024-03-01", 100.0))))
        assertEquals(5.0, TerrainTaskRules.localDownstream(points, "m", "2024-02-28", "2024-03-01"))
        assertEquals(6.0, TerrainTaskRules.localDownstream(points, "m", null, "2024-03-01"))
        assertEquals(0.0, TerrainTaskRules.localDownstream(points, "m", "2024-03-02", "2024-03-01"))
    }
    @Test fun invalidDatesAndTimestampAreSkippedAsBefore() {
        val points = listOf(DownstreamPoint("m", listOf(DownstreamReading("2026-02-29", 2.0),
            DownstreamReading("2026-03-01T00:00:00Z", 3.0), DownstreamReading("2026-03-01", 4.0))))
        assertEquals(4.0, TerrainTaskRules.localDownstream(points, "m", null, "2026-03-02"))
    }
}
