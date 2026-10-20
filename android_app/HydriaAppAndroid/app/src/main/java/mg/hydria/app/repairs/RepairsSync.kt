package mg.hydria.app.repairs

import mg.hydria.app.HydriaNetwork
import mg.hydria.app.sync.SyncDispatch

/**
 * Enregistre les operations de synchro du domaine Reparations aupres du moteur
 * generique (SyncDispatch). Comportement strictement identique a l'ancien
 * "when" de MainActivity.synchronize() pour ces deux types : seul l'endroit
 * ou vit le code a change.
 */
object RepairsSync {
    fun register() {
        SyncDispatch.register("save_repair") { token, payload ->
            HydriaNetwork.saveRepair(token, payload)
        }
        SyncDispatch.register("finish_repair") { token, payload ->
            HydriaNetwork.finishRepair(token, payload.getString("planning_id"))
        }
        SyncDispatch.register("repair_photo") { token, payload ->
            HydriaNetwork.saveRepairPhoto(token, payload)
        }
    }
}
