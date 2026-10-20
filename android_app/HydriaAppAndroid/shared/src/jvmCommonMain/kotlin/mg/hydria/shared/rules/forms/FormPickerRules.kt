package mg.hydria.shared.rules.forms

import org.json.JSONArray
import org.json.JSONObject
import java.text.Normalizer

/**
 * Règles communes Android + Desktop des sélecteurs de formulaires :
 * autocomplétion des ouvrages, cascade Groupe > Type d'activité > Activité,
 * cibles et composants d'une réparation / d'un planning.
 */

/** Recherche tolérante : sans accents, sans casse, n'importe où dans le libellé. */
object AutocompleteMatch {
    private val marks = "\\p{M}+".toRegex()

    fun normalize(value: String): String =
        Normalizer.normalize(value, Normalizer.Form.NFD).replace(marks, "").lowercase().trim()

    /** Tous les mots saisis doivent apparaître dans le libellé (« amb bp » trouve « Ambanja BP »). */
    fun matches(label: String, query: String): Boolean {
        val words = normalize(query).split(' ').filter { it.isNotEmpty() }
        if (words.isEmpty()) return true
        val target = normalize(label)
        return words.all { target.contains(it) }
    }

    /** Indices des libellés correspondants, ceux qui COMMENCENT par la saisie en premier. */
    fun filter(labels: List<String>, query: String): List<Int> {
        val q = normalize(query)
        return labels.indices.filter { matches(labels[it], query) }
            .sortedBy { if (q.isNotEmpty() && normalize(labels[it]).startsWith(q)) 0 else 1 }
    }
}

/**
 * Arbre Groupe > Type d'activité > Activité, depuis les références
 * `planning_fiches` / `repair_fiches` (champs `groupe`, `groupe_ordre`,
 * `type_activite`, `nom`). Sans groupe -> « Autres », sans type -> « Sans type ».
 */
object ActivityCascadeTree {
    const val NO_GROUP = "Autres"
    const val NO_TYPE = "Sans type"

    /** Seul groupe proposé dans les formulaires de réparation. */
    const val REPAIR_GROUP = "Opérations sur les ouvrages"

    data class Node(val name: String, val children: List<Node> = emptyList(), val activity: JSONObject? = null)

    fun groupOf(activity: JSONObject): String = activity.optString("groupe").ifBlank { NO_GROUP }
    fun typeOf(activity: JSONObject): String = activity.optString("type_activite").ifBlank { NO_TYPE }

    /** Nom affiché de l'activité seule (le type est déjà choisi au niveau au-dessus). */
    fun activityName(activity: JSONObject): String =
        activity.optString("nom").ifBlank { activity.optString("label", "Activité") }

    fun build(activities: List<JSONObject>): List<Node> {
        val groups = activities.groupBy(::groupOf)
        val groupOrder = groups.mapValues { (name, items) ->
            if (name == NO_GROUP) Int.MAX_VALUE else items.minOf { it.optInt("groupe_ordre", 9999) }
        }
        return groups.keys
            .sortedWith(compareBy<String>({ groupOrder.getValue(it) }, { it.lowercase() }))
            .map { groupName ->
                val types = groups.getValue(groupName).groupBy(::typeOf)
                Node(groupName, types.keys.sortedWith(compareBy({ it == NO_TYPE }, { it.lowercase() })).map { typeName ->
                    // Ordre des activités : celui du serveur (ordre, puis tâche).
                    Node(typeName, types.getValue(typeName).map { Node(activityName(it), activity = it) })
                })
            }
    }

    /** Arbre à un seul groupe (groupe masqué dans le formulaire). */
    fun buildWithoutGroups(activities: List<JSONObject>): List<Node> =
        build(activities.map { JSONObject(it.toString()).put("groupe", "") })

    /** Chemin (groupe, type, activité) d'une activité par son id, ou null. */
    fun pathOf(tree: List<Node>, activityId: String): Triple<Int, Int, Int>? {
        tree.forEachIndexed { g, group ->
            group.children.forEachIndexed { t, type ->
                val a = type.children.indexOfFirst { it.activity?.optString("id") == activityId }
                if (a >= 0) return Triple(g, t, a)
            }
        }
        return null
    }

    /** Le groupe est-il « Opération(s) sur les ouvrages » (accents, casse et pluriel ignorés) ? */
    fun isWorksOperations(groupName: String): Boolean {
        val n = AutocompleteMatch.normalize(groupName)
        return n.startsWith("operation") && n.contains("ouvrage")
    }

    /** Activités « Opérations sur les ouvrages » ; toutes si aucune ne porte ce groupe (jamais de liste vide). */
    fun repairActivities(activities: List<JSONObject>): List<JSONObject> =
        activities.filter { isWorksOperations(it.optString("groupe")) }.ifEmpty { activities }
}

/** Cible possible d'une réparation / d'un planning : point d'eau (« pe ») ou équipement (« eq »). */
data class WorkTarget(val kind: String, val id: String, val label: String, val typeId: String) {
    val key: String get() = "$kind:$id"
}

object WorkTargetRules {
    private fun objects(array: JSONArray?) = (0 until (array?.length() ?: 0)).mapNotNull { array!!.optJSONObject(it) }

    /** Points d'eau puis équipements de l'ouvrage, depuis `snapshot.terrain.ouvrages[]`. */
    fun targets(terrainWorks: JSONArray?, workId: String): List<WorkTarget> {
        val work = objects(terrainWorks).firstOrNull { it.optString("id") == workId } ?: return emptyList()
        val points = objects(work.optJSONArray("points_eau")).map { point ->
            val name = listOf(point.optString("code"), point.optString("nom")).filter { it.isNotBlank() }.joinToString(" — ")
            WorkTarget("pe", point.optString("id"), "Point d'eau · $name", point.optString("type_id"))
        }
        val equipments = objects(work.optJSONArray("equipements")).map { equipment ->
            val name = equipment.optString("nom").ifBlank { equipment.optString("code") }
            val type = equipment.optString("type").takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
            WorkTarget("eq", equipment.optString("id"), "Équipement · $name$type", equipment.optString("type_id"))
        }
        return points + equipments
    }

    /** Composants proposables pour une cible, depuis `references.composants`. */
    fun components(catalog: JSONObject?, target: WorkTarget?): List<JSONObject> {
        if (target == null) return emptyList()
        return objects(catalog?.optJSONObject(if (target.kind == "eq") "equipement" else "point_eau")?.optJSONArray(target.typeId))
    }

    /** Clé de la cible enregistrée (« eq:id » / « pe:id »), ou null. */
    fun existingKey(item: JSONObject?): String? = item?.let {
        it.optString("equipement_id").takeIf { id -> id.isNotBlank() }?.let { id -> "eq:$id" }
            ?: it.optString("point_eau_id").takeIf { id -> id.isNotBlank() }?.let { id -> "pe:$id" }
    }
}

/**
 * Règles de saisie de la cible / des composants propres à une activité
 * (`repair_fiches[].regles` / `planning_fiches[].regles`, calculées par
 * `apps/planning/reparation_composants.regles_fiche` côté serveur) :
 *  - `cible_mode` / `composants_mode` : « non », « optionnel », « obligatoire » ;
 *  - `cible_types` : « les_deux », « point_eau », « equipement » ;
 *  - `composants_multiple` : plusieurs composants autorisés ;
 *  - `composants_admis` : noms de composants proposés (vide = tous).
 * Snapshot ancien (sans `regles`) : tout reste facultatif, comme avant.
 */
data class ActivityTargetRules(
    val targetMode: String = OPTIONAL,
    val targetTypes: String = BOTH,
    val componentsMode: String = OPTIONAL,
    val multipleComponents: Boolean = true,
    val allowedComponents: List<String> = emptyList(),
) {
    val targetRequired: Boolean get() = targetMode == REQUIRED
    val targetHidden: Boolean get() = targetMode == NONE
    val componentsRequired: Boolean get() = componentsMode == REQUIRED
    val componentsHidden: Boolean get() = componentsMode == NONE

    fun allowsTarget(kind: String): Boolean = when (targetTypes) {
        "point_eau" -> kind == "pe"
        "equipement" -> kind == "eq"
        else -> true
    }

    /** Composants du catalogue de la cible, restreints aux composants admis de l'activité. */
    fun filterComponents(components: List<JSONObject>): List<JSONObject> {
        if (allowedComponents.isEmpty()) return components
        val allowed = allowedComponents.map(::componentKey).toSet()
        return components.filter { componentKey(it.optString("nom")) in allowed }
    }

    /**
     * Message d'erreur (null si conforme) — mêmes messages que
     * `verifier_regles_fiche` côté serveur. [availableComponents] = composants
     * proposés après filtrage : sans catalogue, les composants ne sont pas exigés.
     */
    fun error(activityName: String, target: WorkTarget?, componentIds: List<String>, availableComponents: Int): String? {
        val name = activityName.ifBlank { "cette activité" }
        if (target != null && !allowsTarget(target.kind)) {
            return if (target.kind == "eq") "« $name » se rapporte à un point d'eau, pas à un équipement"
            else "« $name » se rapporte à un équipement, pas à un point d'eau"
        }
        if (target == null && targetRequired) {
            val what = when (targetTypes) {
                "point_eau" -> "le point d'eau"
                "equipement" -> "l'équipement"
                else -> "le point d'eau ou l'équipement"
            }
            return "Précisez $what concerné pour « $name »"
        }
        if (target != null && componentsRequired && componentIds.isEmpty() && availableComponents > 0)
            return "Précisez le ou les composants concernés pour « $name »"
        if (!multipleComponents && componentIds.size > 1) return "Un seul composant peut être indiqué pour « $name »"
        return null
    }

    companion object {
        const val NONE = "non"
        const val OPTIONAL = "optionnel"
        const val REQUIRED = "obligatoire"
        const val BOTH = "les_deux"

        /** Même clé que `normaliser_nom_composant` (serveur) : sans accents, casse ni tirets. */
        fun componentKey(name: String): String =
            AutocompleteMatch.normalize(name.replace('-', ' ').replace('_', ' ')).split(' ').filter { it.isNotEmpty() }.joinToString(" ")

        fun of(activity: JSONObject?): ActivityTargetRules {
            val rules = activity?.optJSONObject("regles") ?: return ActivityTargetRules()
            val allowed = rules.optJSONArray("composants_admis")
            return ActivityTargetRules(
                targetMode = rules.optString("cible_mode").ifBlank { OPTIONAL },
                targetTypes = rules.optString("cible_types").ifBlank { BOTH },
                componentsMode = rules.optString("composants_mode").ifBlank { OPTIONAL },
                multipleComponents = rules.optBoolean("composants_multiple", true),
                allowedComponents = (0 until (allowed?.length() ?: 0)).map { allowed!!.optString(it) }.filter { it.isNotBlank() },
            )
        }
    }
}
