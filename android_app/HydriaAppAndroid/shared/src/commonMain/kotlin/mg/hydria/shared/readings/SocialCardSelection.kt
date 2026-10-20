package mg.hydria.shared.readings

data class SocialCardQuantity(val id: String, val quantity: Int)
data class SocialCardConsumption(val id: String, val quantity: Int, val volume: Double)
enum class SocialCardError { UNLINKED_OR_DUPLICATE_CARD, INVALID_QUANTITY }
data class SocialCardPreparation(val error: SocialCardError?, val cards: List<SocialCardConsumption>) {
    val totalVolume: Double get() = cards.sumOf { it.volume }
}

/** Le relevé référence exclusivement des cartes existantes du point sélectionné. */
object SocialCardSelection {
    fun prepare(selected: List<SocialCardQuantity>, linkedIds: Set<String>): SocialCardPreparation {
        if (!validIds(selected.map { it.id }, linkedIds))
            return SocialCardPreparation(SocialCardError.UNLINKED_OR_DUPLICATE_CARD, emptyList())
        if (selected.any { it.quantity !in 0..30 })
            return SocialCardPreparation(SocialCardError.INVALID_QUANTITY, emptyList())
        return SocialCardPreparation(null, selected.filter { it.quantity > 0 }.map {
            SocialCardConsumption(it.id, it.quantity, ReadingValidation.socialCardVolume(it.quantity))
        })
    }

    fun validIds(selectedIds: List<String>, linkedIds: Set<String>): Boolean =
        selectedIds.all { it.isNotBlank() && it in linkedIds } && selectedIds.distinct().size == selectedIds.size
}
