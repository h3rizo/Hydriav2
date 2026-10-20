package mg.hydria.app.planning

import mg.hydria.app.OfflineStore
import org.json.JSONObject

/**
 * Repository d'acces aux donnees Planning : encapsule OfflineStore pour que
 * MainActivity ne manipule plus directement la forme du snapshot / de la
 * file de synchro. Comportement strictement identique a l'ancien acces
 * direct : seul l'endroit ou vit le code a change. Voir
 * mg.hydria.app.repairs.RepairsRepository pour le meme traitement applique
 * aux reparations.
 */
object PlanningsRepository {
    /** Plannings du snapshot local, ou null si aucune tournee n'a ete prechargee. */
    fun list(store: OfflineStore) = store.snapshot?.optJSONArray("plannings")

    fun enqueueSave(store: OfflineStore, payload: JSONObject) {
        store.enqueue("save_planning", payload)
    }
}
