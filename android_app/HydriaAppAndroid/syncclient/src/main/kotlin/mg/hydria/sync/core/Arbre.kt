package mg.hydria.sync.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** Un element de la hierarchie (region, ..., ouvrage, equipement, point d'eau, activite) ou un groupe virtuel. */
class Element(val type: String, val id: String, var nom: String, var parent: Element?) {
    val enfants = mutableListOf<Element>()
}

class CategorieInfo(val code: String, val libelle: String, val typesEntite: List<String>, val extensions: List<String>)
class DomaineInfo(val code: String, val lecture: Boolean, val ecriture: Boolean, val categories: List<CategorieInfo>)

/** Destination serveur d'un fichier local, deduite de son dossier. */
sealed interface Cible {
    data class Entite(val entityType: String, val entityId: String, val categorie: String) : Cible
    data class Organisation(val domaine: String, val categorie: String) : Cible
}

object Noms {
    private val INTERDITS = Regex("""[<>:"/\\|?*\u0000-\u001F]""")
    private val RESERVES = Regex("""(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$""")
    const val LONGUEUR_MAX = 80

    /** Nom de dossier/fichier valable sous Windows (caracteres interdits, noms reserves, point final...). */
    fun assainir(nom: String): String {
        var resultat = INTERDITS.replace(nom.trim(), "_").take(LONGUEUR_MAX).trimEnd(' ', '.')
        if (resultat.isEmpty()) resultat = "_"
        if (RESERVES.matches(resultat)) resultat = "_$resultat"
        return resultat
    }

    val LIBELLES_DOMAINES = mapOf(
        "operationnel" to "Opérationnel",
        "administratif" to "Administratif",
        "financier" to "Financier",
        "logistique" to "Logistique",
    )
}

/**
 * Arborescence locale :
 *
 *   Territoire/Région/District/Commune/Fokontany/Village/Ouvrage/{Catégorie | Équipements/<nom>/{Catégorie} | Points d'eau/<nom>/{Catégorie}}
 *   Territoire/Activités/<Type d'activité>/<Activité>/{Catégorie}
 *   Organisation/<Domaine>/<Catégorie>
 *
 * Les noms de dossiers sont attribues une fois pour toutes (persistes dans [Etat.noms]) : un homonyme
 * recoit le suffixe « (identifiant) » et un dossier existant n'est jamais renomme.
 */
class Arbre(private val etat: Etat) {
    val racine = Element("groupe", "_racine", "Territoire", null)
    private val sansVillage = Element("groupe", "_sans_village", "Ouvrages sans village", racine).also { racine.enfants += it }
    private val activites = Element("groupe", "_activites", "Activités", racine).also { racine.enfants += it }
    private val elements = HashMap<String, Element>()

    var categoriesEntite: List<CategorieInfo> = emptyList()
        private set
    var domaines: List<DomaineInfo> = emptyList()
        private set

    fun element(id: String): Element? = elements[id]

    fun ouvrages(): List<Element> = elements.values.filter { it.type == "ouvrage" }.sortedBy { it.id }

    // ------------------------------------------------------------------ chargement

    fun charger(arborescence: JsonObject) {
        val territoire = arborescence["territoire"]?.jsonObject
        territoire?.get("regions")?.jsonArray?.forEach { r ->
            val region = ajouter("region", r.jsonObject, racine)
            enfants(r.jsonObject, "districts", "district", region) { district ->
                enfants(district.second, "communes", "commune", district.first) { commune ->
                    enfants(commune.second, "fokontany", "fokontany", commune.first) { fokontany ->
                        enfants(fokontany.second, "villages", "village", fokontany.first) { village ->
                            ouvrages(village.second, village.first)
                            village.second["points_eau"]?.jsonArray?.forEach { ajouter("point_eau", it.jsonObject, village.first) }
                        }
                    }
                }
            }
        }
        territoire?.get("ouvrages_sans_village")?.jsonArray?.forEach { ouvrage(it.jsonObject, sansVillage) }
        territoire?.get("activites")?.jsonArray?.forEach { t ->
            val type = ajouter("type_activite", t.jsonObject, activites)
            t.jsonObject["activites"]?.jsonArray?.forEach { ajouter("activite", it.jsonObject, type) }
        }

        categoriesEntite = arborescence["categories_entite"]?.jsonArray?.map(::categorie) ?: emptyList()
        domaines = arborescence["organisation_branche"]?.jsonObject?.get("domaines")?.jsonArray?.map { d ->
            val o = d.jsonObject
            val acces = o["acces"]?.jsonObject
            DomaineInfo(
                o["code"]!!.jsonPrimitive.content,
                acces?.get("lecture")?.jsonPrimitive?.boolean ?: true,
                acces?.get("ecriture")?.jsonPrimitive?.boolean ?: true,
                o["categories"]?.jsonArray?.map(::categorie) ?: emptyList(),
            )
        } ?: emptyList()
    }

    private fun categorie(e: kotlinx.serialization.json.JsonElement): CategorieInfo {
        val o = e.jsonObject
        return CategorieInfo(
            o["code"]!!.jsonPrimitive.content,
            o["libelle"]!!.jsonPrimitive.content,
            (o["entity_types"] as? JsonArray)?.map { it.jsonPrimitive.content } ?: emptyList(),
            (o["extensions"] as? JsonArray)?.map { it.jsonPrimitive.content } ?: emptyList(),
        )
    }

    private fun enfants(parentJson: JsonObject, cle: String, type: String, parent: Element,
                        suite: (Pair<Element, JsonObject>) -> Unit) {
        parentJson[cle]?.jsonArray?.forEach { suite(ajouter(type, it.jsonObject, parent) to it.jsonObject) }
    }

    private fun ouvrages(parentJson: JsonObject, parent: Element) {
        parentJson["ouvrages"]?.jsonArray?.forEach { ouvrage(it.jsonObject, parent) }
    }

    private fun ouvrage(o: JsonObject, parent: Element) {
        val element = ajouter("ouvrage", o, parent)
        o["equipements"]?.jsonArray?.forEach { ajouter("equipement", it.jsonObject, element) }
        o["points_eau"]?.jsonArray?.forEach { ajouter("point_eau", it.jsonObject, element) }
    }

    private fun ajouter(type: String, o: JsonObject, parent: Element): Element =
        creer(type, o["id"]!!.jsonPrimitive.content, o["nom"]!!.jsonPrimitive.content, parent)

    private fun creer(type: String, id: String, nom: String, parent: Element): Element {
        val existant = elements[id]
        if (existant != null) {
            existant.nom = nom
            return existant
        }
        val element = Element(type, id, nom, parent)
        parent.enfants += element
        elements[id] = element
        return element
    }

    /** Enregistre les noeuds d'un chemin recu du serveur (element absent de l'arborescence chargee). */
    fun assurerChemin(chemin: List<Noeud>): Element? {
        var parent: Element? = null
        var courant: Element? = null
        for (noeud in chemin) {
            courant = elements[noeud.id] ?: creer(noeud.type, noeud.id, noeud.nom, parent ?: parentRacine(noeud.type))
            courant.nom = noeud.nom
            parent = courant
        }
        return courant
    }

    private fun parentRacine(type: String): Element = when (type) {
        "region" -> racine
        "type_activite" -> activites
        else -> sansVillage
    }

    // ------------------------------------------------------------------ noms et chemins

    private fun groupeDe(e: Element) = when (e.type) {
        "equipement" -> "eq"
        "point_eau" -> "pt"
        else -> "std"
    }

    /** Nom du dossier d'un element (attribue une fois, puis fige). */
    fun nomDossier(e: Element): String {
        if (e.type == "groupe") return e.nom
        etat.noms[e.id]?.let { return it }
        val base = Noms.assainir(e.nom)
        val pris = e.parent?.enfants.orEmpty()
            .filter { it !== e && groupeDe(it) == groupeDe(e) }
            .mapNotNull { etat.noms[it.id]?.lowercase() }
            .toSet()
        val choisi = if (base.lowercase() in pris) Noms.assainir("$base (${e.id.take(8)})") else base
        etat.noms[e.id] = choisi
        return choisi
    }

    /** Segments du dossier d'un element, de « Territoire » jusqu'a lui. */
    fun segments(e: Element): List<String> {
        val chaine = ArrayDeque<Element>()
        var courant: Element? = e
        var garde = 0
        while (courant != null && garde++ < 32) {
            chaine.addFirst(courant)
            courant = courant.parent
        }
        val resultat = mutableListOf<String>()
        for (element in chaine) {
            when (element.type) {
                "equipement" -> resultat += listOf("Équipements", nomDossier(element))
                "point_eau" -> resultat += listOf("Points d'eau", nomDossier(element))
                else -> resultat += nomDossier(element)
            }
        }
        return resultat
    }

    fun libelleCategorieEntite(code: String): String =
        Noms.assainir(categoriesEntite.firstOrNull { it.code == code }?.libelle ?: code)

    fun libelleDomaine(code: String): String = Noms.LIBELLES_DOMAINES[code] ?: Noms.assainir(code)

    fun libelleCategorieOrganisation(domaine: String, code: String): String =
        Noms.assainir(domaines.firstOrNull { it.code == domaine }?.categories?.firstOrNull { it.code == code }?.libelle ?: code)

    // ------------------------------------------------------------------ resolution d'un dossier local

    private fun enfantParNom(parent: Element, nom: String, groupe: String): Element? {
        val candidats = parent.enfants.filter { groupeDe(it) == groupe }.sortedBy { it.id }
        candidats.forEach { nomDossier(it) } // attribue les noms dans un ordre stable
        return candidats.firstOrNull { nomDossier(it).equals(nom, ignoreCase = true) }
    }

    /**
     * Destination d'un fichier d'apres les segments de son DOSSIER (sans le nom du fichier), ou null.
     * Exemple : ["Territoire", "Région", ..., "Ouvrage X", "Dossier technique"].
     */
    fun resoudre(segmentsDossier: List<String>): Cible? {
        if (segmentsDossier.size < 3) return null
        if (segmentsDossier[0].equals("Organisation", ignoreCase = true)) {
            if (segmentsDossier.size != 3) return null
            val domaine = domaines.firstOrNull { libelleDomaine(it.code).equals(segmentsDossier[1], ignoreCase = true) } ?: return null
            val categorie = domaine.categories.firstOrNull { libelleCategorieOrganisation(domaine.code, it.code).equals(segmentsDossier[2], ignoreCase = true) } ?: return null
            return Cible.Organisation(domaine.code, categorie.code)
        }
        if (!segmentsDossier[0].equals("Territoire", ignoreCase = true)) return null

        var courant: Element = racine
        var groupe = "std"
        for (segment in segmentsDossier.subList(1, segmentsDossier.size - 1)) {
            when {
                segment.equals("Équipements", ignoreCase = true) && courant.type == "ouvrage" -> groupe = "eq"
                segment.equals("Points d'eau", ignoreCase = true) && (courant.type == "ouvrage" || courant.type == "village") -> groupe = "pt"
                else -> {
                    courant = enfantParNom(courant, segment, groupe) ?: return null
                    groupe = "std"
                }
            }
        }
        if (courant.type == "groupe") return null
        val libelle = segmentsDossier.last()
        val categorie = categoriesEntite.firstOrNull {
            libelleCategorieEntite(it.code).equals(libelle, ignoreCase = true) &&
                (it.typesEntite.isEmpty() || courant.type in it.typesEntite)
        } ?: return null
        return Cible.Entite(courant.type, courant.id, categorie.code)
    }
}
