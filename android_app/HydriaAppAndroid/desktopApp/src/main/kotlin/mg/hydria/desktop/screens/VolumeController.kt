package mg.hydria.desktop.screens

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.volume.DesktopVolumeRepository
import mg.hydria.desktop.volume.VolumePrinting
import mg.hydria.desktop.volume.WebInvoicePrint
import mg.hydria.shared.volume.VolumeQrGateway
import mg.hydria.shared.volume.VolumeWorkflowGateway as Workflow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.math.BigDecimal
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId

enum class VolumeStage(val title: String) { BILLING("Facturation"), COLLECTION("Encaissement"), POINTING("Pointage DiameX") }

/** Operation en attente de confirmation (equivalent du AlertDialog de confirmBatch Android). */
data class VolumeConfirmation(val action: String, val invoices: List<JSONObject>, val extra: JSONObject, val title: String)

/**
 * Ecran Volumetrique Desktop : portage de `app/volume/VolumeActivity.kt`.
 * Trois etapes ouvrage/mois (Facturation, Encaissement, Pointage DiameX), meme
 * cache (`DesktopVolumeRepository`), meme file `volume`, memes regles
 * `VolumeWorkflowGateway` / `VolumeQrGateway` (:shared). Differences propres au
 * poste de travail : pas de ConnectivityManager (on tente le reseau, repli sur
 * le cache en cas d'echec) ; QR saisi au clavier ou par douchette USB (qui
 * « tape » le contenu) ; factures = gabarit de la page web (WebInvoicePrint),
 * recapitulatif d'encaissement via le dialogue systeme (VolumePrinting).
 */
class VolumeController(private val session: DesktopSession) {
    private val repository = DesktopVolumeRepository { session.accountKey }
    private val zone = ZoneId.of("Indian/Antananarivo")

    var stage by mutableStateOf(VolumeStage.BILLING); private set
    var works by mutableStateOf(listOf(ALL_WORKS)); private set
    var workId by mutableStateOf(""); private set
    var month by mutableStateOf(YearMonth.now(zone)); private set
    var pack by mutableStateOf<JSONObject?>(null); private set
    var calculated by mutableStateOf(false); private set
    var selectedEntryId by mutableStateOf<String?>(null)
    var showPointed by mutableStateOf(false)
    val selected = mutableStateListOf<String>()
    var busy by mutableStateOf(false); private set
    var message by mutableStateOf<String?>(null)

    /** Incremente a chaque ecriture locale : force la relecture cache/file par l'UI. */
    var revision by mutableStateOf(0); private set

    // Dialogues
    var confirmation by mutableStateOf<VolumeConfirmation?>(null); private set
    var collectFormOpen by mutableStateOf(false); private set
    var collectJournal by mutableStateOf(0)
    var collectDate by mutableStateOf("")
    var recapShown by mutableStateOf<JSONObject?>(null); private set
    var historyOpen by mutableStateOf(false); private set
    var historyDetail by mutableStateOf<JSONObject?>(null); private set
    var reviewNote by mutableStateOf("")
    var reviewOpen by mutableStateOf(false); private set

    // ── Lecture ──

    fun rows(): List<JSONObject> { revision; return pack?.let(repository::invoices) ?: emptyList() }
    fun pending(): List<JSONObject> { revision; return runCatching { repository.pending() }.getOrDefault(emptyList()) }
    fun actions(row: JSONObject): Set<String> = mg.hydria.shared.volume.VolumeCacheGateway.actions(row.getString("id"), pending())
    fun conflicted(row: JSONObject) = Workflow.conflicted(row, pending())
    fun state(row: JSONObject) = Workflow.statusLabel(row, actions(row), conflicted(row))
    fun entries(): List<JSONObject> = Workflow.reconciledEntries(pack?.optJSONArray("diamex") ?: JSONArray(), pending(), rows())
    fun currentEntry() = entries().firstOrNull { it.optString("id") == selectedEntryId }
    fun journals(): List<JSONObject> = pack?.optJSONArray("journaux")?.let { a -> (0 until a.length()).map(a::getJSONObject) } ?: emptyList()
    fun selectedRows() = rows().filter { it.getString("id") in selected }
    fun total(rows: List<JSONObject>): BigDecimal = Workflow.total(rows)
    fun amount(row: JSONObject): BigDecimal = Workflow.amount(row)
    fun calculable(row: JSONObject) = Workflow.calculable(row)
    fun collectable(row: JSONObject) = Workflow.collectable(row, actions(row))
    fun validated(row: JSONObject) = row.optBoolean("validee") || "validate" in actions(row)
    fun pointMatches() = Workflow.matches(selectedRows(), currentEntry())

    fun statusLine(): String {
        val p = pack
        return "${stage.title} · ${p?.optString("mois") ?: "Période à ouvrir"} · ${rows().size} relevés\n" +
            "${pending().size} opération(s) à synchroniser" +
            (p?.let { " · données du ${it.optString("generated_at").take(10)}" } ?: "")
    }

    // ── Selection ouvrage / mois / etape ──

    fun init() {
        loadWorks()
        runCatching { openCached() }
    }

    private fun loadWorks() {
        val values = repository.read("ouvrages")?.optJSONArray("ouvrages") ?: JSONArray()
        works = listOf(ALL_WORKS) + (0 until values.length()).map(values::getJSONObject)
        if (works.none { it.optString("id") == workId }) workId = ""
    }

    fun selectStage(target: VolumeStage) {
        if (busy) return
        stage = target; selected.clear(); selectedEntryId = null
    }

    fun selectWork(id: String) { workId = id; clearChangedPeriod() }
    fun selectMonth(value: YearMonth) { month = value; clearChangedPeriod() }

    private fun clearChangedPeriod() {
        val current = pack ?: return
        if (workId != current.optString("ouvrage_id") || month.toString() != current.optString("mois")) {
            pack = null; selected.clear(); selectedEntryId = null; calculated = false
        }
    }

    private fun selectionKey(): Pair<String, String> {
        check(workId.isNotBlank() || stage == VolumeStage.COLLECTION) { "Choisissez un ouvrage pour ${stage.title}" }
        return workId to month.toString()
    }

    private fun openCached() {
        val (id, period) = selectionKey()
        pack = repository.read("pack:$id:$period")
        selected.clear(); selectedEntryId = null; calculated = false
    }

    fun toggle(row: JSONObject, checked: Boolean) {
        val id = row.getString("id")
        if (checked) { if (id !in selected) selected.add(id) } else selected.remove(id)
    }

    // ── Reseau ──

    private suspend fun background(block: suspend () -> Unit): Boolean {
        busy = true; message = "Chargement en cours…"
        val failure = try { block(); null } catch (e: Exception) { e.message ?: "Connexion interrompue" }
        busy = false; revision++
        message = failure
        return failure == null
    }

    private fun token() = session.token ?: error("Session expirée, reconnectez-vous")

    suspend fun refreshWorks() = safely {
        val token = token()
        background {
            val result = withContext(Dispatchers.IO) { repository.bootstrap(token) }
            check(result.successful) { result.error }
            repository.write("ouvrages", result.body); loadWorks()
        }
    }

    private suspend fun download(showCalculation: Boolean): Boolean {
        val (id, period) = selectionKey()
        val token = token()
        return background {
            val result = withContext(Dispatchers.IO) { repository.bootstrap(token, id, period) }
            check(result.successful) { result.error }
            withContext(Dispatchers.IO) { repository.savePack(result.body) }
            pack = result.body; selected.clear(); selectedEntryId = null; calculated = showCalculation
        }
    }

    /** « Ouvrir » : reseau si possible, sinon la periode prechargee (cf. openPeriod Android). */
    suspend fun openPeriod() = safely {
        if (!download(false)) {
            val error = message
            openCached()
            message = if (pack != null) "Hors ligne ($error) : données préchargées affichées." else error
        }
    }

    suspend fun calculate() = safely {
        if (!download(true)) {
            val error = message
            openCached()
            check(pack != null) { "Préchargez cette période avant de partir hors ligne ($error)" }
            calculated = true
            message = "Hors ligne : calcul sur les données préchargées."
        }
    }

    suspend fun refreshPeriod() = safely { download(stage == VolumeStage.BILLING && calculated) }

    suspend fun synchronize(): Boolean {
        val token = session.token ?: run { message = "Session expirée"; return false }
        var sent = 0
        val ok = background {
            withContext(Dispatchers.IO) {
                for (item in repository.pending()) {
                    val result = repository.syncOne(token, item.getJSONObject("payload"))
                    check(result.successful) { result.error }
                    sent++
                }
            }
        }
        if (ok) message = "$sent opération(s) synchronisée(s)."
        return ok
    }

    // ── Facturation ──

    fun saveBatch() = guard {
        val batch = rows().filter(::calculable).filter {
            !it.optBoolean("imprimee") && !it.optBoolean("encaissee") && !it.optBoolean("pointee") && "validate" !in actions(it)
        }
        check(batch.isNotEmpty()) { "Aucune facture à enregistrer : le lot est déjà validé, verrouillé ou en attente" }
        askConfirmation("validate", batch)
    }

    /** Meme facture que la page web Facturation (gabarit print_factures_a4.js), ouverte dans le navigateur. */
    suspend fun printInvoices() = safely {
        val invoices = rows().filter(::calculable)
        check(invoices.isNotEmpty()) { "Aucune facture à imprimer" }
        check(invoices.none(::conflicted)) { "Vérifiez les conflits du lot avant de l'imprimer" }
        check(invoices.all(::validated)) { "Enregistrez le lot avant l'impression" }
        val current = pack ?: error("Ouvrez une période")
        val organisation = current.optJSONObject("impression")?.optJSONObject("organisation")
        val ouvrage = invoices.first().optString("ouvrage")
        withContext(Dispatchers.IO) {
            WebInvoicePrint.open(invoices, ouvrage, organisation, File(System.getProperty("java.io.tmpdir"), "hydria-impression"))
        }
        message = "Factures ouvertes dans le navigateur : cliquez « Imprimer », puis « Confirmer l'impression réalisée du lot »."
    }

    fun confirmPrinted() = guard {
        askConfirmation("printed", rows().filter(::calculable).filter { !it.optBoolean("imprimee") && "printed" !in actions(it) })
    }

    // ── Encaissement ──

    /** Numero de facture ou contenu QR (saisi ou tape par une douchette). */
    fun addByCode(raw: String) = guard {
        if (raw.isBlank()) return@guard
        val row = VolumeQrGateway.find(raw.trim(), rows()) ?: error("Facture absente de cet ouvrage/mois")
        check(!conflicted(row)) { "Vérifiez le conflit serveur de cette facture" }
        check(collectable(row)) { "Facture déjà encaissée, pointée ou non validée" }
        toggle(row, true); message = "Facture ajoutée : ${row.optString("abonne")}"
    }

    fun openCollect() = guard {
        val invoices = chosen()
        check(invoices.all(::collectable)) { "Une facture est déjà encaissée ou pointée" }
        check(journals().isNotEmpty()) { "Actualisez les journaux avec cette période" }
        collectJournal = 0
        collectDate = LocalDate.now(zone).toString()
        collectFormOpen = true
    }

    fun closeCollect() { collectFormOpen = false }

    fun continueCollect() = guard {
        val date = runCatching { LocalDate.parse(collectDate.trim()) }.getOrElse { error("Date d'encaissement invalide (AAAA-MM-JJ)") }
        val journal = journals().getOrNull(collectJournal) ?: error("Choisissez un journal")
        collectFormOpen = false
        askConfirmation("collect", chosen(), JSONObject().put("date", date.toString()).put("journal_code", journal.getString("code")))
    }

    fun showLastRecap() = guard {
        val current = pack ?: error("Ouvrez une période")
        val id = repository.read("last_recap:${current.getString("ouvrage_id")}:${current.getString("mois")}")?.optString("id")
            ?: error("Aucun encaissement enregistré ici pour cette période")
        showRecap(id)
    }

    private fun showRecap(id: String) { recapShown = repository.read("recap:$id") ?: error("Récapitulatif non disponible") }
    fun closeRecap() { recapShown = null }
    fun printRecap() = guard { VolumePrinting.printRecap(recapShown ?: error("Récapitulatif non disponible")) }

    // ── Pointage ──

    fun point() = guard {
        val invoices = chosen(); val entry = currentEntry()
        check(Workflow.matches(invoices, entry)) { "Le total des relevés doit correspondre à la ligne DiameX" }
        askConfirmation("point", invoices, JSONObject().put("diamex_id", entry!!.getString("id")))
    }

    // ── Confirmation commune (cf. confirmBatch Android) ──

    private fun chosen() = selectedRows().also { check(it.isNotEmpty()) { "Sélectionnez les factures" } }

    private fun askConfirmation(action: String, invoices: List<JSONObject>, extra: JSONObject = JSONObject()) {
        check(invoices.isNotEmpty()) { "Aucune facture concernée" }
        check(invoices.none(::conflicted)) { "Vérifiez les conflits avant de poursuivre" }
        if (action != "validate") check(invoices.all(::validated)) { "Enregistrez d'abord la facturation" }
        check(action in setOf("validate", "printed") || invoices.size <= 500) { "Sélectionnez au maximum 500 factures pour une opération" }
        val title = when (action) {
            "validate" -> "Enregistrer le lot calculé"; "collect" -> "Confirmer l'encaissement"
            "printed" -> "Confirmer l'impression réalisée"; else -> "Confirmer le pointage"
        }
        confirmation = VolumeConfirmation(action, invoices, extra, title)
    }

    fun cancelConfirmation() { confirmation = null }

    suspend fun confirm() = safely {
        val c = confirmation ?: return@safely
        confirmation = null
        val recap = if (c.action == "collect") Workflow.recap(c.invoices, rows(), c.extra.getString("date"), c.extra.getString("journal_code")) else null
        var receiptId: String? = null
        c.invoices.chunked(500).forEach { receiptId = repository.enqueue(c.action, it, c.extra, recap) }
        selected.clear(); selectedEntryId = null; revision++
        // Pas de detection de connectivite sur Desktop : on tente, la file garde l'operation sinon.
        val synced = synchronize()
        if (!synced) message = "Enregistré localement. Synchronisation différée : ${message ?: "réseau indisponible"}"
        if (recap != null) showRecap(receiptId!!)
    }

    // ── Historique ──

    fun history(): List<JSONObject> { revision; return runCatching { repository.history() }.getOrDefault(emptyList()) }
    fun openHistory() = guard {
        check(history().isNotEmpty()) { "Aucune opération volumétrique sur ce poste" }
        historyOpen = true
    }
    fun closeHistory() { historyOpen = false; historyDetail = null }
    fun openDetail(audit: JSONObject) { historyDetail = audit }
    fun closeDetail() { historyDetail = null }

    fun detailId(audit: JSONObject) = audit.getJSONObject("payload").getString("local_uuid")
    fun detailTotal(audit: JSONObject): BigDecimal {
        val rows = audit.getJSONObject("payload").getJSONArray("factures")
        return (0 until rows.length()).map { rows.getJSONObject(it).optString("montant", "0").toBigDecimalOrNull() ?: BigDecimal.ZERO }
            .fold(BigDecimal.ZERO, BigDecimal::add)
    }
    fun hasRecap(audit: JSONObject) = repository.read("recap:${detailId(audit)}") != null
    fun canReview(audit: JSONObject) = pending().any {
        it.getString("local_uuid") == detailId(audit) && it.getJSONObject("payload").has("_sync_conflict")
    }
    fun reprintFromHistory(audit: JSONObject) = guard { showRecap(detailId(audit)) }

    fun openReview() { reviewNote = ""; reviewOpen = true }
    fun closeReview() { reviewOpen = false }
    fun submitReview() = guard {
        repository.reviewConflict(detailId(historyDetail ?: error("Aucune opération")), reviewNote)
        reviewOpen = false; historyDetail = null; revision++
        message = "Opération clôturée après vérification manuelle."
    }

    // ── Utilitaires ──

    private fun guard(block: () -> Unit) {
        if (busy) { message = "Opération en cours"; return }
        try { block() } catch (e: Exception) { message = e.message ?: "Action impossible" }
    }

    private suspend fun safely(block: suspend () -> Unit) {
        if (busy) { message = "Opération en cours"; return }
        try { block() } catch (e: Exception) { busy = false; message = e.message ?: "Action impossible" }
    }

    companion object {
        /** « Tous les ouvrages » (id vide) : utile en Encaissement uniquement. */
        val ALL_WORKS: JSONObject = JSONObject().put("id", "").put("nom", "Tous les ouvrages")
    }
}
