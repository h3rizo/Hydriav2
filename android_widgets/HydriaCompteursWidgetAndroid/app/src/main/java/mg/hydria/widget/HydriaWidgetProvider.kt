package mg.hydria.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.view.View
import android.widget.RemoteViews
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class HydriaWidgetProvider : AppWidgetProvider() {
    companion object {
        const val ACTION_REFRESH = "mg.hydria.widget.compteurs.ACTION_REFRESH"
        private const val WIDGET_TITLE = "Compteurs de tête"

        private data class Tile(val key: String, val status: String, val label: String)

        private val tiles = listOf(
            Tile("good", "good", "✓ Réseau bon · < 5 %"),
            Tile("acceptable", "acceptable", "≈ Écart tolérable · 5–10 %"),
            Tile("investigate", "investigate", "! À investiguer · 10–20 %"),
            Tile("critical", "critical", "▲ Anormaux · > 20 %"),
            Tile("non_mesure", "non_mesure", "— Sans relevé exploitable"),
            Tile("hors_service", "hors_service", "× Compteurs hors service"),
        )
        private val tileIds = intArrayOf(
            R.id.tile_1, R.id.tile_2, R.id.tile_3, R.id.tile_4,
            R.id.tile_5, R.id.tile_6, R.id.tile_7, R.id.tile_8,
        )
        private val valueIds = intArrayOf(
            R.id.value_1, R.id.value_2, R.id.value_3, R.id.value_4,
            R.id.value_5, R.id.value_6, R.id.value_7, R.id.value_8,
        )
        private val labelIds = intArrayOf(
            R.id.label_1, R.id.label_2, R.id.label_3, R.id.label_4,
            R.id.label_5, R.id.label_6, R.id.label_7, R.id.label_8,
        )

        fun requestUpdate(context: Context) {
            context.sendBroadcast(Intent(context, HydriaWidgetProvider::class.java).apply {
                action = ACTION_REFRESH
            })
        }

        private fun detailPendingIntent(
            context: Context,
            appWidgetId: Int,
            index: Int,
            tile: Tile,
        ): PendingIntent {
            val intent = Intent(context, DetailActivity::class.java).apply {
                putExtra(DetailActivity.EXTRA_STAT_TYPE, tile.status)
                putExtra(DetailActivity.EXTRA_LABEL, tile.label)
                putExtra(DetailActivity.EXTRA_APP_WIDGET_ID, appWidgetId)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            return PendingIntent.getActivity(
                context,
                appWidgetId * 100 + index,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }

        private fun updateWidget(
            context: Context,
            manager: AppWidgetManager,
            appWidgetId: Int,
            finished: () -> Unit,
        ) {
            val views = RemoteViews(context.packageName, R.layout.hydria_widget)
            views.setTextViewText(R.id.widget_title, WIDGET_TITLE)
            val configIntent = Intent(context, ConfigActivity::class.java).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            }
            val configPending = PendingIntent.getActivity(
                context,
                appWidgetId,
                configIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            views.setOnClickPendingIntent(R.id.widget_title, configPending)
            views.setOnClickPendingIntent(R.id.widget_filters, configPending)

            val filters = TokenStore.getFilters(context, appWidgetId)
            views.setTextViewText(R.id.widget_filters, filters.displaySummary())
            tileIds.forEachIndexed { index, tileId ->
                if (index < tiles.size) {
                    val tile = tiles[index]
                    views.setViewVisibility(tileId, View.VISIBLE)
                    views.setTextViewText(labelIds[index], tile.label)
                    views.setTextViewText(valueIds[index], "—")
                    views.setOnClickPendingIntent(tileId, detailPendingIntent(context, appWidgetId, index + 1, tile))
                } else {
                    views.setViewVisibility(tileId, View.GONE)
                }
            }
            manager.updateAppWidget(appWidgetId, views)

            val token = TokenStore.getToken(context)
            if (token == null) {
                views.setTextViewText(R.id.widget_status, "Non connecté · toucher le titre")
                manager.updateAppWidget(appWidgetId, views)
                finished()
                return
            }

            views.setTextViewText(R.id.widget_status, "Chargement…")
            manager.updateAppWidget(appWidgetId, views)
            CoroutineScope(Dispatchers.Main).launch {
                try {
                    val result = HydriaApi.fetchStats(token, filters)
                    if (result.success && result.stats != null) {
                        val stats = result.stats
                        views.setTextViewText(R.id.widget_total, (stats["total"] ?: 0).toString())
                        tiles.forEachIndexed { index, tile ->
                            val value = stats[tile.key]
                            views.setTextViewText(valueIds[index], value?.toString() ?: "—")
                            if ((tile.status == "critical" || tile.status == "investigate" ||
                                    tile.status == "critique" || tile.status == "baisse" ||
                                    tile.status == "surveille" || tile.status == "hors_service") &&
                                (value ?: 0) > 0
                            ) {
                                views.setTextColor(valueIds[index], Color.parseColor("#FFFFBD72"))
                            }
                        }
                        val time = SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date())
                        views.setTextViewText(R.id.widget_status, "Mis à jour à $time")
                    } else {
                        views.setTextViewText(R.id.widget_status, result.error ?: "Données indisponibles")
                        if (result.error == "Session expirée") TokenStore.clearToken(context)
                    }
                    manager.updateAppWidget(appWidgetId, views)
                } finally {
                    finished()
                }
            }
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val pending = goAsync()
        if (ids.isEmpty()) return pending.finish()
        var remaining = ids.size
        ids.forEach { id ->
            updateWidget(context, manager, id) {
                remaining -= 1
                if (remaining <= 0) runCatching { pending.finish() }
            }
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action != ACTION_REFRESH) return
        val pending: BroadcastReceiver.PendingResult = goAsync()
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(
            android.content.ComponentName(context, HydriaWidgetProvider::class.java)
        )
        if (ids.isEmpty()) return pending.finish()
        var remaining = ids.size
        ids.forEach { id ->
            updateWidget(context, manager, id) {
                remaining -= 1
                if (remaining <= 0) runCatching { pending.finish() }
            }
        }
    }

    override fun onDeleted(context: Context, ids: IntArray) {
        ids.forEach { TokenStore.clearFilters(context, it) }
        super.onDeleted(context, ids)
    }
}

