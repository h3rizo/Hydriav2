package mg.hydria.shared.rules.readings

import mg.hydria.shared.readings.PrintBlock
import mg.hydria.shared.readings.ReadingPrintRules
import mg.hydria.shared.readings.ReadingTicket
import mg.hydria.shared.readings.TicketOrganisation
import mg.hydria.shared.readings.TicketUnpaid
import org.json.JSONObject

sealed interface TicketOutcome {
    /** Ticket prêt ; [total] est le montant à enregistrer avec le relevé. */
    data class Ready(val ticket: ReadingTicket, val total: Double) : TicketOutcome
    data class Blocked(val reasons: List<PrintBlock>, val deviationPercent: Double?, val mean: Double) : TicketOutcome
    /** Données de facturation absentes de la tournée préchargée (ancienne synchronisation, tarif manquant...). */
    data class Unavailable(val message: String) : TicketOutcome
}

/**
 * Prépare le ticket 80 mm d'un relevé entièrement à partir de la tournée préchargée
 * (point d'eau + ouvrage) : fonctionne sans réseau. Le numéro imprimé est provisoire
 * (`T-` + 8 premiers caractères du local_uuid) ; le serveur attribue le numéro officiel
 * à la synchronisation et conserve ce repère dans la remarque du relevé.
 */
object ReadingTicketGateway {
    fun provisionalNumber(localUuid: String): String = "T-" + localUuid.replace("-", "").take(8).uppercase()

    fun prepare(
        point: JSONObject, ouvrage: JSONObject, isDirector: Boolean,
        newIndex: Double, oldIndex: Double, socialVolume: Double, nonBillable: Double,
        dateIso: String, localUuid: String,
    ): TicketOutcome {
        if (!point.has("moyenne_consommation") || !point.has("impayes")) {
            return TicketOutcome.Unavailable("Données de facturation absentes : synchronisez la tournée une fois en ligne, puis réessayez.")
        }
        val consumption = newIndex - oldIndex
        val mean = point.optDouble("moyenne_consommation", 0.0)
        val blocks = ReadingPrintRules.blocks(consumption, mean, point.optInt("nb_releves_precedents", 0), nonBillable, isDirector)
        if (blocks.isNotEmpty()) {
            val deviation = ReadingPrintRules.deviation(consumption, mean, point.optInt("nb_releves_precedents", 0))
            return TicketOutcome.Blocked(blocks, deviation?.let { it * 100 }, mean)
        }

        val pointType = point.optString("type")
        val tariff = ReadingInvoiceEngine.tariffFor(ouvrage, pointType, point.optBoolean("est_institutionnel", false))
            ?: return TicketOutcome.Unavailable("Aucun tarif préchargé pour « $pointType » : impression impossible, enregistrez sans imprimer.")
        val calculation = ReadingInvoiceEngine.compute(tariff, consumption, socialVolume, nonBillable)
            ?: return TicketOutcome.Unavailable("Tarif sans tranche : impression impossible, enregistrez sans imprimer.")

        val unpaidJson = point.optJSONArray("impayes")
        val unpaid = (0 until (unpaidJson?.length() ?: 0)).map { unpaidJson!!.getJSONObject(it) }.map {
            TicketUnpaid(displayDate(it.optString("date_releve")), it.optDouble("volume_facture", 0.0), it.optDouble("montant", 0.0))
        }
        val total = calculation.total.toDouble()
        return TicketOutcome.Ready(
            ReadingTicket(
                organisation = ouvrage.optJSONObject("organisation")?.let(::organisation),
                invoiceNumber = provisionalNumber(localUuid),
                date = displayDate(dateIso),
                pointName = point.optString("nom").trim().takeUnless { it.isBlank() || it == "N/A" } ?: "Abonné non renseigné",
                pointCode = text(point, "code") ?: text(point, "idxls").orEmpty(),
                pointType = pointType.takeUnless { it.isBlank() || it == "N/A" },
                oldIndex = oldIndex, newIndex = newIndex, consumption = consumption,
                socialCardsVolume = socialVolume, nonBillable = nonBillable,
                billedVolume = calculation.billedVolume.toDouble(),
                subscription = calculation.subscription.toDouble(),
                volumeAmount = calculation.volumeAmount.toDouble(),
                total = total, unpaid = unpaid, unpaidTotal = unpaid.sumOf { it.amount },
            ),
            total,
        )
    }

    private fun organisation(json: JSONObject) = TicketOrganisation(
        name = text(json, "nom").orEmpty(), address = text(json, "adresse1"), locality = text(json, "localite"),
        province = text(json, "province"), phone = text(json, "telephone"), nif = text(json, "nif"), stat = text(json, "stat"),
    )

    /** `optString` renvoie « null » pour un JSON null : on filtre explicitement. */
    private fun text(json: JSONObject, key: String): String? =
        if (json.isNull(key)) null else json.optString(key).trim().takeIf { it.isNotEmpty() }

    /** `2026-10-05` ou `2026-10-05T00:00:00+03:00` -> `05/10/2026`. */
    private fun displayDate(iso: String): String {
        val parts = iso.take(10).split('-')
        return if (parts.size == 3) "${parts[2]}/${parts[1]}/${parts[0]}" else iso
    }
}
