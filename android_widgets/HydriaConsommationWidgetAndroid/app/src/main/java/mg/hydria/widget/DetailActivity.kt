package mg.hydria.widget

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_STAT_TYPE = "stat_type"
        const val EXTRA_LABEL = "label"
        const val EXTRA_APP_WIDGET_ID = "app_widget_id"
        private val GROUPABLE_TYPES = setOf(
            "ouvrages", "points_eau",
            "factures_volumetriques_mois_courant_non_pointees",
            "factures_volumetriques_mois_passes_non_pointees",
            "factures_forfaitaires_mois_courant_non_pointees",
            "factures_forfaitaires_mois_passes_non_pointees",
        )
    }

    private lateinit var statType: String
    private lateinit var container: LinearLayout
    private lateinit var ouvrageContainer: LinearLayout
    private lateinit var masterPanel: View
    private lateinit var ouvragePanel: View
    private lateinit var titleView: TextView
    private lateinit var totalView: TextView
    private lateinit var progressBar: View
    private lateinit var backButton: View
    private var token: String? = null
    private var filters = TokenStore.Filters()
    private var groupLabel: String? = null
    private var currentListTitle: String? = null
    private var showingOuvrage = false
    private var selectedOuvrageId: String? = null
    private var isTablet = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_detail)
        statType = intent.getStringExtra(EXTRA_STAT_TYPE) ?: run { finish(); return }
        val label = intent.getStringExtra(EXTRA_LABEL) ?: statType
        isTablet = resources.getBoolean(R.bool.is_tablet)
        container = findViewById(R.id.detail_container)
        ouvrageContainer = findViewById(R.id.ouvrage_detail_container)
        masterPanel = findViewById(R.id.master_panel)
        ouvragePanel = findViewById(R.id.ouvrage_detail_panel)
        titleView = findViewById(R.id.detail_title)
        totalView = findViewById(R.id.detail_total)
        progressBar = findViewById(R.id.detail_progress)
        backButton = findViewById(R.id.detail_back)
        backButton.visibility = View.VISIBLE
        backButton.setOnClickListener { navigateBack() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = navigateBack()
        })
        titleView.text = label
        token = TokenStore.getToken(this)
        val widgetId = intent.getIntExtra(EXTRA_APP_WIDGET_ID, android.appwidget.AppWidgetManager.INVALID_APPWIDGET_ID)
        filters = TokenStore.getFilters(this, widgetId)
        if (isTablet) showOuvragePlaceholder()
        if (token == null) showMessage("Non connecté")
        else if (GROUPABLE_TYPES.contains(statType)) { groupLabel = label; loadGroupes() }
        else loadDetails(statType, null)
    }

    private fun navigateBack() {
        when {
            showingOuvrage && !isTablet -> closePhoneOuvrage()
            currentListTitle != null && groupLabel != null -> returnToGroupes()
            else -> finish()
        }
    }

    private fun returnToGroupes() {
        titleView.text = groupLabel
        currentListTitle = null
        showingOuvrage = false
        selectedOuvrageId = null
        masterPanel.visibility = View.VISIBLE
        if (!isTablet) ouvragePanel.visibility = View.GONE else showOuvragePlaceholder()
        backButton.visibility = View.VISIBLE
        loadGroupes()
    }

    private fun closePhoneOuvrage() {
        showingOuvrage = false
        ouvragePanel.visibility = View.GONE
        masterPanel.visibility = View.VISIBLE
        titleView.text = currentListTitle ?: groupLabel
    }

    private fun showMessage(value: String) {
        container.removeAllViews(); container.addView(message(value))
    }

    private fun message(value: String) = text(value, 14f, colorSecondary()).apply {
        gravity = Gravity.CENTER; setPadding(dp(16), dp(40), dp(16), dp(16))
    }

    private fun loadGroupes() {
        progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val result = HydriaApi.fetchGroupes(statType, token!!, filters)
            progressBar.visibility = View.GONE
            if (!result.success) { showMessage(result.error ?: "Erreur de chargement"); return@launch }
            totalView.text = "${result.total} au total"
            container.removeAllViews()
            if (result.districts.isEmpty()) container.addView(message("Aucun élément"))
            else result.districts.forEach { container.addView(buildDistrictBlock(it)) }
        }
    }

    private fun buildDistrictBlock(district: HydriaApi.District): View {
        val block = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, dp(6)) }
        val communes = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE; setPadding(dp(16), dp(4), 0, dp(4)) }
        val toggle = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(colorTileBackground()); setPadding(dp(12), dp(10), dp(12), dp(10)); isClickable = true
        }
        toggle.addView(text("📍 ${district.district}", 14f, colorPrimary()).apply { layoutParams = LinearLayout.LayoutParams(0, -2, 1f) })
        toggle.addView(text("${district.total} ▾", 13f, colorSecondary()))
        toggle.setOnClickListener { communes.visibility = if (communes.visibility == View.VISIBLE) View.GONE else View.VISIBLE }
        district.communes.forEach { commune ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(8), dp(9), dp(8), dp(9)); isClickable = true }
            row.addView(text(commune.commune, 13f, colorPrimary()).apply { layoutParams = LinearLayout.LayoutParams(0, -2, 1f) })
            row.addView(text(commune.count.toString(), 13f, colorAccent()))
            row.setOnClickListener { openList("${groupLabel ?: statType} — ${commune.commune}", commune.communeId) }
            communes.addView(row)
        }
        block.addView(toggle); block.addView(communes)
        return block
    }

    private fun openList(label: String, communeId: String?) {
        currentListTitle = label; titleView.text = label; backButton.visibility = View.VISIBLE
        loadDetails(statType, communeId)
    }

    private fun loadDetails(type: String, communeId: String?) {
        progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val result = HydriaApi.fetchDetails(type, token!!, filters, communeId)
            progressBar.visibility = View.GONE
            if (!result.success) { showMessage(result.error ?: "Erreur de chargement"); return@launch }
            totalView.text = if (result.total > result.shown) "${result.shown} sur ${result.total}" else "${result.total} au total"
            container.removeAllViews()
            if (result.rows.isEmpty()) container.addView(message("Aucun élément"))
            else {
                result.rows.forEach { container.addView(buildDetailRow(it)) }
                if (isTablet && type == "ouvrages") result.rows.firstOrNull { it.id != null }?.id?.let { openOuvrage(it) }
            }
        }
    }

    private fun buildDetailRow(row: HydriaApi.DetailRow): View {
        val wrapper = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(11), dp(12), dp(11))
            if (statType == "ouvrages" && row.id != null) {
                isClickable = true; isFocusable = true; setBackgroundResource(android.R.drawable.list_selector_background)
                setOnClickListener { openOuvrage(row.id) }
            }
        }
        wrapper.addView(text(if (row.id != null) "${row.label}  ›" else row.label, 14f, colorPrimary()))
        if (!row.sub.isNullOrEmpty()) wrapper.addView(text(row.sub, 12f, colorSecondary()))
        return wrapper
    }

    private fun openOuvrage(id: String) {
        if (selectedOuvrageId == id && ouvrageContainer.childCount > 1) return
        selectedOuvrageId = id; showingOuvrage = true; ouvragePanel.visibility = View.VISIBLE
        if (!isTablet) { masterPanel.visibility = View.GONE; titleView.text = "Fiche ouvrage" }
        ouvrageContainer.removeAllViews(); ouvrageContainer.addView(message("Chargement de l’ouvrage…")); progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val result = HydriaApi.fetchOuvrageDetail(id, token!!, filters)
            progressBar.visibility = View.GONE
            if (selectedOuvrageId != id) return@launch
            if (!result.success || result.detail == null) {
                ouvrageContainer.removeAllViews(); ouvrageContainer.addView(message(result.error ?: "Détail indisponible"))
            } else renderOuvrage(result.detail)
        }
    }

    private fun showOuvragePlaceholder() {
        ouvrageContainer.removeAllViews(); ouvrageContainer.addView(message("Sélectionnez un ouvrage dans la liste de gauche."))
    }

    private fun renderOuvrage(detail: HydriaApi.OuvrageDetail) {
        ouvrageContainer.removeAllViews()
        ouvrageContainer.addView(text(detail.name, 22f, colorPrimary(), true))
        ouvrageContainer.addView(text(detail.type, 14f, colorAccent()).apply { setPadding(0, dp(3), 0, dp(14)) })
        val statRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, 0, 0, dp(12)) }
        detail.stats.forEach { (label, value) ->
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setPadding(dp(3), dp(8), dp(3), dp(8)); setBackgroundColor(colorTileBackground())
                layoutParams = LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(3) }
            }
            card.addView(text(value.toString(), 17f, colorAccent(), true)); card.addView(text(label, 9f, colorSecondary())); statRow.addView(card)
        }
        ouvrageContainer.addView(statRow)
        val general = mutableListOf<HydriaApi.InfoRow>()
        if (detail.year.isNotBlank()) general += HydriaApi.InfoRow("Année de réalisation", detail.year)
        if (detail.previousYear.isNotBlank()) general += HydriaApi.InfoRow("Réalisation antérieure", detail.previousYear)
        if (detail.builder.isNotBlank()) general += HydriaApi.InfoRow("Intervenant / constructeur", detail.builder)
        general += HydriaApi.InfoRow("Ouvrage saisonnier", if (detail.seasonal) "Oui" else "Non")
        if (detail.observation.isNotBlank()) general += HydriaApi.InfoRow("Observations", detail.observation)
        addSection("Informations générales", general)
        addSection("Localisation", detail.locations)
        addSection("Gestion", detail.management)
        addSection("Réparations non terminées", detail.repairs)
        addSection("Paiements échus non pointés", detail.overduePayments)
        addSection("Prochains paiements", detail.upcomingPayments)
        addSection("Tarifs actifs", detail.tariffs)
        addSection("Points d’eau", detail.waterPoints)
        addSection("Équipements", detail.equipment)
        if (detail.fullUrl.isNotBlank()) {
            ouvrageContainer.addView(text("Ouvrir la fiche complète sur Hydria  ↗", 14f, colorAccent(), true).apply {
                setPadding(dp(12), dp(14), dp(12), dp(14)); setBackgroundColor(colorTileBackground()); isClickable = true
                setOnClickListener { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(detail.fullUrl))) }
            })
        }
    }

    private fun addSection(title: String, rows: List<HydriaApi.InfoRow>) {
        if (rows.isEmpty()) return
        ouvrageContainer.addView(text(title, 16f, colorPrimary(), true).apply { setPadding(0, dp(12), 0, dp(6)) })
        rows.forEach { row ->
            val item = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(10), dp(8), dp(10), dp(8)); setBackgroundColor(colorTileBackground()) }
            item.addView(text(row.title, 13f, colorPrimary(), true))
            if (row.subtitle.isNotBlank()) item.addView(text(row.subtitle, 12f, colorSecondary()))
            ouvrageContainer.addView(item, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(4) })
        }
    }

    private fun text(value: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun colorPrimary() = ContextCompat.getColor(this, R.color.detail_text_primary)
    private fun colorSecondary() = ContextCompat.getColor(this, R.color.detail_text_secondary)
    private fun colorAccent() = ContextCompat.getColor(this, R.color.detail_text_accent)
    private fun colorTileBackground() = ContextCompat.getColor(this, R.color.detail_tile_background)
}
