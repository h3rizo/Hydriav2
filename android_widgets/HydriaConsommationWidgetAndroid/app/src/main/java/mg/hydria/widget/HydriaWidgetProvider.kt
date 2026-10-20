package mg.hydria.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.widget.RemoteViews
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class HydriaWidgetProvider : AppWidgetProvider() {
    companion object {
        const val ACTION_REFRESH = "mg.hydria.widget.consommation.ACTION_REFRESH"
        private val valueIds = intArrayOf(R.id.value_1, R.id.value_2, R.id.value_3, R.id.value_4)
        private val labels = arrayOf("Ouvrages", "Population", "Volume consommé · m³", "Conso / hab. / jour · L")
        private val keys = arrayOf("nb_ouvrages", "population", "volume_consomme", "conso_hab_jour")

        fun requestUpdate(context: Context) {
            context.sendBroadcast(Intent(context, HydriaWidgetProvider::class.java).apply { action = ACTION_REFRESH })
        }

        private fun formatValue(key: String, value: Double): String {
            val formatter = NumberFormat.getNumberInstance(Locale.FRANCE).apply {
                maximumFractionDigits = if (key == "nb_ouvrages" || key == "population") 0 else 1
            }
            return formatter.format(value)
        }

        private fun chartBitmap(labels: List<String>, values: List<Double>, bars: Boolean): Bitmap {
            val width = 720
            val height = 164
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            val grid = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(42, 230, 245, 247); strokeWidth = 2f }
            val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(175, 225, 240, 243); textSize = 18f; textAlign = Paint.Align.CENTER }
            val series = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = if (bars) Color.rgb(116, 201, 181) else Color.rgb(217, 181, 111); strokeWidth = 5f; style = Paint.Style.STROKE }
            val left = 18f
            val right = width - 12f
            val top = 10f
            val bottom = height - 29f
            repeat(3) { index ->
                val y = top + (bottom - top) * index / 2f
                canvas.drawLine(left, y, right, y, grid)
            }
            val maximum = (values.maxOrNull() ?: 0.0).coerceAtLeast(1.0)
            val step = (right - left) / values.size.coerceAtLeast(1)
            labels.forEachIndexed { index, label -> canvas.drawText(label, left + step * (index + .5f), height - 6f, text) }
            if (bars) {
                series.style = Paint.Style.FILL
                values.forEachIndexed { index, value ->
                    val barHeight = ((value / maximum) * (bottom - top)).toFloat()
                    val x = left + step * index + step * .2f
                    val y = bottom - barHeight
                    canvas.drawRoundRect(x, y, left + step * index + step * .8f, bottom, 5f, 5f, series)
                    val valueLabel = Paint(text).apply { color = Color.rgb(243, 251, 253); textSize = 16f }
                    canvas.drawText(String.format(Locale.FRANCE, "%.1f", value), x + step * .3f, (y - 5f).coerceAtLeast(16f), valueLabel)
                }
            } else {
                values.forEachIndexed { index, value ->
                    val x = left + step * (index + .5f)
                    val y = bottom - ((value / maximum) * (bottom - top)).toFloat()
                    if (index > 0) {
                        val previousX = left + step * (index - .5f)
                        val previousY = bottom - ((values[index - 1] / maximum) * (bottom - top)).toFloat()
                        canvas.drawLine(previousX, previousY, x, y, series)
                    }
                    val point = Paint(series).apply { style = Paint.Style.FILL }
                    canvas.drawCircle(x, y, 6f, point)
                    val valueLabel = Paint(text).apply { color = Color.rgb(243, 251, 253); textSize = 16f }
                    canvas.drawText(String.format(Locale.FRANCE, "%.1f", value), x, (y - 8f).coerceAtLeast(16f), valueLabel)
                }
            }
            return bitmap
        }

        private fun updateWidget(context: Context, manager: AppWidgetManager, appWidgetId: Int, finished: () -> Unit) {
            val views = RemoteViews(context.packageName, R.layout.hydria_widget)
            val configIntent = Intent(context, ConfigActivity::class.java).apply { putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId) }
            val configPending = PendingIntent.getActivity(context, appWidgetId, configIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            views.setOnClickPendingIntent(R.id.widget_title, configPending)
            views.setOnClickPendingIntent(R.id.widget_filters, configPending)
            views.setTextViewText(R.id.widget_filters, TokenStore.getFilters(context, appWidgetId).displaySummary())
            labels.forEachIndexed { index, label ->
                views.setTextViewText(intArrayOf(R.id.label_1, R.id.label_2, R.id.label_3, R.id.label_4)[index], label)
                views.setTextViewText(valueIds[index], "—")
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
                    val result = HydriaApi.fetchStats(token, TokenStore.getFilters(context, appWidgetId))
                    if (result.success && result.stats != null && result.charts != null) {
                        keys.forEachIndexed { index, key -> views.setTextViewText(valueIds[index], formatValue(key, result.stats[key] ?: 0.0)) }
                        views.setImageViewBitmap(R.id.chart_volumes, chartBitmap(result.charts.labels, result.charts.volumes, true))
                        views.setImageViewBitmap(R.id.chart_conso, chartBitmap(result.charts.labels, result.charts.consoHab, false))
                        val time = SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date())
                        views.setTextViewText(R.id.widget_status, "Mis à jour à $time · toucher le périmètre pour filtrer")
                    } else {
                        views.setTextViewText(R.id.widget_status, result.error ?: "Données indisponibles")
                        if (result.error == "Session expirée") TokenStore.clearToken(context)
                    }
                    manager.updateAppWidget(appWidgetId, views)
                } finally { finished() }
            }
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val pending = goAsync()
        if (ids.isEmpty()) return pending.finish()
        var remaining = ids.size
        ids.forEach { id -> updateWidget(context, manager, id) { remaining -= 1; if (remaining <= 0) runCatching { pending.finish() } } }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action != ACTION_REFRESH) return
        val pending: BroadcastReceiver.PendingResult = goAsync()
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(android.content.ComponentName(context, HydriaWidgetProvider::class.java))
        if (ids.isEmpty()) return pending.finish()
        var remaining = ids.size
        ids.forEach { id -> updateWidget(context, manager, id) { remaining -= 1; if (remaining <= 0) runCatching { pending.finish() } } }
    }

    override fun onDeleted(context: Context, ids: IntArray) {
        ids.forEach { TokenStore.clearFilters(context, it) }
        super.onDeleted(context, ids)
    }
}
