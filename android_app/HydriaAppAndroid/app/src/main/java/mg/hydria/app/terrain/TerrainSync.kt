package mg.hydria.app.terrain

import mg.hydria.app.HydriaNetwork
import mg.hydria.app.sync.SyncDispatch

/**
 * Enregistre les operations de synchro des domaines Terrain et Releves
 * aupres du moteur generique (SyncDispatch). Comportement strictement
 * identique a l'ancien "when" de MainActivity.synchronize() pour ces types :
 * seul l'endroit ou vit le code a change. Voir mg.hydria.app.repairs.RepairsSync
 * pour le meme traitement applique aux reparations.
 *
 * Terrain (terrain_data / terrain_photo) : le POST /plannings/api/mobile/terrain/
 * sync-item/ passe par le client Ktor partage (HydriaOperationsGateway) quand le
 * flag de session OfflineStore.useNewTerrainNetwork est actif, avec repli
 * HydriaApi - et extinction du flag pour toute la session - si l'appel Ktor
 * jette. "reading" utilise son propre repli de session Releves.
 *
 * Note : la validation de confirmation serveur specifique a "terrain_data"/
 * "terrain_photo" (verification que le serveur a bien confirme la valeur
 * appliquee - nom d'abonne, coordonnees GPS, photo) reste geree de facon
 * generique dans MainActivity.synchronize() (validateServerConfirmation),
 * qui s'applique quel que soit le chemin de dispatch utilise.
 */
object TerrainSync {
    fun register() {
        SyncDispatch.register("reading") { token, payload ->
            HydriaNetwork.saveReading(token, payload)
        }
        SyncDispatch.register("terrain_data") { token, payload ->
            HydriaNetwork.saveTerrainItem(token, payload)
        }
        SyncDispatch.register("terrain_photo") { token, payload ->
            HydriaNetwork.saveTerrainItem(token, payload)
        }
    }

}
