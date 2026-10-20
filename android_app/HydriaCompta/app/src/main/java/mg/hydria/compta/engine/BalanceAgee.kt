package mg.hydria.compta.engine

import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.sum
import java.time.LocalDate
import java.time.temporal.ChronoUnit

/** Ventilation des créances par ancienneté, calculée en local. */
object BalanceAgee {

    enum class Tranche(val label: String) {
        NON_ECHU("Non échu"),
        J_0_30("0–30 j"),
        J_31_60("31–60 j"),
        J_61_90("61–90 j"),
        PLUS_90("> 90 j"),
    }

    data class Poste(
        val tiersId: String,
        val montantDu: Ariary,
        val dateEcheance: LocalDate,
    )

    data class LigneBalance(
        val tiersId: String,
        val parTranche: Map<Tranche, Ariary>,
        val total: Ariary,
    )

    fun calculer(postes: List<Poste>, dateReference: LocalDate = LocalDate.now()): List<LigneBalance> =
        postes.groupBy { it.tiersId }.map { (tiersId, group) ->
            val parTranche = Tranche.entries.associateWith { Ariary.ZERO }.toMutableMap()
            group.forEach { poste ->
                val tranche = trancheDe(poste.dateEcheance, dateReference)
                parTranche[tranche] = parTranche.getValue(tranche) + poste.montantDu
            }
            LigneBalance(tiersId, parTranche, group.map { it.montantDu }.sum())
        }

    private fun trancheDe(echeance: LocalDate, reference: LocalDate): Tranche {
        if (!echeance.isBefore(reference)) return Tranche.NON_ECHU
        val retard = ChronoUnit.DAYS.between(echeance, reference)
        return when {
            retard <= 30 -> Tranche.J_0_30
            retard <= 60 -> Tranche.J_31_60
            retard <= 90 -> Tranche.J_61_90
            else -> Tranche.PLUS_90
        }
    }
}
