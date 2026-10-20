package mg.hydria.app.readings

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Détection du clavier par variation de hauteur (masquage de l'en-tête et des onglets, L2-1). */
class ReadingKeyboardRulesTest {
    // Téléphone 411 dp x 891 dp, densité 2,625 : 2339 px de haut.
    private val density = 2.625f
    private val total = 2339

    @Test fun windowFullyVisibleMeansClosed() {
        assertFalse(ReadingKeyboardRules.isOpen(total, total, density))
    }

    @Test fun threeButtonNavigationBarIsNotAKeyboard() {
        // 48 dp de barre de navigation = 126 px : en dessous du seuil de 315 px (120 dp).
        assertFalse(ReadingKeyboardRules.isOpen(total, total - (48 * density).toInt(), density))
    }

    @Test fun numericKeyboardOfAboutTwoHundredAndFiftyDpIsOpen() {
        assertTrue(ReadingKeyboardRules.isOpen(total, total - (250 * density).toInt(), density))
    }

    @Test fun hiddenHeightEqualToThresholdIsStillClosed() {
        val threshold = maxOf((ReadingKeyboardRules.MIN_HIDDEN_DP * density).toInt(), total * ReadingKeyboardRules.MIN_HIDDEN_PERCENT / 100)
        assertFalse(ReadingKeyboardRules.isOpen(total, total - threshold, density))
        assertTrue(ReadingKeyboardRules.isOpen(total, total - threshold - 1, density))
    }

    @Test fun bothConditionsMustHold() {
        // Petit écran : 640 dp de haut, 15 % = 96 dp, le seuil de 120 dp l'emporte.
        val small = (640 * density).toInt()
        assertFalse(ReadingKeyboardRules.isOpen(small, small - (110 * density).toInt(), density))
        assertTrue(ReadingKeyboardRules.isOpen(small, small - (130 * density).toInt(), density))
        // Tablette : 1600 dp de haut, 15 % = 240 dp, le pourcentage l'emporte sur 120 dp.
        val tablet = (1600 * density).toInt()
        assertFalse(ReadingKeyboardRules.isOpen(tablet, tablet - (200 * density).toInt(), density))
        assertTrue(ReadingKeyboardRules.isOpen(tablet, tablet - (300 * density).toInt(), density))
    }

    @Test fun zeroHeightWindowIsNeverOpen() {
        assertFalse(ReadingKeyboardRules.isOpen(0, 0, density))
        assertFalse(ReadingKeyboardRules.isOpen(-5, 100, density))
    }
}
