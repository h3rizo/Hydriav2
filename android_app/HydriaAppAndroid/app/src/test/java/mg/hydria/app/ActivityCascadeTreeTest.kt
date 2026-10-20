package mg.hydria.app

import org.json.JSONObject
import mg.hydria.shared.rules.forms.ActivityCascadeTree
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ActivityCascadeTreeTest {
    private fun fiche(id: String, nom: String, type: String, groupe: String = "", ordre: Int = 9999) =
        JSONObject().put("id", id).put("nom", nom).put("type_activite", type)
            .put("label", "$type - $nom").put("groupe", groupe).put("groupe_ordre", ordre)

    private val fiches = listOf(
        fiche("1", "Relevé compteurs", "Relevés", "Exploitation", 1),
        fiche("2", "Nettoyage BF", "Entretien", "Exploitation", 1),
        fiche("3", "Réunion usagers", "Social", "Animation", 2),
        fiche("4", "Congé", "", ""),                       // ancien snapshot : ni type ni groupe
        fiche("5", "Contrôle captage", "Entretien", "Exploitation", 1),
    )

    @Test fun groupesTriesParOrdreEtAutresEnDernier() {
        val tree = ActivityCascadeTree.build(fiches)
        assertEquals(listOf("Exploitation", "Animation", ActivityCascadeTree.NO_GROUP), tree.map { it.name })
        assertEquals(listOf("Entretien", "Relevés"), tree[0].children.map { it.name })
        // Ordre du serveur conservé dans un type ; seul le nom de l'activité est affiché
        assertEquals(listOf("Nettoyage BF", "Contrôle captage"), tree[0].children[0].children.map { it.name })
        assertEquals(ActivityCascadeTree.NO_TYPE, tree[2].children.single().name)
    }

    @Test fun cheminDUneActiviteExistantePourLaPreselection() {
        val tree = ActivityCascadeTree.build(fiches)
        assertEquals(Triple(0, 0, 1), ActivityCascadeTree.pathOf(tree, "5"))
        assertEquals(Triple(2, 0, 0), ActivityCascadeTree.pathOf(tree, "4"))
        assertNull(ActivityCascadeTree.pathOf(tree, "inconnue"))
        // Aucune activité perdue
        assertEquals(fiches.size, tree.sumOf { g -> g.children.sumOf { it.children.size } })
    }

    @Test fun reparationLimiteeAuxOperationsSurLesOuvrages() {
        val repair = listOf(
            fiche("r1", "Réparation fuite", "Maintenance", "Opérations sur les ouvrages", 1),
            fiche("r2", "Remplacement robinet", "Maintenance", "OPERATION SUR LES OUVRAGES", 1),
            fiche("r3", "Visite usager", "Social", "Opérations sur les usagers", 2),
        )
        assertEquals(listOf("r1", "r2"), ActivityCascadeTree.repairActivities(repair).map { it.optString("id") })
        // Ancien snapshot sans groupes : on garde tout plutôt qu'un formulaire vide
        val old = listOf(fiche("a", "Réparation", "Maintenance"), fiche("b", "Contrôle", "Maintenance"))
        assertEquals(2, ActivityCascadeTree.repairActivities(old).size)
    }
}
