package mg.hydria.sync.app

import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import mg.hydria.sync.core.ecrireAtomique
import mg.hydria.sync.core.jsonFormat
import java.nio.file.Files
import java.nio.file.Path

/**
 * Reglages propres a la fenetre, dans `preferences.json` a cote de `config.json` (jamais dans le dossier synchronise).
 * `null` = pas encore choisi : le theme suit alors celui de Windows, le demarrage avec Windows est propose active.
 */
@Serializable
data class Preferences(
    val sombre: Boolean? = null,
    val demarrageWindows: Boolean? = null,
) {
    companion object {
        private fun fichier(dossier: Path) = dossier.resolve("preferences.json")

        /** Fichier absent ou illisible : reglages par defaut (une preference abimee ne doit jamais empecher de demarrer). */
        fun charger(dossier: Path): Preferences = try {
            val f = fichier(dossier)
            if (Files.isRegularFile(f)) jsonFormat.decodeFromString(Files.readString(f)) else Preferences()
        } catch (e: Exception) {
            FichierJournal.erreur("lecture de preferences.json (reglages par defaut utilises)", e)
            Preferences()
        }
    }

    /** Echec d'ecriture : journalise et ignore (le reglage ne sera simplement pas retenu au prochain demarrage). */
    fun enregistrer(dossier: Path) {
        try {
            Files.createDirectories(dossier)
            ecrireAtomique(fichier(dossier), jsonFormat.encodeToString(this))
        } catch (e: Exception) {
            FichierJournal.erreur("enregistrement de preferences.json", e)
        }
    }
}

/** Theme choisi dans les parametres de Windows (Parametres > Personnalisation > Couleurs). */
object ThemeSysteme {
    private const val CLE = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize"

    /** `AppsUseLightTheme    REG_DWORD    0x0` = mode sombre. Toute difficulte de lecture : clair. */
    internal fun sombreDepuis(sortieReg: String): Boolean =
        Regex("""AppsUseLightTheme\s+REG_DWORD\s+0x0\b""").containsMatchIn(sortieReg)

    fun sombre(): Boolean = try {
        if (!System.getProperty("os.name").startsWith("Windows")) false
        else {
            val processus = ProcessBuilder("reg", "query", CLE, "/v", "AppsUseLightTheme").redirectErrorStream(true).start()
            val sortie = processus.inputStream.bufferedReader().readText()
            processus.waitFor()
            sombreDepuis(sortie)
        }
    } catch (e: Exception) {
        false
    }
}
