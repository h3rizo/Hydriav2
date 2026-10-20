package mg.hydria.planningcalendrierwidget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.view.View
import android.widget.RemoteViews
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

class PlanningCalendrierWidgetProvider : AppWidgetProvider() {
    companion object {
        const val ACTION_REFRESH = "mg.hydria.planningcalendrierwidget.ACTION_REFRESH"
        const val ACTION_PREV_MONTH = "mg.hydria.planningcalendrierwidget.ACTION_PREV_MONTH"
        const val ACTION_NEXT_MONTH = "mg.hydria.planningcalendrierwidget.ACTION_NEXT_MONTH"
        const val EXTRA_DATE_ISO = "date_iso"
        private val ISO_FORMAT = SimpleDateFormat("yyyy-MM-dd", Locale.FRANCE)
        private val MONTH_FORMAT = SimpleDateFormat("MMMM yyyy", Locale.FRANCE)

        fun requestUpdate(context: Context) {
            context.sendBroadcast(Intent(context, PlanningCalendrierWidgetProvider::class.java).setAction(ACTION_REFRESH))
        }

        private fun isoDate(cal: Calendar): String = ISO_FORMAT.format(cal.time)

        private fun monthKey(cal: Calendar): String = "${cal.get(Calendar.YEAR)}-${cal.get(Calendar.MONTH)}"

        private fun displayedMonthStart(context: Context): Calendar {
            val cal = Calendar.getInstance()
            cal.set(Calendar.DAY_OF_MONTH, 1)
            cal.set(Calendar.HOUR_OF_DAY, 0); cal.set(Calendar.MINUTE, 0); cal.set(Calendar.SECOND, 0); cal.set(Calendar.MILLISECOND, 0)
            cal.add(Calendar.MONTH, TokenStore.getMonthOffset(context))
            return cal
        }

        private fun gridStartFor(monthStart: Calendar): Calendar {
            val firstWeekday = (monthStart.get(Calendar.DAY_OF_WEEK) + 5) % 7 // 0 = lundi
            val cal = monthStart.clone() as Calendar
            cal.add(Calendar.DAY_OF_YEAR, -firstWeekday)
            return cal
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        refresh(context)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            ACTION_PREV_MONTH -> TokenStore.saveMonthOffset(context, TokenStore.getMonthOffset(context) - 1)
            ACTION_NEXT_MONTH -> TokenStore.saveMonthOffset(context, TokenStore.getMonthOffset(context) + 1)
            ACTION_REFRESH -> Unit
            else -> return
        }
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
        val monthStart = displayedMonthStart(context)
        val gridStart = gridStartFor(monthStart)
        val gridEnd = gridStart.clone() as Calendar
        gridEnd.add(Calendar.DAY_OF_YEAR, 41)
        val result = if (token == null) HydriaApi.ActivitesResult(false, error = "Touchez pour vous connecter")
            else HydriaApi.fetchActivites(
                token, isoDate(gridStart), isoDate(gridEnd),
                employeId = TokenStore.getFiltreEmploye(context),
                baseId = TokenStore.getFiltreBase(context),
                regionId = TokenStore.getFiltreRegion(context),
                districtId = TokenStore.getFiltreDistrict(context),
                communeId = TokenStore.getFiltreCommune(context),
                typeActiviteIds = TokenStore.getFiltreTypes(context),
            )
        withContext(Dispatchers.Main) { updateAll(context, result, monthStart, gridStart) }
    }

    private fun updateAll(context: Context, result: HydriaApi.ActivitesResult, monthStart: Calendar, gridStart: Calendar) {
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(ComponentName(context, PlanningCalendrierWidgetProvider::class.java))
        ids.forEach { manager.updateAppWidget(it, contentViews(context, it, result, monthStart, gridStart)) }
    }

    private fun cellRefs(): List<Triple<Int, Int, Int>> = listOf(
        Triple(R.id.cal_cell_0, R.id.cal_cell_0_day, R.id.cal_cell_0_count),
        Triple(R.id.cal_cell_1, R.id.cal_cell_1_day, R.id.cal_cell_1_count),
        Triple(R.id.cal_cell_2, R.id.cal_cell_2_day, R.id.cal_cell_2_count),
        Triple(R.id.cal_cell_3, R.id.cal_cell_3_day, R.id.cal_cell_3_count),
        Triple(R.id.cal_cell_4, R.id.cal_cell_4_day, R.id.cal_cell_4_count),
        Triple(R.id.cal_cell_5, R.id.cal_cell_5_day, R.id.cal_cell_5_count),
        Triple(R.id.cal_cell_6, R.id.cal_cell_6_day, R.id.cal_cell_6_count),
        Triple(R.id.cal_cell_7, R.id.cal_cell_7_day, R.id.cal_cell_7_count),
        Triple(R.id.cal_cell_8, R.id.cal_cell_8_day, R.id.cal_cell_8_count),
        Triple(R.id.cal_cell_9, R.id.cal_cell_9_day, R.id.cal_cell_9_count),
        Triple(R.id.cal_cell_10, R.id.cal_cell_10_day, R.id.cal_cell_10_count),
        Triple(R.id.cal_cell_11, R.id.cal_cell_11_day, R.id.cal_cell_11_count),
        Triple(R.id.cal_cell_12, R.id.cal_cell_12_day, R.id.cal_cell_12_count),
        Triple(R.id.cal_cell_13, R.id.cal_cell_13_day, R.id.cal_cell_13_count),
        Triple(R.id.cal_cell_14, R.id.cal_cell_14_day, R.id.cal_cell_14_count),
        Triple(R.id.cal_cell_15, R.id.cal_cell_15_day, R.id.cal_cell_15_count),
        Triple(R.id.cal_cell_16, R.id.cal_cell_16_day, R.id.cal_cell_16_count),
        Triple(R.id.cal_cell_17, R.id.cal_cell_17_day, R.id.cal_cell_17_count),
        Triple(R.id.cal_cell_18, R.id.cal_cell_18_day, R.id.cal_cell_18_count),
        Triple(R.id.cal_cell_19, R.id.cal_cell_19_day, R.id.cal_cell_19_count),
        Triple(R.id.cal_cell_20, R.id.cal_cell_20_day, R.id.cal_cell_20_count),
        Triple(R.id.cal_cell_21, R.id.cal_cell_21_day, R.id.cal_cell_21_count),
        Triple(R.id.cal_cell_22, R.id.cal_cell_22_day, R.id.cal_cell_22_count),
        Triple(R.id.cal_cell_23, R.id.cal_cell_23_day, R.id.cal_cell_23_count),
        Triple(R.id.cal_cell_24, R.id.cal_cell_24_day, R.id.cal_cell_24_count),
        Triple(R.id.cal_cell_25, R.id.cal_cell_25_day, R.id.cal_cell_25_count),
        Triple(R.id.cal_cell_26, R.id.cal_cell_26_day, R.id.cal_cell_26_count),
        Triple(R.id.cal_cell_27, R.id.cal_cell_27_day, R.id.cal_cell_27_count),
        Triple(R.id.cal_cell_28, R.id.cal_cell_28_day, R.id.cal_cell_28_count),
        Triple(R.id.cal_cell_29, R.id.cal_cell_29_day, R.id.cal_cell_29_count),
        Triple(R.id.cal_cell_30, R.id.cal_cell_30_day, R.id.cal_cell_30_count),
        Triple(R.id.cal_cell_31, R.id.cal_cell_31_day, R.id.cal_cell_31_count),
        Triple(R.id.cal_cell_32, R.id.cal_cell_32_day, R.id.cal_cell_32_count),
        Triple(R.id.cal_cell_33, R.id.cal_cell_33_day, R.id.cal_cell_33_count),
        Triple(R.id.cal_cell_34, R.id.cal_cell_34_day, R.id.cal_cell_34_count),
        Triple(R.id.cal_cell_35, R.id.cal_cell_35_day, R.id.cal_cell_35_count),
        Triple(R.id.cal_cell_36, R.id.cal_cell_36_day, R.id.cal_cell_36_count),
        Triple(R.id.cal_cell_37, R.id.cal_cell_37_day, R.id.cal_cell_37_count),
        Triple(R.id.cal_cell_38, R.id.cal_cell_38_day, R.id.cal_cell_38_count),
        Triple(R.id.cal_cell_39, R.id.cal_cell_39_day, R.id.cal_cell_39_count),
        Triple(R.id.cal_cell_40, R.id.cal_cell_40_day, R.id.cal_cell_40_count),
        Triple(R.id.cal_cell_41, R.id.cal_cell_41_day, R.id.cal_cell_41_count),
    )

    private fun contentViews(context: Context, widgetId: Int, result: HydriaApi.ActivitesResult, monthStart: Calendar, gridStart: Calendar): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.planning_calendrier_widget)
        val token = TokenStore.getToken(context)
        val detailClass = if (token == null) ConfigActivity::class.java else DetailActivity::class.java

        val monthTitle = MONTH_FORMAT.format(monthStart.time).replaceFirstChar { it.titlecase(Locale.FRANCE) }
        views.setTextViewText(R.id.widget_month_title, monthTitle)
        views.setTextViewText(R.id.widget_title, "CALENDRIER PLANNING")

        val titleIntent = Intent(context, detailClass).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        views.setOnClickPendingIntent(R.id.widget_month_title, PendingIntent.getActivity(context, widgetId, titleIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val refreshIntent = Intent(context, PlanningCalendrierWidgetProvider::class.java).setAction(ACTION_REFRESH)
        views.setOnClickPendingIntent(R.id.widget_refresh, PendingIntent.getBroadcast(context, widgetId, refreshIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val prevIntent = Intent(context, PlanningCalendrierWidgetProvider::class.java).setAction(ACTION_PREV_MONTH)
        views.setOnClickPendingIntent(R.id.widget_prev, PendingIntent.getBroadcast(context, widgetId + 100000, prevIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val nextIntent = Intent(context, PlanningCalendrierWidgetProvider::class.java).setAction(ACTION_NEXT_MONTH)
        views.setOnClickPendingIntent(R.id.widget_next, PendingIntent.getBroadcast(context, widgetId + 200000, nextIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val settingsIntent = Intent(context, ConfigActivity::class.java).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        views.setOnClickPendingIntent(R.id.widget_settings, PendingIntent.getActivity(context, widgetId + 300000, settingsIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))

        if (!result.success) {
            views.setTextViewText(R.id.widget_count, "!")
        } else {
            val byDate = result.activites.groupBy { it.date }
            val monthKeyValue = monthKey(monthStart)
            var monthTotal = 0
            val todayIso = isoDate(Calendar.getInstance())
            val cellDate = gridStart.clone() as Calendar
            cellRefs().forEachIndexed { index, (containerId, dayId, countId) ->
                val iso = isoDate(cellDate)
                val outside = monthKey(cellDate) != monthKeyValue
                val dayItems = byDate[iso].orEmpty()
                val count = dayItems.size
                val allDone = count > 0 && dayItems.all { it.termine }
                if (!outside) monthTotal += count

                views.setTextViewText(dayId, cellDate.get(Calendar.DAY_OF_MONTH).toString())
                views.setTextColor(dayId, if (outside) Color.parseColor("#5A6E75") else Color.parseColor("#FFFFFF"))
                views.setInt(containerId, "setBackgroundResource", if (iso == todayIso) R.drawable.cal_cell_today_background else R.drawable.cal_cell_background)

                if (count > 0) {
                    views.setViewVisibility(countId, View.VISIBLE)
                    views.setTextViewText(countId, count.toString())
                    views.setInt(countId, "setBackgroundResource", if (allDone) R.drawable.dot_termine else R.drawable.dot_en_cours)
                } else {
                    views.setViewVisibility(countId, View.GONE)
                }

                val cellIntent = Intent(context, detailClass)
                    .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
                    .putExtra(EXTRA_DATE_ISO, iso)
                views.setOnClickPendingIntent(containerId, PendingIntent.getActivity(context, widgetId * 1000 + index, cellIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))

                cellDate.add(Calendar.DAY_OF_YEAR, 1)
            }
            views.setTextViewText(R.id.widget_count, monthTotal.toString())
        }
        return views
    }
}
