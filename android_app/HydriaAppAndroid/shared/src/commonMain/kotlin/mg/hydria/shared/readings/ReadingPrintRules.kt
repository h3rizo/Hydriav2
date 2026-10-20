package mg.hydria.shared.readings

import kotlin.math.abs

enum class PrintBlock { CONSUMPTION_DEVIATION, NON_BILLABLE }

/**
 * Qui peut imprimer la facture sur place. Miroir de
 * billing.views_releves._motifs_blocage_impression : le serveur re-contrôle à la
 * synchronisation, mais l'agent doit le savoir avant d'imprimer, même sans réseau.
 */
object ReadingPrintRules {
    /** Écart relatif maximal à la moyenne des relevés précédents (±50 %). */
    const val DEVIATION_LIMIT = 0.5

    fun deviation(consumption: Double, mean: Double, previousCount: Int): Double? =
        if (previousCount > 0 && mean > 0) abs(consumption - mean) / mean else null

    /** Vide = impression autorisée. Le Directeur n'est jamais bloqué. */
    fun blocks(consumption: Double, mean: Double, previousCount: Int, nonBillable: Double, isDirector: Boolean): List<PrintBlock> {
        if (isDirector) return emptyList()
        return buildList {
            if ((deviation(consumption, mean, previousCount) ?: 0.0) > DEVIATION_LIMIT) add(PrintBlock.CONSUMPTION_DEVIATION)
            // Les cartes sociales ne comptent pas : seul le volume non facturé saisi bloque.
            if (nonBillable != 0.0) add(PrintBlock.NON_BILLABLE)
        }
    }
}
