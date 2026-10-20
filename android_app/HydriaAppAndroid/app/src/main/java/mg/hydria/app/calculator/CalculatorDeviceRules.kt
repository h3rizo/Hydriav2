package mg.hydria.app.calculator

/** Règles d'adaptation de la calculatrice avancée au téléphone (taille d'écran, GPS). */
object CalculatorDeviceRules {
    /** Rangées du pavé : 5 rangées de touches + « = Ligne suivante ». */
    private const val KEYPAD_ROWS = 6

    /**
     * Hauteur d'une touche (dp) selon la hauteur d'écran : le pavé occupe au plus ~40 %
     * de l'écran, pour que les lignes de calcul restent visibles sur les petits téléphones.
     * 56 dp (taille d'origine) sur les grands écrans, jamais moins de 38 dp (cible tactile).
     */
    fun keyHeightDp(screenHeightDp: Int): Int =
        ((screenHeightDp * 0.40f - 20f) / KEYPAD_ROWS).toInt().coerceIn(38, 56)

    /** Taille du texte des touches, réduite avec la touche. */
    fun keyTextSizeSp(keyHeightDp: Int): Float = if (keyHeightDp < 46) 16f else 18f

    /** Précision visée pour la position du téléphone (mètres). */
    const val GPS_TARGET_ACCURACY_M = 20f

    /** Au-delà, on retient la meilleure position obtenue plutôt que d'attendre indéfiniment. */
    const val GPS_MAX_WAIT_MS = 30_000L

    /** Une position mémorisée plus ancienne que ça n'est pas celle d'ici et maintenant. */
    const val GPS_MAX_FIX_AGE_MS = 120_000L

    fun isFreshFix(fixAgeMs: Long): Boolean = fixAgeMs in 0..GPS_MAX_FIX_AGE_MS

    /** La nouvelle position est-elle meilleure (plus précise) que celle retenue ? */
    fun isBetter(candidateAccuracyM: Float?, bestAccuracyM: Float?): Boolean =
        bestAccuracyM == null || (candidateAccuracyM ?: Float.MAX_VALUE) < bestAccuracyM

    /** Arrêter la recherche : précision atteinte, ou délai écoulé avec au moins une position. */
    fun captureDone(bestAccuracyM: Float?, elapsedMs: Long): Boolean =
        bestAccuracyM != null && (bestAccuracyM <= GPS_TARGET_ACCURACY_M || elapsedMs >= GPS_MAX_WAIT_MS)
}
