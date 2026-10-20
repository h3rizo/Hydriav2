package mg.hydria.desktop.screens

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.data.SnapshotSync
import mg.hydria.shared.database.HydriaSnapshotGateway
import mg.hydria.shared.database.HydriaSyncQueueGateway
import mg.hydria.shared.network.HydriaOperationsGateway
import mg.hydria.shared.readings.ReadingDraftBook
import mg.hydria.shared.readings.ReadingDraftCard
import mg.hydria.shared.readings.ReadingError
import mg.hydria.shared.readings.ReadingFormSignature
import mg.hydria.shared.readings.ReadingNextPoint
import mg.hydria.shared.readings.ReadingValidation
import mg.hydria.shared.readings.SocialCardError
import mg.hydria.shared.rules.readings.ReadingPointListRules
import mg.hydria.shared.rules.readings.ReadingsRules
import mg.hydria.shared.rules.readings.SocialCardGateway
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/** Une carte sociale sélectionnée pour le relevé courant (kiosque). */
data class SelectedSocialCard(val id: String, val numero: String, val beneficiaire: String, val bidons: Int)

/** Un relevé déjà en file pour un point, sur la campagne courante (mode correction). */
data class PendingReading(
    val uuid: String, val newIndex: Double, val nonBilled: Double, val remark: String, val cartesJson: String,
)

/**
 * Slice verticale "releve" cote Desktop : synchronise le perimetre
 * (prepareTour -> snapshot SQLDelight), saisit un releve dans la file
 * hors-ligne (HydriaSyncQueueGateway, type "reading"), puis draine la file
 * vers /facturation/api/save-releve-terrain/ (HydriaOperationsGateway.saveReading).
 *
 * Calculs 100 % :shared (ReadingValidation / ReadingsRules / SocialCardGateway).
 * Cartes sociales gérées pour les kiosques. Mode correction : sélectionner un
 * point qui a déjà un relevé en file pour la campagne courante pré-remplit le
 * formulaire ; l'enregistrement retire l'ancienne entrée puis ré-enfile
 * (identique à MainActivity). Enrichissement GPS toujours hors périmètre
 * (pas de GPS sur poste de travail).
 *
 * Chantier L2-1 (alignement Desktop) : après un enregistrement, le point suivant de la liste affichée
 * s'ouvre tout seul ([ReadingNextPoint]) ; ce que l'agent a tapé et n'a pas enregistré est gardé en
 * brouillon, point par point ([ReadingDraftBook]), en MÉMOIRE seulement : jamais écrit sur disque, perdu à
 * la fermeture de l'application (le brouillon disque est propre à Android, où le système peut tuer l'appli).
 */
/** "2026-09-28" (ou "2026-09-28T..") -> "28/09/2026" ; parsing manuel, pas de décalage de fuseau. */
internal fun formatReleveDate(iso: String?): String {
    val parts = iso?.take(10)?.split("-") ?: return ""
    return if (parts.size == 3 && parts.all { p -> p.isNotEmpty() && p.all(Char::isDigit) }) {
        "${parts[2]}/${parts[1]}/${parts[0]}"
    } else {
        ""
    }
}

class ReadingsController(
    private val session: DesktopSession,
    /** Horloge des brouillons (millisecondes epoch) : injectable pour les tests. */
    private val clock: () -> Long = System::currentTimeMillis,
) {
    var ouvrages: List<JSONObject> by mutableStateOf(emptyList())
    var selectedOuvrageId: String? by mutableStateOf(null)
    var campaignDate: String by mutableStateOf(todayMadagascar().toString())
        private set

    var selectedPoint: JSONObject? by mutableStateOf(null)
    var newIndexInput: String by mutableStateOf("")
    var nonBilledInput: String by mutableStateOf("")
    var remark: String by mutableStateOf("")
    var socialCards: List<SelectedSocialCard> by mutableStateOf(emptyList())
        private set

    /** Brouillons en mémoire : un livre par campagne « ouvrage|date » ([ReadingDraftBook.key]). */
    private val draftBooks = HashMap<String, ReadingDraftBook>()

    /** Signature du formulaire à l'ouverture du point, AVANT d'appliquer son brouillon : base de comparaison de `put`. */
    private var draftBaseline: List<String> = emptyList()

    /** Incrémenté à chaque changement d'un livre, pour que la liste des points se redessine (puce « brouillon »). */
    private var draftVersion: Int by mutableStateOf(0)

    /** Vrai quand le formulaire ouvert vient d'être rempli depuis un brouillon (bandeau « Brouillon repris »). */
    var draftRestored: Boolean by mutableStateOf(false)
        private set

    var pendingCount: Int by mutableStateOf(0)
    var busy: Boolean by mutableStateOf(false)
    var message: String? by mutableStateOf(null)

    /** Payloads "reading" en file (toutes campagnes). Rafraîchi par [refreshPending]. */
    private var pendingReadings: List<JSONObject> by mutableStateOf(emptyList())

    /** point_eau_id -> relevé déjà en file pour la date de campagne courante. */
    val pendingByPoint: Map<String, PendingReading>
        get() = pendingReadings
            .filter { it.optString("date_releve") == campaignDate }
            .associate { p ->
                p.optString("point_eau_id") to PendingReading(
                    uuid = p.optString("local_uuid"),
                    newIndex = p.optDouble("nouvel_index", 0.0),
                    nonBilled = p.optDouble("volume_non_facture", 0.0),
                    remark = p.optString("remarque"),
                    cartesJson = p.optString("cartes_sociales", "[]"),
                )
            }

    private val correction: PendingReading?
        get() = selectedPoint?.let { pendingByPoint[it.optString("id")] }

    val correcting: Boolean get() = correction != null

    val selectedOuvrage: JSONObject?
        get() = ouvrages.firstOrNull { it.optString("id") == selectedOuvrageId }

    /** Recherche libre (nom d'abonné, même partiel, ou idxls) dans la liste des points. */
    var pointSearch: String by mutableStateOf("")

    /** Filtre Parcelle (cascade) : [ReadingPointListRules.ALL_PARCELS] = toutes. */
    var parcelId: String by mutableStateOf(ReadingPointListRules.ALL_PARCELS)

    val idxlsWidth: Int get() = ReadingPointListRules.idxlsWidth(points)

    /** Filtre Parcelle proposé au-delà de 20 points et s'il y a plusieurs parcelles. */
    val showParcelFilter: Boolean get() = ReadingPointListRules.showParcelFilter(points)

    val parcels: List<ReadingPointListRules.Parcel> get() = ReadingPointListRules.parcels(points)

    /** Parcelle -> recherche -> tri numérique par idxls. */
    val visiblePoints: List<JSONObject>
        get() {
            val width = idxlsWidth
            val byParcel = if (showParcelFilter) ReadingPointListRules.filterByParcel(points, parcelId) else points
            return ReadingPointListRules.sortedByIdxls(ReadingPointListRules.filterBySearch(byParcel, width, pointSearch), width)
        }

    /** Libellé « 💧 07 — Nom » ; « ⚠ » devant un idxls anormal (non numérique ou vide). */
    fun pointLabel(point: JSONObject): String = ReadingPointListRules.label(point, idxlsWidth)

    val points: List<JSONObject>
        get() {
            val array = selectedOuvrage?.optJSONArray("points_eau") ?: return emptyList()
            return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
                .filter { it.optBoolean("a_relever", true) }
        }

    val oldIndex: Double
        get() = selectedPoint?.optJSONObject("dernier_releve")?.optDouble("nouvel_index", 0.0) ?: 0.0

    /** Date du dernier relevé (JJ/MM/AAAA), vide si inconnue. */
    val oldIndexDate: String
        get() = formatReleveDate(selectedPoint?.optJSONObject("dernier_releve")?.optString("date_releve"))

    private val newIndex: Double? get() = newIndexInput.replace(',', '.').toDoubleOrNull()
    private val nonBilled: Double get() = nonBilledInput.replace(',', '.').toDoubleOrNull() ?: 0.0

    /** Un point est un kiosque -> cartes sociales possibles. */
    val isKiosque: Boolean
        get() = selectedPoint?.let { p ->
            listOf("type", "type_pe", "type_point_eau").any { p.optString(it).uppercase().contains("KIOSQUE") }
        } ?: false

    /** Cartes rattachées au point (depuis le snapshot), non encore ajoutées au relevé. */
    val availableSocialCards: List<JSONObject>
        get() {
            if (!isKiosque) return emptyList()
            val array = selectedPoint?.optJSONArray("cartes_sociales") ?: return emptyList()
            return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
                .filter { it.optString("id").isNotBlank() }
                .distinctBy { it.optString("id") }
                .filter { card -> socialCards.none { it.id == card.optString("id") } }
        }

    val socialVolume: Double
        get() = socialCards.sumOf { ReadingsRules.socialCardVolume(it.bidons) }

    val consumption: Double? get() = newIndex?.let { ReadingsRules.consumption(it, oldIndex) }
    val billedVolume: Double? get() = consumption?.let { ReadingsRules.billedVolume(it, socialVolume, nonBilled) }

    val validationError: ReadingError?
        get() = ReadingValidation.validate(
            hasPoint = selectedPoint != null,
            newIndex = newIndex,
            oldIndex = oldIndex,
            nonBillable = nonBilled,
            socialVolume = socialVolume,
            campaignDate = campaignDate,
        )

    /** Vrai après un enregistrement refusé faute de remarque : l'erreur reste affichée tant que la règle n'est pas satisfaite. */
    private var remarkRefused: Boolean by mutableStateOf(false)

    /** Règle du serveur (miroir dans :shared) : remarque obligatoire si consommation nulle ou volume non facturé != 0. */
    val remarkRequired: Boolean get() = ReadingValidation.remarkRequired(consumption, nonBilled)

    val remarkError: ReadingError? get() = ReadingValidation.validateRemark(consumption, nonBilled, remark)

    /** Message sous le champ Remarque (null = rien à signaler). */
    val remarkErrorText: String?
        get() = if (!remarkRefused) null else when (remarkError) {
            ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION -> "Remarque obligatoire : consommation nulle"
            ReadingError.REMARK_REQUIRED_NON_BILLABLE -> "Remarque obligatoire : volume non facture renseigne"
            else -> null
        }

    fun addSocialCard(card: JSONObject) {
        val id = card.optString("id")
        if (id.isBlank() || socialCards.any { it.id == id }) return
        socialCards = socialCards + SelectedSocialCard(
            id = id,
            numero = card.optString("numero_carte"),
            beneficiaire = card.optString("beneficiaire"),
            bidons = 0,
        )
    }

    fun removeSocialCard(id: String) {
        socialCards = socialCards.filterNot { it.id == id }
    }

    fun setSocialBidons(id: String, bidons: Int) {
        val n = bidons.coerceIn(0, 30)
        socialCards = socialCards.map { if (it.id == id) it.copy(bidons = n) else it }
    }

    fun loadFromCache() {
        val snapshot = runCatching { HydriaSnapshotGateway.snapshot() }.getOrNull()
        val array = snapshot?.optJSONArray("ouvrages")
        ouvrages = if (array == null) emptyList()
        else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
        if (selectedOuvrageId != null && ouvrages.none { it.optString("id") == selectedOuvrageId }) {
            selectedOuvrageId = null
        }
        refreshPending()
    }

    fun refreshPending() {
        val payloads = runCatching {
            val pending = HydriaSyncQueueGateway.pending()
            (0 until pending.length()).mapNotNull { i ->
                val row = pending.optJSONObject(i) ?: return@mapNotNull null
                if (row.optString("type") != "reading") return@mapNotNull null
                row.optJSONObject("payload")
            }
        }.getOrDefault(emptyList())
        pendingReadings = payloads
        pendingCount = payloads.size
    }

    /** Un point de la liste a-t-il déjà un relevé en file (à corriger) ? */
    fun hasPendingReading(point: JSONObject): Boolean =
        pendingByPoint.containsKey(point.optString("id"))

    /**
     * Ouvre [point]. La saisie du point quitté est gardée en brouillon (sauf si elle est identique à son état
     * initial), sans question ; le brouillon du point choisi, s'il existe, est remis dans les champs.
     */
    fun selectPoint(point: JSONObject) {
        val current = selectedPoint
        if (current != null && current.optString("id") == point.optString("id")) {
            // Même point (liste rechargée par une synchro) : on garde la saisie, on ne remet rien à zéro.
            selectedPoint = point
            return
        }
        val kept = stashDraft()
        openPoint(point)
        message = if (kept) DRAFT_KEPT_MESSAGE else null
    }

    /** Changement d'ouvrage : le brouillon du point ouvert reste dans la campagne de l'ancien ouvrage. */
    fun selectOuvrage(id: String) {
        val kept = stashDraft()
        selectedOuvrageId = id
        clearForm()
        pointSearch = ""
        parcelId = ReadingPointListRules.ALL_PARCELS
        if (kept) message = DRAFT_KEPT_MESSAGE
    }

    /**
     * Changement de date de campagne : la saisie reste attachée à l'ancienne campagne (brouillon), le point
     * ouvert est rechargé pour la nouvelle (relevé déjà en file ou brouillon de cette date).
     */
    fun changeCampaignDate(iso: String) {
        if (iso == campaignDate) return
        val point = selectedPoint
        val kept = stashDraft()
        campaignDate = iso
        if (point != null) openPoint(point)
        if (kept) message = DRAFT_KEPT_MESSAGE
    }

    /** Un point de la liste a-t-il un brouillon (saisie non enregistrée) dans la campagne courante ? */
    fun hasDraft(point: JSONObject): Boolean {
        draftVersion // lu pour que la liste se redessine quand un brouillon est gardé ou supprimé
        val key = campaignKey() ?: return false
        return draftBooks[key]?.contains(point.optString("id")) == true
    }

    private fun campaignKey(): String? = selectedOuvrageId?.let { ReadingDraftBook.key(it, campaignDate) }

    private fun draftBook(): ReadingDraftBook? {
        val key = campaignKey() ?: return null
        return draftBooks.getOrPut(key) { ReadingDraftBook(key) }
    }

    private fun currentDraftCards(): List<ReadingDraftCard> = socialCards.map { ReadingDraftCard(it.id, it.bidons) }

    /**
     * Garde la saisie du point ouvert dans le brouillon de la campagne courante ; un formulaire identique à
     * son état initial ne laisse aucun brouillon.
     * @return true si un brouillon est gardé après l'appel.
     */
    private fun stashDraft(): Boolean {
        val point = selectedPoint ?: return false
        val book = draftBook() ?: return false
        val kept = book.put(
            pointId = point.optString("id"),
            index = newIndexInput,
            remark = remark,
            nonBillable = nonBilledInput,
            cards = currentDraftCards(),
            baseline = draftBaseline,
            nowMillis = clock(),
        )
        draftVersion++
        return kept
    }

    /** Remplit le formulaire pour [point] : relevé déjà en file (correction), sinon vide ; puis son brouillon. */
    private fun openPoint(point: JSONObject) {
        selectedPoint = point
        remarkRefused = false
        draftRestored = false
        val pointId = point.optString("id")
        val pending = pendingByPoint[pointId]
        if (pending != null) {
            newIndexInput = pending.newIndex.toPlainInput()
            nonBilledInput = pending.nonBilled.takeIf { it != 0.0 }?.toPlainInput() ?: ""
            remark = pending.remark
            socialCards = parseSocialCards(pending.cartesJson, point)
        } else {
            newIndexInput = ""
            nonBilledInput = ""
            remark = ""
            socialCards = emptyList()
        }
        // Base de comparaison : l'état initial, calculé AVANT d'appliquer le brouillon.
        draftBaseline = ReadingFormSignature.of(newIndexInput, remark, nonBilledInput, currentDraftCards())
        val book = draftBook() ?: return
        val knownIds = points.map { it.optString("id") }.toSet()
        if (knownIds.isNotEmpty() && book.purge(clock(), knownIds) > 0) draftVersion++
        val draft = book.get(pointId) ?: return
        newIndexInput = draft.index
        remark = draft.remark
        nonBilledInput = draft.nonBillable
        socialCards = draftCards(draft.cardsAmong(linkedCardIds(point)), point)
        draftRestored = true
    }

    private fun clearForm() {
        selectedPoint = null
        newIndexInput = ""
        nonBilledInput = ""
        remark = ""
        socialCards = emptyList()
        remarkRefused = false
        draftRestored = false
    }

    private fun linkedCardIds(point: JSONObject): Set<String> {
        val array = point.optJSONArray("cartes_sociales") ?: return emptySet()
        return (0 until array.length()).mapNotNull { array.optJSONObject(it)?.optString("id")?.takeIf(String::isNotBlank) }.toSet()
    }

    private fun draftCards(cards: List<ReadingDraftCard>, point: JSONObject): List<SelectedSocialCard> {
        val array = point.optJSONArray("cartes_sociales")
        return cards.map { card ->
            val ref = array?.let { a -> (0 until a.length()).mapNotNull { a.optJSONObject(it) }.firstOrNull { it.optString("id") == card.id } }
            SelectedSocialCard(
                id = card.id,
                numero = ref?.optString("numero_carte").orEmpty(),
                beneficiaire = ref?.optString("beneficiaire").orEmpty(),
                bidons = card.bidons.coerceIn(0, 30),
            )
        }
    }

    /**
     * Point à ouvrir après l'enregistrement de [pointId] : celui qui suit dans la liste affichée (parcelle,
     * recherche), en sautant les points qui ont déjà un relevé en file ; null s'il n'en reste aucun.
     */
    private fun nextPointAfter(pointId: String): JSONObject? {
        val visible = visiblePoints
        val nextId = ReadingNextPoint.after(visible.map { it.optString("id") }, pointId, pendingByPoint.keys + pointId) ?: return null
        return visible.firstOrNull { it.optString("id") == nextId }
    }

    private fun Double.toPlainInput(): String {
        val s = this.toString()
        return if (s.endsWith(".0")) s.dropLast(2) else s
    }

    private fun parseSocialCards(cartesJson: String, point: JSONObject): List<SelectedSocialCard> {
        val arr = runCatching { JSONArray(cartesJson) }.getOrNull() ?: return emptyList()
        val linked = point.optJSONArray("cartes_sociales")
        fun lookup(id: String): JSONObject? {
            if (linked == null) return null
            for (i in 0 until linked.length()) {
                val c = linked.optJSONObject(i) ?: continue
                if (c.optString("id") == id) return c
            }
            return null
        }
        return (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            val id = o.optString("id").ifBlank { return@mapNotNull null }
            val ref = lookup(id)
            SelectedSocialCard(
                id = id,
                numero = ref?.optString("numero_carte").orEmpty(),
                beneficiaire = ref?.optString("beneficiaire").orEmpty(),
                bidons = o.optInt("quantite_bidons", 0).coerceIn(0, 30),
            )
        }
    }

    suspend fun syncPerimeter() {
        val token = session.token ?: run { message = "Session expiree."; return }
        busy = true; message = null
        val outcome = SnapshotSync.refresh(token)
        busy = false
        when (outcome) {
            is SnapshotSync.Outcome.Refreshed -> {
                loadFromCache()
                message = if (outcome.raw) "Perimetre synchronise : ${ouvrages.size} ouvrage(s)."
                else "Perimetre deja a jour."
            }
            is SnapshotSync.Outcome.Failed -> message = outcome.message
        }
    }

    /** @return true si le releve a ete mis en file. */
    fun save(): Boolean {
        val point = selectedPoint ?: return false
        val index = newIndex ?: return false
        when (validationError) {
            null -> {}
            ReadingError.INDEX_DECREASED -> { message = "L'index doit etre >= $oldIndex."; return false }
            ReadingError.NEGATIVE_NON_BILLABLE -> { message = "Volume non facture negatif interdit."; return false }
            ReadingError.NEGATIVE_BILLED_VOLUME -> { message = "Volume facture negatif : reduisez les bidons des cartes sociales ou le volume non facture."; return false }
            ReadingError.INVALID_CAMPAIGN_DATE -> { message = "Date de campagne invalide."; return false }
            else -> { message = "Saisie invalide."; return false }
        }
        // Remarque obligatoire : le serveur refuserait sinon le relevé en HTTP 400 à la synchronisation.
        if (remarkError != null) {
            remarkRefused = true
            message = null
            return false
        }
        // Cartes sociales : validation + payload via :shared (identique a MainActivity).
        val linkedIds = buildSet {
            addAll(socialCards.map { it.id })
            val array = point.optJSONArray("cartes_sociales")
            if (array != null) for (i in 0 until array.length()) {
                array.optJSONObject(i)?.optString("id")?.takeIf { it.isNotBlank() }?.let(::add)
            }
        }
        val selectedJson = socialCards.map { JSONObject().put("id", it.id).put("quantite_bidons", it.bidons) }
        val prepared = SocialCardGateway.prepare(selectedJson, linkedIds)
        val cardError = prepared.error
        if (cardError != null) {
            message = when (cardError) {
                SocialCardError.INVALID_QUANTITY -> "Cartes sociales : entre 0 et 30 bidons par carte."
                SocialCardError.UNLINKED_OR_DUPLICATE_CARD -> "Cartes sociales : choisissez uniquement des cartes rattachees a ce point."
            }
            return false
        }

        val uuid = UUID.randomUUID().toString()
        val payload = JSONObject()
            .put("point_eau_id", point.getString("id"))
            .put("date_releve", campaignDate)
            .put("nouvel_index", index)
            .put("volume_non_facture", nonBilled)
            .put("remarque", remark)
            .put("local_uuid", uuid)
        val cartesArray = SocialCardGateway.payload(prepared)
        if (cartesArray.length() > 0) payload.put("cartes_sociales", cartesArray.toString())

        // Mode correction : retirer l'ancienne entrée de la file avant de ré-enfiler.
        val corrected = correcting
        correction?.let { runCatching { HydriaSyncQueueGateway.remove(it.uuid) } }

        runCatching { HydriaSyncQueueGateway.enqueue(uuid, "reading", payload) }
            .onFailure { message = "Impossible d'enregistrer : ${it.message}"; return false }
        // Point enregistré : son brouillon n'a plus lieu d'être.
        val savedId = point.getString("id")
        draftBook()?.remove(savedId)
        draftVersion++
        refreshPending()
        clearForm()
        // Une recherche ne sert qu'à trouver ce point : le suivant se prend dans la liste complète (parcelle conservée).
        if (pointSearch.isNotBlank()) pointSearch = ""
        val next = nextPointAfter(savedId)
        if (next != null) openPoint(next)
        message = (if (corrected) "Releve corrige dans la file. $pendingCount en attente."
        else "Releve mis en file. $pendingCount en attente.") +
            if (next == null) " Plus de point a relever dans cette liste." else ""
        return true
    }

    suspend fun drainQueue() {
        val token = session.token ?: run { message = "Session expiree."; return }
        busy = true; message = null
        val (ok, failed) = withContext(Dispatchers.IO) {
            var sent = 0
            var errors = 0
            val pending = runCatching { HydriaSyncQueueGateway.pending() }.getOrNull()
            if (pending != null) {
                for (i in 0 until pending.length()) {
                    val row = pending.optJSONObject(i) ?: continue
                    if (row.optString("type") != "reading") continue
                    val localUuid = row.optString("local_uuid")
                    val payload = row.optJSONObject("payload") ?: continue
                    val result = runCatching { HydriaOperationsGateway.saveReading(token, payload) }.getOrNull()
                    if (result != null && result.status in 200..299 && result.body.optBoolean("success", true)) {
                        runCatching { HydriaSyncQueueGateway.remove(localUuid) }
                        sent++
                    } else {
                        val err = result?.body?.optString("error") ?: "reseau indisponible"
                        runCatching { HydriaSyncQueueGateway.markFailed(localUuid, err) }
                        errors++
                    }
                }
            }
            sent to errors
        }
        busy = false
        refreshPending()
        message = buildString {
            append("$ok releve(s) synchronise(s)")
            if (failed > 0) append(", $failed en erreur (reessayez plus tard)")
            append(".")
        }
    }

    private companion object {
        const val DRAFT_KEPT_MESSAGE = "Saisie gardee en brouillon."
    }
}
