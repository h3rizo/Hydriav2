package mg.hydria.planningwidget

import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.view.View
import android.widget.RemoteViews
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * Widget combiné "Calendrier planning" + "Activités du jour" : la grille
 * calendaire du mois occupe le haut, et l'agenda du jour actuellement
 * sélectionné (aujourd'hui par défaut) s'affiche en dessous. Toucher un
 * jour de la grille change le jour affiché dans l'agenda — sans quitter le
 * widget — puisque les deux sections partagent le même appel réseau
 * (fetchActivites sur toute la grille de 42 jours visible).
 */
class PlanningWidgetProvider : AppWidgetProvider() {
    companion object {
        const val ACTION_REFRESH = "mg.hydria.planningwidget.ACTION_REFRESH"
        const val ACTION_PREV_MONTH = "mg.hydria.planningwidget.ACTION_PREV_MONTH"
        const val ACTION_NEXT_MONTH = "mg.hydria.planningwidget.ACTION_NEXT_MONTH"
        const val ACTION_SELECT_DAY = "mg.hydria.planningwidget.ACTION_SELECT_DAY"
        const val EXTRA_DATE_ISO = "date_iso"
        const val AGENDA_MAX_ROWS = 4
        private val ISO_FORMAT = SimpleDateFormat("yyyy-MM-dd", Locale.FRANCE)
        private val MONTH_FORMAT = SimpleDateFormat("MMMM yyyy", Locale.FRANCE)
        private val DAY_LABEL_FORMAT = SimpleDateFormat("EEEE d MMMM", Locale.FRANCE)

        fun requestUpdate(context: Context) {
            context.sendBroadcast(Intent(context, PlanningWidgetProvider::class.java).setAction(ACTION_REFRESH))
        }

        fun todayIso(): String = isoDate(Calendar.getInstance())

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

        /**
         * Jour affiché par défaut dans l'agenda quand aucune sélection
         * explicite n'a été faite (premier chargement, ou après un
         * changement de mois qui invalide la sélection précédente) :
         * aujourd'hui si le mois affiché est le mois courant, sinon le 1er
         * jour du mois affiché (aujourd'hui n'y serait pas visible).
         */
        private fun defaultSelectedIso(monthStart: Calendar): String {
            val now = Calendar.getInstance()
            return if (monthKey(monthStart) == monthKey(now)) todayIso() else isoDate(monthStart)
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        refresh(context)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        when (intent.action) {
            ACTION_PREV_MONTH -> {
                TokenStore.saveMonthOffset(context, TokenStore.getMonthOffset(context) - 1)
                TokenStore.saveSelectedDateIso(context, null)
            }
            ACTION_NEXT_MONTH -> {
                TokenStore.saveMonthOffset(context, TokenStore.getMonthOffset(context) + 1)
                TokenStore.saveSelectedDateIso(context, null)
            }
            ACTION_SELECT_DAY -> {
                val iso = intent.getStringExtra(EXTRA_DATE_ISO) ?: return
                TokenStore.saveSelectedDateIso(context, iso)
            }
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
        val ids = manager.getAppWidgetIds(ComponentName(context, PlanningWidgetProvider::class.java))
        ids.forEach { manager.updateAppWidget(it, contentViews(context, it, result, monthStart, gridStart)) }
    }

    // Une seule TextView par case (cf. planning_widget.xml) : le nombre
    // d'activites est incruste dans le texte via un Spannable colore
    // (buildCellText), pas une sous-vue separee — necessaire pour rester
    // sous la limite de vues RemoteViews d'un AppWidget (cf. commentaire
    // en tete de planning_widget.xml).
    private fun cellRefs(): List<Int> = listOf(
        R.id.cal_cell_0, R.id.cal_cell_1, R.id.cal_cell_2, R.id.cal_cell_3, R.id.cal_cell_4, R.id.cal_cell_5, R.id.cal_cell_6,
        R.id.cal_cell_7, R.id.cal_cell_8, R.id.cal_cell_9, R.id.cal_cell_10, R.id.cal_cell_11, R.id.cal_cell_12, R.id.cal_cell_13,
        R.id.cal_cell_14, R.id.cal_cell_15, R.id.cal_cell_16, R.id.cal_cell_17, R.id.cal_cell_18, R.id.cal_cell_19, R.id.cal_cell_20,
        R.id.cal_cell_21, R.id.cal_cell_22, R.id.cal_cell_23, R.id.cal_cell_24, R.id.cal_cell_25, R.id.cal_cell_26, R.id.cal_cell_27,
        R.id.cal_cell_28, R.id.cal_cell_29, R.id.cal_cell_30, R.id.cal_cell_31, R.id.cal_cell_32, R.id.cal_cell_33, R.id.cal_cell_34,
        R.id.cal_cell_35, R.id.cal_cell_36, R.id.cal_cell_37, R.id.cal_cell_38, R.id.cal_cell_39, R.id.cal_cell_40, R.id.cal_cell_41,
    )

    // Idem pour l'agenda : une seule TextView par ligne (puce + titre +
    // sous-titre combines via buildAgendaRowText), pas de sous-vues.
    private fun agendaRowRefs(): List<Int> = listOf(
        R.id.agenda_row1, R.id.agenda_row2, R.id.agenda_row3, R.id.agenda_row4,
    )

    private fun dayLabel(iso: String): String = try {
        val parsed = ISO_FORMAT.parse(iso)
        if (parsed != null) DAY_LABEL_FORMAT.format(parsed).replaceFirstChar { it.titlecase(Locale.FRANCE) } else iso
    } catch (_: Exception) { iso }

    /** "15" seul, ou "15\n3" avec le compteur colore (vert si tout termine, orange sinon). */
    private fun buildCellText(day: Int, count: Int, allDone: Boolean): CharSequence {
        if (count <= 0) return day.toString()
        val builder = SpannableStringBuilder(day.toString()).append("\n")
        val countStart = builder.length
        builder.append(count.toString())
        val color = if (allDone) Color.parseColor("#6FCF97") else Color.parseColor("#F2A65A")
        builder.setSpan(ForegroundColorSpan(color), countStart, builder.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        builder.setSpan(StyleSpan(Typeface.BOLD), countStart, builder.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        builder.setSpan(RelativeSizeSpan(0.82f), countStart, builder.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        return builder
    }

    /** "● Titre\nHeure · lieu" — puce coloree selon le statut, titre en gras, sous-titre attenue. */
    private fun buildAgendaRowText(item: HydriaApi.PlanningActivite): CharSequence {
        val builder = SpannableStringBuilder()
        val dotStart = builder.length
        builder.append("●  ")
        val dotColor = if (item.termine) Color.parseColor("#6FCF97") else Color.parseColor("#F2A65A")
        builder.setSpan(ForegroundColorSpan(dotColor), dotStart, dotStart + 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        val titleStart = builder.length
        builder.append(item.activite)
        builder.setSpan(StyleSpan(Typeface.BOLD), titleStart, builder.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        builder.append("\n")
        val subStart = builder.length
        val timePart = if (item.heure.isNotBlank()) item.heure else "Toute la journée"
        val extra = listOf(item.employe, item.commune).filter { it.isNotBlank() }.joinToString(" · ")
        builder.append(listOf(timePart, extra).filter { it.isNotBlank() }.joinToString(" · "))
        builder.setSpan(ForegroundColorSpan(Color.parseColor("#91AAB0")), subStart, builder.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        builder.setSpan(RelativeSizeSpan(0.86f), subStart, builder.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        return builder
    }

    private fun contentViews(context: Context, widgetId: Int, result: HydriaApi.ActivitesResult, monthStart: Calendar, gridStart: Calendar): RemoteViews {
        val views = RemoteViews(context.packageName, R.layout.planning_widget)
        val token = TokenStore.getToken(context)
        val detailClass = if (token == null) ConfigActivity::class.java else DetailActivity::class.java
        val selectedIso = TokenStore.getSelectedDateIso(context) ?: defaultSelectedIso(monthStart)

        val monthTitle = MONTH_FORMAT.format(monthStart.time).replaceFirstChar { it.titlecase(Locale.FRANCE) }
        views.setTextViewText(R.id.widget_month_title, monthTitle)
        views.setTextViewText(R.id.widget_title, "PLANNING")

        fun openDetail(requestCode: Int, iso: String): PendingIntent {
            val detailIntent = Intent(context, detailClass)
                .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
                .putExtra(EXTRA_DATE_ISO, iso)
            return PendingIntent.getActivity(context, requestCode, detailIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        }

        views.setOnClickPendingIntent(R.id.widget_month_title, openDetail(widgetId, selectedIso))
        val refreshIntent = Intent(context, PlanningWidgetProvider::class.java).setAction(ACTION_REFRESH)
        views.setOnClickPendingIntent(R.id.widget_refresh, PendingIntent.getBroadcast(context, widgetId, refreshIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val prevIntent = Intent(context, PlanningWidgetProvider::class.java).setAction(ACTION_PREV_MONTH)
        views.setOnClickPendingIntent(R.id.widget_prev, PendingIntent.getBroadcast(context, widgetId + 100000, prevIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val nextIntent = Intent(context, PlanningWidgetProvider::class.java).setAction(ACTION_NEXT_MONTH)
        views.setOnClickPendingIntent(R.id.widget_next, PendingIntent.getBroadcast(context, widgetId + 200000, nextIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val settingsIntent = Intent(context, ConfigActivity::class.java).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        views.setOnClickPendingIntent(R.id.widget_settings, PendingIntent.getActivity(context, widgetId + 300000, settingsIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))

        if (!result.success) {
            views.setTextViewText(R.id.widget_count, "!")
            views.setTextViewText(R.id.agenda_header, result.error ?: "Erreur Hydria")
            agendaRowRefs().forEach { rowId -> views.setViewVisibility(rowId, View.GONE) }
            views.setViewVisibility(R.id.agenda_empty, View.GONE)
            views.setViewVisibility(R.id.agenda_more, View.GONE)
            return views
        }

        val byDate = result.activites.groupBy { it.date }
        val monthKeyValue = monthKey(monthStart)
        var monthTotal = 0
        val todayIso = todayIso()
        val cellDate = gridStart.clone() as Calendar
        cellRefs().forEachIndexed { index, cellId ->
            val iso = isoDate(cellDate)
            val outside = monthKey(cellDate) != monthKeyValue
            val dayItems = byDate[iso].orEmpty()
            val count = dayItems.size
            val allDone = count > 0 && dayItems.all { it.termine }
            if (!outside) monthTotal += count

            views.setTextViewText(cellId, buildCellText(cellDate.get(Calendar.DAY_OF_MONTH), count, allDone))
            views.setTextColor(cellId, if (outside) Color.parseColor("#5A6E75") else Color.parseColor("#FFFFFF"))
            val background = when {
                iso == selectedIso -> R.drawable.cal_cell_selected_background
                iso == todayIso -> R.drawable.cal_cell_today_background
                else -> R.drawable.cal_cell_background
            }
            views.setInt(cellId, "setBackgroundResource", background)

            // Toucher un jour met à jour l'agenda en dessous (broadcast vers
            // le provider, pas de changement d'écran) — voir onReceive/ACTION_SELECT_DAY.
            val selectIntent = Intent(context, PlanningWidgetProvider::class.java)
                .setAction(ACTION_SELECT_DAY)
                .putExtra(EXTRA_DATE_ISO, iso)
            views.setOnClickPendingIntent(
                cellId,
                PendingIntent.getBroadcast(context, widgetId * 1000 + index, selectIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE),
            )

            cellDate.add(Calendar.DAY_OF_YEAR, 1)
        }
        views.setTextViewText(R.id.widget_count, monthTotal.toString())

        // --- Agenda du jour sélectionné, en dessous de la grille ---
        val agendaItems = byDate[selectedIso].orEmpty().sortedWith(compareBy { it.heure })
        val headerLabel = if (selectedIso == todayIso) "AUJOURD’HUI" else dayLabel(selectedIso).uppercase(Locale.FRANCE)
        views.setTextViewText(R.id.agenda_header, "$headerLabel · ${agendaItems.size} activité${if (agendaItems.size > 1) "s" else ""}")

        val agendaContentIntent = openDetail(widgetId + 400000, selectedIso)
        views.setOnClickPendingIntent(R.id.agenda_header, agendaContentIntent)

        if (agendaItems.isEmpty()) {
            views.setViewVisibility(R.id.agenda_empty, View.VISIBLE)
            views.setTextViewText(
                R.id.agenda_empty,
                if (selectedIso == todayIso) "Aucune activité aujourd’hui" else "Aucune activité planifiée ce jour-là",
            )
            agendaRowRefs().forEach { rowId -> views.setViewVisibility(rowId, View.GONE) }
            views.setViewVisibility(R.id.agenda_more, View.GONE)
        } else {
            views.setViewVisibility(R.id.agenda_empty, View.GONE)
            agendaRowRefs().forEachIndexed { index, rowId ->
                val item = agendaItems.getOrNull(index)
                if (item == null) {
                    views.setViewVisibility(rowId, View.GONE)
                } else {
                    views.setViewVisibility(rowId, View.VISIBLE)
                    views.setTextViewText(rowId, buildAgendaRowText(item))
                    views.setOnClickPendingIntent(rowId, agendaContentIntent)
                }
            }
            val remaining = agendaItems.size - AGENDA_MAX_ROWS
            if (remaining > 0) {
                views.setViewVisibility(R.id.agenda_more, View.VISIBLE)
                views.setTextViewText(R.id.agenda_more, "+$remaining autre${if (remaining > 1) "s" else ""} · voir tout")
                views.setOnClickPendingIntent(R.id.agenda_more, agendaContentIntent)
            } else {
                views.setViewVisibility(R.id.agenda_more, View.GONE)
            }
        }
        return views
    }
}
