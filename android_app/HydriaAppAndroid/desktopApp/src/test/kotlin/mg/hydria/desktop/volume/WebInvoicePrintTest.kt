package mg.hydria.desktop.volume

import org.json.JSONObject
import java.io.File
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class WebInvoicePrintTest {
    private fun invoice() = JSONObject()
        .put("id", "r1").put("montant", "5100.00").put("mois", "2026-09").put("imprimee", false)
        .put("detail", JSONObject().put("abonnement", 600).put("montant_volume", 4500).put("montant_ht", 5100)
            .put("tranches", org.json.JSONArray().put(JSONObject().put("tranche", "0-10 m3").put("volume", 1.5)
                .put("tarif_unitaire", 3000).put("montant", 4500))))
        .put("impression", JSONObject().put("releve_id", "r1").put("ouvrage_nom", "Ambanja BP")
            .put("numero_facture", "F-0001").put("abonne", "Rakoto").put("idxls", "7").put("parcelle", "P12")
            .put("type_point_eau", "BP").put("ancienindex", 10.0).put("nouvelindex", 11.5).put("volume_facture", 1.5)
            .put("responsable_ouvrage_nom", "Agent").put("qr_payload", "HYDRIA|FACTURE|r1|F-0001|2026-09|w1"))

    @Test
    fun releveUsesWebFieldsWithCurrentAmount() {
        val r = WebInvoicePrint.webReleve(invoice())
        assertEquals("F-0001", r.getString("numero_facture"))
        assertEquals(5100.0, r.getDouble("montant_calcule"))
        assertEquals("2026-09-01", r.getString("date_facture"))
        assertEquals(4500, r.getJSONObject("detail_calcul").getInt("montant_volume"))
    }

    @Test
    fun pageEmbedsUnmodifiedWebTemplate() {
        val html = WebInvoicePrint.buildHtml(listOf(invoice()), "Ambanja BP", JSONObject().put("nom", "SOAKOJA"),
            Files.createTempDirectory("inv").toFile())
        val template = File("../../../backend/static/js/print_factures_a4.js").readText()
        assertTrue(html.contains(template.replace("</script", "<\\/script")), "gabarit web non embarque tel quel")
        assertTrue(html.contains("data:image/png;base64,"))
        File("build/web-invoice-sample.html").writeText(html) // apercu manuel (navigateur)
    }
}
