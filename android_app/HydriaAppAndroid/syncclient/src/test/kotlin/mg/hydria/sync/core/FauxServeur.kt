package mg.hydria.sync.core

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.util.UUID

val CHEMIN_OUVRAGE = listOf(
    Noeud("region", "r1", "Analanjirofo"), Noeud("district", "d1", "Soanierana"), Noeud("commune", "c1", "Ampasina"),
    Noeud("fokontany", "f1", "Fkt 1"), Noeud("village", "v1", "Village 1"), Noeud("ouvrage", "o1", "Ouvrage A"),
)
const val DOSSIER_OUVRAGE = "Territoire/Analanjirofo/Soanierana/Ampasina/Fkt 1/Village 1/Ouvrage A"

val ARBORESCENCE = """
{"organisation":{"id":"org1","nom":"Org"},
 "territoire":{"regions":[{"id":"r1","nom":"Analanjirofo","districts":[{"id":"d1","nom":"Soanierana","communes":[
   {"id":"c1","nom":"Ampasina","fokontany":[{"id":"f1","nom":"Fkt 1","villages":[
     {"id":"v1","nom":"Village 1","ouvrages":[{"id":"o1","nom":"Ouvrage A",
        "equipements":[{"id":"e1","nom":"Pompe A"}],"points_eau":[{"id":"p1","nom":"Abonne A"}]}],"points_eau":[]}]}]}]}]}],
   "ouvrages_sans_village":[],"activites":[]},
 "organisation_branche":{"domaines":[
   {"code":"operationnel","acces":{"lecture":true,"ecriture":true},"categories":[{"code":"procedure","libelle":"Procédure","extensions":["pdf","txt"]}]},
   {"code":"financier","acces":{"lecture":false,"ecriture":false},"categories":[{"code":"facture","libelle":"Facture","extensions":["pdf"]}]}]},
 "categories_entite":[
   {"code":"dossier_technique","libelle":"Dossier technique","entity_types":["ouvrage","equipement"],"extensions":["xlsx","pdf"]},
   {"code":"photos_equipement","libelle":"Photos d'équipement","entity_types":["equipement"],"extensions":["jpg"]}]}
""".trimIndent()

class PartieRecue(val nom: String, val octets: ByteArray)

/** Faux serveur Hydria en memoire : reproduit le contrat de /api/sync/… et /api/fichiers/… (voir backend/README.md). */
class FauxServeur {
    val fichiers = LinkedHashMap<String, FichierDto>()
    val contenus = HashMap<String, ByteArray>()
    val changes = mutableListOf<ChangeDto>()
    val requetes = mutableListOf<String>()
    val ifMatchRecus = mutableListOf<String>()
    var jetonValide = "T1"
    var arborescence = ARBORESCENCE
    var refuserDepots = false
    var refuserTelechargements = false
    var refuserConnexion = false
    var refuserRenouvellement = false
    private var seq = 0L

    val client: HttpClient = HttpClient(MockEngine { requete ->
        val chemin = requete.url.encodedPath
        requetes += "${requete.method.value} $chemin"
        fun json(texte: String, statut: HttpStatusCode = HttpStatusCode.OK) =
            respond(texte, statut, headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()))

        if (chemin == "/api/sync/auth/login") {
            if (refuserConnexion) return@MockEngine json("""{"code":"IDENTIFIANTS_INVALIDES","message":"Identifiants invalides."}""", HttpStatusCode.Unauthorized)
            return@MockEngine json("""{"access_token":"T1","refresh_token":"R1","expires_in":3600}""")
        }
        if (chemin == "/api/sync/auth/refresh") {
            if (refuserRenouvellement) return@MockEngine json("""{"code":"JETON_INVALIDE","message":"Jeton expiré ou révoqué."}""", HttpStatusCode.Unauthorized)
            jetonValide = "T2"
            return@MockEngine json("""{"access_token":"T2","refresh_token":"R2","expires_in":3600}""")
        }
        if (requete.headers[HttpHeaders.Authorization] != "Bearer $jetonValide") {
            return@MockEngine json("""{"detail":"Jeton invalide."}""", HttpStatusCode.Unauthorized)
        }

        when {
            chemin == "/api/sync/arborescence" -> json(arborescence)
            chemin == "/api/sync/changes" -> {
                val depuis = requete.url.parameters["since"]!!.toLong()
                val limite = requete.url.parameters["limit"]!!.toInt()
                val restants = changes.filter { it.seq > depuis }
                // comme le vrai serveur : la fiche renvoyee est l'etat COURANT, pas un instantane
                val page = restants.take(limite).map { c -> c.copy(fichier = c.fichier?.let { fichiers[it.id] }) }
                json(jsonFormat.encodeToString(ChangesPage(depuis, page.lastOrNull()?.seq ?: depuis, restants.size > limite, page)))
            }
            chemin.endsWith("/telechargement") -> {
                if (refuserTelechargements) return@MockEngine json("""{"code":"ERREUR","message":"refus de test"}""", HttpStatusCode.InternalServerError)
                val id = chemin.removePrefix("/api/fichiers/").substringBefore('/')
                respond(contenus.getValue(id), HttpStatusCode.OK)
            }
            chemin == "/api/sync/upload" -> {
                if (refuserDepots) return@MockEngine json("""{"code":"DOMAINE_INTERDIT","message":"refus de test"}""", HttpStatusCode.Forbidden)
                val p = parties(requete.body.toByteArray(), requete.body.contentType.toString())
                val texte = { cle: String -> p[cle]?.octets?.toString(Charsets.UTF_8) }
                val domaine = texte("domaine")
                val f = nouveau(
                    nom = texte("nom")!!, contenu = p.getValue("fichier").octets,
                    entityType = texte("entity_type"), entityId = texte("entity_id"), domaine = domaine, categorie = texte("categorie")!!,
                )
                json(jsonFormat.encodeToString(f), HttpStatusCode.Created)
            }
            requete.method == HttpMethod.Patch || requete.method == HttpMethod.Delete -> {
                val id = chemin.removePrefix("/api/fichiers/").trimEnd('/')
                val attendue = requete.headers[HttpHeaders.IfMatch]!!.toInt()
                ifMatchRecus += attendue.toString()
                val courant = fichiers.getValue(id)
                if (courant.version != attendue) {
                    return@MockEngine json(
                        """{"code":"CONFLIT_VERSION","message":"conflit","version_actuelle":${courant.version},"fichier":${jsonFormat.encodeToString(courant)}}""",
                        HttpStatusCode.Conflict,
                    )
                }
                if (requete.method == HttpMethod.Delete) {
                    supprimer(id)
                    return@MockEngine json(jsonFormat.encodeToString(fichiers.getValue(id)))
                }
                val p = parties(requete.body.toByteArray(), requete.body.contentType.toString())
                modifier(id, p["fichier"]?.octets, p["nom"]?.octets?.toString(Charsets.UTF_8))
                json(jsonFormat.encodeToString(fichiers.getValue(id)))
            }
            else -> json("""{"code":"INCONNU","message":"$chemin"}""", HttpStatusCode.NotFound)
        }
    })

    fun jetons() = Jetons(renouvellement = "R1")
    fun api(jetons: Jetons = jetons()) = SyncApi(client, "https://hydria.test", jetons)

    private fun parties(corps: ByteArray, contentType: String): Map<String, PartieRecue> {
        val limite = "--" + contentType.substringAfter("boundary=").trim('"')
        val texte = String(corps, Charsets.ISO_8859_1)
        val resultat = mutableMapOf<String, PartieRecue>()
        for (brut in texte.split(limite).drop(1)) {
            if (brut.startsWith("--")) break
            val corpsPartie = brut.removePrefix("\r\n")
            val separation = corpsPartie.indexOf("\r\n\r\n")
            val entetes = corpsPartie.substring(0, separation)
            val contenu = corpsPartie.substring(separation + 4).removeSuffix("\r\n")
            // Ktor ecrit `name=nom` sans guillemets quand ce n'est pas necessaire ; Django accepte les deux formes.
            val nom = Regex("""name="?([^";\r\n]+)"?""").find(entetes)!!.groupValues[1]
            resultat[nom] = PartieRecue(nom, contenu.toByteArray(Charsets.ISO_8859_1))
        }
        return resultat
    }

    // ------------------------------------------------------------------ donnees

    private fun cheminPour(entityType: String?) = if (entityType == "ouvrage") CHEMIN_OUVRAGE else null

    fun nouveau(
        nom: String, contenu: ByteArray, categorie: String, entityType: String? = null, entityId: String? = null,
        domaine: String? = null, id: String = UUID.randomUUID().toString(), shaAnnonce: String? = null,
    ): FichierDto {
        val f = FichierDto(
            id = id, nom = nom, organisation = "org1", portee = if (domaine != null) "organisation" else "entite",
            entityType = entityType, entityId = entityId, domaine = domaine, categorie = categorie,
            sha256 = shaAnnonce ?: sha256Hex(contenu), taille = contenu.size.toLong(), version = 1,
            telechargement = "/api/fichiers/$id/telechargement",
        )
        fichiers[id] = f
        contenus[id] = contenu
        enregistrer("insert", f)
        return f
    }

    fun modifier(id: String, contenu: ByteArray?, nom: String? = null) {
        val f = fichiers.getValue(id)
        if (contenu != null) contenus[id] = contenu
        val octets = contenus.getValue(id)
        fichiers[id] = f.copy(nom = nom ?: f.nom, sha256 = sha256Hex(octets), taille = octets.size.toLong(), version = f.version + 1)
        enregistrer("update", fichiers.getValue(id))
    }

    fun supprimer(id: String) {
        val f = fichiers.getValue(id)
        fichiers[id] = f.copy(version = f.version + 1, deletedAt = "2026-10-26T10:00:00+00:00")
        enregistrer("delete", fichiers.getValue(id))
    }

    private fun enregistrer(action: String, f: FichierDto) {
        changes += ChangeDto(
            seq = ++seq, action = action, portee = f.portee, organisation = "org1", domaine = f.domaine,
            entityType = f.entityType, entityId = f.entityId, chemin = cheminPour(f.entityType), fichier = f,
        )
    }

    fun telechargements() = requetes.count { it.endsWith("/telechargement") }
}
