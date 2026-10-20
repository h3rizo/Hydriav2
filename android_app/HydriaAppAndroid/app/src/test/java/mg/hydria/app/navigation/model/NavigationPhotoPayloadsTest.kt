package mg.hydria.app.navigation.model

import mg.hydria.shared.navigation.NavigationPhotoPayloads
import org.junit.Assert.*
import org.junit.Test

class NavigationPhotoPayloadsTest {
    @Test fun pointAndEquipmentKeepTheirOwnIdentifiersAndFilename() {
        for (category in listOf(GeoCategory.WATER_POINT,GeoCategory.EQUIPMENT)) {
            val equipment = category == GeoCategory.EQUIPMENT
            val candidate = PlacementCandidate("id",category,"name",serverUpdatedAt="version")
            val value = NavigationPhotoPayloads.create(candidate,"encoded","uuid")
            val idKey = if(equipment) "equipment_id" else "point_id"
            assertEquals(setOf("local_uuid","operation_type",idKey,"photo_data","content_type","filename","base_updated_at"),
                value.keys().asSequence().toSet())
            assertEquals("uuid",value.getString("local_uuid"))
            assertEquals("id",value.getString(idKey))
            assertEquals(if(equipment) "photo_equipment" else "photo_point",value.getString("operation_type"))
            assertEquals(if(equipment) "equipement-terrain.jpg" else "point-eau-terrain.jpg",value.getString("filename"))
            assertEquals("image/jpeg",value.getString("content_type"))
            assertEquals("encoded",value.getString("photo_data"))
            assertEquals("version",value.getString("base_updated_at"))
        }
    }
}
