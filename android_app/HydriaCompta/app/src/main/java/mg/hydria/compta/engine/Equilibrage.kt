package mg.hydria.compta.engine

import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.Sens
import mg.hydria.compta.core.sum

/**
 * Contrôle d'équilibre débit / crédit d'une pièce comptable, exécuté entièrement
 * en local. Aucune dépendance Android : testable en JVM pur.
 */
object Equilibrage {

    data class LigneInput(
        val compteNumero: String,
        val debit: Ariary = Ariary.ZERO,
        val credit: Ariary = Ariary.ZERO,
    )

    data class Rapport(
        val totalDebit: Ariary,
        val totalCredit: Ariary,
        val equilibree: Boolean,
        val erreurs: List<String>,
    ) {
        val ecart: Ariary get() = totalDebit - totalCredit
    }

    /** Tolérance d'arrondi : 1 centième d'Ariary. */
    private const val TOLERANCE_CENTIMES = 1L

    fun verifier(lignes: List<LigneInput>): Rapport {
        val erreurs = mutableListOf<String>()

        if (lignes.size < 2) {
            erreurs += "Une pièce doit comporter au moins deux lignes."
        }
        lignes.forEachIndexed { index, ligne ->
            val position = index + 1
            if (ligne.compteNumero.isBlank()) {
                erreurs += "Ligne $position : compte non renseigné."
            }
            if (ligne.debit.isNegative || ligne.credit.isNegative) {
                erreurs += "Ligne $position : montant négatif interdit."
            }
            if (!ligne.debit.isZero && !ligne.credit.isZero) {
                erreurs += "Ligne $position : débit et crédit renseignés simultanément."
            }
            if (ligne.debit.isZero && ligne.credit.isZero) {
                erreurs += "Ligne $position : ni débit ni crédit."
            }
        }

        val totalDebit = lignes.map { it.debit }.sum()
        val totalCredit = lignes.map { it.credit }.sum()
        val ecart = totalDebit - totalCredit
        val equilibree = erreurs.isEmpty() && kotlin.math.abs(ecart.centimes) <= TOLERANCE_CENTIMES

        if (erreurs.isEmpty() && !equilibree) {
            erreurs += "Pièce déséquilibrée : écart de ${ecart.format()}."
        }

        return Rapport(totalDebit, totalCredit, equilibree, erreurs)
    }

    /** Somme d'un sens donné — utilitaire pour l'affichage de la saisie. */
    fun total(lignes: List<LigneInput>, sens: Sens): Ariary =
        when (sens) {
            Sens.DEBIT -> lignes.map { it.debit }.sum()
            Sens.CREDIT -> lignes.map { it.credit }.sum()
        }
}
