package mg.hydria.sync.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ArbreTest {
    private fun arbre(json: String = ARBORESCENCE, etat: Etat = Etat()): Arbre =
        Arbre(etat).also { it.charger(Json.parseToJsonElement(json).jsonObject) }

    @Test
    fun `les noms interdits sous Windows sont assainis`() {
        assertEquals("a_b_c", Noms.assainir("a/b:c"))
        assertEquals("_CON", Noms.assainir("CON"))
        assertEquals("_nul.txt", Noms.assainir("nul.txt"))
        assertEquals("fin", Noms.assainir("fin. . "))
        assertEquals("_", Noms.assainir("   "))
        assertEquals("Photos d'équipement", Noms.assainir("Photos d'équipement"))
        assertTrue(Noms.assainir("x".repeat(300)).length <= Noms.LONGUEUR_MAX)
    }

    @Test
    fun `le chemin d'un equipement suit la hierarchie`() {
        val a = arbre()
        assertEquals(
            listOf("Territoire", "Analanjirofo", "Soanierana", "Ampasina", "Fkt 1", "Village 1", "Ouvrage A", "Équipements", "Pompe A"),
            a.segments(a.element("e1")!!),
        )
        assertEquals(
            listOf("Territoire", "Analanjirofo", "Soanierana", "Ampasina", "Fkt 1", "Village 1", "Ouvrage A", "Points d'eau", "Abonne A"),
            a.segments(a.element("p1")!!),
        )
    }

    @Test
    fun `deux villages homonymes obtiennent des dossiers distincts et stables`() {
        val json = ARBORESCENCE.replace(
            """"villages":[""",
            """"villages":[{"id":"aaaaaaaa-0000","nom":"Village 1","ouvrages":[],"points_eau":[]},""",
        )
        val etat = Etat()
        val a = arbre(json, etat)
        val premier = a.nomDossier(a.element("aaaaaaaa-0000")!!)
        val second = a.nomDossier(a.element("v1")!!)
        assertTrue(premier != second, "$premier / $second")
        assertTrue(premier.equals("Village 1", true) || second.equals("Village 1", true))
        // un rechargement avec le meme etat ne renomme rien
        val relu = arbre(json, etat)
        assertEquals(premier, relu.nomDossier(relu.element("aaaaaaaa-0000")!!))
        assertEquals(second, relu.nomDossier(relu.element("v1")!!))
    }

    @Test
    fun `un dossier cree par l'utilisateur est resolu vers sa cible`() {
        val a = arbre()
        val ouvrage = a.resoudre(DOSSIER_OUVRAGE.split('/') + "Dossier technique")
        assertEquals(Cible.Entite("ouvrage", "o1", "dossier_technique"), ouvrage)
        val equipement = a.resoudre(DOSSIER_OUVRAGE.split('/') + listOf("Équipements", "Pompe A", "Photos d'équipement"))
        assertEquals(Cible.Entite("equipement", "e1", "photos_equipement"), equipement)
        assertEquals(Cible.Organisation("operationnel", "procedure"), a.resoudre(listOf("Organisation", "Opérationnel", "Procédure")))
    }

    @Test
    fun `les emplacements invalides ne sont pas resolus`() {
        val a = arbre()
        // categorie de photos d'equipement posee sur un ouvrage : interdit par la categorie
        assertNull(a.resoudre(DOSSIER_OUVRAGE.split('/') + "Photos d'équipement"))
        assertNull(a.resoudre(DOSSIER_OUVRAGE.split('/')))                          // pas de categorie
        assertNull(a.resoudre(listOf("Territoire", "Inconnu", "Dossier technique")))  // dossier inexistant
        assertNull(a.resoudre(listOf("Autre", "Opérationnel", "Procédure")))
        assertNull(a.resoudre(listOf("Organisation", "Opérationnel", "Inconnue")))
        assertNull(a.resoudre(listOf("Organisation", "Opérationnel")))
    }

    @Test
    fun `un chemin recu du serveur ajoute les noeuds manquants`() {
        val a = arbre()
        val nouveau = a.assurerChemin(CHEMIN_OUVRAGE.dropLast(1) + Noeud("ouvrage", "o9", "Ouvrage Neuf"))
        assertEquals("Ouvrage Neuf", nouveau!!.nom)
        assertEquals(DOSSIER_OUVRAGE.replace("Ouvrage A", "Ouvrage Neuf").split('/'), a.segments(nouveau))
    }
}
