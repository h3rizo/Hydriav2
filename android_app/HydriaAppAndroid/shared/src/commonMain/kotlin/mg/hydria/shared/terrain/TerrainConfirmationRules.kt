package mg.hydria.shared.terrain

data class TerrainServerConfirmation(val hasPhoto: Boolean, val subscriberName: String, val hasCoordinates: Boolean)

object TerrainConfirmationRules {
    fun error(
        type: String,
        operation: String,
        requestedSubscriberName: String?,
        hasLatitudeOrLongitude: Boolean,
        server: TerrainServerConfirmation?,
    ): String? {
        if (type != "terrain_data" && type != "terrain_photo") return null
        if (operation !in setOf("update_point", "photo_point", "photo_equipment")) return null
        if (server == null)
            return "Le serveur n'a pas confirmé les valeurs Terrain. Le correctif backend doit être déployé."
        if (operation == "photo_point" || operation == "photo_equipment")
            return if (server.hasPhoto) null else "Le serveur n'a pas confirmé l'enregistrement de la photo."
        if (requestedSubscriberName != null && server.subscriberName != requestedSubscriberName.trim())
            return "Le serveur n'a pas confirmé le nom de l'abonné."
        if (hasLatitudeOrLongitude && !server.hasCoordinates)
            return "Le serveur n'a pas confirmé les coordonnées GPS."
        return null
    }
}
