package mg.hydria.sync.app

import java.io.PrintWriter
import java.io.StringWriter
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * Journal sur disque (`sync.log` dans le dossier de configuration) : trace les etapes et, surtout, les erreurs
 * et plantages de la fenetre, qui n'a pas de console. Jamais de mot de passe ni de jeton dans ce fichier.
 * Au-dela de 1 Mo, l'ancien journal devient `sync.log.1` (un seul niveau de rotation).
 *
 * Si le journal normal est inutilisable, une trace de secours est ecrite dans le dossier temporaire
 * (`hydria-sync-demarrage.txt`) pour ne jamais rester sans aucune information.
 */
object FichierJournal {
    private const val TAILLE_MAX = 1_000_000L
    private val horodatage = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
    private var fichier: Path? = null

    /** Tout premier signe de vie, ecrit dans le dossier temporaire avant toute autre initialisation. */
    fun marquerDemarrage() {
        traceDeSecours("main() atteint", null)
    }

    fun initialiser(dossier: Path) {
        try {
            Files.createDirectories(dossier)
            val cible = dossier.resolve("sync.log")
            if (Files.exists(cible) && Files.size(cible) > TAILLE_MAX) {
                Files.move(cible, dossier.resolve("sync.log.1"), StandardCopyOption.REPLACE_EXISTING)
            }
            fichier = cible
        } catch (e: Throwable) {
            traceDeSecours("initialisation du journal dans $dossier", e)
            fichier = Path.of(System.getProperty("java.io.tmpdir"), "hydria-sync.log")
        }
    }

    @Synchronized
    fun ecrire(ligne: String) {
        val cible = fichier ?: return
        try {
            Files.writeString(
                cible, "${LocalDateTime.now().format(horodatage)}  $ligne\n", Charsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND,
            )
        } catch (e: Throwable) {
            traceDeSecours("ecriture du journal $cible", e)
        }
    }

    fun erreur(contexte: String, e: Throwable) {
        val pile = StringWriter().also { e.printStackTrace(PrintWriter(it)) }.toString().trimEnd()
        ecrire("ERREUR $contexte : $pile")
    }

    /** A appeler une fois au demarrage : trace aussi les exceptions qui ne seraient attrapees nulle part. */
    fun installerGestionnaireGlobal() {
        Thread.setDefaultUncaughtExceptionHandler { fil, e -> erreur("exception non geree (fil ${fil.name})", e) }
    }

    private fun traceDeSecours(contexte: String, e: Throwable?) {
        try {
            val detail = e?.let { StringWriter().also { sw -> it.printStackTrace(PrintWriter(sw)) }.toString() } ?: ""
            Files.writeString(
                Path.of(System.getProperty("java.io.tmpdir"), "hydria-sync-demarrage.txt"),
                "${LocalDateTime.now().format(horodatage)}  $contexte $detail\n", Charsets.UTF_8,
                StandardOpenOption.CREATE, StandardOpenOption.APPEND,
            )
        } catch (_: Throwable) {
            // rien de plus a faire : on ne doit jamais faire planter l'application a cause du journal
        }
    }
}
