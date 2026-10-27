package mg.hydria.sync.core

import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.AclEntry
import java.nio.file.attribute.AclEntryPermission
import java.nio.file.attribute.AclEntryType
import java.nio.file.attribute.AclFileAttributeView
import java.nio.file.attribute.UserPrincipal

/**
 * Verrou des dossiers de l'arborescence Hydria (NTFS) : sur chaque dossier gere, un refus pour l'utilisateur des droits
 * « Supprimer » ET « Supprimer les sous-dossiers et fichiers ». Windows refuse alors, dans l'Explorateur comme partout,
 * de SUPPRIMER, RENOMMER ou DEPLACER ce dossier. Les deux droits sont necessaires : dans un dossier du profil, le
 * controle total herite donne le droit « Supprimer les enfants » sur le parent, qui suffirait a supprimer un dossier
 * dont le seul droit « Supprimer » est refuse (mesure : voir ProtectionTest et la note du backend).
 *
 * Ce qui reste possible (mesure sur NTFS) : creer des fichiers ou des sous-dossiers, modifier un fichier, l'enregistrer
 * comme Word ou Excel (fichier temporaire renomme par-dessus l'original). Les FICHIERS ne sont volontairement pas
 * verrouilles, sinon l'enregistrement des documents Office echouerait ; c'est le retablissement automatique du moteur
 * qui remet en place un fichier deplace, renomme ou supprime.
 *
 * Limites connues :
 *  - le dossier RACINE ne peut pas etre protege contre le renommage ou la suppression quand son parent est le profil
 *    de l'utilisateur (on ne refuse pas « Supprimer les enfants » sur tout le profil) : le moteur reconstruit alors
 *    l'arbre et retelecharge les fichiers ;
 *  - le proprietaire ou un administrateur peut lever les refus (Proprietes > Securite) : ce n'est pas une barriere de
 *    securite, seulement une protection contre les fausses manipulations.
 *
 * Meilleur effort : hors NTFS ou sans droit sur le dossier, les fonctions renvoient `false` sans lever d'exception.
 */
object Protection {
    private val DROIT = setOf(AclEntryPermission.DELETE, AclEntryPermission.DELETE_CHILD)

    @Volatile private var moiMemorise: UserPrincipal? = null

    private fun vue(p: Path): AclFileAttributeView? = try {
        Files.getFileAttributeView(p, AclFileAttributeView::class.java, LinkOption.NOFOLLOW_LINKS)
    } catch (e: Exception) {
        null
    }

    private fun moi(p: Path): UserPrincipal? {
        moiMemorise?.let { return it }
        val trouve = try {
            p.fileSystem.userPrincipalLookupService.lookupPrincipalByName(System.getProperty("user.name"))
        } catch (e: Exception) {
            try { Files.getOwner(p) } catch (e2: Exception) { null }
        }
        moiMemorise = trouve
        return trouve
    }

    /** Un refus pose par nous : refus, pour l'utilisateur, de « Supprimer » et « Supprimer les enfants », sans heritage. */
    private fun estNotre(e: AclEntry, moi: UserPrincipal) =
        e.type() == AclEntryType.DENY && e.principal() == moi && e.flags().isEmpty() && e.permissions() == DROIT

    /** Le dossier est sur un systeme de fichiers qui gere les permissions NTFS. */
    fun disponible(dossier: Path): Boolean = try {
        Files.isDirectory(dossier) && vue(dossier) != null &&
            Files.getFileStore(dossier).supportsFileAttributeView(AclFileAttributeView::class.java)
    } catch (e: Exception) {
        false
    }

    fun estVerrouille(dossier: Path): Boolean = try {
        val v = vue(dossier); val m = moi(dossier)
        v != null && m != null && v.acl.any { estNotre(it, m) }
    } catch (e: IOException) {
        false
    }

    /** Pose le verrou (sans effet s'il y est deja). `true` si le dossier est verrouille a la sortie. */
    fun verrouiller(dossier: Path): Boolean = try {
        if (!Files.isDirectory(dossier, LinkOption.NOFOLLOW_LINKS)) false
        else {
            val v = vue(dossier); val m = moi(dossier)
            if (v == null || m == null) false
            else {
                val acl = v.acl
                if (acl.any { estNotre(it, m) }) true
                else {
                    val refus = AclEntry.newBuilder().setType(AclEntryType.DENY).setPrincipal(m).setPermissions(DROIT).build()
                    v.acl = listOf(refus) + acl // les refus passent avant les autorisations
                    true
                }
            }
        }
    } catch (e: IOException) {
        false
    }

    /** Leve le verrou. `true` si on en a retire un. */
    fun deverrouiller(dossier: Path): Boolean = try {
        val v = vue(dossier); val m = moi(dossier)
        if (v == null || m == null) false
        else {
            val acl = v.acl
            val reste = acl.filterNot { estNotre(it, m) }
            if (reste.size == acl.size) false else { v.acl = reste; true }
        }
    } catch (e: IOException) {
        false
    }

    /** Leve le verrou de tous les dossiers sous `racine` (desactivation, deconnexion). Renvoie le nombre de dossiers deverrouilles. */
    fun leverTout(racine: Path): Int {
        if (!Files.isDirectory(racine)) return 0
        var leves = 0
        try {
            Files.walk(racine).use { flux ->
                flux.filter { Files.isDirectory(it, LinkOption.NOFOLLOW_LINKS) }.forEach { if (deverrouiller(it)) leves++ }
            }
        } catch (e: IOException) {
            // un sous-dossier illisible ne doit pas empecher de lever les autres : meilleur effort
        }
        return leves
    }

    /** Execute `bloc` avec le verrou de `dossier` leve (suppression d'un dossier vide), puis le rétablit s'il existe encore. */
    inline fun <T> sansVerrou(dossier: Path, bloc: () -> T): T {
        val etait = deverrouiller(dossier)
        try {
            return bloc()
        } finally {
            if (etait && Files.isDirectory(dossier)) verrouiller(dossier)
        }
    }
}
