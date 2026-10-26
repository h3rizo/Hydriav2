package mg.hydria.sync.app

import java.io.IOException
import java.nio.channels.FileChannel
import java.nio.channels.FileLock
import java.nio.channels.OverlappingFileLockException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption

/**
 * Une seule fenetre / un seul moteur de synchronisation par session : avec le demarrage automatique et la zone de
 * notification, l'utilisateur relance facilement l'application alors qu'elle tourne deja, et deux moteurs sur le
 * meme dossier se marcheraient dessus. La seconde instance demande a la premiere de se montrer, puis se ferme.
 */
object InstanceUnique {
    private var canal: FileChannel? = null
    private var verrou: FileLock? = null

    private fun demande(dossier: Path) = dossier.resolve("ouvrir.demande")

    /** `true` si cette instance est la premiere (ou si le verrou est inutilisable : on ne bloque jamais le demarrage). */
    fun obtenir(dossier: Path): Boolean = try {
        Files.createDirectories(dossier)
        val c = FileChannel.open(dossier.resolve("instance.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE)
        val v = try { c.tryLock() } catch (e: OverlappingFileLockException) { null }
        if (v == null) {
            c.close()
            false
        } else {
            canal = c
            verrou = v
            true
        }
    } catch (e: IOException) {
        FichierJournal.erreur("verrou d'instance unique (ignore)", e)
        true
    }

    /** Libere le verrou (a la fermeture ; la fin du processus le libere aussi). */
    fun liberer() {
        runCatching { verrou?.release() }
        runCatching { canal?.close() }
        verrou = null
        canal = null
    }

    /** A appeler par la seconde instance avant de se fermer. */
    fun demanderOuverture(dossier: Path) {
        try {
            Files.writeString(demande(dossier), "1")
        } catch (e: IOException) {
            FichierJournal.erreur("demande d'ouverture de la fenetre", e)
        }
    }

    /** A interroger regulierement par la premiere instance ; consomme la demande. */
    fun ouvertureDemandee(dossier: Path): Boolean = try {
        Files.deleteIfExists(demande(dossier))
    } catch (e: IOException) {
        false
    }
}
