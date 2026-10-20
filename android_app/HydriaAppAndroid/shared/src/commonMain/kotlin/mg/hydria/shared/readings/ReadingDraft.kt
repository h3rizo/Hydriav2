package mg.hydria.shared.readings

import kotlin.time.Duration
import kotlin.time.Duration.Companion.days
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Carte sociale d'un formulaire de relevé : identifiant de la carte et nombre de bidons saisis. */
@Serializable
data class ReadingDraftCard(val id: String, val bidons: Int)

/**
 * Signature d'un formulaire de relevé (index, remarque, volume non facturé, cartes sociales), pour savoir
 * si l'agent a saisi quelque chose par rapport à l'état initial du point. Extraite de `readingFormSignature`
 * de MainActivity, avec la même normalisation :
 *  - index : espaces de bord ignorés, virgule = point ;
 *  - remarque : espaces de bord ignorés ;
 *  - volume non facturé : vide, « 0 », « 0,00 » et « 0.00 » donnent la même clé ; une valeur illisible garde
 *    son texte (elle reste détectée comme modifiée) ;
 *  - cartes : « id:bidons », l'ordre n'a pas d'effet.
 */
object ReadingFormSignature {
    fun of(index: String, remark: String, nonBillable: String, cards: List<ReadingDraftCard>): List<String> {
        val nonBillableText = nonBillable.trim().replace(',', '.')
        val nonBillableKey = if (nonBillableText.isEmpty()) 0.0.toString()
        else nonBillableText.toDoubleOrNull()?.toString() ?: nonBillableText
        return listOf(
            index.trim().replace(',', '.'),
            remark.trim(),
            nonBillableKey,
            cards.map { "${it.id}:${it.bidons}" }.sorted().joinToString(","),
        )
    }
}

/**
 * Brouillon d'un point : ce que l'agent a tapé et n'a pas enregistré. Les textes sont gardés tels que saisis
 * (virgule comprise) pour être remis tels quels dans les champs ; [savedAtMillis] est l'heure d'enregistrement
 * du brouillon (millisecondes epoch, horloge passée par l'appelant).
 */
@Serializable
data class ReadingDraft(
    val pointId: String,
    val index: String = "",
    val remark: String = "",
    val nonBillable: String = "",
    val cards: List<ReadingDraftCard> = emptyList(),
    val savedAtMillis: Long = 0L,
) {
    fun signature(): List<String> = ReadingFormSignature.of(index, remark, nonBillable, cards)

    /** Cartes du brouillon encore rattachées au point : une carte retirée entre-temps est ignorée. */
    fun cardsAmong(linkedCardIds: Set<String>): List<ReadingDraftCard> = cards.filter { it.id in linkedCardIds }
}

@Serializable
private data class ReadingDraftBookData(val campaignKey: String = "", val drafts: List<ReadingDraft> = emptyList())

/**
 * Brouillons d'une campagne de relevés : un par point, clé de campagne « ouvrage|date » (voir [key]).
 * Un brouillon identique à l'état initial du point n'est jamais gardé. Il vit au plus [MAX_AGE] ; les points
 * qui n'existent plus dans la campagne sont purgés. L'horloge est toujours passée en paramètre (testable).
 * Le livre s'écrit en JSON ([toJson]) et se relit sans exception : un JSON illisible donne un livre vide.
 */
class ReadingDraftBook(val campaignKey: String) {
    private val byPoint = LinkedHashMap<String, ReadingDraft>()

    val size: Int get() = byPoint.size
    fun isEmpty(): Boolean = byPoint.isEmpty()
    fun pointIds(): Set<String> = byPoint.keys.toSet()
    fun get(pointId: String): ReadingDraft? = byPoint[pointId]
    fun contains(pointId: String): Boolean = pointId in byPoint

    /**
     * Garde la saisie du point, sauf si elle est identique à l'état initial [baseline] (signature de
     * [ReadingFormSignature.of] à l'ouverture du point) : le brouillon existant est alors supprimé.
     * Retourne true si un brouillon est gardé après l'appel.
     */
    fun put(
        pointId: String,
        index: String,
        remark: String,
        nonBillable: String,
        cards: List<ReadingDraftCard>,
        baseline: List<String>,
        nowMillis: Long,
    ): Boolean {
        if (pointId.isBlank()) return false
        val draft = ReadingDraft(pointId, index, remark, nonBillable, cards, nowMillis)
        if (draft.signature() == baseline) {
            byPoint.remove(pointId)
            return false
        }
        byPoint[pointId] = draft
        return true
    }

    fun remove(pointId: String): Boolean = byPoint.remove(pointId) != null

    fun clear() = byPoint.clear()

    /**
     * Retire les brouillons plus vieux que [MAX_AGE] et, si [knownPointIds] est donné, ceux d'un point qui
     * n'est plus dans la campagne (point relevé entre-temps, masqué ou retiré). Retourne le nombre retiré.
     */
    fun purge(nowMillis: Long, knownPointIds: Set<String>? = null): Int {
        val before = byPoint.size
        val maxAgeMillis = MAX_AGE.inWholeMilliseconds
        byPoint.entries.removeAll { (id, draft) ->
            nowMillis - draft.savedAtMillis > maxAgeMillis || (knownPointIds != null && id !in knownPointIds)
        }
        return before - byPoint.size
    }

    fun toJson(): String = json.encodeToString(ReadingDraftBookData(campaignKey, byPoint.values.toList()))

    companion object {
        /** Durée de vie maximale d'un brouillon non repris (décision 5 ter n°4). Valeur unique. */
        val MAX_AGE: Duration = 3.days

        private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

        /** Clé de campagne : un brouillon n'est repris que dans la même campagne (même ouvrage, même date). */
        fun key(ouvrageId: String, dateIso: String): String = "$ouvrageId|$dateIso"

        /**
         * Relit un livre. JSON absent, illisible, ou écrit pour une autre campagne = livre vide. Les brouillons
         * trop vieux et, si [knownPointIds] est donné, ceux des points inconnus sont purgés dès la lecture.
         */
        fun fromJson(campaignKey: String, text: String?, nowMillis: Long, knownPointIds: Set<String>? = null): ReadingDraftBook {
            val book = ReadingDraftBook(campaignKey)
            if (text.isNullOrBlank()) return book
            val data = runCatching { json.decodeFromString<ReadingDraftBookData>(text) }.getOrNull() ?: return book
            if (data.campaignKey != campaignKey) return book
            data.drafts.filter { it.pointId.isNotBlank() }.forEach { book.byPoint[it.pointId] = it }
            book.purge(nowMillis, knownPointIds)
            return book
        }
    }
}

/** Point suivant à ouvrir après un enregistrement. */
object ReadingNextPoint {
    /**
     * Point qui suit [currentId] dans l'ordre affiché [displayedIds] (celui de la liste à l'écran : parcelle,
     * recherche, « proches de moi »...), en sautant les points de [doneIds] et le point courant lui-même.
     * Fin de liste : retour au début. [currentId] absent de la liste (ou null) : premier point restant.
     * Aucun point restant : null (campagne terminée).
     */
    fun after(displayedIds: List<String>, currentId: String?, doneIds: Set<String>): String? {
        if (displayedIds.isEmpty()) return null
        val position = if (currentId == null) -1 else displayedIds.indexOf(currentId)
        val start = position + 1
        for (offset in displayedIds.indices) {
            val id = displayedIds[(start + offset) % displayedIds.size]
            if (id != currentId && id !in doneIds) return id
        }
        return null
    }
}

/** Mise en page du formulaire de relevé : quand la section « Plus de détails » s'ouvre toute seule. */
object ReadingFormLayout {
    /**
     * Ouvre « Plus de détails » si la remarque est obligatoire et vide (l'agent doit la voir), si le point est
     * un kiosque avec cartes sociales rattachées (sinon l'agent oublie de déduire les bidons et la facture est
     * fausse), ou si le brouillon ou la correction contient une valeur de la section ([hiddenValues]).
     */
    fun shouldOpenDetails(remarkRequired: Boolean, remarkBlank: Boolean, kioskWithCards: Boolean, hiddenValues: Boolean): Boolean =
        (remarkRequired && remarkBlank) || kioskWithCards || hiddenValues

    /** Vrai si la section contient une saisie : remarque, volume non facturé différent de 0, ou bidons. */
    fun hasHiddenValues(remark: String, nonBillable: String, cards: List<ReadingDraftCard>): Boolean =
        remark.isNotBlank() ||
            nonBillable.trim().replace(',', '.').let { text -> text.isNotEmpty() && (text.toDoubleOrNull()?.let { it != 0.0 } ?: true) } ||
            cards.any { it.bidons > 0 }
}
