package mg.hydria.app.readings

/**
 * Détection du clavier à l'écran par variation de hauteur de la fenêtre. minSdk est 26 : sous Android 11,
 * WindowInsets.isVisible(ime()) n'est pas fiable, alors qu'une fenêtre qui se redimensionne sous le clavier
 * (adjustResize) laisse toujours un rectangle visible plus court que la fenêtre.
 *
 * Utilisée par MainActivity pour masquer l'en-tête et la barre d'onglets du téléphone tant que le clavier
 * est ouvert sur le formulaire de relevé d'une campagne (décision 5 ter n°5).
 */
object ReadingKeyboardRules {
    /** Hauteur masquée minimale, en dp : plus que la barre de navigation à trois boutons (48 dp). */
    const val MIN_HIDDEN_DP = 120

    /** Part minimale de la fenêtre masquée, en pour cent, pour les grands écrans. */
    const val MIN_HIDDEN_PERCENT = 15

    /**
     * Vrai si le clavier est ouvert : la partie de la fenêtre qui n'est pas visible dépasse
     * [MIN_HIDDEN_DP] dp ET [MIN_HIDDEN_PERCENT] % de la hauteur totale.
     *
     * @param totalHeightPx hauteur totale de la fenêtre (vue racine de la fenêtre)
     * @param visibleBottomPx bas du rectangle visible (getWindowVisibleDisplayFrame)
     * @param density densité d'écran (dp -> px)
     */
    fun isOpen(totalHeightPx: Int, visibleBottomPx: Int, density: Float): Boolean {
        if (totalHeightPx <= 0) return false
        val hiddenPx = totalHeightPx - visibleBottomPx
        val thresholdPx = maxOf((MIN_HIDDEN_DP * density).toInt(), totalHeightPx * MIN_HIDDEN_PERCENT / 100)
        return hiddenPx > thresholdPx
    }
}
