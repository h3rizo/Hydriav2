package mg.hydria.app.search

import android.content.Context
import android.content.Intent
import android.app.DatePickerDialog
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import mg.hydria.app.Tone
import mg.hydria.app.HydriaNetwork
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaType
import mg.hydria.app.HydriaUi
import mg.hydria.app.OfflineStore
import org.json.JSONArray
import org.json.JSONObject
import java.util.Calendar
import java.util.Locale
import java.io.File
import java.util.concurrent.Executors

class RecentInterventionsActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var store: OfflineStore
    private lateinit var content: LinearLayout
    private lateinit var progress: ProgressBar
    private lateinit var state: TextView
    private lateinit var filterButton: Button
    private var page = 1
    private var status = ""
    private var sort = "created"
    private var otherBases = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        store = OfflineStore(this)
        status = savedInstanceState?.getString("status").orEmpty()
        sort = savedInstanceState?.getString("sort") ?: "created"
        otherBases = savedInstanceState?.getBoolean("other_bases") ?: false
        buildScreen()
        load()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("status", status); outState.putString("sort", sort); outState.putBoolean("other_bases", otherBases)
        super.onSaveInstanceState(outState)
    }

    private fun buildScreen() {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(HydriaColors.background) }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(9)); setBackgroundColor(HydriaColors.backgroundDeep)
        }
        header.addView(Button(this).apply { text = "‹"; HydriaUi.styleSecondary(this); setOnClickListener { finish() } }, LinearLayout.LayoutParams(dp(52), dp(48)))
        header.addView(text("Dernières interventions", 19f, true, HydriaColors.text), LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(10) })
        state = text("", 11f, true, HydriaColors.textSecondary)
        header.addView(state)
        root.addView(header)
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(12), dp(8), dp(12), dp(8)) }
        filterButton = Button(this).apply { HydriaUi.styleSecondary(this, true); setOnClickListener { showFilters() } }
        actions.addView(filterButton, LinearLayout.LayoutParams(0, dp(48), 1f))
        progress = ProgressBar(this).apply { visibility = View.GONE }
        actions.addView(progress, LinearLayout.LayoutParams(dp(38), dp(38)).apply { marginStart = dp(10) })
        root.addView(actions)
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, dp(12), dp(24)) }
        root.addView(ScrollView(this).apply { addView(content) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        updateFilterLabel()
    }

    private fun showFilters() {
        val wrapper = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(18), 0, dp(18), 0) }
        val statusOptions = listOf("" to "Tous", "en_cours" to "En cours", "termine" to "Terminé", "annule" to "Annulé", "reporte" to "Reporté")
        wrapper.addView(text("Statut", 13f, true, HydriaColors.text))
        val statusSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@RecentInterventionsActivity, android.R.layout.simple_spinner_dropdown_item, statusOptions.map { it.second })
            setSelection(statusOptions.indexOfFirst { it.first == status }.coerceAtLeast(0)); HydriaUi.styleSpinner(this)
        }
        wrapper.addView(statusSpinner, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(4) })
        wrapper.addView(text("Tri", 13f, true, HydriaColors.text), margin(top = 12))
        val sortOptions = listOf("created" to "Date de saisie", "intervention" to "Date d’intervention")
        val sortSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@RecentInterventionsActivity, android.R.layout.simple_spinner_dropdown_item, sortOptions.map { it.second })
            setSelection(sortOptions.indexOfFirst { it.first == sort }.coerceAtLeast(0)); HydriaUi.styleSpinner(this)
        }
        wrapper.addView(sortSpinner, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(4) })
        val otherBasesCheck = CheckBox(this).apply {
            text = "Afficher les autres bases"; setTextColor(HydriaColors.text); isChecked = otherBases
        }
        wrapper.addView(otherBasesCheck, margin(top = 10))
        AlertDialog.Builder(this).setTitle("Filtrer les interventions").setView(wrapper)
            .setNegativeButton("Fermer", null).setPositiveButton("Appliquer") { _, _ ->
                status = statusOptions[statusSpinner.selectedItemPosition].first
                sort = sortOptions[sortSpinner.selectedItemPosition].first
                otherBases = otherBasesCheck.isChecked
                page = 1; updateFilterLabel(); load()
            }.show()
    }

    private fun updateFilterLabel() {
        val statusLabel = mapOf("" to "Tous", "en_cours" to "En cours", "termine" to "Terminés", "annule" to "Annulés", "reporte" to "Reportés")[status] ?: status
        filterButton.text = "$statusLabel · ${if (sort == "created") "Saisie" else "Intervention"}${if (otherBases) " · autres bases" else ""}"
    }

    private fun cacheKey() = "interventions:$status:$sort:$otherBases:$page"

    private fun load() {
        progress.visibility = View.VISIBLE
        val cached = store.searchCache(cacheKey())
        if (!online()) {
            progress.visibility = View.GONE
            if (cached != null) render(cached, true) else message("Aucune intervention téléchargée pour ces filtres.")
            return
        }
        executor.execute {
            val result = runCatching { HydriaNetwork.interventions(store.token.orEmpty(), page, otherBases, status, sort) }
            runOnUiThread {
                progress.visibility = View.GONE
                result.onSuccess {
                    if (it.successful) { store.saveSearchCache(cacheKey(), it.body); render(it.body, false) }
                    else if (cached != null) render(cached, true) else message(it.error)
                }.onFailure { if (cached != null) render(cached, true) else message(it.message ?: "Erreur réseau") }
            }
        }
    }

    private fun render(payload: JSONObject, offline: Boolean) {
        content.removeAllViews(); state.text = if (offline) "HORS LIGNE" else "EN LIGNE"; state.setTextColor(if (offline) HydriaColors.warning else HydriaColors.success)
        val rows = payload.optJSONArray("results") ?: JSONArray()
        content.addView(text("${payload.optInt("total", rows.length())} intervention(s)", 13f, true, HydriaColors.textSecondary), margin(bottom = 8))
        for (index in 0 until rows.length()) content.addView(card(rows.getJSONObject(index)), margin(bottom = 9))
        if (rows.length() == 0) message("Aucune intervention.")
        if (payload.optBoolean("has_next")) content.addView(Button(this).apply {
            text = "Page suivante"; HydriaUi.styleSecondary(this, true); setOnClickListener { page += 1; load() }
        }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(8) })
    }

    private fun card(item: JSONObject): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(15), dp(13), dp(15), dp(13)); HydriaUi.card(this)
        val statusValue = item.optString("status", "-")
        addView(HydriaUi.badge(this@RecentInterventionsActivity, statusValue.replace('_', ' '), when (statusValue) {
            "termine" -> Tone.SUCCESS; "annule" -> Tone.ERROR; "reporte" -> Tone.WARNING; else -> Tone.INFO
        }))
        addView(text(item.optString("activity", "Intervention"), 17f, true, HydriaColors.text), margin(top = 8))
        addView(text(item.optString("work"), 15f, true, HydriaColors.cyan), margin(top = 4))
        addView(text(listOf(item.optString("date"), item.optString("employee"), item.optString("base")).filter { it.isNotBlank() }.joinToString(" · "), 12f, false, HydriaColors.textSecondary), margin(top = 4))
        item.optString("description").takeIf { it.isNotBlank() }?.let { addView(text(it, 13f, false, HydriaColors.text), margin(top = 7)) }
        val mediaCount = item.optJSONArray("attachments")?.length() ?: 0
        if (mediaCount > 0) addView(text("$mediaCount photo(s) ou vidéo(s) · Voir", 12f, true, HydriaColors.warning).apply {
            setPadding(0, dp(7), 0, dp(4))
            setOnClickListener { showMedia(item.optJSONArray("attachments") ?: JSONArray()) }
        })
        val itemActions = item.optJSONObject("actions") ?: JSONObject()
        val buttons = LinearLayout(this@RecentInterventionsActivity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.END
        }
        val workId = item.optString("work_id")
        if (workId.isNotBlank()) buttons.addView(Button(this@RecentInterventionsActivity).apply {
            text = "Voir l’ouvrage"
            HydriaUi.styleSecondary(this)
            setOnClickListener { openWork(item) }
        }, LinearLayout.LayoutParams(-1, dp(46)))
        if (itemActions.optBoolean("complete")) buttons.addView(Button(this@RecentInterventionsActivity).apply {
            text = "Terminer"
            HydriaUi.stylePrimary(this)
            setOnClickListener { confirmCompletion(item) }
        }, LinearLayout.LayoutParams(-1, dp(46)).apply { topMargin = dp(7) })
        if (itemActions.optBoolean("postpone")) buttons.addView(Button(this@RecentInterventionsActivity).apply {
            text = "Reporter"
            HydriaUi.styleSecondary(this, true)
            setOnClickListener { choosePostponeDate(item) }
        }, LinearLayout.LayoutParams(-1, dp(46)).apply { topMargin = dp(7) })
        if (itemActions.optBoolean("edit")) buttons.addView(Button(this@RecentInterventionsActivity).apply {
            text = "Modifier"
            HydriaUi.styleSecondary(this)
            setOnClickListener { loadEditOptions(item) }
        }, LinearLayout.LayoutParams(-1, dp(46)).apply { topMargin = dp(7) })
        if (itemActions.optBoolean("delete")) buttons.addView(Button(this@RecentInterventionsActivity).apply {
            text = "Supprimer"
            HydriaUi.styleSecondary(this)
            setTextColor(HydriaColors.error)
            setOnClickListener { confirmDelete(item) }
        }, LinearLayout.LayoutParams(-1, dp(46)).apply { topMargin = dp(7) })
        if (buttons.childCount > 0) addView(buttons, margin(top = 10))
        setOnClickListener {
            if (workId.isNotBlank()) openWork(item)
        }
    }

    private fun openWork(item: JSONObject) {
        val workId = item.optString("work_id")
        if (workId.isBlank()) return
        startActivity(Intent(this, SearchDetailActivity::class.java).apply {
            putExtra("entity_type", "ouvrage")
            putExtra("entity_id", workId)
            putExtra("title", item.optString("work"))
        })
    }

    private fun confirmCompletion(item: JSONObject) {
        if (!online()) {
            AlertDialog.Builder(this).setMessage("Cette action nécessite une connexion Internet.").setPositiveButton("OK", null).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Terminer la réparation ?")
            .setMessage("La réparation sur ${item.optString("work", "cet ouvrage")} sera marquée comme terminée.")
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Terminer") { _, _ -> complete(item.optString("id")) }
            .show()
    }

    private fun complete(planningId: String) {
        if (planningId.isBlank()) return
        progress.visibility = View.VISIBLE
        executor.execute {
            val result = runCatching { HydriaNetwork.finishIntervention(store.token.orEmpty(), planningId) }
            runOnUiThread {
                progress.visibility = View.GONE
                result.onSuccess {
                    if (it.successful) {
                        AlertDialog.Builder(this).setMessage(it.body.optString("message", "Réparation terminée."))
                            .setPositiveButton("OK") { _, _ -> load() }.show()
                    } else {
                        AlertDialog.Builder(this).setTitle("Action impossible").setMessage(it.error).setPositiveButton("OK", null).show()
                    }
                }.onFailure {
                    AlertDialog.Builder(this).setTitle("Erreur réseau").setMessage(it.message ?: "Impossible de terminer la réparation.")
                        .setPositiveButton("OK", null).show()
                }
            }
        }
    }

    private fun choosePostponeDate(item: JSONObject) {
        if (!online()) {
            AlertDialog.Builder(this).setMessage("Cette action nécessite une connexion Internet.").setPositiveButton("OK", null).show()
            return
        }
        val tomorrow = Calendar.getInstance().apply { add(Calendar.DAY_OF_MONTH, 1) }
        DatePickerDialog(
            this,
            { _, year, month, day ->
                val date = String.format(Locale.US, "%04d-%02d-%02d", year, month + 1, day)
                confirmPostpone(item, date)
            },
            tomorrow.get(Calendar.YEAR),
            tomorrow.get(Calendar.MONTH),
            tomorrow.get(Calendar.DAY_OF_MONTH),
        ).apply {
            datePicker.minDate = tomorrow.timeInMillis
            show()
        }
    }

    private fun confirmPostpone(item: JSONObject, date: String) {
        AlertDialog.Builder(this)
            .setTitle("Reporter l’intervention ?")
            .setMessage("Nouvelle date : $date")
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Reporter") { _, _ -> postpone(item.optString("id"), date) }
            .show()
    }

    private fun postpone(planningId: String, date: String) {
        if (planningId.isBlank()) return
        progress.visibility = View.VISIBLE
        executor.execute {
            val result = runCatching { HydriaNetwork.postponeIntervention(store.token.orEmpty(), planningId, date) }
            runOnUiThread {
                progress.visibility = View.GONE
                result.onSuccess {
                    if (it.successful) {
                        AlertDialog.Builder(this).setMessage(it.body.optString("message", "Intervention reportée."))
                            .setPositiveButton("OK") { _, _ -> load() }.show()
                    } else {
                        AlertDialog.Builder(this).setTitle("Action impossible").setMessage(it.error).setPositiveButton("OK", null).show()
                    }
                }.onFailure {
                    AlertDialog.Builder(this).setTitle("Erreur réseau").setMessage(it.message ?: "Impossible de reporter l’intervention.")
                        .setPositiveButton("OK", null).show()
                }
            }
        }
    }

    private fun confirmDelete(item: JSONObject) {
        if (!online()) {
            AlertDialog.Builder(this).setMessage("Cette action nécessite une connexion Internet.").setPositiveButton("OK", null).show()
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Supprimer définitivement ?")
            .setMessage("Cette intervention et son suivi seront supprimés. Cette action est irréversible.")
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Supprimer") { _, _ -> delete(item.optString("id")) }
            .show()
    }

    private fun loadEditOptions(item: JSONObject) {
        if (!online()) {
            AlertDialog.Builder(this).setMessage("La modification nécessite une connexion Internet.").setPositiveButton("OK", null).show()
            return
        }
        val workId = item.optString("work_id")
        if (workId.isBlank()) return
        progress.visibility = View.VISIBLE
        executor.execute {
            val result = runCatching { HydriaNetwork.interventionOptions(store.token.orEmpty(), workId) }
            runOnUiThread {
                progress.visibility = View.GONE
                result.onSuccess {
                    if (it.successful) showEditDialog(item, it.body)
                    else AlertDialog.Builder(this).setTitle("Modification impossible").setMessage(it.error).setPositiveButton("OK", null).show()
                }.onFailure {
                    AlertDialog.Builder(this).setTitle("Erreur réseau").setMessage(it.message ?: "Options indisponibles.").setPositiveButton("OK", null).show()
                }
            }
        }
    }

    private fun showEditDialog(item: JSONObject, options: JSONObject) {
        val form = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(18), 0, dp(18), 0) }
        fun label(value: String) { form.addView(text(value, 13f, true, HydriaColors.text), margin(top = 10, bottom = 3)) }

        label("Date")
        val dateField = EditText(this).apply {
            setText(item.optString("date")); isFocusable = false; isClickable = true; HydriaUi.styleInput(this)
            setOnClickListener { chooseDateForField(this) }
        }
        form.addView(dateField, LinearLayout.LayoutParams(-1, dp(50)))

        val statuses = listOf("en_cours" to "En cours", "termine" to "Terminé", "annule" to "Annulé", "reporte" to "Reporté")
        label("Statut")
        val statusSpinner = Spinner(this).apply { HydriaUi.styleSpinner(this) }
        statusSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, statuses.map { it.second })
        statusSpinner.setSelection(statuses.indexOfFirst { it.first == item.optString("status") }.coerceAtLeast(0))
        form.addView(statusSpinner, LinearLayout.LayoutParams(-1, dp(50)))

        val employees = jsonObjects(options.optJSONArray("employees"))
        val employeeRows = listOf(JSONObject().put("id", "").put("label", "Non affecté")) + employees
        label("Employé")
        val employeeSpinner = Spinner(this).apply { HydriaUi.styleSpinner(this) }
        setRows(employeeSpinner, employeeRows, item.optString("employee_id"))
        form.addView(employeeSpinner, LinearLayout.LayoutParams(-1, dp(50)))

        val targetTypes = listOf("" to "Conserver sans cible", "point_eau" to "Point d’eau", "equipement" to "Équipement")
        label("Type de cible")
        val typeSpinner = Spinner(this).apply { HydriaUi.styleSpinner(this) }
        typeSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, targetTypes.map { it.second })
        typeSpinner.setSelection(targetTypes.indexOfFirst { it.first == item.optString("target_type") }.coerceAtLeast(0))
        form.addView(typeSpinner, LinearLayout.LayoutParams(-1, dp(50)))

        label("Cible")
        val targetSpinner = Spinner(this).apply { HydriaUi.styleSpinner(this) }
        form.addView(targetSpinner, LinearLayout.LayoutParams(-1, dp(50)))
        label("Activité")
        val activitySpinner = Spinner(this).apply { HydriaUi.styleSpinner(this) }
        form.addView(activitySpinner, LinearLayout.LayoutParams(-1, dp(50)))

        val allActivities = jsonObjects(options.optJSONArray("activities"))
        var visibleTargets = emptyList<JSONObject>()
        var visibleActivities = emptyList<JSONObject>()
        var desiredTarget = item.optString("target_id")
        var desiredActivity = item.optString("activity_id")
        var initializing = true

        fun refreshActivities(selectedId: String = "") {
            val type = targetTypes[typeSpinner.selectedItemPosition].first
            val target = visibleTargets.getOrNull(targetSpinner.selectedItemPosition)
            val targetTypeId = target?.optString("type_id").orEmpty()
            visibleActivities = if (type.isBlank()) {
                allActivities.filter { it.optString("id") == item.optString("activity_id") }
            } else allActivities.filter { activityAllowed(it, type, targetTypeId) }
            setRows(activitySpinner, visibleActivities, selectedId)
        }

        fun refreshTargets(selectedId: String = "", activityId: String = "") {
            val type = targetTypes[typeSpinner.selectedItemPosition].first
            visibleTargets = when (type) {
                "point_eau" -> jsonObjects(options.optJSONArray("points"))
                "equipement" -> jsonObjects(options.optJSONArray("equipements"))
                else -> emptyList()
            }
            setRows(targetSpinner, visibleTargets, selectedId)
            targetSpinner.isEnabled = type.isNotBlank()
            refreshActivities(activityId)
            activitySpinner.isEnabled = type.isNotBlank()
        }

        targetSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (!initializing) refreshActivities()
            }
        }
        typeSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (!initializing) refreshTargets()
            }
        }
        refreshTargets(desiredTarget, desiredActivity)
        desiredTarget = ""; desiredActivity = ""; initializing = false

        val dialog = AlertDialog.Builder(this).setTitle("Modifier l’intervention").setView(ScrollView(this).apply { addView(form) })
            .setNegativeButton("Annuler", null).setPositiveButton("Enregistrer", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val targetType = targetTypes[typeSpinner.selectedItemPosition].first
                if (dateField.text.isNullOrBlank()) { dateField.error = "Date obligatoire"; return@setOnClickListener }
                if (targetType.isNotBlank() && (visibleTargets.isEmpty() || visibleActivities.isEmpty())) {
                    AlertDialog.Builder(this).setMessage("Choisissez une cible et une activité compatibles.").setPositiveButton("OK", null).show()
                    return@setOnClickListener
                }
                val payload = JSONObject()
                    .put("date", dateField.text.toString())
                    .put("status", statuses[statusSpinner.selectedItemPosition].first)
                    .put("employee_id", employeeRows[employeeSpinner.selectedItemPosition].optString("id"))
                    .put("existing_attachment_indexes", JSONArray().apply {
                        repeat(item.optJSONArray("attachments")?.length() ?: 0) { put(it) }
                    })
                    .put("attachments", JSONArray())
                if (targetType.isNotBlank()) payload
                    .put("target_type", targetType)
                    .put("target_id", visibleTargets[targetSpinner.selectedItemPosition].optString("id"))
                    .put("activity_id", visibleActivities[activitySpinner.selectedItemPosition].optString("id"))
                submitEdit(item, payload, dialog)
            }
        }
        dialog.show()
    }

    private fun chooseDateForField(field: EditText) {
        val calendar = Calendar.getInstance()
        val parts = field.text.toString().split('-').mapNotNull { it.toIntOrNull() }
        if (parts.size == 3) calendar.set(parts[0], parts[1] - 1, parts[2])
        DatePickerDialog(this, { _, year, month, day ->
            field.setText(String.format(Locale.US, "%04d-%02d-%02d", year, month + 1, day))
        }, calendar.get(Calendar.YEAR), calendar.get(Calendar.MONTH), calendar.get(Calendar.DAY_OF_MONTH)).show()
    }

    private fun submitEdit(item: JSONObject, payload: JSONObject, dialog: AlertDialog) {
        progress.visibility = View.VISIBLE
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = false
        executor.execute {
            val result = runCatching { HydriaNetwork.updateIntervention(store.token.orEmpty(), item.optString("work_id"), item.optString("id"), payload) }
            runOnUiThread {
                progress.visibility = View.GONE
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = true
                result.onSuccess {
                    if (it.successful) { dialog.dismiss(); load() }
                    else AlertDialog.Builder(this).setTitle("Modification impossible").setMessage(it.error).setPositiveButton("OK", null).show()
                }.onFailure {
                    AlertDialog.Builder(this).setTitle("Erreur réseau").setMessage(it.message ?: "Impossible de modifier l’intervention.").setPositiveButton("OK", null).show()
                }
            }
        }
    }

    private fun activityAllowed(activity: JSONObject, targetType: String, targetTypeId: String): Boolean {
        if (targetTypeId.isBlank()) return false
        val key = if (targetType == "point_eau") "allowed_point_type_ids" else "allowed_equipment_type_ids"
        val ids = activity.optJSONArray(key) ?: JSONArray()
        for (index in 0 until ids.length()) if (ids.optString(index) == targetTypeId) return true
        return false
    }

    private fun jsonObjects(array: JSONArray?): List<JSONObject> = buildList {
        if (array != null) for (index in 0 until array.length()) array.optJSONObject(index)?.let { add(it) }
    }

    private fun setRows(spinner: Spinner, rows: List<JSONObject>, selectedId: String) {
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, rows.map { it.optString("label", "-") })
        spinner.setSelection(rows.indexOfFirst { it.optString("id") == selectedId }.coerceAtLeast(0))
    }

    private fun delete(planningId: String) {
        if (planningId.isBlank()) return
        progress.visibility = View.VISIBLE
        executor.execute {
            val result = runCatching { HydriaNetwork.deleteIntervention(store.token.orEmpty(), planningId) }
            runOnUiThread {
                progress.visibility = View.GONE
                result.onSuccess {
                    if (it.successful) {
                        AlertDialog.Builder(this).setMessage(it.body.optString("message", "Intervention supprimée."))
                            .setPositiveButton("OK") { _, _ -> load() }.show()
                    } else {
                        AlertDialog.Builder(this).setTitle("Suppression impossible").setMessage(it.error).setPositiveButton("OK", null).show()
                    }
                }.onFailure {
                    AlertDialog.Builder(this).setTitle("Erreur réseau").setMessage(it.message ?: "Impossible de supprimer l’intervention.")
                        .setPositiveButton("OK", null).show()
                }
            }
        }
    }

    private fun showMedia(attachments: JSONArray) {
        val gallery = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(16))
        }
        for (index in 0 until attachments.length()) {
            val attachment = attachments.optJSONObject(index) ?: continue
            val name = attachment.optString("name", "Pièce jointe ${index + 1}")
            val type = attachment.optString("type")
            gallery.addView(text(name, 14f, true, HydriaColors.text), margin(top = if (index == 0) 0 else 14, bottom = 5))
            if (type.startsWith("image/")) {
                val bitmap = previewBitmap(attachment.optString("data"))
                if (bitmap != null) gallery.addView(ImageView(this).apply {
                    setImageBitmap(bitmap)
                    adjustViewBounds = true
                    scaleType = ImageView.ScaleType.CENTER_INSIDE
                    contentDescription = name
                }, LinearLayout.LayoutParams(-1, -2))
                else gallery.addView(text("Aperçu disponible uniquement depuis le site web.", 12f, false, HydriaColors.textSecondary))
            } else {
                gallery.addView(Button(this).apply {
                    text = "Lire la vidéo"
                    HydriaUi.styleSecondary(this, true)
                    setOnClickListener { playAttachment(attachment) }
                }, LinearLayout.LayoutParams(-1, dp(46)))
            }
        }
        AlertDialog.Builder(this).setTitle("Médias de l’intervention")
            .setView(ScrollView(this).apply { addView(gallery) })
            .setPositiveButton("Fermer", null).show()
    }

    private fun previewBitmap(source: String): Bitmap? = runCatching {
        if (!source.startsWith("data:") || !source.contains(',')) return@runCatching null
        val bytes = Base64.decode(source.substringAfter(','), Base64.DEFAULT)
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        var sample = 1
        while (bounds.outWidth / sample > 1600 || bounds.outHeight / sample > 1600) sample *= 2
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
    }.getOrNull()

    private fun playAttachment(attachment: JSONObject) {
        val source = attachment.optString("data")
        val type = attachment.optString("type", "video/mp4")
        if (source.startsWith("http://") || source.startsWith("https://")) {
            launchVideo(Uri.parse(source), type, false)
            return
        }
        if (!source.startsWith("data:") || !source.contains(',')) {
            AlertDialog.Builder(this).setMessage("Cette vidéo ne peut pas être ouverte sur ce téléphone.").setPositiveButton("OK", null).show()
            return
        }
        progress.visibility = View.VISIBLE
        executor.execute {
            val uri = runCatching {
                val extension = when (type) { "video/webm" -> "webm"; "video/3gpp" -> "3gp"; else -> "mp4" }
                val directory = File(cacheDir, "intervention_media").apply { mkdirs() }
                val file = File(directory, "intervention_${System.currentTimeMillis()}.$extension")
                file.writeBytes(Base64.decode(source.substringAfter(','), Base64.DEFAULT))
                FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
            }.getOrNull()
            runOnUiThread {
                progress.visibility = View.GONE
                if (uri != null) launchVideo(uri, type, true)
                else AlertDialog.Builder(this).setMessage("Impossible de préparer cette vidéo.").setPositiveButton("OK", null).show()
            }
        }
    }

    private fun launchVideo(uri: Uri, type: String, grantRead: Boolean) {
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, type)
            if (grantRead) addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        runCatching { startActivity(intent) }.onFailure {
            AlertDialog.Builder(this).setMessage("Aucun lecteur vidéo compatible n’est installé.").setPositiveButton("OK", null).show()
        }
    }

    private fun message(value: String) { content.removeAllViews(); content.addView(text(value, 15f, false, HydriaColors.textSecondary), margin(top = 30)) }
    private fun online(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        return manager.getNetworkCapabilities(network)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }
    private fun text(value: String, size: Float, bold: Boolean, color: Int) = TextView(this).apply { text = value; textSize = size; setTextColor(color); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD) }
    private fun margin(top: Int = 0, bottom: Int = 0) = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top); bottomMargin = dp(bottom) }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
