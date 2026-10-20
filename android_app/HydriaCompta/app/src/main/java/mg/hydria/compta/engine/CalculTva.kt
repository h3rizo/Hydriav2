package mg.hydria.compta.engine

import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.sum
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Calcul de facture avec TVA et remises, en local.
 *
 * La taxe communale (7 %) reste indicative et n'est PAS ajoutée au total —
 * comportement aligné sur le workflow de facturation Django existant.
 */
object CalculTva {

    /** Taux standard Madagascar. `BigDecimal("0")` pour une ligne exonérée. */
    val TAUX_STANDARD: BigDecimal = BigDecimal("0.20")
    val TAUX_EXONERE: BigDecimal = BigDecimal.ZERO
    private val TAUX_TAXE_COMMUNALE: BigDecimal = BigDecimal("0.07")

    data class LigneInput(
        val designation: String,
        val quantite: BigDecimal,
        val prixUnitaire: Ariary,
        /** Remise ligne en pourcentage (0..100). */
        val remisePct: BigDecimal = BigDecimal.ZERO,
        val tauxTva: BigDecimal = TAUX_STANDARD,
    )

    data class LigneCalculee(
        val designation: String,
        val montantHt: Ariary,
        val montantTva: Ariary,
        val montantTtc: Ariary,
        val tauxTva: BigDecimal,
    )

    data class Facture(
        val lignes: List<LigneCalculee>,
        val totalHt: Ariary,
        val totalTva: Ariary,
        val totalTtc: Ariary,
        /** Indicatif seulement — pour information de l'usager. */
        val taxeCommunaleIndicative: Ariary,
    )

    fun calculer(
        lignes: List<LigneInput>,
        remiseGlobalePct: BigDecimal = BigDecimal.ZERO,
    ): Facture {
        val lignesHt = lignes.map { ligne ->
            val brut = ligne.prixUnitaire * ligne.quantite
            val apresRemiseLigne = brut * pourcentageRestant(ligne.remisePct)
            val apresRemiseGlobale = apresRemiseLigne * pourcentageRestant(remiseGlobalePct)
            apresRemiseGlobale to ligne
        }

        val lignesCalculees = lignesHt.map { (ht, source) ->
            val tva = ht * source.tauxTva
            LigneCalculee(
                designation = source.designation,
                montantHt = ht,
                montantTva = tva,
                montantTtc = ht + tva,
                tauxTva = source.tauxTva,
            )
        }

        val totalHt = lignesCalculees.map { it.montantHt }.sum()
        val totalTva = lignesCalculees.map { it.montantTva }.sum()
        return Facture(
            lignes = lignesCalculees,
            totalHt = totalHt,
            totalTva = totalTva,
            totalTtc = totalHt + totalTva,
            taxeCommunaleIndicative = totalHt * TAUX_TAXE_COMMUNALE,
        )
    }

    private fun pourcentageRestant(pct: BigDecimal): BigDecimal =
        BigDecimal.ONE - pct.divide(BigDecimal(100), 6, RoundingMode.HALF_UP)
}
