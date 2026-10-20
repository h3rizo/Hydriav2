package mg.hydria.compta.engine

import mg.hydria.compta.core.Ariary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EquilibrageTest {

    private fun d(ariary: Int) = Ariary.fromAriary(ariary)

    @Test
    fun `piece equilibree acceptee`() {
        val rapport = Equilibrage.verifier(
            listOf(
                Equilibrage.LigneInput("606100", debit = d(120_000)),
                Equilibrage.LigneInput("512000", credit = d(120_000)),
            )
        )
        assertTrue(rapport.equilibree)
        assertTrue(rapport.erreurs.isEmpty())
        assertEquals(0L, rapport.ecart.centimes)
    }

    @Test
    fun `piece desequilibree refusee`() {
        val rapport = Equilibrage.verifier(
            listOf(
                Equilibrage.LigneInput("606100", debit = d(120_000)),
                Equilibrage.LigneInput("512000", credit = d(119_000)),
            )
        )
        assertFalse(rapport.equilibree)
        assertEquals(1_000_00L, rapport.ecart.centimes)
    }

    @Test
    fun `ligne unique refusee`() {
        val rapport = Equilibrage.verifier(listOf(Equilibrage.LigneInput("606100", debit = d(1000))))
        assertFalse(rapport.equilibree)
        assertTrue(rapport.erreurs.any { it.contains("au moins deux lignes") })
    }

    @Test
    fun `debit et credit simultanes refuses`() {
        val rapport = Equilibrage.verifier(
            listOf(
                Equilibrage.LigneInput("606100", debit = d(1000), credit = d(1000)),
                Equilibrage.LigneInput("512000", credit = d(1000)),
            )
        )
        assertFalse(rapport.equilibree)
    }

    @Test
    fun `tolerance arrondi 1 centime`() {
        val rapport = Equilibrage.verifier(
            listOf(
                Equilibrage.LigneInput("606100", debit = Ariary(12_000_001L)),
                Equilibrage.LigneInput("512000", credit = Ariary(12_000_000L)),
            )
        )
        assertTrue(rapport.equilibree)
    }
}
