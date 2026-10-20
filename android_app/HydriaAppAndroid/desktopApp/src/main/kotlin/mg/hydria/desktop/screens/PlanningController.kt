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
import mg.hydria.shared.planning.PlanningActivityKind
import mg.hydria.shared.planning.PlanningAgendaDay
import mg.hydria.shared.planning.PlanningDraft
import mg.hydria.shared.planning.PlanningFormRules
import mg.hydria.shared.rules.planning.PlanningRules
import org.json.JSONObject
import java.util.UUID

/**
 * Ecran Planning Desktop : agenda groupe par date depuis `snapshot.plannings[]`,
 * prepare/trie/selectionne par `PlanningRules.agenda` (:shared, meme moteur que
 * l'app Android). Creation / modification via `PlanningFormRules.validate` ->
 * file `save_planning` -> drain `HydriaOperationsGateway.savePlanning`.
 */
class PlanningController(private val session: DesktopSession) {
    var days: List<PlanningAgendaDay<JSONObject>> by mutableStateOf(emptyList())
        private set
    var selectedDate: String by mutableStateOf("")
        private set
    var busy: Boolean by mutableStateOf(false)
    var message: String? by mutableStateOf(null)
    var loaded: Boolean by mutableStateOf(false)
        private set
    var pendingSaveCount: Int by mutableStateOf(0)
        private set

    private var references: JSONObject? by mutableStateOf(null)

    val selectedDay: PlanningAgendaDay<JSONObject>?
        get() = days.firstOrNull { it.dateKey == selectedDate }

    fun activityKind(planning: JSONObject): PlanningActivityKind = PlanningRules.activityKind(planning)

    fun dayIndicator(day: PlanningAgendaDay<JSONObject>): String = PlanningRules.dayIndicatorText(day.state)
    fun weekdayLabel(dateKey: String): String = PlanningRules.weekdayLabel(dateKey)
    fun fullDateLabel(dateKey: String): String = PlanningRules.fullDateLabel(dateKey)
    fun shortWeekdayLabel(dateKey: String): String = PlanningRules.shortWeekdayLabel(dateKey)
    fun dayNumberLabel(dateKey: String): String = PlanningRules.dayNumberLabel(dateKey)

    fun loadFromCache() {
        val snapshot = runCatching { HydriaSnapshotGateway.snapshot() }.getOrNull()
        val array = snapshot?.optJSONArray("plannings")
        loaded = array != null
        references = snapshot?.optJSONObject("references")
        terrainWorks = snapshot?.optJSONObject("terrain")?.optJSONArray("ouvrages")
        val list = if (array == null) emptyList()
        else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
        val state = PlanningRules.agenda(list, selectedDate, todayMadagascar().toString())
        days = state.days
        selectedDate = state.selectedDate
        refreshPending()
    }

    fun refreshPending() {
        pendingSaveCount = runCatching {
            val pending = HydriaSyncQueueGateway.pending()
            (0 until pending.length()).count { pending.optJSONObject(it)?.optString("type") == "save_planning" }
        }.getOrDefault(0)
    }

    fun selectDate(dateKey: String) {
        if (days.any { it.dateKey == dateKey }) selectedDate = dateKey
    }

    suspend fun syncPerimeter() {
        val token = session.token ?: run { message = "Session expiree."; return }
        busy = true; message = null
        val outcome = SnapshotSync.refresh(token)
        busy = false
        when (outcome) {
            is SnapshotSync.Outcome.Refreshed -> {
                loadFromCache()
                message = if (outcome.raw) "Perimetre synchronise : ${days.sumOf { it.items.size }} planning(s)."
                else "Perimetre deja a jour."
            }
            is SnapshotSync.Outcome.Failed -> message = outcome.message
        }
    }

    // ── Formulaire creation / edition ──

    // ── Cible (point d'eau / équipement) et composants — mêmes règles que l'app Android ──
    private var terrainWorks: org.json.JSONArray? by mutableStateOf(null)
    var fTarget: String by mutableStateOf("")
    var fComponents: Set<String> by mutableStateOf(emptySet())
    private var existingTargetKey: String? = null

    val targets: List<mg.hydria.shared.rules.forms.WorkTarget>
        get() = mg.hydria.shared.rules.forms.WorkTargetRules.targets(terrainWorks, fWork)
    val targetComponents: List<JSONObject>
        get() = mg.hydria.shared.rules.forms.WorkTargetRules.components(
            references?.optJSONObject("composants"), targets.firstOrNull { it.key == fTarget })

    fun setWork(id: String) {
        fWork = id
        if (targets.none { it.key == fTarget }) { fTarget = ""; fComponents = emptySet() }
    }
    fun setTarget(key: String) { if (key != fTarget) { fTarget = key; fComponents = emptySet() } }
    fun toggleComponent(id: String, on: Boolean) { fComponents = if (on) fComponents + id else fComponents - id }

    /** N'envoyer la cible que si l'écran la connaît, pour ne pas effacer côté serveur une cible non affichable. */
    private fun targetKnown(): Boolean = targets.isNotEmpty() &&
        (existingTargetKey == null || targets.any { it.key == existingTargetKey })

    private fun loadTargetState(item: JSONObject?) {
        fTarget = mg.hydria.shared.rules.forms.WorkTargetRules.existingKey(item).orEmpty()
        existingTargetKey = fTarget.ifBlank { null }
        val ids = item?.optJSONArray("composants_ids")
        fComponents = (0 until (ids?.length() ?: 0)).map { ids!!.getString(it) }.toSet()
    }

    var editorOpen: Boolean by mutableStateOf(false)
        private set
    private var editingId: String? by mutableStateOf(null)
    val editingExisting: Boolean get() = editingId != null

    var fEmployee: String by mutableStateOf("")
    var fWork: String by mutableStateOf("")
    var fActivity: String by mutableStateOf("")
    var fDate: String by mutableStateOf("")
    var fStatus: String by mutableStateOf("")
    var fRemark: String by mutableStateOf("")

    val hasReferences: Boolean get() = references != null
    val employees: List<JSONObject> get() = refList("employes")
    val works: List<JSONObject> get() = refList("ouvrages")
    val activities: List<JSONObject> get() = refList("planning_fiches")
    val statuses: List<JSONObject> get() = refList("statuts")

    private fun refList(key: String): List<JSONObject> {
        val arr = references?.optJSONArray(key) ?: return emptyList()
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
    }

    fun openEditor(planning: JSONObject?) {
        if (!hasReferences) { message = "Synchronisez le perimetre pour charger les listes de saisie."; return }
        if (employees.isEmpty() || activities.isEmpty()) {
            message = "Listes de reference vides. Verifiez vos droits Hydria puis resynchronisez."; return
        }
        editingId = planning?.optString("id")?.takeIf { it.isNotBlank() }
        fEmployee = planning?.optString("employe_id").orEmpty()
        fWork = planning?.optString("ouvrage_id").orEmpty()
        fActivity = planning?.optString("fiche_poste_id").orEmpty()
        fDate = planning?.optString("date")?.take(10)?.takeIf { it.isNotBlank() } ?: (selectedDate.takeIf { it.isNotBlank() } ?: todayMadagascar().toString())
        fStatus = planning?.optString("statut_code").orEmpty().ifBlank { statuses.firstOrNull()?.optString("id").orEmpty() }
        fRemark = planning?.optString("remarque").orEmpty()
        loadTargetState(planning)
        message = null
        editorOpen = true
    }

    fun closeEditor() { editorOpen = false }

    /** @return true si le planning a ete mis en file. */
    fun savePlanningForm(): Boolean {
        val result = PlanningFormRules.validate(
            PlanningDraft(
                employeeId = fEmployee.takeIf { it.isNotBlank() },
                activityId = fActivity.takeIf { it.isNotBlank() },
                date = fDate.trim(),
                workId = fWork,
                status = fStatus.ifBlank { "en_cours" },
                remark = fRemark,
                existingId = editingId,
            )
        )
        val err = result.error
        if (err != null) { message = err.message; return false }
        val fields = result.fields ?: run { message = "Formulaire invalide."; return false }
        val uuid = UUID.randomUUID().toString()
        val payload = JSONObject().apply {
            fields.forEach { (k, v) -> put(k, v) }
            put("local_uuid", uuid)
            if (targetKnown()) {
                put("equipement_id", fTarget.removePrefix("eq:").takeIf { fTarget.startsWith("eq:") }.orEmpty())
                put("point_eau_id", fTarget.removePrefix("pe:").takeIf { fTarget.startsWith("pe:") }.orEmpty())
                put("composants_ids", fComponents.joinToString(","))
            }
        }
        runCatching { HydriaSyncQueueGateway.enqueue(uuid, "save_planning", payload) }
            .onFailure { message = "Impossible d'enregistrer : ${it.message}"; return false }
        editorOpen = false
        refreshPending()
        message = if (editingId != null) "Modification mise en file. $pendingSaveCount en attente."
        else "Nouveau planning mis en file. $pendingSaveCount en attente."
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
                    if (row.optString("type") != "save_planning") continue
                    val localUuid = row.optString("local_uuid")
                    val payload = row.optJSONObject("payload") ?: continue
                    val result = runCatching { HydriaOperationsGateway.savePlanning(token, payload) }.getOrNull()
                    if (result != null && result.status in 200..299 && result.body.optBoolean("success", true)) {
                        runCatching { HydriaSyncQueueGateway.remove(localUuid) }
                        sent++
                    } else {
                        val e = result?.body?.optString("error") ?: "reseau indisponible"
                        runCatching { HydriaSyncQueueGateway.markFailed(localUuid, e) }
                        errors++
                    }
                }
            }
            sent to errors
        }
        busy = false
        refreshPending()
        message = buildString {
            append("$ok planning(s) synchronise(s)")
            if (failed > 0) append(", $failed en erreur")
            append(".")
        }
    }
}
