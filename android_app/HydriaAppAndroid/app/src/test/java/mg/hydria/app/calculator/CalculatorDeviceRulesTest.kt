package mg.hydria.app.calculator

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CalculatorDeviceRulesTest {
    @Test fun paveReduitSurLesPetitsEcrans() {
        assertEquals(38, CalculatorDeviceRules.keyHeightDp(560))   // très petit téléphone : minimum tactile
        assertEquals(39, CalculatorDeviceRules.keyHeightDp(640))
        assertEquals(46, CalculatorDeviceRules.keyHeightDp(740))
        assertEquals(56, CalculatorDeviceRules.keyHeightDp(900))   // grand écran : taille d'origine
        // Le pavé (6 rangées) ne dépasse pas ~40 % de l'écran au-dessus du minimum
        assertTrue(CalculatorDeviceRules.keyHeightDp(740) * 6 <= 740 * 0.40)
        assertEquals(16f, CalculatorDeviceRules.keyTextSizeSp(40))
        assertEquals(18f, CalculatorDeviceRules.keyTextSizeSp(56), 0f)
    }

    @Test fun captureGpsRetientLaMeilleurePosition() {
        assertTrue(CalculatorDeviceRules.isBetter(12f, null))
        assertTrue(CalculatorDeviceRules.isBetter(12f, 30f))
        assertFalse(CalculatorDeviceRules.isBetter(40f, 30f))
        assertFalse(CalculatorDeviceRules.isFreshFix(10 * 60_000L))      // dernière position connue ancienne
        assertTrue(CalculatorDeviceRules.isFreshFix(5_000L))
        assertTrue(CalculatorDeviceRules.captureDone(15f, 2_000L))      // précision atteinte
        assertFalse(CalculatorDeviceRules.captureDone(60f, 10_000L))    // on attend mieux
        assertTrue(CalculatorDeviceRules.captureDone(60f, 31_000L))     // délai écoulé : meilleure position
        assertFalse(CalculatorDeviceRules.captureDone(null, 31_000L))   // aucune position
    }
}
