package mg.hydria.app.search

import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.content.res.ColorStateList
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.FrameLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import mg.hydria.app.Tone
import mg.hydria.app.HydriaNetwork
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaType
import mg.hydria.app.HydriaUi
import mg.hydria.app.HydriaWindow
import mg.hydria.app.OfflineStore
import org.json.JSONArray
import org.json.JSONObject
import java.text.DateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors

class SearchActivity : AppCompatActivity() {
    private enum class Section { ALL, PEOPLE, WORKS }
    private data class Option(val id: String, val label: String)

    private val executor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var store: OfflineStore
    private lateinit var queryField: EditText
    private lateinit var resultList: LinearLayout
    private lateinit var stateLabel: TextView
    private lateinit var progress: ProgressBar
    private lateinit var filterButton: Button
    private lateinit var activeFilters: LinearLayout
    private lateinit var resultsScroll: ScrollView
    private var detailPane: FrameLayout? = null
    private var facetsHost: LinearLayout? = null
    private var workFiltersPayload: JSONObject? = null
    private var wideLayout = false
    private var section = Section.ALL
    private var generation = 0
    private var page = 1
    private var hasNext = false
    private var total = 0
    private var currentResults = JSONArray()
    private val selectedTypes = ALL_TYPES.filter { it.first != "planning" }.map { it.first }.toMutableSet()
    private var peopleType = ""
    private var peopleStatus = "actif"
    private var workRegion = ""
    private var workDistrict = ""
    private var workCommune = ""
    private var workEmployee = ""
    private var workRegionLabel = ""
    private var workDistrictLabel = ""
    private var workCommuneLabel = ""
    private var workEmployeeLabel = ""
    private var restoredScrollY = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        store = OfflineStore(this)
        section = savedInstanceState?.getString("section")?.let { runCatching { Section.valueOf(it) }.getOrNull() } ?: Section.ALL
        peopleType = savedInstanceState?.getString("people_type").orEmpty()
        peopleStatus = savedInstanceState?.getString("people_status") ?: "actif"
        restoredScrollY = savedInstanceState?.getInt("scroll_y") ?: 0
        workRegion = savedInstanceState?.getString("work_region").orEmpty()
        workDistrict = savedInstanceState?.getString("work_district").orEmpty()
        workCommune = savedInstanceState?.getString("work_commune").orEmpty()
        workEmployee = savedInstanceState?.getString("work_employee").orEmpty()
        workRegionLabel = savedInstanceState?.getString("work_region_label").orEmpty()
        workDistrictLabel = savedInstanceState?.getString("work_district_label").orEmpty()
        workCommuneLabel = savedInstanceState?.getString("work_commune_label").orEmpty()
        workEmployeeLabel = savedInstanceState?.getString("work_employee_label").orEmpty()
        savedInstanceState?.getStringArrayList("types")?.let { selectedTypes.apply { clear(); addAll(it) } }
        buildScreen(savedInstanceState?.getString("query").orEmpty())
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("section", section.name)
        outState.putString("query", queryField.text.toString())
        outState.putString("people_type", peopleType)
        outState.putString("people_status", peopleStatus)
        outState.putStringArrayList("types", ArrayList(selectedTypes))
        if (::resultsScroll.isInitialized) outState.putInt("scroll_y", resultsScroll.scrollY)
        outState.putString("work_region", workRegion); outState.putString("work_district", workDistrict)
        outState.putString("work_commune", workCommune); outState.putString("work_employee", workEmployee)
        outState.putString("work_region_label", workRegionLabel); outState.putString("work_district_label", workDistrictLabel)
        outState.putString("work_commune_label", workCommuneLabel); outState.putString("work_employee_label", workEmployeeLabel)
        super.onSaveInstanceState(outState)
    }

    private fun buildScreen(initialQuery: String) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(HydriaColors.background)
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(8))
            setBackgroundColor(HydriaColors.backgroundDeep)
        }
        header.addView(Button(this).apply {
            text = "‹"
            HydriaUi.styleSecondary(this)
            contentDescription = "Retour"
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(dp(52), dp(48)))
        header.addView(label("Recherche", 22f, true, HydriaColors.text), LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(10) })
        stateLabel = label("", 11f, true, HydriaColors.textSecondary).apply { gravity = Gravity.END }
        header.addView(stateLabel, LinearLayout.LayoutParams(-2, -2))
        root.addView(header, LinearLayout.LayoutParams(-1, -2))

        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            // Les puces mesurent 48 dp (zone tactile, pastille visible de 34 dp) : marges réduites d'autant.
            setPadding(dp(12), dp(3), dp(12), 0)
        }
        Section.entries.forEach { value ->
            tabs.addView(HydriaUi.chip(this,
                when (value) { Section.ALL -> "Tout"; Section.PEOPLE -> "Personnes"; Section.WORKS -> "Ouvrages" },
                section == value,
            ).apply {
                setOnClickListener { section = value; page = 1; buildScreen(queryField.text.toString()) }
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginEnd = dp(6) })
        }
        root.addView(tabs, LinearLayout.LayoutParams(-1, -2))

        // Champ de recherche 56 dp pleine largeur, filet cyan, croix d'effacement.
        val searchRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(6), dp(12), dp(8))
            background = HydriaUi.rounded(this@SearchActivity, HydriaColors.surface, 14f, HydriaColors.cyan, 2f)
        }
        val clearButton = TextView(this).apply {
            text = "✕"
            textSize = 16f
            setTextColor(HydriaColors.textSecondary)
            gravity = Gravity.CENTER
            contentDescription = "Effacer la recherche"
            setOnClickListener { queryField.text.clear() }
        }
        queryField = EditText(this).apply {
            hint = when (section) { Section.ALL -> "Au moins 2 caractères"; Section.PEOPLE -> "Nom, téléphone ou e-mail"; Section.WORKS -> "Nom, type, point d’eau ou village" }
            setSingleLine(true)
            HydriaUi.styleInput(this)
            background = null
            setPadding(dp(4), 0, 0, 0)
            setText(initialQuery)
            setSelection(text.length)
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    clearButton.visibility = if ((s?.length ?: 0) > 0) View.VISIBLE else View.GONE
                    handler.removeCallbacksAndMessages(DEBOUNCE_TOKEN)
                    handler.postAtTime({ page = 1; load() }, DEBOUNCE_TOKEN, System.currentTimeMillis() + if (section == Section.PEOPLE) 400 else 500)
                }
                override fun afterTextChanged(s: Editable?) = Unit
            })
            setOnEditorActionListener { _, _, _ -> load(); true }
        }
        clearButton.visibility = if (initialQuery.isNotEmpty()) View.VISIBLE else View.GONE
        searchRow.addView(queryField, LinearLayout.LayoutParams(0, dp(48), 1f))
        searchRow.addView(clearButton, LinearLayout.LayoutParams(dp(36), dp(36)))
        root.addView(searchRow, LinearLayout.LayoutParams(-1, dp(56)).apply {
            leftMargin = dp(12); rightMargin = dp(12); topMargin = dp(4)
        })

        val filterRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), 0, dp(12), dp(8))
        }
        filterButton = Button(this).apply {
            HydriaUi.styleSecondary(this, true)
            setOnClickListener { showFilters() }
        }
        // Sur tablette, les facettes vivent dans le volet de gauche : plus de bouton « Filtres ».
        if (!HydriaWindow.of(this).isTablet) filterRow.addView(filterButton, LinearLayout.LayoutParams(-2, dp(46)))
        if (section == Section.WORKS) filterRow.addView(Button(this).apply {
            text = "Interventions récentes"
            HydriaUi.styleSecondary(this, true)
            setOnClickListener { startActivity(Intent(this@SearchActivity, RecentInterventionsActivity::class.java)) }
        }, LinearLayout.LayoutParams(0, dp(46), 1f).apply { marginStart = dp(8) })
        progress = ProgressBar(this).apply { visibility = View.GONE }
        filterRow.addView(progress, LinearLayout.LayoutParams(dp(34), dp(34)).apply { marginStart = dp(12) })
        root.addView(filterRow, LinearLayout.LayoutParams(-1, -2))

        activeFilters = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(12), 0, dp(12), dp(8))
        }
        root.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(activeFilters)
        }, LinearLayout.LayoutParams(-1, -2))

        resultList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(4), dp(12), dp(24))
        }
        resultsScroll = ScrollView(this).apply { addView(resultList) }

        wideLayout = HydriaWindow.of(this).isTablet
        if (wideLayout) {
            // Tablette : facettes permanentes (300) | résultats (400) | fiche du résultat.
            val facets = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(14), dp(14), dp(14), dp(14))
            }
            facetsHost = facets
            val pane = FrameLayout(this).apply { setBackgroundColor(HydriaColors.background) }
            detailPane = pane
            fun sep() = View(this).apply { setBackgroundColor(HydriaColors.outline) }
            root.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                addView(ScrollView(this@SearchActivity).apply { addView(facets) },
                    LinearLayout.LayoutParams(dp(300), LinearLayout.LayoutParams.MATCH_PARENT))
                addView(sep(), LinearLayout.LayoutParams(dp(1), LinearLayout.LayoutParams.MATCH_PARENT))
                addView(resultsScroll, LinearLayout.LayoutParams(dp(400), LinearLayout.LayoutParams.MATCH_PARENT))
                addView(sep(), LinearLayout.LayoutParams(dp(1), LinearLayout.LayoutParams.MATCH_PARENT))
                addView(pane, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))
            }, LinearLayout.LayoutParams(-1, 0, 1f))
            rebuildFacets()
            renderResultDetailPlaceholder()
        } else {
            detailPane = null
            facetsHost = null
            root.addView(resultsScroll, LinearLayout.LayoutParams(-1, 0, 1f))
        }
        setContentView(root)
        updateFilterLabel()
        load()
    }

    private fun renderResultDetailPlaceholder() {
        val pane = detailPane ?: return
        pane.removeAllViews()
        pane.addView(TextView(this).apply {
            text = "Touchez un résultat pour ouvrir sa fiche ici."
            textSize = 13f
            setTextColor(HydriaColors.textSecondary)
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(24), dp(24), dp(24))
        }, FrameLayout.LayoutParams(-1, -1))
    }

    private fun renderResultDetail(item: JSONObject) {
        val pane = detailPane ?: return
        pane.removeAllViews()
        val type = item.optString("type", if (section == Section.PEOPLE) item.optString("type") else "ouvrage")
        val title = item.optString("title", item.optString("nom", item.optString("name", "Sans nom")))
        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(24))
        }
        body.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(searchTypeToken(item, type), LinearLayout.LayoutParams(dp(56), dp(56)))
            addView(label(title, 20f, true, HydriaColors.text),
                LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(12) })
        })
        val subtitle = item.optString("subtitle", item.optString("sous_titre", buildWorkSubtitle(item)))
        if (subtitle.isNotBlank()) body.addView(label(subtitle, 13f, false, HydriaColors.textSecondary)
            .apply { setPadding(0, dp(10), 0, 0) })
        val contact = item.optString("contact")
        if (contact.isNotBlank() && contact != "-") body.addView(label(contact, 13f, false, HydriaColors.cyan)
            .apply { setPadding(0, dp(4), 0, 0) })
        val fields = item.optJSONArray("fields")
        if (fields != null) for (i in 0 until fields.length()) {
            val field = fields.optJSONObject(i) ?: continue
            val value = field.optString("value")
            if (value.isBlank() || isTechnicalUuid(value)) continue
            body.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(14), dp(10), dp(14), dp(10))
                HydriaUi.card(this)
                addView(label(field.optString("label"), 11f, true, HydriaColors.textSecondary))
                addView(label(value, 14f, false, HydriaColors.text).apply { setPadding(0, dp(3), 0, 0) })
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        }
        body.addView(Button(this).apply {
            text = "Ouvrir la fiche complète"
            HydriaUi.stylePrimary(this)
            setOnClickListener { openDetailActivity(item, type, title) }
        }, LinearLayout.LayoutParams(-1, dp(56)).apply { topMargin = dp(16) })
        pane.addView(ScrollView(this).apply { addView(body) })
    }

    private fun openDetailActivity(item: JSONObject, type: String, title: String) {
        startActivity(Intent(this, SearchDetailActivity::class.java).apply {
            putExtra("entity_type", type)
            putExtra("entity_id", item.optString("id"))
            putExtra("title", title)
            putExtra("cached_item", item.toString())
            putExtra("person_mode", section == Section.PEOPLE)
        })
    }

    // ── Facettes permanentes (tablette) — remplacent les AlertDialog de showFilters() ──

    private fun rebuildFacets() {
        val host = facetsHost ?: return
        host.removeAllViews()
        host.addView(label("FILTRES", 11f, true, HydriaColors.textSecondary).apply {
            letterSpacing = 0.09f
            setPadding(0, 0, 0, dp(10))
        })
        when (section) {
            Section.ALL -> {
                host.addView(label("Catégories", 13f, true, HydriaColors.text))
                ALL_TYPES.forEach { (id, labelText) ->
                    host.addView(CheckBox(this).apply {
                        text = labelText
                        textSize = 13.5f
                        setTextColor(HydriaColors.text)
                        buttonTintList = ColorStateList.valueOf(HydriaColors.cyan)
                        isChecked = id in selectedTypes
                        setOnCheckedChangeListener { _, checked ->
                            if (checked) selectedTypes.add(id) else selectedTypes.remove(id)
                            updateFilterLabel(); page = 1
                            handler.removeCallbacksAndMessages(FILTER_TOKEN)
                            handler.postAtTime({ load() }, FILTER_TOKEN, System.currentTimeMillis() + 250)
                        }
                    }, LinearLayout.LayoutParams(-1, dp(42)))
                }
            }
            Section.PEOPLE -> {
                val types = listOf("" to "Tous les types") + PEOPLE_TYPES
                val statuses = listOf("actif" to "Actifs", "inactif" to "Inactifs", "tous" to "Actifs et inactifs")
                host.addView(label("Type", 13f, true, HydriaColors.text))
                host.addView(
                    facetSpinner(types.map { it.second }, types.indexOfFirst { it.first == peopleType }) { pos ->
                        val v = types[pos].first
                        if (v != peopleType) { peopleType = v; updateFilterLabel(); page = 1; load() }
                    },
                    LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(4) },
                )
                host.addView(label("Statut", 13f, true, HydriaColors.text),
                    LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
                host.addView(
                    facetSpinner(statuses.map { it.second }, statuses.indexOfFirst { it.first == peopleStatus }) { pos ->
                        val v = statuses[pos].first
                        if (v != peopleStatus) { peopleStatus = v; updateFilterLabel(); page = 1; load() }
                    },
                    LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(4) },
                )
            }
            Section.WORKS -> {
                val payload = workFiltersPayload
                if (payload == null) {
                    host.addView(Button(this).apply {
                        text = "Charger les filtres géographiques"
                        HydriaUi.styleSecondary(this)
                        setOnClickListener { loadWorkFiltersForPanel() }
                    }, LinearLayout.LayoutParams(-1, dp(48)))
                } else {
                    val regions = options(payload, "regions")
                    val districts = options(payload, "districts")
                    val communes = options(payload, "communes")
                    val employees = options(payload, "employees")
                    fun geo(title: String, values: List<Option>, current: String, set: (Option) -> Unit) {
                        host.addView(label(title, 13f, true, HydriaColors.text),
                            LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })
                        host.addView(
                            facetSpinner(values.map { it.label }, values.indexOfFirst { it.id == current }) { pos ->
                                set(values[pos]); page = 1; updateFilterLabel(); load()
                            },
                            LinearLayout.LayoutParams(-1, dp(48)).apply { topMargin = dp(4) },
                        )
                    }
                    geo("Région", regions, workRegion) { workRegion = it.id; workRegionLabel = if (it.id.isBlank()) "" else it.label }
                    geo("District", districts, workDistrict) { workDistrict = it.id; workDistrictLabel = if (it.id.isBlank()) "" else it.label }
                    geo("Commune", communes, workCommune) { workCommune = it.id; workCommuneLabel = if (it.id.isBlank()) "" else it.label }
                    geo("Employé responsable", employees, workEmployee) { workEmployee = it.id; workEmployeeLabel = if (it.id.isBlank()) "" else it.label }
                    host.addView(Button(this).apply {
                        text = "Interventions récentes"
                        HydriaUi.styleSecondary(this)
                        setOnClickListener { startActivity(Intent(this@SearchActivity, RecentInterventionsActivity::class.java)) }
                    }, LinearLayout.LayoutParams(-1, dp(44)).apply { topMargin = dp(14) })
                }
            }
        }
        host.addView(Button(this).apply {
            text = "Réinitialiser"
            HydriaUi.styleSecondary(this)
            setOnClickListener { resetFilters() }
        }, LinearLayout.LayoutParams(-1, dp(44)).apply { topMargin = dp(18) })
    }

    private fun facetSpinner(labels: List<String>, selectedIndex: Int, onPick: (Int) -> Unit): Spinner =
        Spinner(this).apply {
            adapter = ArrayAdapter(this@SearchActivity, android.R.layout.simple_spinner_dropdown_item, labels)
            setSelection(selectedIndex.coerceAtLeast(0), false)
            HydriaUi.styleSpinner(this)
            // Attacher le listener après la sélection initiale pour ne pas déclencher load() au montage.
            post {
                onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                    override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) { onPick(position) }
                    override fun onNothingSelected(parent: AdapterView<*>?) {}
                }
            }
        }

    private fun resetFilters() {
        selectedTypes.clear()
        selectedTypes.addAll(ALL_TYPES.filter { it.first != "planning" }.map { it.first })
        peopleType = ""; peopleStatus = "actif"
        workRegion = ""; workDistrict = ""; workCommune = ""; workEmployee = ""
        workRegionLabel = ""; workDistrictLabel = ""; workCommuneLabel = ""; workEmployeeLabel = ""
        page = 1
        updateFilterLabel(); rebuildFacets(); load()
    }

    private fun loadWorkFiltersForPanel() {
        val cacheKey = "work_filters"
        store.searchCache(cacheKey)?.let { workFiltersPayload = it; rebuildFacets() }
        if (!isOnline()) return
        progress.visibility = View.VISIBLE
        executor.execute {
            val response = runCatching { HydriaNetwork.workFilters(store.token.orEmpty()) }
            runOnUiThread {
                progress.visibility = View.GONE
                response.onSuccess {
                    if (it.successful) {
                        store.saveSearchCache(cacheKey, it.body)
                        workFiltersPayload = it.body
                        rebuildFacets()
                    }
                }
            }
        }
    }

    private fun showFilters() {
        when (section) {
            Section.ALL -> {
                val labels = ALL_TYPES.map { it.second }.toTypedArray()
                val checked = ALL_TYPES.map { it.first in selectedTypes }.toBooleanArray()
                AlertDialog.Builder(this).setTitle("Catégories")
                    .setMultiChoiceItems(labels, checked) { _, index, value ->
                        if (value) selectedTypes.add(ALL_TYPES[index].first) else selectedTypes.remove(ALL_TYPES[index].first)
                        updateFilterLabel(); page = 1
                        handler.removeCallbacksAndMessages(FILTER_TOKEN)
                        handler.postAtTime({ load() }, FILTER_TOKEN, System.currentTimeMillis() + 200)
                    }
                    .setNeutralButton("Tout désélectionner") { _, _ -> selectedTypes.clear(); updateFilterLabel(); load() }
                    .setNegativeButton("Tout sélectionner") { _, _ ->
                        selectedTypes.clear(); selectedTypes.addAll(ALL_TYPES.map { it.first }); updateFilterLabel(); load()
                    }
                    .setPositiveButton("Appliquer") { _, _ -> updateFilterLabel(); page = 1; load() }
                    .show()
            }
            Section.PEOPLE -> showPeopleFilters()
            Section.WORKS -> showWorkFilters()
        }
    }

    private fun showPeopleFilters() {
        val container = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), 0) }
        val types = listOf("" to "Tous les types") + PEOPLE_TYPES
        val statuses = listOf("actif" to "Actifs seulement", "inactif" to "Inactifs seulement", "tous" to "Actifs et inactifs")
        container.addView(label("Type", 13f, true, HydriaColors.text))
        val typeSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@SearchActivity, android.R.layout.simple_spinner_dropdown_item, types.map { it.second })
            setSelection(types.indexOfFirst { it.first == peopleType }.coerceAtLeast(0)); HydriaUi.styleSpinner(this)
        }
        container.addView(typeSpinner, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(4) })
        container.addView(label("Statut", 13f, true, HydriaColors.text), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        val statusSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@SearchActivity, android.R.layout.simple_spinner_dropdown_item, statuses.map { it.second })
            setSelection(statuses.indexOfFirst { it.first == peopleStatus }.coerceAtLeast(0)); HydriaUi.styleSpinner(this)
        }
        container.addView(statusSpinner, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(4) })
        AlertDialog.Builder(this).setTitle("Filtres personnes").setView(container)
            .setNegativeButton("Fermer", null).setPositiveButton("Appliquer") { _, _ ->
                peopleType = types[typeSpinner.selectedItemPosition].first
                peopleStatus = statuses[statusSpinner.selectedItemPosition].first
                updateFilterLabel(); page = 1; load()
            }.show()
    }

    private fun showWorkFilters() {
        val key = "work_filters"
        val cached = store.searchCache(key)
        if (!isOnline()) {
            if (cached != null) renderWorkFiltersDialog(cached)
            else AlertDialog.Builder(this).setMessage("Les filtres géographiques ne sont pas encore téléchargés.").setPositiveButton("OK", null).show()
            return
        }
        progress.visibility = View.VISIBLE
        executor.execute {
            val response = runCatching { HydriaNetwork.workFilters(store.token.orEmpty()) }
            runOnUiThread {
                progress.visibility = View.GONE
                response.onSuccess {
                    if (it.successful) {
                        store.saveSearchCache(key, it.body)
                        renderWorkFiltersDialog(it.body)
                    } else if (cached != null) renderWorkFiltersDialog(cached) else renderMessage(it.error)
                }.onFailure { if (cached != null) renderWorkFiltersDialog(cached) else renderMessage(it.message ?: "Filtres indisponibles") }
            }
        }
    }

    private fun options(payload: JSONObject, key: String): List<Option> {
        val rows = payload.optJSONArray(key) ?: JSONArray()
        return listOf(Option("", "Tous")) + (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index); Option(row.optString("id"), row.optString("label"))
        }
    }

    private fun renderWorkFiltersDialog(payload: JSONObject) {
        val regions = options(payload, "regions")
        val districts = options(payload, "districts")
        val communes = options(payload, "communes")
        val employees = options(payload, "employees")
        val wrapper = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(18), 0, dp(18), 0) }
        fun spinner(title: String, values: List<Option>, current: String): Spinner {
            wrapper.addView(label(title, 13f, true, HydriaColors.text), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })
            return Spinner(this).apply {
                adapter = ArrayAdapter(this@SearchActivity, android.R.layout.simple_spinner_dropdown_item, values.map { it.label })
                setSelection(values.indexOfFirst { it.id == current }.coerceAtLeast(0)); HydriaUi.styleSpinner(this)
                wrapper.addView(this, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(4) })
            }
        }
        val regionSpinner = spinner("Région", regions, workRegion)
        val districtSpinner = spinner("District", districts, workDistrict)
        val communeSpinner = spinner("Commune", communes, workCommune)
        val employeeSpinner = spinner("Employé responsable", employees, workEmployee)
        AlertDialog.Builder(this).setTitle("Filtres ouvrages").setView(wrapper)
            .setNeutralButton("Réinitialiser") { _, _ ->
                workRegion = ""; workDistrict = ""; workCommune = ""; workEmployee = ""
                workRegionLabel = ""; workDistrictLabel = ""; workCommuneLabel = ""; workEmployeeLabel = ""
                page = 1; updateFilterLabel(); load()
            }
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Appliquer") { _, _ ->
                regions[regionSpinner.selectedItemPosition].also { workRegion = it.id; workRegionLabel = if (it.id.isBlank()) "" else it.label }
                districts[districtSpinner.selectedItemPosition].also { workDistrict = it.id; workDistrictLabel = if (it.id.isBlank()) "" else it.label }
                communes[communeSpinner.selectedItemPosition].also { workCommune = it.id; workCommuneLabel = if (it.id.isBlank()) "" else it.label }
                employees[employeeSpinner.selectedItemPosition].also { workEmployee = it.id; workEmployeeLabel = if (it.id.isBlank()) "" else it.label }
                page = 1; updateFilterLabel(); load()
            }.show()
    }

    private fun updateFilterLabel() {
        filterButton.text = when (section) {
            Section.ALL -> "Filtres · ${selectedTypes.size}/${ALL_TYPES.size}"
            Section.PEOPLE -> "Filtres · ${PEOPLE_TYPES.firstOrNull { it.first == peopleType }?.second ?: "Tous"} · ${peopleStatus.replaceFirstChar { it.uppercase() }}"
            Section.WORKS -> "Filtres ouvrages"
        }
        if (::activeFilters.isInitialized) {
            activeFilters.removeAllViews()
            when (section) {
                Section.ALL -> ALL_TYPES.filter { it.first in selectedTypes }.forEach { (id, value) ->
                    activeFilters.addView(filterToken(value) {
                        selectedTypes.remove(id); updateFilterLabel(); page = 1; load()
                    }, LinearLayout.LayoutParams(-2, dp(34)).apply { marginEnd = dp(6) })
                }
                Section.PEOPLE -> listOf(
                    PEOPLE_TYPES.firstOrNull { it.first == peopleType }?.second ?: "Tous les types",
                    peopleStatus.replaceFirstChar { it.uppercase() },
                ).forEach { value ->
                    activeFilters.addView(filterToken(value, null),
                        LinearLayout.LayoutParams(-2, dp(34)).apply { marginEnd = dp(6) })
                }
                Section.WORKS -> (listOf("Périmètre autorisé") +
                    listOf(workRegionLabel, workDistrictLabel, workCommuneLabel, workEmployeeLabel).filter { it.isNotBlank() })
                    .forEach { value ->
                        activeFilters.addView(filterToken(value, null),
                            LinearLayout.LayoutParams(-2, dp(34)).apply { marginEnd = dp(6) })
                    }
            }
        }
    }

    /** Jeton de filtre actif : label + « ✕ » retirable si [onRemove] est fourni. */
    private fun filterToken(value: String, onRemove: (() -> Unit)?): TextView = TextView(this).apply {
        text = if (onRemove != null) "$value  ✕" else value
        textSize = 12f
        typeface = HydriaType.display(600)
        setTextColor(HydriaColors.cyan)
        gravity = Gravity.CENTER
        setPadding(dp(12), 0, dp(12), 0)
        background = HydriaUi.rounded(this@SearchActivity, HydriaColors.surfaceRaised, 17f, HydriaColors.cyan)
        if (onRemove != null) setOnClickListener { onRemove() }
    }

    private fun cacheKey(): String = "search:${section.name}:${queryField.text.toString().trim().lowercase(Locale.ROOT)}:${selectedTypes.sorted()}:$peopleType:$peopleStatus:$workRegion:$workDistrict:$workCommune:$workEmployee:$page"

    private fun load() {
        val query = queryField.text.toString().trim()
        if (section == Section.ALL && query.length < 2) {
            currentResults = JSONArray(); total = 0; hasNext = false
            renderMessage("Saisissez au moins 2 caractères pour lancer la recherche.")
            updateNetworkState(false)
            return
        }
        val requestGeneration = ++generation
        progress.visibility = View.VISIBLE
        val key = cacheKey()
        if (!isOnline()) {
            progress.visibility = View.GONE
            val cached = store.searchCache(key) ?: offlineSnapshotResults(query)
            if (cached != null) consume(cached, cachedResult = true)
            else renderMessage("Aucun résultat téléchargé pour cette recherche. Connectez-vous puis relancez-la pour la rendre disponible hors ligne.")
            updateNetworkState(true)
            return
        }
        executor.execute {
            val token = store.token.orEmpty()
            val response = runCatching {
                when (section) {
                    Section.ALL -> HydriaNetwork.search(token, query, selectedTypes, page)
                    Section.PEOPLE -> HydriaNetwork.people(token, query, peopleType, peopleStatus, page)
                    Section.WORKS -> HydriaNetwork.works(token, query, page, workRegion, workDistrict, workCommune, workEmployee)
                }
            }
            runOnUiThread {
                if (requestGeneration != generation) return@runOnUiThread
                progress.visibility = View.GONE
                response.onSuccess {
                    if (it.successful) {
                        store.saveSearchCache(key, it.body)
                        consume(it.body, cachedResult = false)
                    } else renderMessage(it.error)
                }.onFailure {
                    val cached = store.searchCache(key)
                    if (cached != null) consume(cached, cachedResult = true)
                    else renderMessage("Recherche indisponible : ${it.message ?: "erreur réseau"}")
                }
                updateNetworkState(false)
            }
        }
    }

    private fun consume(payload: JSONObject, cachedResult: Boolean) {
        currentResults = payload.optJSONArray("results") ?: JSONArray()
        total = payload.optInt("total", currentResults.length())
        hasNext = payload.optBoolean("has_next", false)
        resultList.removeAllViews()
        resultList.addView(label(
            "$total RÉSULTAT${if (total > 1) "S" else ""}${if (cachedResult) " · COPIE HORS LIGNE" else ""}",
            11.5f, true, if (cachedResult) HydriaColors.warning else HydriaColors.textSecondary,
        ).apply { letterSpacing = 0.08f }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8) })
        if (currentResults.length() == 0) {
            resultList.addView(label("Aucun résultat.", 15f, false, HydriaColors.textSecondary))
            return
        }
        if (section == Section.WORKS) renderGroupedWorks(currentResults)
        else for (index in 0 until currentResults.length()) resultList.addView(resultCard(currentResults.getJSONObject(index)))
        if (hasNext) resultList.addView(Button(this).apply {
            text = "Page suivante"
            HydriaUi.styleSecondary(this, true)
            setOnClickListener { page += 1; load() }
        }, LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(10) })
        if (restoredScrollY > 0) resultsScroll.post {
            resultsScroll.scrollTo(0, restoredScrollY)
            restoredScrollY = 0
        }
    }

    private fun renderGroupedWorks(rows: JSONArray) {
        val grouped = linkedMapOf<String, MutableList<JSONObject>>()
        for (index in 0 until rows.length()) {
            val item = rows.getJSONObject(index)
            val key = mg.hydria.shared.rules.search.SearchRules.worksGroupKey(item)
            grouped.getOrPut(key) { mutableListOf() }.add(item)
        }
        grouped.forEach { (key, works) ->
            val path = key.split(mg.hydria.shared.rules.search.SearchRules.GROUP_KEY_SEPARATOR)
            val container = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = View.VISIBLE }
            val header = Button(this).apply {
                text = "▾ ${path.joinToString("  ›  ")} · ${works.size}"
                gravity = Gravity.START or Gravity.CENTER_VERTICAL
                HydriaUi.styleSecondary(this, true)
                setOnClickListener {
                    val opening = container.visibility != View.VISIBLE
                    container.visibility = if (opening) View.VISIBLE else View.GONE
                    text = "${if (opening) "▾" else "▸"} ${path.joinToString("  ›  ")} · ${works.size}"
                }
            }
            resultList.addView(header, LinearLayout.LayoutParams(-1, dp(50)).apply { bottomMargin = dp(7) })
            works.forEach { container.addView(resultCard(it)) }
            resultList.addView(container)
        }
    }

    private fun resultCard(item: JSONObject): View {
        val type = item.optString("type", if (section == Section.PEOPLE) item.optString("type") else if (section == Section.WORKS) "ouvrage" else "")
        val title = item.optString("title", item.optString("nom", item.optString("name", "Sans nom")))
        val subtitle = item.optString("subtitle", item.optString("sous_titre", buildWorkSubtitle(item)))
        val isIntervention = type.contains("interv", true) || type.contains("repar", true) || type.contains("répar", true)
        val overdue = isIntervention && (item.optBoolean("en_retard") ||
            item.optString("statut").contains("retard", true) || item.optString("statut_display").contains("retard", true))

        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(14), dp(13), dp(14), dp(13))
            if (overdue) HydriaUi.accentedCard(this, Tone.ERROR) else HydriaUi.card(this)
            isClickable = true; isFocusable = true
        }
        card.addView(searchTypeToken(item, type), LinearLayout.LayoutParams(dp(38), dp(38)))
        card.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(label(title, 16f, true, HydriaColors.text))
            if (subtitle.isNotBlank()) addView(label(subtitle, 12.5f, false, HydriaColors.textSecondary)
                .apply { setPadding(0, dp(3), 0, 0) })
            val contact = item.optString("contact")
            if (contact.isNotBlank() && contact != "-") addView(label(contact, 12.5f, false, HydriaColors.cyan)
                .apply { setPadding(0, dp(3), 0, 0) })
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(12) })
        card.setOnClickListener {
            if (wideLayout) renderResultDetail(item) else openDetailActivity(item, type, title)
        }
        return card.apply { layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) } }
    }

    /** Jeton de type 38 dp : PE cyan, V violet, EQ vase, IN rouge, initiales pour une personne. */
    private fun searchTypeToken(item: JSONObject, type: String): TextView {
        val t = type.lowercase(Locale.ROOT)
        val (code, color) = when {
            section == Section.PEOPLE || t.contains("employe") || t.contains("personne") || t.contains("client") -> {
                val name = item.optString("title", item.optString("nom", item.optString("name", "?")))
                (name.split(" ", "-").filter { it.isNotBlank() }.take(2)
                    .joinToString("") { it.first().uppercaseChar().toString() }.ifBlank { "?" }) to HydriaColors.cyan
            }
            t.contains("point") || t == "pe" -> "PE" to HydriaColors.cyan
            t.contains("village") -> "V" to android.graphics.Color.parseColor("#8B78F0")
            t.contains("equip") || t.contains("équip") -> "EQ" to HydriaColors.vase
            t.contains("interv") || t.contains("repar") || t.contains("répar") -> "IN" to HydriaColors.error
            t.contains("commune") -> "CO" to HydriaColors.cyan
            else -> "OU" to HydriaColors.cyan
        }
        return TextView(this).apply {
            text = code
            typeface = HydriaType.numeral(700)
            textSize = if (code.length > 2) 11f else 12f
            setTextColor(color)
            gravity = Gravity.CENTER
            background = HydriaUi.rounded(
                this@SearchActivity,
                android.graphics.Color.argb(34, android.graphics.Color.red(color), android.graphics.Color.green(color), android.graphics.Color.blue(color)),
                10f,
                android.graphics.Color.argb(90, android.graphics.Color.red(color), android.graphics.Color.green(color), android.graphics.Color.blue(color)),
            )
        }
    }

    // Regles portees vers shared/ (Phase 1 migration KMP, module Recherche) :
    // voir mg.hydria.shared.rules.search.SearchRules.
    private fun buildWorkSubtitle(item: JSONObject): String = mg.hydria.shared.rules.search.SearchRules.workSubtitle(item)

    private fun offlineSnapshotResults(query: String): JSONObject? {
        if (section != Section.WORKS && section != Section.ALL) return null
        val works = store.snapshot?.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: return null
        return mg.hydria.shared.rules.search.SearchRules.offlineWorksResults(works, query)
    }

    private fun renderMessage(message: String) {
        resultList.removeAllViews()
        resultList.addView(label(message, 15f, false, HydriaColors.textSecondary).apply {
            gravity = Gravity.CENTER; setPadding(dp(16), dp(40), dp(16), dp(16))
        })
    }

    private fun updateNetworkState(offline: Boolean) {
        val key = cacheKey()
        val updated = store.searchCacheUpdatedAt(key)
        stateLabel.text = if (offline || !isOnline()) {
            "HORS LIGNE\n${updated?.let { DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(it)) } ?: "périmètre téléchargé"}"
        } else "EN LIGNE\npérimètre autorisé"
        stateLabel.setTextColor(if (offline || !isOnline()) HydriaColors.warning else HydriaColors.success)
    }

    private fun isOnline(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        return manager.getNetworkCapabilities(network)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }

    private fun label(value: String, size: Float, bold: Boolean, color: Int) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    companion object {
        private val DEBOUNCE_TOKEN = Any()
        private val FILTER_TOKEN = Any()
        val ALL_TYPES = listOf(
            "village" to "Villages", "ouvrage" to "Ouvrages", "commune" to "Communes",
            "planning" to "Plannings", "employe" to "Employés", "point_eau" to "Points d’eau",
            "representant" to "Représentantes", "autorite" to "Autorités", "tiers" to "Tiers",
            "fournisseur" to "Fournisseurs", "equipement" to "Équipements",
            "designation" to "Désignations", "modalite" to "Modalités", "carte_sociale" to "Cartes sociales",
        )
        val PEOPLE_TYPES = listOf(
            "abonne" to "Abonné", "employe" to "Employé", "representant" to "Représentante",
            "autorite" to "Autorité", "tiers" to "Tiers", "fournisseur" to "Fournisseur",
        )
    }
}
