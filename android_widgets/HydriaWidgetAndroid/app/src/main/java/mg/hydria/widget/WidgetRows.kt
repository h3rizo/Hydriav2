package mg.hydria.widget

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Une tuile de stat affichée dans le widget (déjà formatée : le service de liste ne refait aucun calcul). */
data class WidgetTile(
    val value: String,
    val color: String,
    val label: String,
    val amount: String,
    val detailType: String,
    val detailLabel: String,
)

/**
 * Une ligne de la liste défilante du widget : titre de section, deux tuiles côte à côte, ou note
 * (impayé estimé). Un RemoteViews ne sait pas défiler autrement qu'avec une collection (ListView),
 * d'où cette liste de lignes persistée pour que le service de liste la relise à chaque rafraîchissement.
 */
sealed class WidgetRow {
    data class Header(val text: String) : WidgetRow()
    data class Note(val text: String) : WidgetRow()
    data class Tiles(val left: WidgetTile, val right: WidgetTile?) : WidgetRow()
    /** Titre de la section « Fait … » suivi du sélecteur J / S / M (période active mise en valeur). */
    data class Periode(val title: String, val active: String) : WidgetRow()
}

object WidgetRowStore {
    private const val PREFS = "hydria_widget_rows"

    private fun tileJson(t: WidgetTile) = JSONObject()
        .put("v", t.value).put("c", t.color).put("l", t.label)
        .put("a", t.amount).put("d", t.detailType).put("dl", t.detailLabel)

    private fun tileFrom(o: JSONObject) = WidgetTile(
        o.optString("v"), o.optString("c", "#FFFFFF"), o.optString("l"),
        o.optString("a"), o.optString("d"), o.optString("dl"),
    )

    fun save(context: Context, appWidgetId: Int, rows: List<WidgetRow>) {
        val array = JSONArray()
        rows.forEach { row ->
            array.put(when (row) {
                is WidgetRow.Header -> JSONObject().put("t", "h").put("text", row.text)
                is WidgetRow.Note -> JSONObject().put("t", "n").put("text", row.text)
                is WidgetRow.Periode -> JSONObject().put("t", "p").put("text", row.title).put("active", row.active)
                is WidgetRow.Tiles -> JSONObject().put("t", "r").put("l", tileJson(row.left))
                    .also { o -> row.right?.let { o.put("r", tileJson(it)) } }
            })
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString("rows_$appWidgetId", array.toString()).apply()
    }

    fun load(context: Context, appWidgetId: Int): List<WidgetRow> {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString("rows_$appWidgetId", null) ?: return emptyList()
        val array = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        return (0 until array.length()).mapNotNull { i ->
            val o = array.optJSONObject(i) ?: return@mapNotNull null
            when (o.optString("t")) {
                "h" -> WidgetRow.Header(o.optString("text"))
                "n" -> WidgetRow.Note(o.optString("text"))
                "p" -> WidgetRow.Periode(o.optString("text"), o.optString("active", "jour"))
                "r" -> WidgetRow.Tiles(tileFrom(o.getJSONObject("l")), o.optJSONObject("r")?.let(::tileFrom))
                else -> null
            }
        }
    }

    fun clear(context: Context, appWidgetId: Int) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove("rows_$appWidgetId").apply()
    }
}
