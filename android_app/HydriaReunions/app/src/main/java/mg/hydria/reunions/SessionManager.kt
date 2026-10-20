package mg.hydria.reunions

import android.content.Context
import android.content.SharedPreferences

/**
 * Session locale : jeton mobile + identite de l'employe connecte.
 *
 * Option "rester connecte" (ecran de connexion) : quand elle est cochee (comportement
 * par defaut), le jeton est persiste dans les SharedPreferences et survit au redemarrage
 * de l'application. Quand elle est decochee, le jeton n'est garde qu'en memoire (variable
 * statique du companion object, propre au process) : il disparait des qu'Android tue le
 * process de l'application (fermeture complete, ou simplement au bout d'un moment en
 * arriere-plan), et l'ecran de connexion sera redemande au prochain lancement.
 */
class SessionManager(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("hydria_reunions_session", Context.MODE_PRIVATE)

    companion object {
        // Session "non memorisee" : vecue uniquement en memoire, jamais ecrite sur disque.
        private var memoryToken: String? = null
        private var memoryEmployeId: String? = null
        private var memoryEmployeNom: String? = null
    }

    val token: String? get() = memoryToken ?: prefs.getString("token", null)
    val employeId: String? get() = memoryEmployeId ?: prefs.getString("employe_id", null)
    val employeNom: String? get() = memoryEmployeNom ?: prefs.getString("employe_nom", null)
    val isLoggedIn: Boolean get() = !token.isNullOrBlank()

    /** @param rememberMe si vrai (comportement historique), la session est persistee sur
     *  disque et survit au redemarrage de l'app ; sinon elle ne vit qu'en memoire pour ce
     *  lancement du process. */
    fun save(token: String, employeId: String?, employeNom: String?, rememberMe: Boolean = true) {
        if (rememberMe) {
            prefs.edit()
                .putString("token", token)
                .putString("employe_id", employeId)
                .putString("employe_nom", employeNom)
                .apply()
            memoryToken = null
            memoryEmployeId = null
            memoryEmployeNom = null
        } else {
            prefs.edit().clear().apply()
            memoryToken = token
            memoryEmployeId = employeId
            memoryEmployeNom = employeNom
        }
    }

    fun clear() {
        prefs.edit().clear().apply()
        memoryToken = null
        memoryEmployeId = null
        memoryEmployeNom = null
    }
}
