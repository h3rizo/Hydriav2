package mg.hydria.app

import mg.hydria.shared.rules.forms.AutocompleteMatch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AutocompleteMatchTest {
    private val ouvrages = listOf("Ambanja BP", "Ambatofanahazana Ouest PPMH", "Vohipeno", "Anjohy AEPG", "Ampétsapetsa PPMH2")

    @Test fun rechercheSansAccentNiCasseNImporteOuDansLeNom() {
        assertTrue(AutocompleteMatch.matches("Ampétsapetsa PPMH2", "ampets"))
        assertTrue(AutocompleteMatch.matches("Ampétsapetsa PPMH2", "PPMH2"))
        assertTrue(AutocompleteMatch.matches("Ambanja BP", "amb bp"))
        assertFalse(AutocompleteMatch.matches("Vohipeno", "amb"))
    }

    @Test fun lesNomsQuiCommencentParLaSaisieSontProposesEnPremier() {
        assertEquals(listOf(0, 1), AutocompleteMatch.filter(ouvrages, "amba"))
        // « ohy » est au milieu de « Anjohy » seulement
        assertEquals(listOf(3), AutocompleteMatch.filter(ouvrages, "ohy"))
        // « pp » : Ampétsapetsa ne commence pas par « pp » ; Ambatofanahazana non plus -> ordre d'origine
        assertEquals(listOf(1, 4), AutocompleteMatch.filter(ouvrages, "ppmh"))
        assertEquals(ouvrages.indices.toList(), AutocompleteMatch.filter(ouvrages, ""))
    }
}
