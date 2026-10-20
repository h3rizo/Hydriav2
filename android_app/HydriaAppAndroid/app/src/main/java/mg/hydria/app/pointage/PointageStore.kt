package mg.hydria.app.pointage

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate

/**
 * Mémoire locale du pointage : dernière réponse « aujourd'hui » (pour travailler hors
 * ligne) et journal des tentatives du téléphone (en attente / validé / refusé).
 * La file de synchronisation elle-même reste celle d'OfflineStore.
 */
object PointageStore {
    const val PENDING = "pending"
    const val OK = "ok"
    const val REFUSE = "refuse"
    private const val MAX_ENTRIES = 60

    data class Entry(val localUuid: String, val account: String, val type: String?, val status: String, val message: String, val atMs: Long)

    private var prefs: SharedPreferences? = null

    fun bind(context: Context) {
        prefs = context.applicationContext.getSharedPreferences("hydria_pointage", Context.MODE_PRIVATE)
    }

    private fun p() = checkNotNull(prefs) { "PointageStore.bind(context) doit être appelé au démarrage." }

    fun today(): LocalDate = LocalDate.now(PointageRules.ZONE)

    // -- cache de la réponse /pointage/aujourdhui ----------------------------------------------
    @Synchronized
    fun saveToday(account: String, json: JSONObject) {
        p().edit().putString("today_$account", json.toString()).apply()
    }

    /** Réponse en cache, seulement si elle date d'aujourd'hui (heure de Madagascar). */
    @Synchronized
    fun cachedToday(account: String): JSONObject? {
        val json = p().getString("today_$account", null)?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return null
        return if (json.optString("date") == today().toString()) json else null
    }

    // -- créneaux prévus des prochains jours (rappels locaux) --------------------------------------
    @Synchronized
    fun saveUpcoming(account: String, calendrier: JSONArray) {
        p().edit().putString("upcoming", calendrier.toString()).putString("upcoming_account", account).apply()
    }

    fun upcoming(): JSONArray =
        runCatching { JSONArray(p().getString("upcoming", "[]")) }.getOrDefault(JSONArray())

    fun upcomingAccount(): String = p().getString("upcoming_account", "") ?: ""

    /** Codes des alarmes déjà programmées, pour pouvoir les annuler avant de reprogrammer. */
    fun alarmCodes(): Set<Int> =
        (p().getStringSet("alarm_codes", emptySet()) ?: emptySet()).mapNotNull { it.toIntOrNull() }.toSet()

    fun saveAlarmCodes(codes: Set<Int>) {
        p().edit().putStringSet("alarm_codes", codes.map { it.toString() }.toSet()).apply()
    }

    // -- journal des tentatives ------------------------------------------------------------------
    @Synchronized
    private fun readAll(): MutableList<Entry> {
        val array = runCatching { JSONArray(p().getString("log", "[]")) }.getOrDefault(JSONArray())
        return (0 until array.length()).map {
            val o = array.getJSONObject(it)
            Entry(o.getString("local_uuid"), o.optString("account"), o.optString("type").ifBlank { null },
                o.getString("status"), o.optString("message"), o.optLong("at_ms"))
        }.toMutableList()
    }

    @Synchronized
    private fun writeAll(entries: List<Entry>) {
        val array = JSONArray()
        entries.takeLast(MAX_ENTRIES).forEach {
            array.put(JSONObject().put("local_uuid", it.localUuid).put("account", it.account)
                .put("type", it.type ?: JSONObject.NULL).put("status", it.status)
                .put("message", it.message).put("at_ms", it.atMs))
        }
        p().edit().putString("log", array.toString()).apply()
    }

    @Synchronized
    fun addPending(localUuid: String, account: String, type: String?, atMs: Long) {
        val entries = readAll().filterNot { it.localUuid == localUuid }.toMutableList()
        entries.add(Entry(localUuid, account, type, PENDING, "", atMs))
        writeAll(entries)
    }

    @Synchronized
    fun resolve(localUuid: String, status: String, message: String, type: String? = null, account: String = "", atMs: Long = System.currentTimeMillis()) {
        val entries = readAll()
        val index = entries.indexOfFirst { it.localUuid == localUuid }
        if (index >= 0) {
            val old = entries[index]
            entries[index] = old.copy(status = status, message = message, type = type ?: old.type)
        } else {
            entries.add(Entry(localUuid, account, type, status, message, atMs))
        }
        writeAll(entries)
    }

    /** Tentatives d'aujourd'hui (heure de Madagascar) pour ce compte. */
    fun todayEntries(account: String): List<Entry> = readAll().filter {
        it.account == account &&
            Instant.ofEpochMilli(it.atMs).atZone(PointageRules.ZONE).toLocalDate() == today()
    }

    fun pendingCount(account: String): Int = todayEntries(account).count { it.status == PENDING }
}
