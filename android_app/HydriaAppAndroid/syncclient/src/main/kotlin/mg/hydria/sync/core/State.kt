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

internal fun ecrireAtomique(cible: Path, contenu: String) {
    val temporaire = cible.resolveSibling(cible.fileName.toString() + ".tmp")
    Files.writeString(temporaire, contenu, Charsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING)
    Files.move(temporaire, cible, StandardCopyOption.REPLACE_EXISTING)
}
