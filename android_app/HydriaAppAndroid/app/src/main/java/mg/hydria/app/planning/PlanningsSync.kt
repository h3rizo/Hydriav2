package mg.hydria.app.planning

import mg.hydria.app.HydriaNetwork
import mg.hydria.app.sync.SyncDispatch

/**
 * Enregistre les operations de synchro du domaine Planning aupres du moteur
 * generique (SyncDispatch). Comportement strictement identique a l'ancien
 * "when" de MainActivity.synchronize() pour ce type : seul l'endroit ou vit
 * le code a change. Voir mg.hydria.app.repairs.RepairsSync pour le meme
 * traitement applique aux reparations.
 */
object PlanningsSync {
    fun register() {
        SyncDispatch.register("save_planning") { token, payload ->
            HydriaNetwork.savePlanning(token, payload)
        }
    }
}
