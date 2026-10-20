package mg.hydria.app.search

import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaUi
import org.json.JSONArray
import org.json.JSONObject
import java.text.NumberFormat
import java.util.Locale

/**
 * Fiche commune de la Recherche : synthèse (habitants, habitants desservis, villages, ouvrages), ouvrages et points
 * d'eau par type, diagramme de flux de la commune, puis listes de villages et d'ouvrages cliquables vers leurs fiches.
 * Toutes les données viennent du serveur (`details` de /recherche/api/mobile/details/commune/<id>/).
 */
class CommuneDetailRenderer(
    private val activity: AppCompatActivity,
    private val body: LinearLayout,
    private val renderPointsEau: (JSONObject) -> Unit,
    private val openDetail: (type: String, id: String, title: String) -> Unit,
) {
    private val density = activity.resources.displayMetrics.density
    private val numbers = NumberFormat.getIntegerInstance(Locale.FRANCE)

    fun render(details: JSONObject) {
        details.optJSONObject("synthese")?.let(::renderSynthese)
        details.optJSONArray("ouvrages_par_type")?.let(::renderOuvragesParType)
        details.optJSONObject("repartition_points_eau")?.let(renderPointsEau)
        details.optJSONObject("flux")?.let(::renderFlux)
        details.optJSONArray("villages")?.let { renderList("VILLAGES", it, "village") }
        details.optJSONArray("ouvrages")?.let { renderList("OUVRAGES", it, "ouvrage") }
    }

    // ── Synthèse ──────────────────────────────────────────────────────────────

    private fun renderSynthese(s: JSONObject) {
        val cards = listOf(
            Triple("Habitants", fmt(s.optInt("habitants")), "dans la commune"),
            Triple("Habitants desservis", fmt(s.optInt("habitants_desservis")), "${s.optInt("taux_desserte_pct")} % des habitants"),
            Triple("Villages", "${fmt(s.optInt("villages_desservis"))} / ${fmt(s.optInt("villages"))}", "desservis / total"),
            Triple("Ouvrages", "${fmt(s.optInt("ouvrages_fonctionnels"))} / ${fmt(s.optInt("ouvrages"))}", "fonctionnels / total"),
            Triple("Points d'eau en service", fmt(s.optInt("points_eau_en_service")), "branchés, non coupés"),
        )
        body.addView(text("SYNTHÈSE DE LA COMMUNE", 11f, true, HydriaColors.cyan), margin(top = 6, bottom = 6))
        cards.chunked(2).forEach { pair ->
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL }
            pair.forEachIndexed { index, (label, value, sub) ->
                row.addView(statCard(label, value, sub), LinearLayout.LayoutParams(0, -2, 1f).apply {
                    if (index == 0) marginEnd = dp(8)
                })
            }
            if (pair.size == 1) row.addView(View(activity), LinearLayout.LayoutParams(0, 1, 1f))
            body.addView(row, margin(bottom = 8))
        }
    }

    private fun statCard(label: String, value: String, sub: String) = LinearLayout(activity).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(10), dp(12), dp(10)); HydriaUi.card(this)
        addView(text(label, 11f, true, HydriaColors.textSecondary))
        addView(text(value, 22f, true, HydriaColors.text), margin(top = 3))
        addView(text(sub, 11f, false, HydriaColors.textSecondary), margin(top = 2))
    }

    // ── Ouvrages par type ─────────────────────────────────────────────────────

    private fun renderOuvragesParType(items: JSONArray) {
        if (items.length() == 0) return
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        card.addView(text("OUVRAGES PAR TYPE", 11f, true, HydriaColors.cyan))
        for (i in 0 until items.length()) {
            val row = items.getJSONObject(i)
            val total = row.optInt("count")
            val fonctionnels = row.optInt("fonctionnels")
            val horsService = total - fonctionnels
            card.addView(text("${row.optString("type")} : $total", 15f, true, HydriaColors.text), margin(top = 6))
            if (horsService > 0) {
                card.addView(text("   ↳ $fonctionnels fonctionnel(s) · $horsService non fonctionnel(s)", 13f, false, HydriaColors.error), margin(top = 2))
            }
        }
        body.addView(card, margin(top = 4, bottom = 8))
    }

    // ── Diagramme de flux ─────────────────────────────────────────────────────

    private fun renderFlux(flux: JSONObject) {
        val total = flux.optInt("total")
        val dimsJson = flux.optJSONObject("dimensions") ?: return
        val dims = FlowDiagramLayout.parseDimensions(dimsJson)
        val rows = FlowDiagramLayout.parseRows(flux.optJSONArray("rows") ?: JSONArray(), dims.keys)
        val defaults = flux.optJSONArray("defaut")?.let { a -> (0 until a.length()).map { a.optString(it) } } ?: dims.keys.toList()
        val order = defaults.filter { it in dims }.toMutableList()

        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        card.addView(text("DIAGRAMME DE FLUX DES VILLAGES", 11f, true, HydriaColors.cyan))
        card.addView(text(
            if (total > 0) "${fmt(total)} village(s) répartis selon les éléments choisis. Faites défiler vers la droite."
            else "Aucun village dans ce périmètre.",
            12f, false, HydriaColors.textSecondary,
        ), margin(top = 3, bottom = 8))
        if (total == 0) { body.addView(card, margin(bottom = 8)); return }

        val chooser = Button(activity).apply { HydriaUi.styleSecondary(this) }
        card.addView(chooser, LinearLayout.LayoutParams(-1, dp(46)))
        val view = FlowDiagramView(activity)
        card.addView(HorizontalScrollView(activity).apply {
            isHorizontalScrollBarEnabled = true; addView(view)
        }, margin(top = 8))

        fun redraw() {
            chooser.text = "Éléments affichés (${order.size}) — modifier"
            view.show(FlowDiagramLayout.build(
                rows, dims, order, "Villages de la commune",
                columnWidth = view.columnWidth, height = view.height, topMargin = view.topMargin,
                bottomMargin = view.bottomMargin, gap = view.gap, leftMargin = view.leftMargin, labelWidth = view.labelWidth,
            ))
        }
        chooser.setOnClickListener {
            val keys = dims.keys.toList()
            val checked = BooleanArray(keys.size) { keys[it] in order }
            AlertDialog.Builder(activity)
                .setTitle("Éléments du diagramme")
                .setMultiChoiceItems(keys.map { dims.getValue(it).title }.toTypedArray(), checked) { _, which, isChecked -> checked[which] = isChecked }
                .setPositiveButton("Appliquer") { _, _ ->
                    val kept = order.filter { checked[keys.indexOf(it)] }
                    val added = keys.filterIndexed { index, key -> checked[index] && key !in order }
                    val next = (kept + added).take(MAX_COLUMNS)
                    if (next.isEmpty()) {
                        Toast.makeText(activity, "Choisissez au moins un élément.", Toast.LENGTH_SHORT).show()
                    } else {
                        if (kept.size + added.size > MAX_COLUMNS) {
                            Toast.makeText(activity, "$MAX_COLUMNS éléments au maximum.", Toast.LENGTH_SHORT).show()
                        }
                        order.clear(); order.addAll(next); redraw()
                    }
                }
                .setNegativeButton("Annuler", null)
                .show()
        }
        redraw()
        body.addView(card, margin(bottom = 8))
    }

    // ── Listes cliquables ─────────────────────────────────────────────────────

    private fun renderList(title: String, items: JSONArray, type: String) {
        if (items.length() == 0) return
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        val heading = text("$title (${items.length()})", 11f, true, HydriaColors.cyan)
        card.addView(heading)
        val filter = EditText(activity).apply {
            hint = "Filtrer par nom…"; inputType = InputType.TYPE_CLASS_TEXT; setSingleLine(true); textSize = 14f
            setTextColor(HydriaColors.text); setHintTextColor(HydriaColors.textSecondary)
        }
        val rowsHost = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        card.addView(filter, margin(top = 6))
        card.addView(rowsHost, margin(top = 4))

        fun rebuild() {
            val query = filter.text.toString().trim().lowercase(Locale.ROOT)
            rowsHost.removeAllViews()
            var shown = 0
            for (i in 0 until items.length()) {
                val item = items.getJSONObject(i)
                if (query.isNotEmpty() && !item.optString("nom").lowercase(Locale.ROOT).contains(query)) continue
                rowsHost.addView(buildRow(item, type), margin(top = 6))
                shown++
            }
            heading.text = if (query.isEmpty()) "$title (${items.length()})" else "$title ($shown / ${items.length()})"
            if (shown == 0) rowsHost.addView(text("Aucun résultat.", 13f, false, HydriaColors.textSecondary), margin(top = 8))
        }
        filter.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) = rebuild()
        })
        rebuild()
        body.addView(card, margin(bottom = 8))
    }

    private fun buildRow(item: JSONObject, type: String): View {
        val name = item.optString("nom")
        val clickable = if (type == "village") item.optBoolean("cliquable", true) else true
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = HydriaUi.rounded(activity, HydriaColors.surfaceRaised, 12f, HydriaColors.outline)
            alpha = if (clickable) 1f else 0.6f
        }
        val left = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        left.addView(text(name, 15f, true, HydriaColors.text))
        if (type == "village") {
            val desservi = item.optBoolean("desservi")
            left.addView(text(
                "${fmt(item.optInt("habitants"))} habitant(s) · ${item.optInt("points_eau")} point(s) d'eau en service",
                12f, false, HydriaColors.textSecondary,
            ), margin(top = 2))
            left.addView(
                if (desservi) text("Desservi", 11f, true, HydriaColors.success)
                else text(if (clickable) "Non desservi" else "Non desservi · pas de fiche", 11f, true, HydriaColors.warning),
                margin(top = 2),
            )
        } else {
            left.addView(text(
                "${item.optString("type")} · ${item.optInt("points_eau")} point(s) d'eau en service",
                12f, false, HydriaColors.textSecondary,
            ), margin(top = 2))
            if (!item.optBoolean("fonctionnel", true)) left.addView(text("⚠ Non fonctionnel", 11f, true, HydriaColors.error), margin(top = 2))
        }
        row.addView(left, LinearLayout.LayoutParams(0, -2, 1f))
        if (clickable) {
            row.addView(text("›", 24f, true, HydriaColors.textSecondary))
            row.setOnClickListener { openDetail(type, item.optString("id"), name) }
        }
        return row
    }

    // ── Utilitaires ───────────────────────────────────────────────────────────

    private fun fmt(value: Int): String = numbers.format(value).replace(' ', ' ').replace(' ', ' ')

    private fun text(value: String, size: Float, bold: Boolean, color: Int) = TextView(activity).apply {
        text = value; textSize = size; setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun margin(top: Int = 0, bottom: Int = 0) =
        LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top); bottomMargin = dp(bottom) }

    private fun dp(value: Int) = (value * density).toInt()

    private companion object {
        const val MAX_COLUMNS = 6
    }
}
