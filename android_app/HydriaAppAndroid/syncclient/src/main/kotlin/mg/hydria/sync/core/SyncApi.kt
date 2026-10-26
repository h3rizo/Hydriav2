package mg.hydria.sync.core

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.delete
import io.ktor.client.request.parameter
import io.ktor.client.request.patch
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.PartData
import io.ktor.http.content.TextContent
import io.ktor.http.defaultForFilePath
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.IOException

/** Jetons courants ; [renouvellement] est conserve dans la configuration pour la session suivante. */
class Jetons(var acces: String? = null, var renouvellement: String? = null)

/**
 * Appels HTTP vers le serveur Hydria (/api/sync/… et /api/fichiers/…). Renouvelle le jeton d'acces une fois
 * en cas de 401. Les erreurs reseau deviennent [ErreurReseau], l'echec de connexion [ErreurAuthentification].
 */
class SyncApi(
    private val client: HttpClient,
    baseUrl: String,
    val jetons: Jetons,
    private val surNouveauxJetons: (TokenPair) -> Unit = {},
) {
    private val base = baseUrl.trimEnd('/')

    /** Derniere erreur d'enregistrement du jeton renouvele (null si tout va bien) : a journaliser par l'appelant. */
    var persistanceEchouee: Exception? = null
        private set

    // ------------------------------------------------------------------ authentification

    suspend fun connecter(utilisateur: String, motDePasse: String, deviceId: String, libelle: String): TokenPair {
        val reponse = appeler {
            client.post("$base/api/sync/auth/login") {
                setBody(json(buildJsonObject {
                    put("username", utilisateur); put("password", motDePasse)
                    put("device_id", deviceId); put("device_label", libelle)
                }))
            }
        }
        if (reponse.status != HttpStatusCode.OK) throw ErreurAuthentification(message(reponse))
        return appliquer(jsonFormat.decodeFromString(reponse.bodyAsText()))
    }

    private suspend fun renouveler(): String {
        val refresh = jetons.renouvellement ?: throw ErreurAuthentification("Session expirée : reconnectez-vous.")
        val reponse = appeler {
            client.post("$base/api/sync/auth/refresh") { setBody(json(buildJsonObject { put("refresh_token", refresh) })) }
        }
        if (reponse.status != HttpStatusCode.OK) {
            jetons.acces = null
            throw ErreurAuthentification("Session expirée : reconnectez-vous. (${message(reponse)})")
        }
        return appliquer(jsonFormat.decodeFromString<TokenPair>(reponse.bodyAsText())).accessToken
    }

    private fun appliquer(paire: TokenPair): TokenPair {
        jetons.acces = paire.accessToken
        jetons.renouvellement = paire.refreshToken
        // Echec d'enregistrement (disque, droits...) : on garde le jeton en memoire pour poursuivre la session en cours.
        try {
            surNouveauxJetons(paire)
        } catch (e: Exception) {
            persistanceEchouee = e
        }
        return paire
    }

    // ------------------------------------------------------------------ lecture

    suspend fun changements(depuis: Long, limite: Int, organisation: String?, appareil: String?): ChangesPage {
        val reponse = authentifie { jeton ->
            client.get("$base/api/sync/changes") {
                bearer(jeton)
                parameter("since", depuis); parameter("limit", limite)
                organisation?.let { parameter("organisation", it) }
                appareil?.let { parameter("appareil", it) }
            }
        }
        exiger(reponse)
        return jsonFormat.decodeFromString(reponse.bodyAsText())
    }

    suspend fun arborescence(organisation: String?): JsonObject {
        val reponse = authentifie { jeton ->
            client.get("$base/api/sync/arborescence") {
                bearer(jeton)
                organisation?.let { parameter("organisation", it) }
            }
        }
        exiger(reponse)
        return jsonFormat.decodeFromString(reponse.bodyAsText())
    }

    suspend fun telecharger(fichier: FichierDto): ByteArray {
        val reponse = authentifie { jeton -> client.get("$base${fichier.telechargement}") { bearer(jeton) } }
        exiger(reponse)
        return reponse.body()
    }

    // ------------------------------------------------------------------ ecriture

    suspend fun deposer(nom: String, contenu: ByteArray, cible: Cible, organisation: String?): Resultat {
        val reponse = authentifie { jeton ->
            client.post("$base/api/sync/upload") {
                bearer(jeton)
                setBody(MultiPartFormDataContent(formData {
                    when (cible) {
                        is Cible.Entite -> {
                            append("categorie", cible.categorie)
                            append("entity_type", cible.entityType); append("entity_id", cible.entityId)
                        }
                        is Cible.Organisation -> {
                            append("categorie", cible.categorie); append("domaine", cible.domaine)
                        }
                    }
                    organisation?.let { append("organisation", it) }
                    partieFichier(nom, nom, contenu)
                }))
            }
        }
        return interpreter(reponse)
    }

    /** Remplace le contenu (et/ou le nom) d'un fichier : `If-Match` = derniere version connue. */
    suspend fun remplacer(
        id: String, versionAttendue: Int, nouveauNom: String?, contenu: ByteArray?, nomLocal: String? = null,
    ): Resultat {
        val reponse = authentifie { jeton ->
            client.patch("$base/api/fichiers/$id/") {
                bearer(jeton)
                header(HttpHeaders.IfMatch, versionAttendue.toString())
                setBody(MultiPartFormDataContent(formData {
                    nouveauNom?.let { append("nom", it) } // jamais envoye pour un simple remplacement de contenu
                    if (contenu != null) partieFichier(null, nomLocal ?: nouveauNom ?: "fichier", contenu)
                }))
            }
        }
        return interpreter(reponse)
    }

    suspend fun supprimer(id: String, versionAttendue: Int): Resultat {
        val reponse = authentifie { jeton ->
            client.delete("$base/api/fichiers/$id/") {
                bearer(jeton)
                header(HttpHeaders.IfMatch, versionAttendue.toString())
            }
        }
        return interpreter(reponse)
    }

    // ------------------------------------------------------------------ outils

    /** Le nom reel passe par le champ `nom` (UTF-8) ; le nom de la partie reste ASCII pour eviter tout souci d'en-tete. */
    private fun io.ktor.client.request.forms.FormBuilder.partieFichier(
        nomAEnvoyer: String?, nomPourExtension: String, contenu: ByteArray,
    ) {
        nomAEnvoyer?.let { append("nom", it) }
        val extension = nomPourExtension.substringAfterLast('.', "").filter { it.isLetterOrDigit() }.take(10)
        val sur = if (extension.isEmpty()) "fichier" else "fichier.$extension"
        append("fichier", contenu, Headers.build {
            append(HttpHeaders.ContentType, ContentType.defaultForFilePath(sur).toString())
            append(HttpHeaders.ContentDisposition, "filename=\"$sur\"")
        })
    }

    private fun io.ktor.client.request.HttpRequestBuilder.bearer(jeton: String) {
        header(HttpHeaders.Authorization, "Bearer $jeton")
    }

    private fun json(objet: JsonObject) = TextContent(objet.toString(), ContentType.Application.Json)

    private suspend fun appeler(requete: suspend () -> HttpResponse): HttpResponse =
        try {
            requete()
        } catch (e: IOException) {
            throw ErreurReseau("Serveur injoignable : ${e.message ?: e::class.simpleName}", e)
        }

    private suspend fun authentifie(requete: suspend (String) -> HttpResponse): HttpResponse {
        var reponse = appeler { requete(jetons.acces ?: renouveler()) }
        if (reponse.status == HttpStatusCode.Unauthorized && jetons.renouvellement != null) {
            reponse = appeler { requete(renouveler()) }
        }
        if (reponse.status == HttpStatusCode.Unauthorized) throw ErreurAuthentification(message(reponse))
        return reponse
    }

    private suspend fun exiger(reponse: HttpResponse) {
        if (reponse.status.value !in 200..299) throw ErreurReseau("HTTP ${reponse.status.value} : ${message(reponse)}")
    }

    private suspend fun interpreter(reponse: HttpResponse): Resultat {
        val texte = reponse.bodyAsText()
        return when (reponse.status.value) {
            200, 201 -> Resultat.Ok(jsonFormat.decodeFromString(texte))
            409 -> {
                val erreur = runCatching { jsonFormat.decodeFromString<ApiErreur>(texte) }.getOrNull()
                Resultat.Conflit(erreur?.fichier, erreur?.versionActuelle)
            }
            else -> {
                val erreur = runCatching { jsonFormat.decodeFromString<ApiErreur>(texte) }.getOrNull()
                Resultat.Refus(reponse.status.value, erreur?.code, erreur?.message ?: texte.take(200))
            }
        }
    }

    private suspend fun message(reponse: HttpResponse): String {
        val texte = runCatching { reponse.bodyAsText() }.getOrDefault("")
        val erreur = runCatching { jsonFormat.decodeFromString<ApiErreur>(texte) }.getOrNull()
        return erreur?.message ?: "HTTP ${reponse.status.value}"
    }
}
