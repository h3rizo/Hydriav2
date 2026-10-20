package mg.hydria.widget

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.view.View
import android.widget.RemoteViews
import android.widget.RemoteViewsService

/** Alimente la liste défilante du widget (ListView) à partir des lignes enregistrées par HydriaWidgetProvider. */
class HydriaWidgetService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory =
        Factory(applicationContext, intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID))

    private class Factory(private val context: Context, private val appWidgetId: Int) : RemoteViewsFactory {
        private var rows: List<WidgetRow> = emptyList()

        override fun onCreate() { rows = WidgetRowStore.load(context, appWidgetId) }
        override fun onDataSetChanged() { rows = WidgetRowStore.load(context, appWidgetId) }
        override fun onDestroy() { rows = emptyList() }
        override fun getCount() = rows.size
        override fun getViewTypeCount() = 4
        override fun getItemId(position: Int) = position.toLong()
        override fun hasStableIds() = false
        override fun getLoadingView(): RemoteViews? = null

        override fun getViewAt(position: Int): RemoteViews {
            val pkg = context.packageName
            return when (val row = rows.getOrNull(position)) {
                is WidgetRow.Header -> RemoteViews(pkg, R.layout.widget_row_header).apply {
                    setTextViewText(R.id.row_header_text, row.text)
                    // Léger espace au-dessus du titre, sauf pour le tout premier.
                    setViewPadding(R.id.row_header_text, 9, if (position == 0) 2 else 22, 0, 6)
                }
                is WidgetRow.Note -> RemoteViews(pkg, R.layout.widget_row_note).apply {
                    setTextViewText(R.id.row_note_text, row.text)
                }
                is WidgetRow.Tiles -> RemoteViews(pkg, R.layout.widget_row_tiles).apply {
                    bindTile(this, R.id.tile_left, R.id.value_left, R.id.label_left, R.id.amount_left, row.left)
                    if (row.right != null) {
                        bindTile(this, R.id.tile_right, R.id.value_right, R.id.label_right, R.id.amount_right, row.right)
                    } else {
                        // INVISIBLE (pas GONE) : la tuile seule garde la largeur d'une demi-ligne.
                        setViewVisibility(R.id.tile_right, View.INVISIBLE)
                    }
                }
                is WidgetRow.Periode -> RemoteViews(pkg, R.layout.widget_row_periode).apply {
                    setTextViewText(R.id.periode_title, row.title)
                    setViewPadding(R.id.periode_title, 0, if (position == 0) 2 else 18, 0, 0)
                    listOf(
                        "jour" to R.id.periode_jour,
                        "semaine" to R.id.periode_semaine,
                        "mois" to R.id.periode_mois,
                    ).forEach { (periode, viewId) ->
                        val active = periode == row.active
                        setTextColor(viewId, if (active) Color.parseColor("#0B1F2A") else Color.parseColor("#CCFFFFFF"))
                        setInt(viewId, "setBackgroundColor", if (active) Color.parseColor("#B9F3DF") else Color.parseColor("#1AFFFFFF"))
                        // DetailActivity enregistre la période, relance le widget et se ferme aussitôt.
                        setOnClickFillInIntent(viewId, Intent().putExtra(DetailActivity.EXTRA_PERIODE, periode))
                    }
                }
                null -> RemoteViews(pkg, R.layout.widget_row_note)
            }
        }

        private fun bindTile(v: RemoteViews, tileId: Int, valueId: Int, labelId: Int, amountId: Int, t: WidgetTile) {
            v.setViewVisibility(tileId, View.VISIBLE)
            v.setTextViewText(valueId, t.value)
            v.setTextColor(valueId, runCatching { Color.parseColor(t.color) }.getOrDefault(Color.WHITE))
            v.setTextViewText(labelId, t.label)
            v.setTextViewText(amountId, t.amount)
            v.setViewVisibility(amountId, if (t.amount.isEmpty()) View.GONE else View.VISIBLE)
            // Tuile sans liste détaillée (compteurs « fait ») : pas de clic.
            if (t.detailType.isEmpty()) return
            // Les extras complètent le PendingIntent modèle posé par le fournisseur (DetailActivity).
            v.setOnClickFillInIntent(tileId, Intent().apply {
                putExtra(DetailActivity.EXTRA_STAT_TYPE, t.detailType)
                putExtra(DetailActivity.EXTRA_LABEL, t.detailLabel)
            })
        }
    }
}
