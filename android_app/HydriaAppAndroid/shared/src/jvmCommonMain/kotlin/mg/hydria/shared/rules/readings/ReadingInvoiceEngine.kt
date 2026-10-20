package mg.hydria.shared.rules.readings

import org.json.JSONObject
import java.math.BigDecimal
import java.math.RoundingMode

data class InvoiceCalculation(
    val subscription: BigDecimal,
    val billedVolume: BigDecimal,
    val chargedVolume: BigDecimal,
    val volumeAmount: BigDecimal,
    val total: BigDecimal,
    val communalTax: BigDecimal,
)

/**
 * Moteur tarifaire hors ligne : miroir de billing.views_facturation.calculer_montant_releve
 * (abonnement + volume minimum + tranches + arrondi supérieur à 100 Ar). Calcul en
 * BigDecimal comme le Decimal serveur, pour que l'arrondi tombe pareil. Au moment de la
 * synchronisation, le serveur recalcule et fait foi.
 *
 * Tarif attendu (`ouvrage.tarifs[]` de la tournée) :
 * `prixabonnement`, `volume_minimum_facture`, `tranches[]{tranchesuperieur, tarif}`,
 * `institutionnel` (absent = tarif ordinaire).
 */
object ReadingInvoiceEngine {
    private val HUNDRED = BigDecimal(100)

    /**
     * Même choix que le serveur : un branchement institutionnel prend d'abord le tarif institutionnel
     * de son type, à défaut le tarif ordinaire ; un point ordinaire n'utilise jamais le tarif institutionnel.
     */
    fun tariffFor(ouvrage: JSONObject, pointType: String, institutional: Boolean = false): JSONObject? {
        val tariffs = ouvrage.optJSONArray("tarifs") ?: return null
        val ofType = (0 until tariffs.length()).map { tariffs.getJSONObject(it) }
            .filter { it.optString("type_point_eau") == pointType }
        val ordinary = ofType.firstOrNull { !it.optBoolean("institutionnel", false) }
        return if (institutional) ofType.firstOrNull { it.optBoolean("institutionnel", false) } ?: ordinary else ordinary
    }

    /** null si le tarif n'a aucune tranche alors qu'il y a du volume à facturer (erreur serveur équivalente). */
    fun compute(tariff: JSONObject, consumption: Double, socialCards: Double, nonBillable: Double): InvoiceCalculation? {
        val subscription = decimal(tariff.opt("prixabonnement"))
        val minimum = decimal(tariff.opt("volume_minimum_facture"))
        // Bruit des flottants (newIndex - oldIndex = 1.3000000000000007) : sans nettoyage, un montant
        // exact multiple de 100 Ar passerait à la centaine suivante. Même règle que le serveur (3 décimales).
        val billed = (clean(consumption) - clean(socialCards) - clean(nonBillable)).max(BigDecimal.ZERO)
        val charged = when {
            billed <= BigDecimal.ZERO -> if (minimum > BigDecimal.ZERO) minimum else BigDecimal.ZERO
            else -> billed.max(minimum)
        }
        val tranchesJson = tariff.optJSONArray("tranches")
        val tranches = (0 until (tranchesJson?.length() ?: 0)).map { tranchesJson!!.getJSONObject(it) }
            .map { decimal(it.opt("tranchesuperieur")) to decimal(it.opt("tarif")) }
            .sortedBy { it.first }
        if (charged > BigDecimal.ZERO && tranches.isEmpty()) return null

        var amount = BigDecimal.ZERO
        var remaining = charged
        var lower = BigDecimal.ZERO
        for ((upper, price) in tranches) {
            val inTranche = remaining.min(upper - lower)
            if (inTranche > BigDecimal.ZERO) {
                amount += inTranche * price
                remaining -= inTranche
                lower = upper
            }
            if (remaining <= BigDecimal.ZERO) break
        }
        // Au-delà de la dernière tranche : dernier tarif.
        if (remaining > BigDecimal.ZERO && tranches.isNotEmpty()) amount += remaining * tranches.last().second

        val excludingTax = subscription + amount
        val rounded = excludingTax.divide(HUNDRED, 0, RoundingMode.CEILING) * HUNDRED
        return InvoiceCalculation(
            subscription = subscription, billedVolume = billed, chargedVolume = charged,
            volumeAmount = amount, total = rounded, communalTax = excludingTax * BigDecimal("0.07"),
        )
    }

    private fun clean(volume: Double): BigDecimal = decimal(volume).setScale(3, RoundingMode.HALF_UP)

    private fun decimal(value: Any?): BigDecimal = when (value) {
        null, JSONObject.NULL -> BigDecimal.ZERO
        is Number -> BigDecimal(value.toString())
        else -> value.toString().toBigDecimalOrNull() ?: BigDecimal.ZERO
    }
}
