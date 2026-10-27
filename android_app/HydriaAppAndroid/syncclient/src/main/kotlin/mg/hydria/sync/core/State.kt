package mg.hydria.sync.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.util.UUID

internal val jsonFormat = Json { ignoreUnknownKeys = true; prettyPrint = true; encodeDefaults = true }

/** Reglages de l'utilisateur, stockes HORS du dossier synchronise (%APPDATA%\HydriaSync\config.json). */
@Serializable
data class Config(
    val baseUrl: String,
    val root: String,
    val username: String,
    val deviceId: String = UUID.randomUUID().toString(),
    val deviceLabel: String = "PC",
    val refreshToken: String? = null,
    /** Organisation a utiliser (comptes superutilisateurs sans organisation propre). */
    val organisation: String? = null,
    /** Propager au serveur les fichiers supprimes localement. Desactive par defaut (securite). */
    val propagerSuppressions: Boolean = false,
    /**
     * Protege l'arborescence : dossiers verrouilles (ni suppression, ni renommage, ni deplacement sous Windows) et
     * retablissement automatique des fichiers deplaces, renommes ou supprimes. Active par defaut.
     */
    val protegerArborescence: Boolean = true,
) {
    companion object {
        /** Dossier de configuration : variable HYDRIA_SYNC_DIR (installation portable, essais), sinon %APPDATA%\HydriaSync. */
        fun dossierParDefaut(): Path {
            System.getenv("HYDRIA_SYNC_DIR")?.takeIf { it.isNotBlank() }?.let { return Path.of(it) }
            val appData = System.getenv("APPDATA")
            return if (appData != null) Path.of(appData, "HydriaSync")
            else Path.of(System.getProperty("user.home"), ".hydria-sync")
        }

        fun charger(dossier: Path = dossierParDefaut()): Config? {
            val fichier = dossier.resolve("config.json")
            if (!Files.isRegularFile(fichier)) return null
            return jsonFormat.decodeFromString(Files.readString(fichier))
        }
    }

    fun enregistrer(dossier: Path = dossierParDefaut()) {
        Files.createDirectories(dossier)
        ecrireAtomique(dossier.resolve("config.json"), jsonFormat.encodeToString(this))
    }
}

/** Ce que l'on sait d'un fichier deja synchronise (par identifiant serveur). */
@Serializable
data class FichierSuivi(
    val id: String,
    /** Chemin relatif au dossier racine, separateur '/'. */
    val relPath: String,
    val version: Int,
    val sha256: String,
    val taille: Long,
    val mtime: Long,
    /** Supprime localement par l'utilisateur : on ne le retelecharge pas tant que le serveur n'a pas change. */
    val supprimeLocalement: Boolean = false,
    /** Conflit non resolu : le local a ete modifie ET le serveur aussi. */
    val conflit: Boolean = false,
    val conflitVersionServeur: Int? = null,
    val conflitShaServeur: String? = null,
    val conflitCopie: String? = null,
)

/** Etat de synchronisation, stocke DANS le dossier racine (.hydria-sync/state.json). */
@Serializable
data class Etat(
    var curseur: Long = 0,
    val fichiers: MutableMap<String, FichierSuivi> = mutableMapOf(),
    /** Nom de dossier attribue a chaque noeud (identifiant -> nom), fige des la premiere attribution. */
    val noms: MutableMap<String, String> = mutableMapOf(),
    /** Fichiers locaux refuses par le serveur : chemin -> sha256 refuse (on n'insiste pas tant qu'il ne change pas). */
    val refuses: MutableMap<String, String> = mutableMapOf(),
    /** Telechargements echoues (integrite, disque...) a reprendre a la prochaine synchronisation. */
    val enAttente: MutableMap<String, FichierDto> = mutableMapOf(),
    /** Tous les dossiers de l'arborescence sont verrouilles (evite de relire les permissions a chaque synchronisation). */
    var protection: Boolean = false,
) {
    companion object {
        const val DOSSIER = ".hydria-sync"

        fun charger(racine: Path): Etat {
            val fichier = racine.resolve(DOSSIER).resolve("state.json")
            if (!Files.isRegularFile(fichier)) return Etat()
            return jsonFormat.decodeFromString(Files.readString(fichier))
        }
    }

    fun enregistrer(racine: Path) {
        val dossier = racine.resolve(DOSSIER)
        Files.createDirectories(dossier)
        ecrireAtomique(dossier.resolve("state.json"), jsonFormat.encodeToString(this))
    }
}

/**
 * Ecriture d'un petit fichier de configuration/etat : fichier temporaire puis renommage (atomique).
 *
 * Sous Windows, un antivirus (Defender en temps reel) peut verrouiller quelques instants un fichier qu'on vient
 * de creer : le renommage echoue alors (« acces refuse »). On reessaie donc plusieurs fois, puis en dernier recours
 * on ecrit directement dans le fichier final (ces fichiers font quelques Ko : le risque d'ecriture partielle est
 * negligeable). L'exception finale, si tout echoue, nomme le fichier concerne.
 */
/** « TypeDException : message » : le type seul distingue « acces refuse » de « fichier introuvable ». */
fun decrire(e: Throwable): String = "${e::class.simpleName}: ${e.message ?: "(sans message)"}"

internal fun ecrireAtomique(cible: Path, contenu: String, tentatives: Int = 5, pauseMs: Long = 100) {
    val temporaire = cible.resolveSibling(cible.fileName.toString() + ".tmp")
    var derniere: java.io.IOException? = null
    for (essai in 1..tentatives) {
        try {
            Files.writeString(temporaire, contenu, Charsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING)
            Files.move(temporaire, cible, StandardCopyOption.REPLACE_EXISTING)
            return
        } catch (e: java.io.IOException) {
            derniere = e
            if (essai < tentatives) Thread.sleep(pauseMs * essai)
        }
    }
    try {
        Files.writeString(cible, contenu, Charsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING)
        runCatching { Files.deleteIfExists(temporaire) }
    } catch (e: java.io.IOException) {
        throw java.io.IOException(
            "Impossible d'enregistrer ${cible.fileName} : ${decrire(e)} (essai par fichier temporaire : ${derniere?.let { decrire(it) }})", e,
        )
    }
}
