package mg.hydria.app.sync

import mg.hydria.app.HydriaApi
import org.json.JSONObject

/**
 * Point d'extension du moteur de synchro.
 *
 * MainActivity.synchronize() gere deja, de facon generique pour tous les types
 * d'operation de la file locale : le conflit serveur (HTTP 409), le retrait de
 * la file une fois confirme, et (pour certains types) la validation de la
 * confirmation serveur. La seule partie vraiment specifique a chaque domaine
 * metier est *quel appel API* declenche l'envoi d'un type d'operation donne.
 *
 * SyncDispatch est ce registre : chaque domaine (repairs, plannings, ...) qui
 * est extrait de MainActivity enregistre ici ses types au lieu d'ajouter une
 * branche dans le "when" de synchronize(). Les types pas encore enregistres
 * restent geres par le "when" existant le temps de leur propre extraction.
 */
object SyncDispatch {
    private val handlers = mutableMapOf<String, (token: String, payload: JSONObject) -> HydriaApi.Result>()

    /** A appeler une fois au demarrage de l'app (voir HydriaApp.onCreate) pour chaque domaine. */
    fun register(type: String, handler: (token: String, payload: JSONObject) -> HydriaApi.Result) {
        handlers[type] = handler
    }

    /** Retourne null si aucun handler n'est enregistre pour ce type : synchronize() se rabat alors sur le "when" existant. */
    fun push(type: String, token: String, payload: JSONObject): HydriaApi.Result? =
        handlers[type]?.invoke(token, payload)
}
