package mg.hydria.shared.terrain

import kotlin.test.*

class TerrainConfirmationRulesTest {
    @Test fun onlySupportedOperationsRequireConfirmation() {
        assertNull(TerrainConfirmationRules.error("volume","photo_point",null,false,null))
        assertNull(TerrainConfirmationRules.error("terrain_data","unknown",null,false,null))
        assertEquals("Le serveur n'a pas confirmé les valeurs Terrain. Le correctif backend doit être déployé.",
            TerrainConfirmationRules.error("terrain_photo","photo_point",null,false,null))
    }
    @Test fun photosRequirePhotoFlagAndIgnoreUnrelatedFields() {
        for (operation in listOf("photo_point","photo_equipment")) {
            assertNull(TerrainConfirmationRules.error("terrain_photo",operation,"name",true,
                TerrainServerConfirmation(true,"wrong",false)))
            assertEquals("Le serveur n'a pas confirmé l'enregistrement de la photo.",
                TerrainConfirmationRules.error("terrain_photo",operation,null,false,
                    TerrainServerConfirmation(false,"",true)))
        }
    }
    @Test fun subscriberCheckPrecedesGpsAndTrimsOnlyRequestedName() {
        val server = TerrainServerConfirmation(false,"name",false)
        assertEquals("Le serveur n'a pas confirmé le nom de l'abonné.",
            TerrainConfirmationRules.error("terrain_data","update_point","wrong",true,server))
        assertEquals("Le serveur n'a pas confirmé les coordonnées GPS.",
            TerrainConfirmationRules.error("terrain_data","update_point"," name ",true,server))
        assertNull(TerrainConfirmationRules.error("terrain_data","update_point",null,false,server))
        assertNull(TerrainConfirmationRules.error("terrain_data","update_point"," name ",true,server.copy(hasCoordinates=true)))
    }
}
