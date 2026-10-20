package mg.hydria.planningdujourwidget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.RemoteViews
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class PlanningDuJourWidgetProvider : AppWidgetProvider() {
    companion object {
        const val ACTION_REFRESH = "mg.hydria.planningdujourwidget.ACTION_REFRESH"
        const val MAX_ROWS = 5

        fun requestUpdate(context: Context) {
            context.sendBroadcast(Intent(context, PlanningDuJourWidgetProvider::class.java).setAction(ACTION_REFRESH))
        }

        fun todayIso(): String = SimpleDateFormat("yyyy-MM-dd", Locale.FRANCE).format(Date())
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        refresh(context)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action != ACTION_REFRESH) return
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try { refreshNow(context) } finally { pending.finish() }
        }
    }

    private fun refresh(context: Context) {
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try { refreshNow(context) } finally { pending.finish() }
        }
    }

    private suspend fun refreshNow(context: Context) {
        val token = TokenStore.getToken(context)
        val result = if (token == null) HydriaApi.ActivitesResult(false, error = "Touchez pour vous connecter")
            else HydriaApi.fetchActivites(
                token, todayIso(), todayIso(),
                employeId = TokenStore.getFiltreEmploye(context),
                baseId = TokenStore.getFiltreBase(context),
                regionId = TokenStore.getFiltreRegion(context),
                districtId = TokenStore.getFiltreDistrict(context),
                communeId = TokenStore.getFiltreCommune(context),
                typeActiviteIds = TokenStore.getFiltreTypes(context),
            )
        withContext(Dispatchers.Main) { updateAll(context, result) }
    }

    private fun updateAll(context: Context, result: HydriaApi.ActivitesResult) {
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(ComponentName(context, PlanningDuJourWidgetProvider::class.java))
        ids.forEach { manager.updateAppWidget(it, contentViews(context, it, result)) }
    }

    private fun contentViews(context: Context, widgetId: Int, result: HydriaApi.ActivitesResult): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.planning_du_jour_widget)
        val sorted = result.activites.sortedWith(compareBy({ it.date }, { it.heure }))
        views.setTextViewText(R.id.widget_count, sorted.size.toString())

        val rowIds = listOf(
            Triple(R.id.widget_row1, R.id.widget_row1_dot, Pair(R.id.widget_row1_title, R.id.widget_row1_sub)),
            Triple(R.id.widget_row2, R.id.widget_row2_dot, Pair(R.id.widget_row2_title, R.id.widget_row2_sub)),
            Triple(R.id.widget_row3, R.id.widget_row3_dot, Pair(R.id.widget_row3_title, R.id.widget_row3_sub)),
            Triple(R.id.widget_row4, R.id.widget_row4_dot, Pair(R.id.widget_row4_title, R.id.widget_row4_sub)),
            Triple(R.id.widget_row5, R.id.widget_row5_dot, Pair(R.id.widget_row5_title, R.id.widget_row5_sub)),
        )

        if (!result.success) {
            views.setTextViewText(R.id.widget_title, "PLANNING INDISPONIBLE")
            views.setViewVisibility(R.id.widget_empty, View.VISIBLE)
            views.setTextViewText(R.id.widget_empty, result.error ?: "Erreur de chargement")
            rowIds.forEach { (rowId, _, _) -> views.setViewVisibility(rowId, View.GONE) }
            views.setViewVisibility(R.id.widget_more, View.GONE)
        } else {
            views.setTextViewText(R.id.widget_title, "ACTIVITÉS DU JOUR")
            if (sorted.isEmpty()) {
                views.setViewVisibility(R.id.widget_empty, View.VISIBLE)
                views.setTextViewText(R.id.widget_empty, "Aucune activité aujourd’hui")
                rowIds.forEach { (rowId, _, _) -> views.setViewVisibility(rowId, View.GONE) }
                views.setViewVisibility(R.id.widget_more, View.GONE)
            } else {
                views.setViewVisibility(R.id.widget_empty, View.GONE)
                rowIds.forEachIndexed { index, (rowId, dotId, textIds) ->
                    val item = sorted.getOrNull(index)
                    if (item == null) {
                        views.setViewVisibility(rowId, View.GONE)
                    } else {
                        views.setViewVisibility(rowId, View.VISIBLE)
                        views.setImageViewResource(dotId, if (item.termine) R.drawable.dot_termine else R.drawable.dot_en_cours)
                        views.setTextViewText(textIds.first, item.activite)
                        val timePart = if (item.heure.isNotBlank()) item.heure else "Toute la journée"
                        val extra = listOf(item.employe, item.commune).filter { it.isNotBlank() }.joinToString(" · ")
                        views.setTextViewText(textIds.second, listOf(timePart, extra).filter { it.isNotBlank() }.joinToString(" · "))
                    }
                }
                val remaining = sorted.size - MAX_ROWS
                if (remaining > 0) {
                    views.setViewVisibility(R.id.widget_more, View.VISIBLE)
                    views.setTextViewText(R.id.widget_more, "+$remaining autre${if (remaining > 1) "s" else ""} · voir tout")
                } else {
                    views.setViewVisibility(R.id.widget_more, View.GONE)
                }
            }
        }

        val detailClass = if (TokenStore.getToken(context) == null) ConfigActivity::class.java else DetailActivity::class.java
        val openIntent = Intent(context, detailClass).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        views.setOnClickPendingIntent(R.id.widget_content, PendingIntent.getActivity(context, widgetId, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val refreshIntent = Intent(context, PlanningDuJourWidgetProvider::class.java).setAction(ACTION_REFRESH)
        views.setOnClickPendingIntent(R.id.widget_refresh, PendingIntent.getBroadcast(context, widgetId, refreshIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val settingsIntent = Intent(context, ConfigActivity::class.java).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        views.setOnClickPendingIntent(R.id.widget_settings, PendingIntent.getActivity(context, widgetId + 300000, settingsIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        return views
    }
}
