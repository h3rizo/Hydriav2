package mg.hydria.app.search

import org.json.JSONObject

/** Catégorie d'une dimension du diagramme (couleur en hexadécimal, décrite par le serveur). */
data class FlowCategory(val key: String, val label: String, val color: String)

/** Dimension du diagramme : taille des villages, desserte, fonctionnement, gestion, recouvrement... */
data class FlowDimension(val key: String, val title: String, val categories: List<FlowCategory>)

/** Combinaison de catégories (une par dimension) et nombre de villages concernés. */
data class FlowRow(val values: Map<String, String>, val count: Int)

/** Noeud du diagramme : une catégorie d'une dimension (ou la racine). `column` 0 = racine. */
class FlowNode(
    val key: String,
    val dimension: String?,
    val category: String?,
    val label: String,
    val color: String,
    val count: Int,
    val column: Int,
    val index: Int,
) {
    var x = 0f
    var y = 0f
    var height = 0f
    internal var offsetOut = 0f
    internal var offsetIn = 0f
}

/** Flux entre deux noeuds de colonnes consécutives. `y0`/`y1` = bord haut du ruban à la source / à la cible. */
class FlowLink(val from: FlowNode, val to: FlowNode, val count: Int, val color: String) {
    var y0 = 0f
    var y1 = 0f
    var thickness = 0f
}

class FlowLayout(
    val nodes: List<FlowNode>,
    val links: List<FlowLink>,
    val columnTitles: List<String>,
    val total: Int,
    val width: Float,
    val height: Float,
)

/**
 * Calcul du diagramme de flux (type Sankey) : colonnes, noeuds proportionnels aux effectifs, rubans empilés
 * sans chevauchement. Logique pure, sans Android : testable en JVM. Reprend le calcul du diagramme du dashboard.
 */
object FlowDiagramLayout {
    const val ROOT_KEY = "root"

    fun parseDimensions(json: JSONObject): Map<String, FlowDimension> {
        val result = LinkedHashMap<String, FlowDimension>()
        json.keys().forEach { key ->
            val dim = json.optJSONObject(key) ?: return@forEach
            val cats = dim.optJSONArray("cats")
            val categories = buildList {
                if (cats != null) for (i in 0 until cats.length()) {
                    val cat = cats.getJSONObject(i)
                    add(FlowCategory(cat.optString("k"), cat.optString("court"), cat.optString("color", "#9ca3af")))
                }
            }
            result[key] = FlowDimension(key, dim.optString("titre", key), categories)
        }
        return result
    }

    fun parseRows(rows: org.json.JSONArray, dimensionKeys: Collection<String>): List<FlowRow> = buildList {
        for (i in 0 until rows.length()) {
            val row = rows.getJSONObject(i)
            add(FlowRow(dimensionKeys.associateWith { row.optString(it) }, row.optInt("n", 0)))
        }
    }

    /**
     * @param order dimensions affichées, dans l'ordre des colonnes (après la racine)
     * @param columnWidth écart entre deux colonnes ; @param height hauteur disponible pour les noeuds
     */
    fun build(
        rows: List<FlowRow>,
        dimensions: Map<String, FlowDimension>,
        order: List<String>,
        rootLabel: String,
        columnWidth: Float = 640f,
        height: Float = 1100f,
        topMargin: Float = 90f,
        bottomMargin: Float = 24f,
        gap: Float = 28f,
        leftMargin: Float = 24f,
        labelWidth: Float = 420f,
    ): FlowLayout {
        val dims = order.mapNotNull { dimensions[it] }
        val total = rows.sumOf { it.count }
        if (total == 0 || dims.isEmpty()) {
            return FlowLayout(emptyList(), emptyList(), emptyList(), total, leftMargin + labelWidth, height)
        }

        // Colonnes : racine, puis une colonne par dimension (catégories absentes ignorées)
        val columns = ArrayList<List<FlowNode>>()
        columns.add(listOf(FlowNode(ROOT_KEY, null, null, rootLabel, "#6b7280", total, 0, 0)))
        dims.forEachIndexed { dimIndex, dim ->
            val counts = HashMap<String, Int>()
            rows.forEach { row -> row.values[dim.key]?.let { counts[it] = (counts[it] ?: 0) + row.count } }
            val nodes = dim.categories.filter { (counts[it.key] ?: 0) > 0 }.mapIndexed { idx, cat ->
                FlowNode("${dim.key}:${cat.key}", dim.key, cat.key, cat.label, cat.color, counts.getValue(cat.key), dimIndex + 1, idx)
            }
            columns.add(nodes)
        }

        // Liens entre colonnes consécutives
        val links = ArrayList<FlowLink>()
        columns[1].forEach { links.add(FlowLink(columns[0][0], it, it.count, it.color)) }
        for (i in 1 until dims.size) {
            val a = dims[i - 1].key
            val b = dims[i].key
            val pairs = HashMap<Pair<String, String>, Int>()
            rows.forEach { row ->
                val ka = row.values[a] ?: return@forEach
                val kb = row.values[b] ?: return@forEach
                pairs[ka to kb] = (pairs[ka to kb] ?: 0) + row.count
            }
            columns[i].forEach { source ->
                columns[i + 1].forEach { target ->
                    val n = pairs[(source.category ?: "") to (target.category ?: "")] ?: 0
                    if (n > 0) links.add(FlowLink(source, target, n, source.color))
                }
            }
        }

        // Géométrie : noeuds centrés verticalement dans chaque colonne
        val maxNodes = columns.maxOf { it.size }
        val scale = (height - topMargin - bottomMargin - gap * (maxNodes - 1)) / total
        columns.forEachIndexed { columnIndex, column ->
            val stackHeight = total * scale + gap * (column.size - 1)
            var y = topMargin + (height - topMargin - bottomMargin - stackHeight) / 2
            column.forEach { node ->
                node.x = leftMargin + columnIndex * columnWidth
                node.y = y
                node.height = node.count * scale
                y += node.height + gap
            }
        }
        // Empilement des rubans à l'intérieur de chaque noeud, dans l'ordre des noeuds voisins
        links.sortedWith(compareBy({ it.from.column }, { it.from.index }, { it.to.index })).forEach {
            it.thickness = it.count * scale
            it.y0 = it.from.y + it.from.offsetOut
            it.from.offsetOut += it.thickness
        }
        links.sortedWith(compareBy({ it.to.column }, { it.to.index }, { it.from.index })).forEach {
            it.y1 = it.to.y + it.to.offsetIn
            it.to.offsetIn += it.thickness
        }

        val titles = listOf("Total") + dims.map { it.title }
        return FlowLayout(
            columns.flatten(), links, titles, total,
            leftMargin + (columns.size - 1) * columnWidth + labelWidth, height,
        )
    }
}
