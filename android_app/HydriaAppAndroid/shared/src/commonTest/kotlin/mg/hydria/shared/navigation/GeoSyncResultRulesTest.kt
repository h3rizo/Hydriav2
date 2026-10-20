package mg.hydria.shared.navigation

import kotlin.test.*

class GeoSyncResultRulesTest {
    @Test fun successfulPositionUpdatesEntityBeforeItsHistory() {
        val operation = GeoSyncOperation("geo_position_upsert", "water_point", "landmark", "p", "history")
        assertEquals(listOf(
            GeoSyncChange(GeoSyncChangeKind.ENTITY_SYNCED, "water_point", "p"),
            GeoSyncChange(GeoSyncChangeKind.HISTORY_SYNCED, id = "history"),
        ), GeoSyncResultRules.changes(operation, false))
    }
    @Test fun positionConflictPreservesHistoryAndFallsBackToEntityKind() {
        val operation = GeoSyncOperation("geo_position_upsert", " ", "equipment", "e", "history")
        assertEquals(listOf(GeoSyncChange(GeoSyncChangeKind.ENTITY_CONFLICT, "equipment", "e")),
            GeoSyncResultRules.changes(operation, true))
    }
    @Test fun archiveConflictsNeverArchiveAndMarkerCategoriesRemainExplicit() {
        val operation = GeoSyncOperation("landmark_archive", markerCategory = "water_point", markerId = "m")
        assertEquals(listOf(GeoSyncChange(GeoSyncChangeKind.ENTITY_ARCHIVED, "water_point", "m")),
            GeoSyncResultRules.changes(operation, false))
        assertEquals(listOf(GeoSyncChange(GeoSyncChangeKind.ENTITY_CONFLICT, "water_point", "m")),
            GeoSyncResultRules.changes(operation, true))
        assertEquals(listOf(GeoSyncChange(GeoSyncChangeKind.ENTITY_SYNCED, "landmark", "m")),
            GeoSyncResultRules.changes(GeoSyncOperation("landmark_upsert", markerId = "m"), false))
    }
    @Test fun photosAndUnknownOperationsDoNotChangeGeographicStatus() {
        for (type in listOf("landmark_photo_upload","unknown","")) {
            for (conflict in listOf(true,false)) {
                assertTrue(GeoSyncResultRules.changes(GeoSyncOperation(type),conflict).isEmpty())
            }
        }
    }
}
