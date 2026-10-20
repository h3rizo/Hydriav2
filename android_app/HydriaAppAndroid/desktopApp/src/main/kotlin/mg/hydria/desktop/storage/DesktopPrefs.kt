package mg.hydria.desktop.storage

import org.json.JSONObject
import java.io.File

/**
 * Preferences locales du poste de travail : petit fichier JSON dans le dossier
 * de donnees (equivalent Desktop de SharedPreferences cote Android). Sert pour
 * l'instant a persister la session (jeton, nom d'employe, cle de compte).
 *
 * Ecriture best-effort : un echec disque ne doit pas planter l'app.
 */
class DesktopPrefs(private val file: File) {
    private val data: JSONObject = runCatching {
        if (file.exists()) JSONObject(file.readText()) else JSONObject()
    }.getOrDefault(JSONObject())

    fun getString(key: String): String? = data.optString(key, "").takeIf { it.isNotBlank() }

    fun putString(key: String, value: String?) {
        if (value.isNullOrBlank()) data.remove(key) else data.put(key, value)
        flush()
    }

    fun clear(vararg keys: String) {
        keys.forEach { data.remove(it) }
        flush()
    }

    private fun flush() {
        runCatching {
            file.parentFile?.mkdirs()
            file.writeText(data.toString(2))
        }
    }
}
