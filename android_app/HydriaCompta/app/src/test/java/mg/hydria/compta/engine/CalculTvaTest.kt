package mg.hydria.compta.engine

import mg.hydria.compta.core.Ariary
import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

class CalculTvaTest {

    private fun ariary(v: Int) = Ariary.fromAriary(v)

    @Test
    fun `tva standard 20 pourcent`() {
        val facture = CalculTva.calculer(
            listOf(
                CalculTva.LigneInput(
                    designation = "Prestation",
                    quantite = BigDecimal("2"),
                    prixUnitaire = ariary(50_000),
                )
            )
        )
        assertEquals(ariary(100_000), facture.totalHt)
        assertEquals(ariary(20_000), facture.totalTva)
        assertEquals(ariary(120_000), facture.totalTtc)
    }

    @Test
    fun `ligne exoneree sans tva`() {
        val facture = CalculTva.calculer(
            listOf(
                CalculTva.LigneInput(
                    designation = "Produit exonéré",
                    quantite = BigDecimal.ONE,
                    prixUnitaire = ariary(80_000),
                    tauxTva = CalculTva.TAUX_EXONERE,
                )
            )
        )
        assertEquals(ariary(80_000), facture.totalHt)
        assertEquals(Ariary.ZERO, facture.totalTva)
    }

    @Test
    fun `remise ligne et remise globale cumulees`() {
        val facture = CalculTva.calculer(
            lignes = listOf(
                CalculTva.LigneInput(
                    designation = "Article",
                    quantite = BigDecimal.ONE,
                    prixUnitaire = ariary(100_000),
                    remisePct = BigDecimal("10"), // -> 90 000
                )
            ),
            remiseGlobalePct = BigDecimal("5"), // -> 85 500
        )
        assertEquals(ariary(85_500), facture.totalHt)
    }

    @Test
    fun `taxe communale 7 pourcent indicative non ajoutee au total`() {
        val facture = CalculTva.calculer(
            listOf(
                CalculTva.LigneInput("Eau", BigDecimal.ONE, ariary(100_000), tauxTva = CalculTva.TAUX_EXONERE)
            )
        )
        assertEquals(ariary(7_000), facture.taxeCommunaleIndicative)
        assertEquals(ariary(100_000), facture.totalTtc) // taxe NON incluse
    }
}
