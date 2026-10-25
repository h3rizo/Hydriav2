package mg.hydria.sync.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// --- Contrat de l'API serveur (/api/sync/… et /api/fichiers/…), voir backend/README.md ---

@Serializable
data class TokenPair(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresIn: Int = 3600,
)

/** Noeud de l'arborescence : un element de la hierarchie (region, district, ..., ouvrage, equipement...). */
@Serializable
data class Noeud(val type: String, val id: String, val nom: String)

@Serializable
data class FichierDto(
    val id: String,
    val nom: String,
    val organisation: String,
    val portee: String,
    @SerialName("entity_type") val entityType: String? = null,
    @SerialName("entity_id") val entityId: String? = null,
    val domaine: String? = null,
    val categorie: String,
    val sha256: String,
    val taille: Long,
    val version: Int,
    val statut: String = "complet",
    @SerialName("deleted_at") val deletedAt: String? = null,
    val telechargement: String = "",
)

@Serializable
data class ChangeDto(
    val seq: Long,
    val action: String,
    val portee: String,
    val organisation: String? = null,
    val domaine: String? = null,
    @SerialName("entity_type") val entityType: String? = null,
    @SerialName("entity_id") val entityId: String? = null,
    val chemin: List<Noeud>? = null,
    val fichier: FichierDto? = null,
)

@Serializable
data class ChangesPage(
    val since: Long,
    @SerialName("next_seq") val nextSeq: Long,
    @SerialName("has_more") val hasMore: Boolean,
    val changes: List<ChangeDto> = emptyList(),
)

@Serializable
data class ApiErreur(
    val code: String? = null,
    val message: String? = null,
    @SerialName("version_actuelle") val versionActuelle: Int? = null,
    val fichier: FichierDto? = null,
)

/** Resultat d'un appel d'ecriture : succes, conflit de version (409) ou refus du serveur. */
sealed interface Resultat {
    data class Ok(val fichier: FichierDto) : Resultat
    data class Conflit(val fichierServeur: FichierDto?, val versionActuelle: Int?) : Resultat
    data class Refus(val statut: Int, val code: String?, val message: String) : Resultat
}

class ErreurReseau(message: String, cause: Throwable? = null) : Exception(message, cause)
class ErreurAuthentification(message: String) : Exception(message)
