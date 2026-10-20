package mg.hydria.shared.rules.readings

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ReadingPointListRulesTest {
    private fun point(idxls: String, nom: String, parcelle: String = "", lat: Double? = null, lon: Double? = null) =
        JSONObject().put("id", "p$idxls").put("idxls", idxls).put("nom", nom).put("code", "PE-XYZ")
            .put("parcelle_id", parcelle).put("parcelle", if (parcelle.isBlank()) "" else "Parcelle $parcelle")
            .apply { if (lat != null && lon != null) put("has_coordinates", true).put("latitude", lat).put("longitude", lon) }

    @Test fun largeurSelonLePlusGrandIdxls() {
        assertEquals(2, ReadingPointListRules.idxlsWidth(listOf(point("7", "A"), point("99", "B"))))
        assertEquals(3, ReadingPointListRules.idxlsWidth(listOf(point("7", "A"), point("100", "B"))))
    }

    @Test fun libelleSansCodeEtTriAlphabetique() {
        val points = listOf(point("12", "Rabe"), point("7", "Rakoto"), point("3", "Soa"))
        val width = ReadingPointListRules.idxlsWidth(points)
        assertEquals("💧 07 — Rakoto", ReadingPointListRules.label(points[1], width))
        assertEquals(listOf("3", "7", "12"), ReadingPointListRules.sortedAlphabetically(points, width).map { it.optString("idxls") })
    }

    @Test fun triNumeriqueParIdxls() {
        val points = listOf(point("10", "A"), point("2", "B"), point("", "C"), point("1", "D"))
        assertEquals(listOf("1", "2", "10", ""), ReadingPointListRules.sortedByIdxls(points, 2).map { it.optString("idxls") })
    }

    @Test fun filtreParcelleAuDelaDeVingtPoints() {
        val few = (1..20).map { point("$it", "N$it", parcelle = if (it % 2 == 0) "a" else "b") }
        assertFalse(ReadingPointListRules.showParcelFilter(few))
        val many = few + point("21", "N21")
        assertTrue(ReadingPointListRules.showParcelFilter(many))
        val parcels = ReadingPointListRules.parcels(many)
        assertEquals(listOf("a", "b", ReadingPointListRules.NO_PARCEL), parcels.map { it.id })
        assertEquals(1, ReadingPointListRules.filterByParcel(many, ReadingPointListRules.NO_PARCEL).size)
    }

    @Test fun rechercheParNomPartielOuIdxls() {
        val points = listOf(point("12", "Rabe Jean"), point("7", "Rakoto Éloïse"), point("3", "Soa"))
        fun found(query: String) = ReadingPointListRules.filterBySearch(points, 2, query).map { it.optString("idxls") }
        assertEquals(listOf("12", "7", "3"), found("  "))
        assertEquals(listOf("7"), found("rak"))
        assertEquals(listOf("7"), found("eloise"))
        assertEquals(listOf("12"), found("12"))
        assertEquals(listOf("3"), found("3"))
        assertEquals(listOf("12"), found("jean rabe"))
        assertEquals(emptyList(), found("zzz"))
    }

    @Test fun pointsProchesDabord() {
        val points = listOf(point("1", "Loin", lat = -18.95, lon = 47.55), point("2", "SansGps"), point("3", "Pres", lat = -18.9001, lon = 47.5001))
        val sorted = ReadingPointListRules.sortedByDistance(points, 2, -18.9, 47.5)
        assertEquals(listOf("Pres", "Loin", "SansGps"), sorted.map { it.optString("nom") })
        assertEquals(" · sans GPS", ReadingPointListRules.distanceSuffix(null))
        assertEquals(" · 1,5 km", ReadingPointListRules.distanceSuffix(1500.0))
    }
}
