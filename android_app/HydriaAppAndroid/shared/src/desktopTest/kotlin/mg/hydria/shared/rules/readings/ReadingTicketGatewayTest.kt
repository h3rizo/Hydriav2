package mg.hydria.shared.rules.readings

import mg.hydria.shared.readings.PrintBlock
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class ReadingTicketGatewayTest {
    // Cas réel du CLAUDE.md : 0-10 m³ à 3 250 Ar, 10-2000 m³ à 5 000 Ar.
    private fun tariff(subscription: Any = 0, minimum: Any = 0) = JSONObject()
        .put("type_point_eau", "BP").put("prixabonnement", subscription).put("volume_minimum_facture", minimum)
        .put("tranches", JSONArray()
            .put(JSONObject().put("tranchesuperieur", 10).put("tarif", "3250.00"))
            .put(JSONObject().put("tranchesuperieur", 2000).put("tarif", "5000.00")))

    private fun ouvrage(tariff: JSONObject = tariff(2000)) = JSONObject().put("tarifs", JSONArray().put(tariff))
        .put("organisation", JSONObject().put("nom", "Soakoja").put("adresse1", JSONObject.NULL).put("localite", "Ambanja"))

    private fun point(mean: Double = 10.0, count: Int = 5) = JSONObject()
        .put("nom", "RAKOTO Jean").put("code", "PE-1").put("idxls", "12").put("type", "BP")
        .put("moyenne_consommation", mean).put("nb_releves_precedents", count)
        .put("impayes", JSONArray().put(JSONObject().put("date_releve", "2026-08-05").put("volume_facture", 8.0).put("montant", 5500.0)))

    private fun prepare(p: JSONObject = point(), o: JSONObject = ouvrage(), director: Boolean = false,
                        newIndex: Double = 112.0, social: Double = 0.0, nonBillable: Double = 0.0) =
        ReadingTicketGateway.prepare(p, o, director, newIndex, 100.0, social, nonBillable, "2026-10-05", "abcd1234-0000-0000-0000-000000000000")

    @Test fun unBranchementInstitutionnelPrendSonTarifDedieSinonLeTarifOrdinaire() {
        val ordinaire = tariff(1000)
        val institutionnel = tariff(2000).put("institutionnel", true)
        val avecLesDeux = JSONObject().put("tarifs", JSONArray().put(institutionnel).put(ordinaire))
        // Même si le tarif institutionnel est listé en premier, un point ordinaire garde le tarif ordinaire.
        assertEquals(1000, ReadingInvoiceEngine.tariffFor(avecLesDeux, "BP", false)!!.getInt("prixabonnement"))
        assertEquals(2000, ReadingInvoiceEngine.tariffFor(avecLesDeux, "BP", true)!!.getInt("prixabonnement"))
        // Sans tarif dédié, l'institutionnel retombe sur l'ordinaire.
        val seulementOrdinaire = JSONObject().put("tarifs", JSONArray().put(ordinaire))
        assertEquals(1000, ReadingInvoiceEngine.tariffFor(seulementOrdinaire, "BP", true)!!.getInt("prixabonnement"))
        // Un point ordinaire n'utilise jamais un tarif institutionnel seul.
        val seulementInstitutionnel = JSONObject().put("tarifs", JSONArray().put(institutionnel))
        assertNull(ReadingInvoiceEngine.tariffFor(seulementInstitutionnel, "BP", false))
    }

    @Test fun leTicketUtiliseLeTarifInstitutionnelDuPointInstitutionnel() {
        val o = JSONObject().put("tarifs", JSONArray().put(tariff(1000)).put(tariff(2000).put("institutionnel", true)))
        val ordinaire = assertIs<TicketOutcome.Ready>(prepare(o = o))
        val institutionnel = assertIs<TicketOutcome.Ready>(prepare(p = point().put("est_institutionnel", true), o = o))
        assertEquals(1000.0, ordinaire.ticket.subscription)
        assertEquals(2000.0, institutionnel.ticket.subscription)
    }

    @Test fun trancheEtArrondiSuperieurACentAriary() {
        // 120,67 m³ : 10 × 3 250 + 110,67 × 5 000 = 585 850 -> 585 900 (arrondi supérieur 100 Ar).
        val calc = ReadingInvoiceEngine.compute(tariff(), 120.67, 0.0, 0.0)!!
        assertEquals(0, calc.volumeAmount.compareTo(java.math.BigDecimal("585850")))
        assertEquals(0, calc.total.compareTo(java.math.BigDecimal("585900")))
    }

    @Test fun leBruitDesFlottantsNAjoutePasCentAriary() {
        // 1,3 m³ à 1 000 Ar = 1 300 Ar exact ; 112.5 - 111.2 donne 1.2999999999999972 / 1.3000000000000007 selon les cas.
        val flat = JSONObject().put("prixabonnement", 0).put("volume_minimum_facture", 0)
            .put("tranches", JSONArray().put(JSONObject().put("tranchesuperieur", 2000).put("tarif", 1000)))
        val calc = ReadingInvoiceEngine.compute(flat, 1.3000000000000007, 0.0, 0.0)!!
        assertEquals(0, calc.total.compareTo(java.math.BigDecimal("1300")))
    }

    @Test fun lesCartesSocialesSontDeduitesDuVolumeFacture() {
        val calc = ReadingInvoiceEngine.compute(tariff(), 12.0, 2.0, 0.0)!!
        assertEquals(0, calc.billedVolume.compareTo(java.math.BigDecimal("10")))
        assertEquals(0, calc.total.compareTo(java.math.BigDecimal("32500")))
    }

    @Test fun volumeMinimumFactureQuandLeVolumeEstNul() {
        val calc = ReadingInvoiceEngine.compute(tariff(subscription = 1000, minimum = 3), 0.0, 0.0, 0.0)!!
        assertEquals(0, calc.chargedVolume.compareTo(java.math.BigDecimal("3")))
        assertEquals(0, calc.total.compareTo(java.math.BigDecimal("10800"))) // 1 000 + 3 × 3 250 = 10 750
    }

    @Test fun ticketPretAvecNumeroProvisoireEtImpayes() {
        val outcome = assertIs<TicketOutcome.Ready>(prepare())
        assertEquals("T-ABCD1234", outcome.ticket.invoiceNumber)
        assertEquals("05/10/2026", outcome.ticket.date)
        assertEquals("SOAKOJA".lowercase(), outcome.ticket.organisation!!.name.lowercase())
        assertNull(outcome.ticket.organisation!!.address) // JSON null ne devient pas « null »
        assertEquals(5500.0, outcome.ticket.unpaidTotal)
        assertEquals("05/08/2026", outcome.ticket.unpaid.single().date)
        assertEquals(outcome.ticket.total, outcome.total)
    }

    @Test fun ecartSuperieurA50PourcentBloqueLAgent() {
        // moyenne 10, consommation 16 -> +60 %
        val outcome = assertIs<TicketOutcome.Blocked>(prepare(newIndex = 116.0))
        assertEquals(listOf(PrintBlock.CONSUMPTION_DEVIATION), outcome.reasons)
    }

    @Test fun exactement50PourcentNeBloquePas() {
        assertIs<TicketOutcome.Ready>(prepare(newIndex = 115.0)) // 15 vs 10 = +50 %, limite incluse
    }

    @Test fun volumeNonFactureBloqueMaisPasLesCartesSociales() {
        val blocked = assertIs<TicketOutcome.Blocked>(prepare(nonBillable = 0.5))
        assertEquals(listOf(PrintBlock.NON_BILLABLE), blocked.reasons)
        assertIs<TicketOutcome.Ready>(prepare(social = 1.0))
    }

    @Test fun leDirecteurNEstJamaisBloque() {
        assertIs<TicketOutcome.Ready>(prepare(director = true, newIndex = 160.0, nonBillable = 2.0))
    }

    @Test fun sansHistoriqueLaRegleDesCinquantePourcentNeJoueurPas() {
        assertIs<TicketOutcome.Ready>(prepare(p = point(mean = 0.0, count = 0), newIndex = 160.0))
    }

    @Test fun tourneeSansDonneesDeFacturationOuSansTarif() {
        assertTrue(prepare(p = JSONObject().put("nom", "X").put("type", "BP")) is TicketOutcome.Unavailable)
        assertTrue(prepare(o = JSONObject().put("tarifs", JSONArray())) is TicketOutcome.Unavailable)
    }
}
