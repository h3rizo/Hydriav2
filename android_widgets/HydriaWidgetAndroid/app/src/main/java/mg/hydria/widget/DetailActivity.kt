package mg.hydria.widget

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_STAT_TYPE = "stat_type"
        const val EXTRA_LABEL = "label"
        const val EXTRA_APP_WIDGET_ID = "app_widget_id"
        /** Tap sur J / S / M dans le widget : changer la période des compteurs « fait » (aucun écran affiché). */
        const val EXTRA_PERIODE = "realisations_periode"
        // Indemnités RBF : Région → District → Commune → Ouvrage (lignes à plat renvoyées par l'API).
        private val RBF_TYPES = setOf(
            "rbf_points_depassement_plafond",
            "rbf_points_sans_paiement_effectif",
        )

        private val GROUPABLE_TYPES = RBF_TYPES + setOf(
            "ouvrages", "points_eau",
            "factures_volumetriques_mises_a_jour_mois_courant_non_pointees",
            "factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees",
            "factures_forfaitaires_mises_a_jour_mois_courant_non_pointees",
            "factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees",
            "factures_volumetriques_mois_courant_non_pointees",
            "factures_volumetriques_mois_passes_non_pointees",
            "factures_forfaitaires_mois_courant_non_pointees",
            "factures_forfaitaires_mois_passes_non_pointees",
        )

        // Factures : District → Commune → Ouvrage → liste des factures.
        private val OUVRAGE_GROUPED_TYPES = GROUPABLE_TYPES - RBF_TYPES - setOf("ouvrages", "points_eau")

        private class GeoLevel(
            val level: Int,
            val icon: String,
            val key: (HydriaApi.GeoRow) -> String,
            val name: (HydriaApi.GeoRow) -> String,
        )

        // 1 = région, 2 = district, 3 = commune, 4 = ouvrage (feuille des RBF).
        private val GEO_LEVELS = listOf(
            GeoLevel(1, "🗺️", { it.regionId }, { it.region }),
            GeoLevel(2, "📍", { it.districtId }, { it.district }),
            GeoLevel(3, "🏘️", { it.communeId }, { it.commune }),
            GeoLevel(4, "🏗️", { it.ouvrageId }, { it.ouvrage }),
        )

        // Types de détail dont chaque ligne représente une facture d'un point
        // d'eau rattaché à un ouvrage précis : on peut alors ouvrir directement
        // le modal de pointage correspondant sur hydria.mg, au lieu de forcer
        // le parcours manuel (taper l'adresse, chercher l'ouvrage, ouvrir le modal).
        private val VOLUME_FACTURE_TYPES = setOf(
            "factures_volumetriques_mises_a_jour_mois_courant_non_pointees",
            "factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees",
            "factures_volumetriques_mois_courant_non_pointees",
            "factures_volumetriques_mois_passes_non_pointees",
        )
        private val FORFAIT_FACTURE_TYPES = setOf(
            "factures_forfaitaires_mises_a_jour_mois_courant_non_pointees",
            "factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees",
            "factures_forfaitaires_mois_courant_non_pointees",
            "factures_forfaitaires_mois_passes_non_pointees",
            "factures_forfaitaires_jour",
        )
    }

    /**
     * Construit l'URL du dashboard Hydria correspondant, pré-filtrée sur
     * l'ouvrage (et le mois pour le volumétrique), pour ouvrir directement le
     * bon modal de pointage au chargement de la page (cf. scripts ajoutés dans
     * dashboard_paiements_volume.html / dashboard_paiements_forfaitaire.html).
     */
    private fun hydriaFactureLink(type: String, row: HydriaApi.DetailRow): Uri? {
        // Lignes RBF : page Hydria qui explique pourquoi le point d'eau figure dans le compteur.
        row.href?.let { return Uri.parse("https://www.hydria.mg$it") }
        val ouvrageId = row.ouvrageId ?: return null
        return when {
            VOLUME_FACTURE_TYPES.contains(type) -> {
                val mois = row.mois ?: return null
                val builder = Uri.parse("https://www.hydria.mg/comptabilite/dashboard-paiements-volume/").buildUpon()
                    .appendQueryParameter("ouvrage", ouvrageId)
                    .appendQueryParameter("open_mois", mois.toString())
                row.annee?.let { builder.appendQueryParameter("annee", it.toString()) }
                row.ouvrageNom?.let { builder.appendQueryParameter("open_ouvrage_nom", it) }
                builder.build()
            }
            FORFAIT_FACTURE_TYPES.contains(type) -> {
                val builder = Uri.parse("https://www.hydria.mg/comptabilite/dashboard-paiements-forfaitaire/").buildUpon()
                    .appendQueryParameter("ouvrage", ouvrageId)
                    .appendQueryParameter("open_details", "1")
                row.annee?.let { builder.appendQueryParameter("annee", it.toString()) }
                builder.build()
            }
            else -> null
        }
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
        // Les clics d'une liste de widget passent tous par le même PendingIntent modèle (cette activité) :
        // le sélecteur de période y arrive donc aussi, on l'applique puis on se ferme sans rien afficher.
        intent.getStringExtra(EXTRA_PERIODE)?.let { periode ->
            val widgetId = intent.getIntExtra(EXTRA_APP_WIDGET_ID, android.appwidget.AppWidgetManager.INVALID_APPWIDGET_ID)
            TokenStore.saveRealisationsPeriode(this, widgetId, periode)
            HydriaWidgetProvider.requestUpdate(this)
            finish()
            @Suppress("DEPRECATION") overridePendingTransition(0, 0)
            return
        }
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
        backButton.setOnClickListener { navigateBack() }
        titleView.text = label
        token = TokenStore.getToken(this)
        val widgetId = intent.getIntExtra(EXTRA_APP_WIDGET_ID, android.appwidget.AppWidgetManager.INVALID_APPWIDGET_ID)
        filters = TokenStore.getFilters(this, widgetId)
        if (isTablet) showOuvragePlaceholder()
        if (token == null) showMessage("Non connecté")
        else if (GROUPABLE_TYPES.contains(statType)) { groupLabel = label; loadGroupes() }
        else loadDetails(statType, null)
    }

    override fun onBackPressed() {
        if (showingOuvrage && !isTablet) closePhoneOuvrage()
        else if (backButton.visibility == View.VISIBLE) returnToGroupes()
        else super.onBackPressed()
    }

    private fun navigateBack() {
        if (showingOuvrage && !isTablet) closePhoneOuvrage() else returnToGroupes()
    }

    private fun returnToGroupes() {
        val commune = ouvrageGroupCommune
        if (commune != null && inOuvrageList) {
            inOuvrageList = false
            openOuvrageGroupes(commune, ouvrageRoot)
            return
        }
        inOuvrageList = false
        ouvrageGroupCommune = null
        titleView.text = groupLabel
        currentListTitle = null
        showingOuvrage = false
        selectedOuvrageId = null
        masterPanel.visibility = View.VISIBLE
        if (!isTablet) ouvragePanel.visibility = View.GONE else showOuvragePlaceholder()
        backButton.visibility = View.GONE
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

    // Niveau géographique déjà fixé par le filtre actif du widget (0 = aucun, 1 = région, 2 = district,
    // 3 = commune). Un modal ne propose jamais un regroupement que le filtre a déjà tranché.
    private fun fixedLevel() = when {
        filters.communeId != "all" -> 3
        filters.districtId != "all" -> 2
        filters.regionId != "all" -> 1
        else -> 0
    }

    private fun loadGroupes() {
        val fixed = fixedLevel()
        // Commune déjà choisie : plus de région / district / commune à parcourir.
        // (Les ouvrages et les RBF passent par l'API, qui sait sauter ces niveaux.)
        if (fixed >= 3 && statType != "ouvrages" && !RBF_TYPES.contains(statType)) {
            if (OUVRAGE_GROUPED_TYPES.contains(statType)) {
                openOuvrageGroupes(HydriaApi.Commune(filters.communeId, filters.communeName, 0), root = true)
            } else {
                totalView.text = ""
                loadDetails(statType, filters.communeId)
            }
            return
        }
        progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val result = HydriaApi.fetchGroupes(statType, token!!, filters)
            progressBar.visibility = View.GONE
            if (!result.success) { showMessage(result.error ?: "Erreur de chargement"); return@launch }
            totalView.text = "${result.total} au total"
            container.removeAllViews()
            val flat = result.flat
            if ((flat != null && flat.isEmpty()) || (flat == null && result.districts.isEmpty())) {
                container.addView(message("Aucun élément")); return@launch
            }
            if (statType == "ouvrages") {
                // Groupes « modalité » (parfois + district) déjà construits par l'API.
                if (fixed >= 3) {
                    result.districts.forEach { d -> d.communes.forEach { c ->
                        container.addView(leafRow(d.district, c.count) { openList("${groupLabel ?: statType} — ${d.district}", c.communeId) })
                    } }
                } else result.districts.forEach { container.addView(buildDistrictBlock(it)) }
                return@launch
            }
            // Autres types : arbre Région → District → Commune (→ Ouvrage pour les RBF), niveaux fixés par le filtre retirés.
            val isRbf = RBF_TYPES.contains(statType)
            val rows = flat ?: result.districts.flatMap { d ->
                d.communes.map { c ->
                    HydriaApi.GeoRow(d.regionId, d.region.ifBlank { "Sans région" }, d.districtId ?: "", d.district,
                        c.communeId, c.commune, "", "", c.count)
                }
            }
            val levels = GEO_LEVELS.filter { it.level > fixed && (isRbf || it.level <= 3) }
            geoTreeViews(rows, levels) { row ->
                when {
                    isRbf -> openList("${groupLabel ?: statType} — ${row.ouvrage}", row.communeId, row.ouvrageId)
                    OUVRAGE_GROUPED_TYPES.contains(statType) -> openOuvrageGroupes(HydriaApi.Commune(row.communeId, row.commune, row.count))
                    else -> openList("${groupLabel ?: statType} — ${row.commune}", row.communeId)
                }
            }.forEach { container.addView(it) }
        }
    }

    private fun leafRow(title: String, count: Int, onClick: () -> Unit): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(9), dp(8), dp(9)); isClickable = true
        }
        row.addView(text(title, 13f, colorPrimary()).apply { layoutParams = LinearLayout.LayoutParams(0, -2, 1f) })
        row.addView(text(count.toString(), 13f, colorAccent()))
        row.setOnClickListener { onClick() }
        return row
    }

    // Arbre dépliable sur les niveaux donnés ; le dernier niveau est la feuille cliquable.
    private fun geoTreeViews(rows: List<HydriaApi.GeoRow>, levels: List<GeoLevel>, onLeaf: (HydriaApi.GeoRow) -> Unit): List<View> {
        val level = levels.first()
        val rest = levels.drop(1)
        return rows.groupBy { level.key(it) + "|" + level.name(it) }.values.map { list ->
            val count = list.sumOf { it.count }
            val title = "${level.icon} ${level.name(list.first())}"
            if (rest.isEmpty()) return@map leafRow(title, count) { onLeaf(list.first()) }
            val block = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, dp(6)) }
            val children = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.GONE; setPadding(dp(16), dp(4), 0, dp(4)) }
            val toggle = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setBackgroundColor(colorTileBackground()); setPadding(dp(12), dp(10), dp(12), dp(10)); isClickable = true
            }
            toggle.addView(text(title, 14f, colorPrimary()).apply { layoutParams = LinearLayout.LayoutParams(0, -2, 1f) })
            toggle.addView(text("$count ▾", 13f, colorSecondary()))
            toggle.setOnClickListener { children.visibility = if (children.visibility == View.VISIBLE) View.GONE else View.VISIBLE }
            geoTreeViews(list, rest, onLeaf).forEach { children.addView(it) }
            block.addView(toggle); block.addView(children)
            block
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
            row.setOnClickListener {
                if (OUVRAGE_GROUPED_TYPES.contains(statType)) openOuvrageGroupes(commune)
                else openList("${groupLabel ?: statType} — ${commune.commune}", commune.communeId)
            }
            communes.addView(row)
        }
        block.addView(toggle); block.addView(communes)
        return block
    }

    private fun openList(label: String, communeId: String?, ouvrageId: String? = null) {
        inOuvrageList = ouvrageId != null
        currentListTitle = label; titleView.text = label; backButton.visibility = View.VISIBLE
        loadDetails(statType, communeId, ouvrageId)
    }

    // Niveau « ouvrage » : nombre de factures, de points d'eau et montant par ouvrage de la commune.
    private var ouvrageGroupCommune: HydriaApi.Commune? = null
    private var inOuvrageList = false

    // `root` : la commune vient du filtre du widget, c'est donc le premier niveau du modal (pas de retour vers les communes).
    private var ouvrageRoot = false

    private fun openOuvrageGroupes(commune: HydriaApi.Commune, root: Boolean = false) {
        ouvrageGroupCommune = commune
        ouvrageRoot = root
        val label = if (root) (groupLabel ?: statType) else "${groupLabel ?: statType} — ${commune.commune}"
        currentListTitle = label; titleView.text = label
        backButton.visibility = if (root) View.GONE else View.VISIBLE
        progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val result = HydriaApi.fetchOuvrageGroupes(statType, token!!, filters, commune.communeId)
            progressBar.visibility = View.GONE
            if (!result.success) { showMessage(result.error ?: "Erreur de chargement"); return@launch }
            totalView.text = "${result.ouvrages.size} ouvrage(s) · ${result.total} facture(s)"
            container.removeAllViews()
            if (result.ouvrages.isEmpty()) { container.addView(message("Aucun élément")); return@launch }
            result.ouvrages.forEach { o ->
                val row = LinearLayout(this@DetailActivity).apply {
                    orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                    setPadding(dp(12), dp(10), dp(12), dp(10)); isClickable = o.ouvrageId.isNotBlank()
                }
                val info = LinearLayout(this@DetailActivity).apply { orientation = LinearLayout.VERTICAL; layoutParams = LinearLayout.LayoutParams(0, -2, 1f) }
                info.addView(text("🏗️ ${o.ouvrage}", 14f, colorPrimary(), true))
                val montant = java.text.DecimalFormat("0.#").format(o.montant / 1000.0)
                info.addView(text("${o.pointsEau} point(s) d'eau · $montant K Ar", 12f, colorSecondary()))
                row.addView(info)
                row.addView(text(o.count.toString(), 14f, colorAccent(), true))
                if (o.ouvrageId.isNotBlank()) row.setOnClickListener {
                    openList("$label — ${o.ouvrage}", commune.communeId, o.ouvrageId)
                }
                container.addView(row)
            }
        }
    }

    private fun loadDetails(type: String, communeId: String?, ouvrageId: String? = null) {
        progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            val result = HydriaApi.fetchDetails(type, token!!, filters, communeId, ouvrageId)
            progressBar.visibility = View.GONE
            if (!result.success) { showMessage(result.error ?: "Erreur de chargement"); return@launch }
            totalView.text = if (result.total > result.shown) "${result.shown} sur ${result.total}" else "${result.total} au total"
            container.removeAllViews()
            if (result.rows.isEmpty()) container.addView(message("Aucun élément"))
            else {
                var lastGroup: String? = null
                result.rows.forEach { row ->
                    if (row.group != null && row.group != lastGroup) {
                        lastGroup = row.group
                        val n = result.rows.count { it.group == row.group }
                        container.addView(text("${row.group.uppercase()} ($n)", 12f, colorSecondary(), bold = true).apply {
                            setPadding(dp(12), dp(14), dp(12), dp(4))
                        })
                    }
                    container.addView(buildDetailRow(row))
                }
                if (isTablet && type == "ouvrages") result.rows.firstOrNull { it.id != null }?.id?.let { openOuvrage(it) }
                if (result.total > result.shown) {
                    // Bas de liste : lien vers la page Hydria « liste complète » (même périmètre, sans limite).
                    val listeUrl = HydriaApi.listeUrl(type, filters, communeId, ouvrageId, titleView.text.toString())
                    container.addView(text("Voir la liste complète sur Hydria  ↗", 13f, colorAccent(), true).apply {
                        gravity = Gravity.CENTER; setPadding(dp(12), dp(16), dp(12), dp(16)); isClickable = true
                        setOnClickListener { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(listeUrl))) }
                    })
                }
            }
        }
    }

    private fun buildDetailRow(row: HydriaApi.DetailRow): View {
        val factureLink = hydriaFactureLink(statType, row)
        val wrapper = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(11), dp(12), dp(11))
            if (statType == "ouvrages" && row.id != null) {
                isClickable = true; isFocusable = true; setBackgroundResource(android.R.drawable.list_selector_background)
                setOnClickListener { openOuvrage(row.id) }
            } else if (factureLink != null) {
                isClickable = true; isFocusable = true; setBackgroundResource(android.R.drawable.list_selector_background)
                setOnClickListener { startActivity(Intent(Intent.ACTION_VIEW, factureLink)) }
            }
        }
        // IDXLS du point d'eau en tête de ligne.
        val label = if (row.idxls != null) "${row.idxls} · ${row.label}" else row.label
        wrapper.addView(text(if (row.id != null || factureLink != null) "$label  ›" else label, 14f, colorPrimary()))
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
