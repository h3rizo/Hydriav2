package mg.hydria.app.navigation

import mg.hydria.app.HydriaNetwork
import mg.hydria.app.sync.SyncDispatch

/**
 * Enregistre les operations de synchro du domaine Navigation terrain
 * (positions et reperes/marquages GPS) aupres du moteur generique
 * (SyncDispatch). Comportement strictement identique a l'ancien "when" de
 * MainActivity.synchronize() pour ces types : seul l'endroit ou vit le code
 * a change. Voir mg.hydria.app.repairs.RepairsSync pour le meme traitement
 * applique aux reparations.
 *
 * A ne pas confondre avec navigation.sync.NavigationSyncManager, qui gere le
 * telechargement paginé de la carte terrain (sens serveur -> local), un sujet
 * distinct de l'envoi des operations en attente (sens local -> serveur).
 */
object NavigationSync {
    fun register() {
        SyncDispatch.register("geo_position_upsert") { token, payload ->
            HydriaNetwork.saveNavigationPosition(token, payload)
        }
        SyncDispatch.register("landmark_upsert") { token, payload ->
            HydriaNetwork.saveNavigationLandmark(token, payload)
        }
        SyncDispatch.register("landmark_archive") { token, payload ->
            HydriaNetwork.saveNavigationLandmark(token, payload)
        }
        SyncDispatch.register("landmark_photo_upload") { token, payload ->
            HydriaNetwork.saveNavigationPhoto(token, payload)
        }
    }
}
