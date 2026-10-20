package mg.hydria.shared.sync

data class QueueItem<T>(val value: T, val type: String, val error: String, val hasConflict: Boolean)
data class QueueOverview<T>(
    val items: List<T>,
    val conflicts: List<T>,
    val ordinary: List<T>,
    val readingCount: Int,
    val photoCount: Int,
)

object QueueOverviewRules {
    fun isConflict(hasConflict: Boolean, error: String): Boolean =
        hasConflict || error.startsWith("Conflit", ignoreCase = true)

    /** Clé posée dans le payload d'un relevé quand le serveur le refuse (HTTP 400 : ni conflit, ni panne réseau). */
    const val REFUSED_KEY = "_sync_refused"

    /**
     * Le marqueur suit le DERNIER envoi : posé quand un relevé reçoit HTTP 400, retiré après toute autre issue
     * (succès, conflit 409, 5xx, timeout, coupure). Sinon une panne passagère survenue après un refus
     * s'afficherait comme « refusé par le serveur ».
     */
    fun isRefusalResponse(type: String, status: Int): Boolean = type == "reading" && status == 400

    /**
     * Relevé refusé par le serveur (règle métier, index plus ancien que celui d'un collègue, remarque manquante…).
     * Il ne partira jamais tel quel : le centre de synchronisation propose alors « Corriger ». Une panne
     * passagère n'est pas un refus, et un conflit a déjà son propre parcours (« Comparer »).
     */
    fun isServerRefusal(type: String, hasRefusalMarker: Boolean, hasConflict: Boolean, error: String): Boolean =
        type == "reading" && hasRefusalMarker && error.isNotBlank() && !isConflict(hasConflict, error)

    fun <T> summarize(items: List<QueueItem<T>>): QueueOverview<T> {
        val conflicts = items.filter { isConflict(it.hasConflict,it.error) }
        val ordinary = items.filterNot { isConflict(it.hasConflict,it.error) }
        return QueueOverview(items.map { it.value },conflicts.map { it.value },ordinary.map { it.value },
            ordinary.count { it.type == "reading" },ordinary.count { it.type == "terrain_photo" })
    }

    fun typeLabel(type: String): String = when (type) {
        "reading" -> "Relevé de point d'eau"
        "terrain_photo" -> "Photo Terrain"
        "terrain_data" -> "Donnée ou mesure Terrain"
        "save_repair" -> "Réparation"
        "save_planning" -> "Planning"
        else -> type
    }

    fun status(count: Int, online: Boolean): String = when {
        count == 0 && online -> "Synchronisation à jour"
        count == 0 -> "Hors ligne · rien en attente"
        online -> "$count en attente · reprise possible maintenant"
        else -> "Hors ligne · $count conservée(s) sur ce téléphone"
    }
}
