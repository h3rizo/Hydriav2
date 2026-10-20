package mg.hydria.app.search

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FlowDiagramLayoutTest {
    private val dims = mapOf(
        "taille" to FlowDimension("taille", "Taille", listOf(
            FlowCategory("petit", "Petits", "#38bdf8"), FlowCategory("grand", "Grands", "#1e3a8a"))),
        "desserte" to FlowDimension("desserte", "Desserte", listOf(
            FlowCategory("desservi", "Desservis", "#0ea5e9"), FlowCategory("non_desservi", "Non desservis", "#475569"))),
    )
    private val rows = listOf(
        FlowRow(mapOf("taille" to "petit", "desserte" to "desservi"), 10),
        FlowRow(mapOf("taille" to "petit", "desserte" to "non_desservi"), 5),
        FlowRow(mapOf("taille" to "grand", "desserte" to "desservi"), 5),
    )

    private fun node(layout: FlowLayout, key: String) = layout.nodes.first { it.key == key }

    @Test
    fun `colonnes, noeuds et effectifs`() {
        val layout = FlowDiagramLayout.build(rows, dims, listOf("taille", "desserte"), "Villages")
        assertEquals(20, layout.total)
        assertEquals(listOf("Total", "Taille", "Desserte"), layout.columnTitles)
        assertEquals(5, layout.nodes.size)
        assertEquals(15, node(layout, "taille:petit").count)
        assertEquals(5, node(layout, "taille:grand").count)
        assertEquals(15, node(layout, "desserte:desservi").count)
        assertEquals(5, node(layout, "desserte:non_desservi").count)
        assertEquals(0, node(layout, "root").column)
        assertEquals(2, node(layout, "desserte:desservi").column)
    }

    @Test
    fun `les flux conservent les effectifs`() {
        val layout = FlowDiagramLayout.build(rows, dims, listOf("taille", "desserte"), "Villages")
        // racine -> 2 + taille -> desserte : 3 flux (grand -> non desservi n'existe pas)
        assertEquals(5, layout.links.size)
        layout.nodes.filter { it.column > 0 }.forEach { n ->
            assertEquals("entrant ${n.key}", n.count, layout.links.filter { it.to === n }.sumOf { it.count })
        }
        layout.nodes.filter { it.column < 2 }.forEach { n ->
            assertEquals("sortant ${n.key}", n.count, layout.links.filter { it.from === n }.sumOf { it.count })
        }
    }

    @Test
    fun `les rubans restent dans leur noeud sans se chevaucher`() {
        val layout = FlowDiagramLayout.build(rows, dims, listOf("taille", "desserte"), "Villages")
        val eps = 0.01f
        layout.nodes.forEach { n ->
            val sortants = layout.links.filter { it.from === n }.sortedBy { it.y0 }
            val entrants = layout.links.filter { it.to === n }.sortedBy { it.y1 }
            sortants.forEach { assertTrue(it.y0 >= n.y - eps && it.y0 + it.thickness <= n.y + n.height + eps) }
            entrants.forEach { assertTrue(it.y1 >= n.y - eps && it.y1 + it.thickness <= n.y + n.height + eps) }
            sortants.zipWithNext().forEach { (a, b) -> assertTrue(a.y0 + a.thickness <= b.y0 + eps) }
            entrants.zipWithNext().forEach { (a, b) -> assertTrue(a.y1 + a.thickness <= b.y1 + eps) }
        }
        // les hauteurs sont proportionnelles aux effectifs
        val petit = node(layout, "taille:petit")
        val grand = node(layout, "taille:grand")
        assertEquals(3f, petit.height / grand.height, 0.001f)
    }

    @Test
    fun `une seule dimension affichee`() {
        val layout = FlowDiagramLayout.build(rows, dims, listOf("desserte"), "Villages")
        assertEquals(3, layout.nodes.size)
        assertEquals(2, layout.links.size)
        assertEquals(listOf("Total", "Desserte"), layout.columnTitles)
    }

    @Test
    fun `ordre des colonnes respecte`() {
        val layout = FlowDiagramLayout.build(rows, dims, listOf("desserte", "taille"), "Villages")
        assertEquals(listOf("Total", "Desserte", "Taille"), layout.columnTitles)
        assertEquals(1, node(layout, "desserte:desservi").column)
        assertEquals(2, node(layout, "taille:petit").column)
    }

    @Test
    fun `aucune donnee ou aucune dimension`() {
        assertTrue(FlowDiagramLayout.build(emptyList(), dims, listOf("taille"), "Villages").nodes.isEmpty())
        assertTrue(FlowDiagramLayout.build(rows, dims, emptyList(), "Villages").nodes.isEmpty())
        assertTrue(FlowDiagramLayout.build(rows, dims, listOf("inconnue"), "Villages").nodes.isEmpty())
    }

    @Test
    fun `lecture du JSON du serveur`() {
        val json = JSONObject("""{"taille": {"titre": "Taille du village", "cats": [
            {"k": "petit", "court": "Petits", "color": "#38bdf8"}, {"k": "grand", "court": "Grands", "color": "#1e3a8a"}]},
            "desserte": {"titre": "Desserte", "cats": [{"k": "desservi", "court": "Desservis", "color": "#0ea5e9"}]}}""")
        val parsed = FlowDiagramLayout.parseDimensions(json)
        assertEquals(listOf("taille", "desserte"), parsed.keys.toList())
        assertEquals("Taille du village", parsed.getValue("taille").title)
        assertEquals("grand", parsed.getValue("taille").categories[1].key)
        val rowsJson = JSONArray("""[{"taille": "petit", "desserte": "desservi", "n": 7}, {"taille": "grand", "desserte": "desservi", "n": 3}]""")
        val flux = FlowDiagramLayout.parseRows(rowsJson, parsed.keys)
        assertEquals(10, flux.sumOf { it.count })
        assertEquals("petit", flux[0].values["taille"])
    }
}
