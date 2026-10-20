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
import mg.hydria.shared.repairs.OverdueLabel
import mg.hydria.shared.repairs.RepairDraft
import mg.hydria.shared.repairs.RepairFormRules
import mg.hydria.shared.rules.repairs.RepairOverviewGateway
import mg.hydria.shared.rules.repairs.RepairRules
import org.json.JSONObject
import java.io.File
import java.util.Base64
import java.util.UUID

/** Groupe de reparations pour l'affichage (un ouvrage). */
data class RepairWorkGroup(val ouvrage: String, val repairs: List<JSONObject>)

/**
 * Ecran Reparations Desktop : liste depuis le snapshot de perimetre (meme
 * source que Releves), regroupee/triee par `RepairOverviewGateway` (:shared).
 *  - "Marquer terminee" -> file `finish_repair` -> drain `HydriaOperationsGateway.finishRepair`.
 *  - Creation / modification -> `RepairFormRules.validate` (:shared) -> file `save_repair`
 *    -> drain `HydriaOperationsGateway.saveRepair`. Listes de saisie depuis
 *    `snapshot.references` (memes clefs que MainActivity).
 *  - Photo preuve -> file `repair_photo` -> drain `HydriaOperationsGateway.saveRepairPhoto`.
 *    Meme route/format que l'app Android (RepairsRepository.enqueuePhoto), photo
 *    uniquement (jpeg/png/webp, 5 Mo max cote serveur) : pas de video.
 */
class RepairsController(private val session: DesktopSession) {
    var showCompleted: Boolean by mutableStateOf(false)
    var showOutside: Boolean by mutableStateOf(false)
    var pendingFinishCount: Int by mutableStateOf(0)
    var pendingSaveCount: Int by mutableStateOf(0)
    var pendingPhotoCount: Int by mutableStateOf(0)
    var busy: Boolean by mutableStateOf(false)
    var message: String? by mutableStateOf(null)

    val pendingCount: Int get() = pendingFinishCount + pendingSaveCount + pendingPhotoCount

    private var all: List<JSONObject> by mutableStateOf(emptyList())
    private var pendingCompletionIds: Set<String> by mutableStateOf(emptySet())
    private var references: JSONObject? by mutableStateOf(null)

    var loaded: Boolean by mutableStateOf(false)
        private set

    // ── Liste ──

    val groups: List<RepairWorkGroup>
        get() {
            val visible = RepairOverviewGateway.visible(all, pendingCompletionIds, showCompleted, showOutside)
            return RepairOverviewGateway.prepare(visible, pendingCompletionIds).groups.map { group ->
                RepairWorkGroup(
                    ouvrage = group.items.firstOrNull()?.optString("ouvrage_nom").orEmpty().ifBlank { "Sans ouvrage" },
                    repairs = group.items,
                )
            }
        }

    val completedCount: Int
        get() = RepairOverviewGateway.prepare(all, pendingCompletionIds).completedCount

    fun isCompleted(repair: JSONObject): Boolean =
        RepairRules.isCompleted(repair) || repair.optString("id") in pendingCompletionIds

    fun activityLabel(repair: JSONObject) = RepairRules.activityLabel(repair)
    fun priorityLabel(repair: JSONObject) = RepairRules.priorityLabel(repair)
    /** « 224 j » + RETARD, « AUJ. » ou « dans 5 j » : libellé partagé avec l'app Android (:shared). */
    fun overdueLabel(repair: JSONObject): OverdueLabel? = RepairRules.overdueLabel(repair)

    fun loadFromCache() {
        val snapshot = runCatching { HydriaSnapshotGateway.snapshot() }.getOrNull()
        val array = snapshot?.optJSONArray("reparations")
        all = if (array == null) emptyList()
        else (0 until array.length()).mapNotNull { array.optJSONObject(it) }
        references = snapshot?.optJSONObject("references")
        terrainWorks = snapshot?.optJSONObject("terrain")?.optJSONArray("ouvrages")
        loaded = array != null
        refreshPending()
    }

    fun refreshPending() {
        val pending = runCatching { HydriaSyncQueueGateway.pending() }.getOrNull()
        pendingCompletionIds = pending?.let { RepairRules.pendingCompletionIds(it) } ?: emptySet()
        fun count(type: String) = pending?.let { p ->
            (0 until p.length()).count { p.optJSONObject(it)?.optString("type") == type }
        } ?: 0
        pendingFinishCount = count("finish_repair")
        pendingSaveCount = count("save_repair")
        pendingPhotoCount = count("repair_photo")
    }

    // ── Photo preuve ──

    private val photoExtensions = mapOf(
        "jpg" to "image/jpeg", "jpeg" to "image/jpeg", "png" to "image/png", "webp" to "image/webp",
    )
    private val maxPhotoBytes = 5 * 1024 * 1024

    /** Formats/taille acceptes par le serveur (voir _decode_mobile_photo cote Django) :
     * jpeg/png/webp, 5 Mo max. Pas de video : Planning.photo stocke les photos en
     * base64 dans un champ JSON, un format non adapte a des fichiers video. */
    fun addPhoto(repairId: String, file: File) {
        val extension = file.extension.lowercase()
        val contentType = photoExtensions[extension] ?: run {
            message = "Format non pris en charge (jpg, png ou webp uniquement)."; return
        }
        if (file.length() > maxPhotoBytes) {
            message = "La photo doit faire moins de 5 Mo."; return
        }
        val encoded = runCatching { Base64.getEncoder().encodeToString(file.readBytes()) }
            .getOrElse { message = "Impossible de lire le fichier : ${it.message}"; return }
        val uuid = UUID.randomUUID().toString()
        val payload = JSONObject()
            .put("planning_id", repairId)
            .put("photo_data", encoded)
            .put("content_type", contentType)
            .put("filename", file.name)
            .put("local_uuid", uuid)
        runCatching { HydriaSyncQueueGateway.enqueue(uuid, "repair_photo", payload) }
            .onFailure { message = "Impossible d'enregistrer la photo : ${it.message}"; return }
        refreshPending()
        message = "Photo mise en file. $pendingCount en attente de synchronisation."
    }

    suspend fun syncPerimeter() {
        val token = session.token ?: run { message = "Session expiree."; return }
        busy = true; message = null
        val outcome = SnapshotSync.refresh(token)
        busy = false
        when (outcome) {
            is SnapshotSync.Outcome.Refreshed -> {
                loadFromCache()
                message = if (outcome.raw) "Perimetre synchronise : ${all.size} reparation(s)."
                else "Perimetre deja a jour."
            }
            is SnapshotSync.Outcome.Failed -> message = outcome.message
        }
    }

    fun markDone(repair: JSONObject) {
        val id = repair.optString("id").takeIf { it.isNotBlank() } ?: run {
            message = "Reparation sans identifiant."; return
        }
        val uuid = UUID.randomUUID().toString()
        val payload = JSONObject().put("planning_id", id).put("local_uuid", uuid)
        runCatching { HydriaSyncQueueGateway.enqueue(uuid, "finish_repair", payload) }
            .onFailure { message = "Impossible d'enregistrer : ${it.message}"; return }
        refreshPending()
        message = "Marquee terminee. $pendingCount en attente de synchronisation."
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
    var editingId: String? by mutableStateOf(null)
        private set
    val editingExisting: Boolean get() = editingId != null

    var fEmployee: String by mutableStateOf("")
    var fWork: String by mutableStateOf("")
    var fActivity: String by mutableStateOf("")
    var fDate: String by mutableStateOf("")
    var fStatus: String by mutableStateOf("")
    var fPriority: String by mutableStateOf("")
    var fRemark: String by mutableStateOf("")

    val hasReferences: Boolean get() = references != null
    val employees: List<JSONObject> get() = refList("employes")
    val works: List<JSONObject> get() = refList("ouvrages")
    val activities: List<JSONObject>
        get() = mg.hydria.shared.rules.forms.ActivityCascadeTree.repairActivities(refList("repair_fiches"))
    val statuses: List<JSONObject> get() = refList("statuts")
    val priorities: List<JSONObject> get() = refList("priorites")

    private fun refList(key: String): List<JSONObject> {
        val arr = references?.optJSONArray(key) ?: return emptyList()
        return (0 until arr.length()).mapNotNull { arr.optJSONObject(it) }
    }

    fun openEditor(repair: JSONObject?) {
        if (!hasReferences) { message = "Synchronisez le perimetre pour charger les listes de saisie."; return }
        if (employees.isEmpty() || activities.isEmpty() || works.isEmpty()) {
            message = "Listes de reference vides. Verifiez vos droits Hydria puis resynchronisez."; return
        }
        editingId = repair?.optString("id")?.takeIf { it.isNotBlank() }
        fEmployee = repair?.optString("employe_id").orEmpty()
        fWork = repair?.optString("ouvrage_id").orEmpty()
        fActivity = repair?.optString("fiche_poste_id").orEmpty()
        fDate = repair?.optString("date_prevue")?.take(10)?.takeIf { it.isNotBlank() } ?: todayMadagascar().toString()
        fStatus = repair?.optString("statut_code").orEmpty().ifBlank { statuses.firstOrNull()?.optString("id").orEmpty() }
        fPriority = repair?.optString("priorite_code").orEmpty().ifBlank { "normale" }
        fRemark = repair?.optString("remarque").orEmpty()
        loadTargetState(repair)
        message = null
        editorOpen = true
    }

    fun closeEditor() { editorOpen = false }

    /** @return true si la reparation a ete mise en file. */
    fun saveRepairForm(): Boolean {
        val result = RepairFormRules.validate(
            RepairDraft(
                employeeId = fEmployee.takeIf { it.isNotBlank() },
                activityId = fActivity.takeIf { it.isNotBlank() },
                workId = fWork,
                date = fDate.trim(),
                status = fStatus.ifBlank { "en_cours" },
                priority = fPriority.ifBlank { "normale" },
                remark = fRemark,
                existingId = editingId,
                target = if (!targetKnown()) null else mg.hydria.shared.repairs.RepairTarget(
                    equipmentId = fTarget.removePrefix("eq:").takeIf { fTarget.startsWith("eq:") }.orEmpty(),
                    pointEauId = fTarget.removePrefix("pe:").takeIf { fTarget.startsWith("pe:") }.orEmpty(),
                    componentIds = fComponents.toList(),
                ),
            )
        )
        val err = result.error
        if (err != null) { message = err.message; return false }
        val fields = result.fields ?: run { message = "Formulaire invalide."; return false }
        val uuid = UUID.randomUUID().toString()
        val payload = JSONObject().apply {
            fields.forEach { (k, v) -> put(k, v) }
            put("local_uuid", uuid)
        }
        runCatching { HydriaSyncQueueGateway.enqueue(uuid, "save_repair", payload) }
            .onFailure { message = "Impossible d'enregistrer : ${it.message}"; return false }
        editorOpen = false
        refreshPending()
        message = if (editingId != null) "Modification mise en file. $pendingCount en attente."
        else "Nouvelle reparation mise en file. $pendingCount en attente."
        return true
    }

    // ── Synchronisation de la file (finish_repair + save_repair + repair_photo) ──

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
                    val type = row.optString("type")
                    if (type != "finish_repair" && type != "save_repair" && type != "repair_photo") continue
                    val localUuid = row.optString("local_uuid")
                    val payload = row.optJSONObject("payload") ?: continue
                    val result = runCatching {
                        when (type) {
                            "finish_repair" -> HydriaOperationsGateway.finishRepair(token, payload.optString("planning_id"))
                            "repair_photo" -> HydriaOperationsGateway.saveRepairPhoto(token, payload)
                            else -> HydriaOperationsGateway.saveRepair(token, payload)
                        }
                    }.getOrNull()
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
            append("$ok operation(s) synchronisee(s)")
            if (failed > 0) append(", $failed en erreur")
            append(".")
        }
    }
}
