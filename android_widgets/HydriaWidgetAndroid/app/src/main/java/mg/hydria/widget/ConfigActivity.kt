package mg.hydria.widget

import android.Manifest
import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.content.pm.PackageManager
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class ConfigActivity : AppCompatActivity() {
    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID
    private lateinit var loginSection: LinearLayout
    private lateinit var filterSection: LinearLayout
    private lateinit var usernameInput: EditText
    private lateinit var passwordInput: EditText
    private lateinit var errorText: TextView
    private lateinit var filterStatus: TextView
    private lateinit var loginButton: Button
    private lateinit var applyButton: Button
    private lateinit var organisationSpinner: Spinner
    private lateinit var employeeSpinner: Spinner
    private lateinit var regionSpinner: Spinner
    private lateinit var districtSpinner: Spinner
    private lateinit var communeSpinner: Spinner

    private var allDistricts: List<HydriaApi.DistrictOption> = emptyList()
    private var allCommunes: List<HydriaApi.CommuneOption> = emptyList()
    private var suppressCallbacks = false
    private var loadedGeoOrganisationId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(Activity.RESULT_CANCELED)
        appWidgetId = intent?.extras?.getInt(
            AppWidgetManager.EXTRA_APPWIDGET_ID,
            AppWidgetManager.INVALID_APPWIDGET_ID,
        ) ?: AppWidgetManager.INVALID_APPWIDGET_ID
        setContentView(R.layout.activity_config)
        bindViews()
        configureListeners()

        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            applyButton.text = "Ajouter le widget à l'écran d'accueil"
        }

        if (TokenStore.getToken(this) != null) {
            requestNotificationPermission()
            showFilters()
            loadFilters(TokenStore.getFilters(this, appWidgetId).organisationId)
        }
    }

    private fun bindViews() {
        loginSection = findViewById(R.id.login_section)
        filterSection = findViewById(R.id.filter_section)
        usernameInput = findViewById(R.id.input_username)
        passwordInput = findViewById(R.id.input_password)
        errorText = findViewById(R.id.login_error)
        filterStatus = findViewById(R.id.filter_status)
        loginButton = findViewById(R.id.btn_login)
        applyButton = findViewById(R.id.btn_apply_filters)
        organisationSpinner = findViewById(R.id.filter_organisation)
        employeeSpinner = findViewById(R.id.filter_employee)
        regionSpinner = findViewById(R.id.filter_region)
        districtSpinner = findViewById(R.id.filter_district)
        communeSpinner = findViewById(R.id.filter_commune)
    }

    private fun configureListeners() {
        loginButton.setOnClickListener { login() }
        applyButton.setOnClickListener { saveAndFinish() }
        findViewById<Button>(R.id.btn_change_account).setOnClickListener {
            TokenStore.clearToken(this)
            filterSection.visibility = View.GONE
            loginSection.visibility = View.VISIBLE
            errorText.text = "Connectez le nouveau compte."
            passwordInput.text.clear()
        }

        organisationSpinner.onItemSelectedListener = listener { position ->
            if (suppressCallbacks) return@listener
            val selected = optionAt(organisationSpinner, position)?.id ?: return@listener
            if (selected != loadedGeoOrganisationId) loadFilters(selected)
        }
        employeeSpinner.onItemSelectedListener = listener {
            if (!suppressCallbacks) updateSummary()
        }
        regionSpinner.onItemSelectedListener = listener {
            if (!suppressCallbacks) {
                populateDistricts(selectedId(regionSpinner), "all", "all")
                updateSummary()
            }
        }
        districtSpinner.onItemSelectedListener = listener {
            if (!suppressCallbacks) {
                populateCommunes(selectedId(districtSpinner), "all")
                updateSummary()
            }
        }
        communeSpinner.onItemSelectedListener = listener {
            if (!suppressCallbacks) updateSummary()
        }
    }

    private fun login() {
        val username = usernameInput.text.toString().trim()
        val password = passwordInput.text.toString()
        if (username.isEmpty() || password.isEmpty()) {
            errorText.text = "Nom d'utilisateur et mot de passe requis"
            return
        }
        loginButton.isEnabled = false
        errorText.text = "Connexion…"
        lifecycleScope.launch {
            val result = HydriaApi.login(username, password)
            loginButton.isEnabled = true
            if (result.success && result.token != null) {
                TokenStore.saveToken(this@ConfigActivity, result.token)
                requestNotificationPermission()
                errorText.text = ""
                showFilters()
                loadFilters(null)
            } else {
                errorText.text = result.error ?: "Connexion échouée"
            }
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                73,
            )
        }
    }

    private fun showFilters() {
        loginSection.visibility = View.GONE
        filterSection.visibility = View.VISIBLE
    }

    private fun loadFilters(organisationId: String?) {
        val token = TokenStore.getToken(this) ?: return
        applyButton.isEnabled = false
        filterStatus.text = "Chargement des filtres…"
        lifecycleScope.launch {
            val result = HydriaApi.fetchFilters(token, organisationId)
            if (!result.success) {
                filterStatus.text = result.error ?: "Filtres indisponibles"
                if (result.error == "Session expirée") {
                    TokenStore.clearToken(this@ConfigActivity)
                    filterSection.visibility = View.GONE
                    loginSection.visibility = View.VISIBLE
                }
                return@launch
            }

            val saved = TokenStore.getFilters(this@ConfigActivity, appWidgetId)
            val organisations = result.organisations.ifEmpty {
                listOf(HydriaApi.FilterOption("all", "Toutes les organisations"))
            }
            val selectedOrganisation = sequenceOf(
                organisationId,
                saved.organisationId,
                result.defaultOrganisationId,
                organisations.firstOrNull()?.id,
            ).filterNotNull().firstOrNull { id -> organisations.any { it.id == id } } ?: "all"

            allDistricts = result.districts
            allCommunes = result.communes
            loadedGeoOrganisationId = selectedOrganisation
            suppressCallbacks = true
            setOptions(organisationSpinner, organisations, selectedOrganisation)

            val employees = listOf(HydriaApi.FilterOption("all", "Tous les agents de recouvrement")) + result.employees
            val preferredEmployee = saved.employeeId.takeIf { id -> employees.any { it.id == id } } ?: "all"
            setOptions(employeeSpinner, employees, preferredEmployee)

            val regions = listOf(HydriaApi.FilterOption("all", "Toutes les régions")) + result.regions
            val preferredRegion = saved.regionId.takeIf { id -> regions.any { it.id == id } } ?: "all"
            setOptions(regionSpinner, regions, preferredRegion)
            populateDistricts(preferredRegion, saved.districtId, saved.communeId)
            suppressCallbacks = false
            applyButton.isEnabled = true
            updateSummary()
        }
    }

    private fun populateDistricts(regionId: String, preferredDistrictId: String, preferredCommuneId: String) {
        val previousSuppression = suppressCallbacks
        suppressCallbacks = true
        val filtered = allDistricts.filter { regionId == "all" || it.regionId == regionId }
            .map { HydriaApi.FilterOption(it.id, it.name) }
        val options = listOf(HydriaApi.FilterOption("all", "Tous les districts")) + filtered
        val districtId = preferredDistrictId.takeIf { id -> options.any { it.id == id } } ?: "all"
        setOptions(districtSpinner, options, districtId)
        populateCommunes(districtId, preferredCommuneId)
        suppressCallbacks = previousSuppression
    }

    private fun populateCommunes(districtId: String, preferredCommuneId: String) {
        val previousSuppression = suppressCallbacks
        suppressCallbacks = true
        val filtered = allCommunes.filter { districtId == "all" || it.districtId == districtId }
            .map { HydriaApi.FilterOption(it.id, it.name) }
        val options = listOf(HydriaApi.FilterOption("all", "Toutes les communes")) + filtered
        val communeId = preferredCommuneId.takeIf { id -> options.any { it.id == id } } ?: "all"
        setOptions(communeSpinner, options, communeId)
        suppressCallbacks = previousSuppression
    }

    private fun setOptions(spinner: Spinner, options: List<HydriaApi.FilterOption>, selectedId: String) {
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, options)
        spinner.setSelection(options.indexOfFirst { it.id == selectedId }.coerceAtLeast(0), false)
    }

    private fun saveAndFinish() {
        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            requestPinWidget()
            return
        }
        TokenStore.saveFilters(
            this,
            appWidgetId,
            TokenStore.Filters(
                organisationId = selectedId(organisationSpinner),
                employeeId = selectedId(employeeSpinner),
                regionId = selectedId(regionSpinner),
                districtId = selectedId(districtSpinner),
                communeId = selectedId(communeSpinner),
                organisationName = selectedName(organisationSpinner),
                employeeName = selectedName(employeeSpinner),
                regionName = selectedName(regionSpinner),
                districtName = selectedName(districtSpinner),
                communeName = selectedName(communeSpinner),
            ),
        )
        val resultValue = Intent().apply {
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
        }
        setResult(Activity.RESULT_OK, resultValue)
        HydriaWidgetProvider.requestUpdate(this)
        finish()
    }

    private fun requestPinWidget() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            filterStatus.text = "Ajoutez Hydria Widget depuis la liste des widgets de l'écran d'accueil."
            return
        }
        val manager = AppWidgetManager.getInstance(this)
        if (!manager.isRequestPinAppWidgetSupported) {
            filterStatus.text = "Ce lanceur ne permet pas l'ajout direct. Ouvrez la liste des widgets de l'écran d'accueil."
            return
        }
        val provider = ComponentName(this, HydriaWidgetProvider::class.java)
        val requested = manager.requestPinAppWidget(provider, null, null)
        filterStatus.text = if (requested) {
            "Confirmez maintenant l'ajout proposé par Android."
        } else {
            "Android n'a pas pu ouvrir la demande d'ajout du widget."
        }
    }

    private fun updateSummary() {
        filterStatus.text = "Périmètre : ${selectedName(organisationSpinner)} · " +
            "${selectedName(employeeSpinner)} · ${selectedName(regionSpinner)} · " +
            "${selectedName(districtSpinner)} · ${selectedName(communeSpinner)}"
    }

    private fun selectedId(spinner: Spinner) = (spinner.selectedItem as? HydriaApi.FilterOption)?.id ?: "all"
    private fun selectedName(spinner: Spinner) = (spinner.selectedItem as? HydriaApi.FilterOption)?.name ?: "Tous"
    private fun optionAt(spinner: Spinner, position: Int) = spinner.adapter?.getItem(position) as? HydriaApi.FilterOption

    private fun listener(block: (Int) -> Unit) = object : AdapterView.OnItemSelectedListener {
        override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) = block(position)
        override fun onNothingSelected(parent: AdapterView<*>?) = Unit
    }
}
