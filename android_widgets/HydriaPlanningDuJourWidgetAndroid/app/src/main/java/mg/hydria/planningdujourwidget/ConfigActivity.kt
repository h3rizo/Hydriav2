package mg.hydria.planningdujourwidget

import android.app.AlertDialog
import android.app.Activity
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class ConfigActivity : AppCompatActivity() {
    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID
    private lateinit var username: EditText
    private lateinit var password: EditText
    private lateinit var status: TextView
    private lateinit var loginButton: Button
    private lateinit var addButton: Button
    private lateinit var filtresContainer: View
    private lateinit var employeSpinner: Spinner
    private lateinit var baseSpinner: Spinner
    private lateinit var regionSpinner: Spinner
    private lateinit var districtSpinner: Spinner
    private lateinit var communeSpinner: Spinner
    private lateinit var typeButton: Button

    private var filtres: HydriaApi.FiltresResult? = null
    private var selectedTypeIds: MutableList<String> = mutableListOf()
    private var isReconfigure = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(Activity.RESULT_CANCELED)
        setContentView(R.layout.activity_config)
        appWidgetId = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        isReconfigure = appWidgetId != AppWidgetManager.INVALID_APPWIDGET_ID

        username = findViewById(R.id.username)
        password = findViewById(R.id.password)
        status = findViewById(R.id.config_status)
        loginButton = findViewById(R.id.login_button)
        addButton = findViewById(R.id.add_widget_button)
        filtresContainer = findViewById(R.id.filtres_container)
        employeSpinner = findViewById(R.id.filtre_employe)
        baseSpinner = findViewById(R.id.filtre_base)
        regionSpinner = findViewById(R.id.filtre_region)
        districtSpinner = findViewById(R.id.filtre_district)
        communeSpinner = findViewById(R.id.filtre_commune)
        typeButton = findViewById(R.id.filtre_type_button)

        selectedTypeIds = TokenStore.getFiltreTypes(this).toMutableList()

        loginButton.setOnClickListener { login() }
        addButton.setOnClickListener { completeConfiguration() }
        typeButton.setOnClickListener { showTypeDialog() }
        regionSpinner.onItemSelectedListener = SimpleSelectionListener { onRegionChanged() }
        districtSpinner.onItemSelectedListener = SimpleSelectionListener { onDistrictChanged() }

        if (isReconfigure) {
            addButton.text = "ENREGISTRER LES FILTRES"
        }

        if (TokenStore.getToken(this) != null) {
            showConnected()
            loadFiltres()
        }
    }

    private fun login() {
        val user = username.text.toString().trim()
        val secret = password.text.toString()
        if (user.isBlank() || secret.isBlank()) {
            status.text = "Saisissez votre identifiant et votre mot de passe."
            return
        }
        loginButton.isEnabled = false
        status.text = "Connexion à Hydria…"
        lifecycleScope.launch {
            val result = HydriaApi.login(user, secret)
            loginButton.isEnabled = true
            if (result.success && result.token != null) {
                TokenStore.saveToken(this@ConfigActivity, result.token)
                password.text.clear()
                showConnected()
                loadFiltres()
                PlanningDuJourWidgetProvider.requestUpdate(this@ConfigActivity)
            } else status.text = result.error ?: "Connexion impossible"
        }
    }

    private fun showConnected() {
        status.text = "Connecté. Choisissez éventuellement des filtres, puis validez."
        addButton.visibility = View.VISIBLE
        loginButton.text = "Reconnecter"
    }

    private fun loadFiltres() {
        val token = TokenStore.getToken(this) ?: return
        lifecycleScope.launch {
            val result = HydriaApi.fetchFiltres(token)
            if (result.success) {
                filtres = result
                populateFiltres(result)
                filtresContainer.visibility = View.VISIBLE
            }
        }
    }

    private fun populateFiltres(data: HydriaApi.FiltresResult) {
        setSpinner(employeSpinner, "Moi-même et mes subordonnés", data.employes, TokenStore.getFiltreEmploye(this))
        setSpinner(baseSpinner, "Toutes les bases", data.bases, TokenStore.getFiltreBase(this))
        setSpinner(regionSpinner, "Toutes les régions", data.regions, TokenStore.getFiltreRegion(this))
        refreshDistrictSpinner(TokenStore.getFiltreDistrict(this))
        refreshCommuneSpinner(TokenStore.getFiltreCommune(this))
        updateTypeButtonLabel()
    }

    private fun setSpinner(spinner: Spinner, allLabel: String, options: List<HydriaApi.Option>, selectedId: String) {
        val labels = mutableListOf(allLabel)
        labels.addAll(options.map { it.nom })
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, labels)
        val index = options.indexOfFirst { it.id == selectedId }
        spinner.setSelection(if (index >= 0) index + 1 else 0)
        spinner.tag = options
    }

    @Suppress("UNCHECKED_CAST")
    private fun spinnerSelectedId(spinner: Spinner): String {
        val options = spinner.tag as? List<HydriaApi.Option> ?: return "all"
        val position = spinner.selectedItemPosition - 1
        return if (position in options.indices) options[position].id else "all"
    }

    private fun onRegionChanged() {
        refreshDistrictSpinner("all")
        refreshCommuneSpinner("all")
    }

    private fun onDistrictChanged() {
        refreshCommuneSpinner("all")
    }

    private fun refreshDistrictSpinner(preselectId: String) {
        val data = filtres ?: return
        val regionId = spinnerSelectedId(regionSpinner)
        val filtered = if (regionId == "all") data.districts else data.districts.filter { it.parentId == regionId }
        setSpinner(districtSpinner, "Tous les districts", filtered, preselectId)
    }

    private fun refreshCommuneSpinner(preselectId: String) {
        val data = filtres ?: return
        val districtId = spinnerSelectedId(districtSpinner)
        val filtered = if (districtId == "all") data.communes else data.communes.filter { it.parentId == districtId }
        setSpinner(communeSpinner, "Toutes les communes", filtered, preselectId)
    }

    private fun updateTypeButtonLabel() {
        typeButton.text = when {
            selectedTypeIds.isEmpty() -> "Tous les types"
            selectedTypeIds.size == 1 -> {
                val nom = filtres?.typesActivite?.firstOrNull { it.id == selectedTypeIds[0] }?.nom
                nom ?: "1 type sélectionné"
            }
            else -> "${selectedTypeIds.size} types sélectionnés"
        }
    }

    private fun showTypeDialog() {
        val options = filtres?.typesActivite ?: return
        if (options.isEmpty()) return
        val labels = options.map { it.nom }.toTypedArray()
        val checked = BooleanArray(options.size) { index -> selectedTypeIds.contains(options[index].id) }
        AlertDialog.Builder(this)
            .setTitle("Types d'activité")
            .setMultiChoiceItems(labels, checked) { _, which, isChecked -> checked[which] = isChecked }
            .setPositiveButton("OK") { _, _ ->
                selectedTypeIds = options.filterIndexed { index, _ -> checked[index] }.map { it.id }.toMutableList()
                updateTypeButtonLabel()
            }
            .setNegativeButton("Annuler", null)
            .setNeutralButton("Tout effacer") { _, _ ->
                selectedTypeIds = mutableListOf()
                updateTypeButtonLabel()
            }
            .show()
    }

    private fun saveFiltresSelection() {
        TokenStore.saveFiltres(
            this,
            employeId = spinnerSelectedId(employeSpinner),
            baseId = spinnerSelectedId(baseSpinner),
            regionId = spinnerSelectedId(regionSpinner),
            districtId = spinnerSelectedId(districtSpinner),
            communeId = spinnerSelectedId(communeSpinner),
            typeIds = selectedTypeIds,
        )
    }

    private fun completeConfiguration() {
        saveFiltresSelection()
        if (appWidgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
            setResult(Activity.RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId))
            PlanningDuJourWidgetProvider.requestUpdate(this)
            finish()
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = AppWidgetManager.getInstance(this)
            if (manager.isRequestPinAppWidgetSupported) {
                val provider = ComponentName(this, PlanningDuJourWidgetProvider::class.java)
                val callback = PendingIntent.getBroadcast(this, 844, Intent(this, PlanningDuJourWidgetProvider::class.java).setAction(PlanningDuJourWidgetProvider.ACTION_REFRESH), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                manager.requestPinAppWidget(provider, null, callback)
                status.text = "Confirmez l’ajout proposé par Android."
                return
            }
        }
        status.text = "Maintenez un espace vide sur l’écran d’accueil, puis choisissez Widgets > Hydria · Calendrier planning."
    }
}

private class SimpleSelectionListener(private val onSelected: () -> Unit) : android.widget.AdapterView.OnItemSelectedListener {
    override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) = onSelected()
    override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
}
