package mg.hydria.app.repairs

import mg.hydria.app.OfflineStore
import org.json.JSONObject

/**
 * Repository d'acces aux donnees Reparations : encapsule OfflineStore pour
 * que MainActivity ne manipule plus directement la forme du snapshot / de la
 * file de synchro. Comportement strictement identique a l'ancien acces
 * direct : seul l'endroit ou vit le code a change. Voir
 * mg.hydria.app.terrain.TerrainRepository pour le meme traitement applique
 * au domaine Terrain.
 */
object RepairsRepository {
    /** Reparations du snapshot local, ou null si aucune tournee n'a ete prechargee. */
    fun list(store: OfflineStore) = store.snapshot?.optJSONArray("reparations")

    fun enqueueFinish(store: OfflineStore, planningId: String) {
        store.enqueue("finish_repair", JSONObject().put("planning_id", planningId))
    }

    fun enqueueSave(store: OfflineStore, payload: JSONObject) {
        store.enqueue("save_repair", payload)
    }

    /** Photo preuve jointe a une reparation : s'accumule cote serveur (voir
     * Planning.photo) au lieu de remplacer, contrairement a la photo Terrain
     * d'un point d'eau/equipement. */
    fun enqueuePhoto(store: OfflineStore, planningId: String, photoData: String, contentType: String, filename: String) {
        store.enqueue("repair_photo", JSONObject()
            .put("planning_id", planningId)
            .put("photo_data", photoData)
            .put("content_type", contentType)
            .put("filename", filename))
    }
}
