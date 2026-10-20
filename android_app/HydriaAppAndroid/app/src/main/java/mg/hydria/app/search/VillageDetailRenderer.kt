package mg.hydria.app.search

import android.graphics.Color
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaUi
import org.json.JSONArray
import org.json.JSONObject
import java.text.NumberFormat
import java.util.Locale

/**
 * Fiche village de la Recherche : synthèse (population, population desservie, ouvrages, points d'eau), localisation
 * (avec accès à la fiche de la commune), profil du village, points d'eau par type, ouvrages cliquables vers leurs
 * fiches et parcelles. Données calculées par le serveur (`details` de /recherche/api/mobile/details/village/<id>/).
 */
class VillageDetailRenderer(
    private val activity: AppCompatActivity,
    private val body: LinearLayout,
    private val renderPointsEau: (JSONObject) -> Unit,
    private val openDetail: (type: String, id: String, title: String) -> Unit,
) {
    private val density = activity.resources.displayMetrics.density
    private val numbers = NumberFormat.getIntegerInstance(Locale.FRANCE)

    fun render(details: JSONObject) {
        details.optJSONObject("synthese")?.let(::renderSynthese)
        details.optJSONObject("localisation")?.let(::renderLocalisation)
        details.optJSONArray("profil")?.let(::renderProfil)
        details.optJSONObject("repartition_points_eau")?.let(renderPointsEau)
        details.optJSONArray("ouvrages")?.let(::renderOuvrages)
        details.optJSONArray("parcelles")?.let(::renderParcelles)
    }

    // ── Synthèse ──────────────────────────────────────────────────────────────

    private fun renderSynthese(s: JSONObject) {
        val desservi = s.optBoolean("desservi")
        body.addView(HydriaUi.badge(
            activity, if (desservi) "Village desservi" else "Village non desservi",
            if (desservi) mg.hydria.app.Tone.SUCCESS else mg.hydria.app.Tone.WARNING,
        ), margin(top = 4, bottom = 8))

        val distance = if (s.isNull("distance_dernier_point_km")) null else s.optDouble("distance_dernier_point_km")
        val access = s.optString("accessibilite")
        val cards = buildList {
            add(Triple("Habitants", fmt(s.optInt("habitants")), "${fmt(s.optInt("menages"))} ménage(s)"))
            add(Triple("Population desservie", fmt(s.optInt("habitants_desservis")),
                "${s.optInt("taux_desserte_pct")} % des habitants · ${fmt(s.optInt("menages_desservis"))} ménage(s)"))
            add(Triple("Ouvrages", "${fmt(s.optInt("ouvrages_fonctionnels"))} / ${fmt(s.optInt("ouvrages"))}", "fonctionnels / total"))
            add(Triple("Points d'eau en service", fmt(s.optInt("points_eau_en_service")), "branchés, non coupés"))
            add(Triple("Parcelles", "${fmt(s.optInt("parcelles_desservies"))} / ${fmt(s.optInt("parcelles"))}", "desservies / total"))
            if (access.isNotBlank() || distance != null) {
                add(Triple("Accessibilité", access.ifBlank { "Non renseignée" },
                    if (distance != null && distance > 0) "${String.format(Locale.FRANCE, "%.1f", distance)} km à pied depuis le dernier point accessible" else ""))
            }
        }
        body.addView(text("SYNTHÈSE DU VILLAGE", 11f, true, HydriaColors.cyan), margin(top = 2, bottom = 6))
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
        addView(text(value, 20f, true, HydriaColors.text), margin(top = 3))
        if (sub.isNotBlank()) addView(text(sub, 11f, false, HydriaColors.textSecondary), margin(top = 2))
    }

    // ── Localisation (la commune ouvre sa fiche) ─────────────────────────────

    private fun renderLocalisation(l: JSONObject) {
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        card.addView(text("LOCALISATION", 11f, true, HydriaColors.cyan))
        l.optString("fokontany").takeIf { it.isNotBlank() }?.let { card.addView(text("Fokontany : $it", 14f, false, HydriaColors.text), margin(top = 6)) }
        l.optString("district").takeIf { it.isNotBlank() }?.let { card.addView(text("District : $it", 14f, false, HydriaColors.text), margin(top = 3)) }
        l.optString("region").takeIf { it.isNotBlank() }?.let { card.addView(text("Région : $it", 14f, false, HydriaColors.text), margin(top = 3)) }
        l.optJSONObject("commune")?.let { commune ->
            val name = commune.optString("nom")
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
                background = HydriaUi.rounded(activity, HydriaColors.surfaceRaised, 12f, HydriaColors.outline)
                setOnClickListener { openDetail("commune", commune.optString("id"), name) }
            }
            row.addView(text("Commune : $name", 15f, true, HydriaColors.text), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(text("›", 24f, true, HydriaColors.textSecondary))
            card.addView(row, margin(top = 8))
        }
        body.addView(card, margin(top = 4, bottom = 8))
    }

    // ── Profil : classement du village sur chaque dimension du diagramme ─────

    private fun renderProfil(items: JSONArray) {
        if (items.length() == 0) return
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        card.addView(text("PROFIL DU VILLAGE", 11f, true, HydriaColors.cyan))
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            val row = LinearLayout(activity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            row.addView(View(activity).apply {
                background = HydriaUi.rounded(activity, runCatching { Color.parseColor(item.optString("color")) }.getOrDefault(Color.GRAY), 4f)
            }, LinearLayout.LayoutParams(dp(10), dp(10)).apply { marginEnd = dp(8) })
            row.addView(text(item.optString("titre"), 12f, false, HydriaColors.textSecondary), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(text(item.optString("label"), 13f, true, HydriaColors.text))
            card.addView(row, margin(top = 6))
        }
        body.addView(card, margin(bottom = 8))
    }

    // ── Ouvrages et parcelles ─────────────────────────────────────────────────

    private fun renderOuvrages(items: JSONArray) {
        if (items.length() == 0) return
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        card.addView(text("OUVRAGES QUI DESSERVENT LE VILLAGE (${items.length()})", 11f, true, HydriaColors.cyan))
        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            val name = item.optString("nom")
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
                background = HydriaUi.rounded(activity, HydriaColors.surfaceRaised, 12f, HydriaColors.outline)
                setOnClickListener { openDetail("ouvrage", item.optString("id"), name) }
            }
            val left = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
            left.addView(text(name, 15f, true, HydriaColors.text))
            left.addView(text("${item.optString("type")} · ${item.optInt("points_eau")} point(s) d'eau en service", 12f, false, HydriaColors.textSecondary), margin(top = 2))
            if (!item.optBoolean("fonctionnel", true)) left.addView(text("⚠ Non fonctionnel", 11f, true, HydriaColors.error), margin(top = 2))
            row.addView(left, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(text("›", 24f, true, HydriaColors.textSecondary))
            card.addView(row, margin(top = 6))
        }
        body.addView(card, margin(bottom = 8))
    }

    private fun renderParcelles(items: JSONArray) {
        if (items.length() == 0) return
        val card = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this)
        }
        card.addView(text("PARCELLES (${items.length()})", 11f, true, HydriaColors.cyan))
        val shown = minOf(items.length(), MAX_PARCELLES)
        for (i in 0 until shown) {
            val item = items.getJSONObject(i)
            val desservie = item.optBoolean("desservie")
            card.addView(text(item.optString("reference"), 14f, true, HydriaColors.text), margin(top = 8))
            card.addView(text(
                "${fmt(item.optInt("habitants"))} habitant(s) · ${fmt(item.optInt("menages"))} ménage(s) · ${item.optInt("points_eau")} point(s) d'eau" +
                    if (desservie) "" else " · non desservie",
                12f, false, if (desservie) HydriaColors.textSecondary else HydriaColors.warning,
            ), margin(top = 2))
        }
        if (items.length() > shown) {
            card.addView(text("… et ${items.length() - shown} autre(s) parcelle(s).", 12f, false, HydriaColors.textSecondary), margin(top = 8))
        }
        body.addView(card, margin(bottom = 8))
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
        const val MAX_PARCELLES = 100
    }
}
