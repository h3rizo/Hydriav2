package mg.hydria.app.network

/** Un seul choix pour la duree du processus, partage entre toutes les Activities.
 * Les appels d'un domaine sont serialises : aucun nouvel appel Ktor ne part apres
 * un echec concurrent. Les autres domaines restent independants.
 */
internal class SessionNetworkRoute(probe: () -> Unit) {
    @Volatile
    var enabled: Boolean = runCatching { probe(); true }.getOrDefault(false)
        private set

    @Synchronized
    fun disable() { enabled = false }

    @Synchronized
    fun <T> call(shared: () -> T, legacy: () -> T): T {
        if (enabled) {
            try { return shared() }
            catch (_: Throwable) { enabled = false }
        }
        return legacy()
    }
}
