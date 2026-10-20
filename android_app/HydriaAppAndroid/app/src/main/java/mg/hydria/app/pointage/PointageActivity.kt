package mg.hydria.app.pointage

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Color
import android.location.Location
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import mg.hydria.app.HydriaApi
import mg.hydria.app.HydriaActivityCascade
import mg.hydria.app.HydriaAutocomplete
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaFeedback
import mg.hydria.app.HydriaType
import mg.hydria.app.HydriaUi
import mg.hydria.app.OfflineStore
import mg.hydria.app.Tone
import mg.hydria.app.navigation.location.TerrainLocationController
import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.fillColor
import org.maplibre.android.style.layers.PropertyFactory.fillOutlineColor
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.Point
import org.maplibre.geojson.Polygon
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors
import kotlin.math.cos

/**
 * Écran de pointage GPS : planning du jour, carte de la position, bouton « Pointer ma
 * position » et suivi de l'équipe pour les supérieurs.
 *
 * En ligne, le serveur valide (heure serveur + distance). Hors ligne, le pointage est
 * gardé sur le téléphone puis envoyé à la synchronisation : l'employé n'est jamais
 * bloqué par le réseau, seulement par les règles (créneau, distance).
 */
class PointageActivity : AppCompatActivity() {
    private companion object {
        const val ONLINE_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"
        private const val MAP_GUARD_KEY = "map_load_pending"
        const val TEAM_REFRESH_MS = 45_000L
        const val FIX_MAX_AGE_MS = 60_000L
    }

    private lateinit var store: OfflineStore
    /** null si la carte est désactivée (téléphone sans OpenGL ES 3.0 ou échec de MapLibre). */
    private var mapView: MapView? = null
    private var map: MapLibreMap? = null
    private var mapStyle: Style? = null
    private var cameraFitted = false
    private lateinit var locationController: TerrainLocationController
    private var lastLocation: Location? = null

    private var today: JSONObject? = null
    private var team: JSONObject? = null
    private var offlineNote = ""

    private lateinit var headerName: TextView
    private lateinit var headerRight: FrameLayout
    private lateinit var planningsBox: LinearLayout
    private lateinit var gpsStatus: TextView
    private lateinit var resultCard: TextView
    private lateinit var pointButton: Button
    private lateinit var teamBox: LinearLayout

    private val io = Executors.newSingleThreadExecutor()
    private val ui = Handler(Looper.getMainLooper())
    private val teamRefresh = object : Runnable {
        override fun run() {
            loadTeam()
            ui.postDelayed(this, TEAM_REFRESH_MS)
        }
    }

    private val account get() = store.accountKey

    /** Relance l'affichage quand le créneau en cours change (10h, 12h, 15h, 18h, 19h, 21h). */
    private var openSlots: List<String> = emptyList()
    private val clock = object : Runnable {
        override fun run() {
            val now = listOfNotNull(PointageRules.creneauActuel(ZonedDateTime.now(PointageRules.ZONE))?.type)
            if (now != openSlots) { openSlots = now; renderToday() }
            ui.postDelayed(this, 30_000L)
        }
    }

    private val locationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) locationController.start() else gpsStatus.text = "Localisation refusée : autorisez-la pour pointer."
    }

    // Android 13+ : les rappels de pointage sont des notifications, à autoriser une fois.
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        // Garde-fou : un plantage natif de la carte ne se rattrape pas. Si le lancement précédent
        // n'a jamais fini de charger la carte, on la désactive durablement sur ce téléphone.
        mapSupported = !mapCrashGuard().getBoolean(MAP_GUARD_KEY, false) && supportsMap() &&
            runCatching { MapLibre.getInstance(applicationContext) }.isSuccess
        store = OfflineStore(this)
        buildUi(savedInstanceState)
        locationController = TerrainLocationController(this, ::onLocation) { runOnUiThread { gpsStatus.text = it } }
        today = PointageStore.cachedToday(account)
        renderToday()
    }

    // ------------------------------------------------------------------ interface --

    private fun buildUi(savedInstanceState: Bundle?) {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(HydriaColors.background)
        }
        headerRight = FrameLayout(this)
        headerName = label("", 12f, HydriaColors.textSecondary)
        root.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(HydriaColors.backgroundDeep)
            setPadding(dp(10), dp(8), dp(12), dp(10))
            addView(secondary("←") { finish() }.apply { contentDescription = "Retour" }, LinearLayout.LayoutParams(dp(48), dp(44)))
            addView(LinearLayout(this@PointageActivity).apply {
                orientation = LinearLayout.VERTICAL
                addView(label("Pointage", 19f, HydriaColors.text, bold = true))
                addView(headerName)
            }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(10) })
            addView(headerRight)
        }, LinearLayout.LayoutParams(-1, -2))

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(24))
        }
        planningsBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(planningsBox, LinearLayout.LayoutParams(-1, -2))

        // MapLibre 11+ exige OpenGL ES 3.0 : sur un téléphone d'entrée de gamme qui ne l'a pas,
        // créer la carte fait planter l'application en code natif (impossible à rattraper).
        // Le pointage n'a pas besoin de la carte : on l'omet et on l'indique.
        if (mapSupported) mapCrashGuard().edit().putBoolean(MAP_GUARD_KEY, true).commit()
        val createdMap = if (mapSupported) runCatching { MapView(this).also { it.onCreate(savedInstanceState) } }.getOrNull() else null
        mapView = createdMap
        if (createdMap == null) {
            column.addView(note("Carte indisponible sur ce téléphone. Le pointage fonctionne normalement : la distance au village s'affiche en bas.", Tone.NEUTRAL),
                LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        } else {
            // La carte est dans un ScrollView : elle garde ses gestes de déplacement.
            createdMap.setOnTouchListener { v, event ->
                if (event.actionMasked == MotionEvent.ACTION_DOWN) v.parent.requestDisallowInterceptTouchEvent(true)
                if (event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) {
                    v.parent.requestDisallowInterceptTouchEvent(false)
                }
                false
            }
            column.addView(FrameLayout(this).apply {
                background = HydriaUi.rounded(this@PointageActivity, HydriaColors.surface, 14f, HydriaColors.outline)
                setPadding(dp(1), dp(1), dp(1), dp(1))
                addView(createdMap, FrameLayout.LayoutParams(-1, -1))
            }, LinearLayout.LayoutParams(-1, dp(240)).apply { topMargin = dp(12) })
            createdMap.getMapAsync { m ->
                map = m
                m.uiSettings.isAttributionEnabled = isOnline()
                val uri = if (isOnline()) ONLINE_STYLE_URL else "asset://navigation_neutral_style.json"
                m.setStyle(Style.Builder().fromUri(uri)) { style ->
                    mapCrashGuard().edit().putBoolean(MAP_GUARD_KEY, false).apply()
                    installLayers(style)
                    mapStyle = style
                    updateMap()
                }
            }
        }

        teamBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(teamBox, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(20) })

        root.addView(ScrollView(this).apply { addView(column) }, LinearLayout.LayoutParams(-1, 0, 1f))

        // Barre fixe en bas : le bouton « Pointer » reste visible quel que soit le défilement.
        val bottomBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(HydriaColors.backgroundDeep)
            setPadding(dp(16), dp(8), dp(16), dp(12))
        }
        resultCard = label("", 14f, HydriaColors.text).apply {
            visibility = View.GONE
            setPadding(dp(14), dp(10), dp(14), dp(10))
        }
        bottomBar.addView(resultCard, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8) })
        gpsStatus = label("Recherche du signal GPS…", 13f, HydriaColors.textSecondary).apply { setPadding(dp(2), 0, dp(2), dp(6)) }
        bottomBar.addView(gpsStatus, LinearLayout.LayoutParams(-1, -2))
        pointButton = Button(this).apply {
            text = "Pointer ma position"
            HydriaUi.primaryButton(this)
            setOnClickListener { onPointer() }
        }
        bottomBar.addView(pointButton, LinearLayout.LayoutParams(-1, -2))
        root.addView(bottomBar, LinearLayout.LayoutParams(-1, -2))
        setContentView(root)
    }

    private fun renderToday() {
        val t = today
        headerName.text = (t?.optString("surnom").orEmpty().ifBlank { store.employeeName }) + " · " +
            PointageStore.today().format(DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.FRANCE))
        planningsBox.removeAllViews()
        if (offlineNote.isNotBlank()) planningsBox.addView(note(offlineNote, Tone.WARNING))

        val plannings = t?.optJSONArray("plannings")
        when {
            t == null -> planningsBox.addView(note(
                "Aucune donnée en mémoire. Connectez-vous au réseau une première fois aujourd'hui pour charger votre planning.",
                Tone.NEUTRAL))
            plannings == null || plannings.length() == 0 -> planningsBox.addView(note(
                "Aucun planning enregistré pour vous aujourd'hui. Ajoutez-le ci-dessous pour pouvoir pointer.", Tone.NEUTRAL))
            else -> {
                val maintenant = ZonedDateTime.now(PointageRules.ZONE)
                val actuel = PointageRules.creneauActuel(maintenant)
                if (actuel == null) {
                    val prochain = PointageRules.prochainCreneau(maintenant)
                    planningsBox.addView(note(
                        if (prochain != null) "Pas de pointage en ce moment. Prochain créneau : ${prochain.label} ${prochain.fenetre}."
                        else "Plus de créneau de pointage aujourd'hui.", Tone.NEUTRAL))
                }
                for (i in 0 until plannings.length()) planningsBox.addView(planningCard(plannings.getJSONObject(i), actuel))
            }
        }
        // Planning modifié au dernier moment : l'employé le corrige ici, sans quitter le pointage.
        if (t != null) planningsBox.addView(secondary("+ Ajouter un planning aujourd'hui") { showPlanningEditor(null) },
            LinearLayout.LayoutParams(-1, dp(46)).apply { bottomMargin = dp(4) })
        updatePending()
        updateMap()
        updateGpsStatus()
    }

    /** Planning sur lequel le dernier pointage a été enregistré (mis en évidence). */
    private var pointedPlanningId: String? = null

    private fun planningCard(planning: JSONObject, actuel: PointageRules.Creneau?): View {
        val villages = planning.optJSONArray("villages") ?: JSONArray()
        val names = (0 until villages.length()).joinToString(", ") { villages.getJSONObject(it).optString("nom") }
        val mine = planning.optBoolean("proprietaire", true)
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            HydriaUi.card(this)
        }
        card.addView(label(planning.optString("activite").ifBlank { "Activité" }, 15f, HydriaColors.text, bold = true))
        if (planning.optString("planning_id") == pointedPlanningId) {
            card.background = HydriaUi.rounded(this, HydriaUi.toneWash(Tone.SUCCESS), 14f, HydriaUi.toneColor(Tone.SUCCESS))
            card.addView(label("✓ Pointage enregistré sur ce planning", 12.5f, HydriaUi.toneTextColor(Tone.SUCCESS), bold = true))
        }
        val where = listOf(planning.optString("ouvrage"), names).filter { it.isNotBlank() }.joinToString(" · ")
        if (where.isNotBlank()) card.addView(label(where, 12.5f, HydriaColors.textSecondary))
        if (planning.optBoolean("valide")) card.addView(label("Planning validé", 12f, HydriaUi.toneTextColor(Tone.SUCCESS), bold = true))
        if (!PointageRules.pointageRequis(planning)) {
            val type = planning.optString("type_ouvrage").takeIf { it.isNotBlank() }?.let { " de type « $it »" }.orEmpty()
            card.addView(note("Pas de pointage pour ce planning : ouvrage$type.", Tone.NEUTRAL))
            if (mine) card.addView(secondary("Modifier ce planning") { showPlanningEditor(planning) },
                LinearLayout.LayoutParams(-2, dp(40)).apply { topMargin = dp(8) })
            return card.also { it.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) } }
        }
        val creneaux = planning.getJSONArray("creneaux")
        val pendingTypes = PointageStore.todayEntries(account).filter { it.status == PointageStore.PENDING }.mapNotNull { it.type }.toSet()
        for (i in 0 until creneaux.length()) {
            val c = creneaux.getJSONObject(i)
            // Interface épurée : seul le créneau de l'heure actuelle est affiché.
            if (c.optString("type") != actuel?.type) continue
            val statut = if (c.optString("statut") != "ok" && c.optString("type") in pendingTypes) "attente" else c.optString("statut")
            card.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp(6), 0, 0)
                addView(CheckBox(this@PointageActivity).apply {
                    text = "${c.optString("label")}  ${c.optString("fenetre")}"
                    textSize = 13.5f
                    setTextColor(HydriaColors.text)
                    isChecked = c.optBoolean("prevu")
                    isEnabled = mine
                    contentDescription = "Prévu : ${c.optString("label")}"
                    setOnCheckedChangeListener { _, checked ->
                        if (checked != c.optBoolean("prevu")) declarePrevu(planning, c, checked)
                    }
                }, LinearLayout.LayoutParams(0, -2, 1f))
                val (text, tone) = statutLabel(statut, c.optString("heure"), c.optBoolean("hors_ligne"))
                addView(label(text, 13f, HydriaUi.toneTextColor(tone), bold = true))
            })
        }
        if (mine) card.addView(secondary("Modifier ce planning") { showPlanningEditor(planning) },
            LinearLayout.LayoutParams(-2, dp(40)).apply { topMargin = dp(8) })
        return card.also { it.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) } }
    }

    // ------------------------------------------------------ modification du planning --

    private fun jsonList(array: JSONArray?): List<JSONObject> =
        (0 until (array?.length() ?: 0)).map { array!!.getJSONObject(it) }

    /**
     * Crée ou modifie un planning du jour de l'employé, depuis l'écran Pointage.
     * Même contrat que l'écran Planning (PlanningFormRules + file « save_planning ») ;
     * envoi immédiat si le réseau est là, sinon à la prochaine synchronisation.
     */
    private fun showPlanningEditor(existing: JSONObject?) {
        val t = today ?: return
        val references = store.snapshot?.optJSONObject("references")
        val activities = jsonList(references?.optJSONArray("planning_fiches"))
        val works = jsonList(references?.optJSONArray("ouvrages"))
        val employees = jsonList(references?.optJSONArray("employes"))
        val employeeId = t.optString("employe_id")
        // Planning validé : ni annulation ni changement d'activité ou d'ouvrage ;
        // seuls la date et l'employé peuvent changer (même règle que le serveur).
        val locked = existing?.optBoolean("valide") == true
        if (activities.isEmpty() || employeeId.isBlank()) {
            toast("Listes indisponibles : synchronisez une fois l'application en ligne (écran Terrain).")
            return
        }
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(8), dp(18), 0)
        }
        val workPicker = HydriaAutocomplete(this, works.map { it.optString("nom", "Ouvrage") }, "Rechercher un ouvrage…")
        existing?.optString("ouvrage_id")?.takeIf { it.isNotBlank() }?.let { wanted ->
            workPicker.select(works.indexOfFirst { it.optString("id") == wanted })
        }
        val activityCascade = HydriaActivityCascade(this, activities)
        existing?.optString("fiche_poste_id")?.takeIf { it.isNotBlank() }?.let { activityCascade.select(it) }
        val remark = android.widget.EditText(this).apply {
            hint = "Remarque (facultatif)"
            setText(existing?.optString("remarque").orEmpty())
            HydriaUi.styleInput(this)
        }
        val todayIso = PointageStore.today().toString()
        // Date au sélecteur (JJ/MM/AAAA) : une date réelle par construction, future autorisée (déplacer un planning).
        val dateField = HydriaUi.dateField(this,
            existing?.optString("date")?.takeIf { it.isNotBlank() } ?: t.optString("date").ifBlank { todayIso }, maxToday = false)
        // Employé : moi par défaut ; la liste n'apparaît que pour modifier un planning existant.
        val employeeOptions = employees.ifEmpty { listOf(JSONObject().put("id", employeeId).put("nom", "Moi")) }
        val employeeSpinner = android.widget.Spinner(this).apply {
            HydriaUi.styleSpinner(this)
            adapter = android.widget.ArrayAdapter(this@PointageActivity, android.R.layout.simple_spinner_dropdown_item,
                employeeOptions.map { it.optString("nom", "Employé") })
            val wanted = existing?.optString("employe_id")?.ifBlank { null } ?: employeeId
            setSelection(employeeOptions.indexOfFirst { it.optString("id") == wanted }.coerceAtLeast(0), false)
        }
        if (locked) {
            workPicker.isEnabled = false
            workPicker.alpha = 0.55f
            activityCascade.setLocked(true)
            form.addView(note("Planning validé : l'activité et l'ouvrage ne peuvent plus changer, "
                + "ni le planning être annulé. Vous pouvez changer la date ou l'employé.", Tone.INFO))
        }
        form.addView(label("Ouvrage où vous travaillez aujourd'hui", 13f, HydriaColors.textSecondary))
        form.addView(workPicker, LinearLayout.LayoutParams(-1, dp(56)).apply { topMargin = dp(4) })
        form.addView(activityCascade, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        if (existing != null) {
            form.addView(label("Date", 13f, HydriaColors.textSecondary), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
            form.addView(dateField, LinearLayout.LayoutParams(-1, dp(56)).apply { topMargin = dp(4) })
            form.addView(label("Employé", 13f, HydriaColors.textSecondary), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
            form.addView(employeeSpinner, LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(4) })
        }
        form.addView(remark, LinearLayout.LayoutParams(-1, dp(56)).apply { topMargin = dp(12) })

        val dialog = androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle(if (existing == null) "Ajouter un planning aujourd'hui" else "Modifier mon planning")
            .setView(ScrollView(this).apply { addView(form) })
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Enregistrer", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(androidx.appcompat.app.AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                if (workPicker.selectedIndex < 0 && workPicker.text.toString().isNotBlank()) {
                    workPicker.error = "Choisissez un ouvrage dans la liste"
                    return@setOnClickListener
                }
                val work = works.getOrNull(workPicker.selectedIndex)
                val activity = activityCascade.selectedActivity
                val chosenEmployee = if (existing != null)
                    employeeOptions.getOrNull(employeeSpinner.selectedItemPosition)?.optString("id")?.ifBlank { null } ?: employeeId
                else employeeId
                val chosenDate = if (existing != null) dateField.iso
                    else t.optString("date").ifBlank { todayIso }
                val result = mg.hydria.shared.planning.PlanningFormRules.validate(mg.hydria.shared.planning.PlanningDraft(
                    employeeId = chosenEmployee,
                    activityId = activity?.optString("id"),
                    date = chosenDate,
                    workId = work?.optString("id").orEmpty(),
                    // Jamais « annulé » depuis le pointage : on garde le statut actuel (sauf annulé -> en cours).
                    status = existing?.optString("statut").orEmpty().takeIf { it.isNotBlank() && it != "annule" } ?: "en_cours",
                    remark = remark.text.toString(),
                    existingId = existing?.optString("planning_id")))
                val error = result.error
                if (error != null) {
                    toast(error.message)
                    return@setOnClickListener
                }
                store.enqueue("save_planning", JSONObject(requireNotNull(result.fields)))
                val movedAway = existing != null && (chosenDate != t.optString("date").ifBlank { todayIso } || chosenEmployee != employeeId)
                if (movedAway) {
                    // Planning déplacé à une autre date ou confié à un autre employé : il sort du pointage du jour.
                    t.optJSONArray("plannings")?.let { list ->
                        val kept = JSONArray()
                        for (i in 0 until list.length()) list.getJSONObject(i).let { if (it !== existing) kept.put(it) }
                        t.put("plannings", kept)
                    }
                    PointageStore.saveToday(account, t)
                    renderToday()
                } else existing?.let { applyLocalPlanningEdit(it, work, activity?.optString("label")?.ifBlank { null }, remark.text.toString()) }
                dialog.dismiss()
                showResult(Tone.INFO, if (isOnline()) "Planning enregistré, envoi en cours…"
                    else "Planning enregistré sur le téléphone : il sera envoyé à la prochaine connexion.")
                io.execute { flushPending(); runOnUiThread { refresh() } }
            }
        }
        dialog.show()
    }

    /**
     * Affichage immédiat de la modification. Si l'ouvrage change, les villages du planning
     * ne sont plus connus avant le rechargement serveur : on les efface pour que le contrôle
     * local des 3 km ne bloque pas le pointage (le serveur tranchera).
     */
    private fun applyLocalPlanningEdit(planning: JSONObject, work: JSONObject?, activityLabel: String?, remark: String) {
        val newWorkId = work?.optString("id").orEmpty()
        if (newWorkId != planning.optString("ouvrage_id")) planning.put("villages", JSONArray())
        planning.put("ouvrage_id", newWorkId).put("ouvrage", work?.optString("nom").orEmpty()).put("remarque", remark.trim())
        activityLabel?.let { planning.put("activite", it) }
        today?.let { PointageStore.saveToday(account, it) }
        renderToday()
    }

    private fun statutLabel(statut: String, heure: String, horsLigne: Boolean): Pair<String, Tone> = when (statut) {
        "ok" -> "✓ ${heure.ifBlank { "OK" }}${if (horsLigne) " (synchro)" else ""}" to Tone.SUCCESS
        "manque" -> "✗ Manqué" to Tone.ERROR
        "en_cours" -> "À pointer maintenant" to Tone.WARNING
        "a_venir" -> "À venir" to Tone.NEUTRAL
        "attente" -> "⏳ En attente d'envoi" to Tone.WARNING
        "non_requis" -> "Pas de pointage" to Tone.NEUTRAL
        else -> "—" to Tone.NEUTRAL
    }

    private fun updatePending() {
        headerRight.removeAllViews()
        val pending = PointageStore.pendingCount(account)
        headerRight.addView(HydriaUi.syncChip(this, pending, isOnline()))
    }

    private fun showResult(tone: Tone, message: String) {
        resultCard.text = message
        resultCard.setTextColor(HydriaUi.toneTextColor(tone))
        resultCard.background = HydriaUi.rounded(this, HydriaUi.toneWash(tone), 12f, HydriaUi.toneColor(tone))
        resultCard.visibility = View.VISIBLE
        if (tone == Tone.SUCCESS) HydriaFeedback.success() else if (tone == Tone.ERROR) HydriaFeedback.error()
    }

    private var busy = false

    private fun setBusy(value: Boolean) {
        busy = value
        updatePointButton()
    }

    /** Distance au village le plus proche si l'employé est à plus de 3 km (bouton grisé), sinon null. */
    private fun tooFar(): Pair<PointageRules.Village, Double>? {
        val loc = lastLocation ?: return null
        return PointageRules.tropLoin(loc.latitude, loc.longitude,
            if (loc.hasAccuracy()) loc.accuracy.toDouble() else null, PointageRules.villagesDuJour(today))
    }

    /** Dernier style appliqué au bouton de pointage (null = jamais). */
    private var pointButtonStyledEnabled: Boolean? = null

    private fun updatePointButton() {
        if (!::pointButton.isInitialized) return
        val far = tooFar()
        val maintenant = ZonedDateTime.now(PointageRules.ZONE)
        val actuel = PointageRules.creneauActuel(maintenant)
        // Plannings du jour tous sur des ouvrages sans pointage (bureau, terrain…) : rien à pointer.
        val sansPointage = today?.optJSONArray("plannings")?.let { it.length() > 0 } == true && !PointageRules.pointageAttendu(today)
        pointButton.isEnabled = !busy && far == null && actuel != null && !sansPointage
        // Inactif : texte opaque sur fond plat avec contour, jamais d'alpha (le libellé donne la raison
        // du blocage et tombait à ~2:1). Restylé seulement au changement d'état pour ne pas casser le ripple.
        if (pointButtonStyledEnabled != pointButton.isEnabled) {
            pointButtonStyledEnabled = pointButton.isEnabled
            if (pointButton.isEnabled) HydriaUi.primaryButton(pointButton) else HydriaUi.disabledButton(pointButton)
            pointButton.alpha = 1f
        }
        pointButton.text = when {
            busy -> "Envoi en cours…"
            sansPointage -> "Pas de pointage pour vos plannings du jour"
            actuel == null -> PointageRules.prochainCreneau(maintenant)
                ?.let { "Pointage possible à ${it.debut.hour}h (${it.label.lowercase()})" } ?: "Plus de pointage aujourd'hui"
            far != null -> "Trop loin pour pointer (${PointageRules.formatDistance(far.second)})"
            else -> "Pointer ma position · ${actuel.label.lowercase()}"
        }
    }

    // ---------------------------------------------------------------------- carte --

    private fun installLayers(style: Style) {
        val empty = FeatureCollection.fromFeatures(emptyList<Feature>())
        style.addSource(GeoJsonSource("pointage-zones", empty))
        style.addSource(GeoJsonSource("pointage-villages", empty))
        style.addSource(GeoJsonSource("pointage-moi", empty))
        style.addLayer(FillLayer("pointage-zones-fill", "pointage-zones").withProperties(
            fillColor(Color.argb(46, 0, 170, 210)), fillOutlineColor(Color.argb(200, 0, 150, 190))))
        style.addLayer(CircleLayer("pointage-villages-c", "pointage-villages").withProperties(
            circleRadius(7f), circleColor(Color.rgb(155, 138, 251)),
            circleStrokeColor(Color.WHITE), circleStrokeWidth(2f)))
        style.addLayer(CircleLayer("pointage-moi-c", "pointage-moi").withProperties(
            circleRadius(9f), circleColor(Color.rgb(37, 99, 235)),
            circleStrokeColor(Color.WHITE), circleStrokeWidth(3f)))
    }

    private fun updateMap() {
        val style = mapStyle ?: return
        val villages = PointageRules.villagesDuJour(today)
        style.getSourceAs<GeoJsonSource>("pointage-villages")?.setGeoJson(FeatureCollection.fromFeatures(
            villages.map { Feature.fromGeometry(Point.fromLngLat(it.lng, it.lat)) }))
        style.getSourceAs<GeoJsonSource>("pointage-zones")?.setGeoJson(FeatureCollection.fromFeatures(
            villages.map { Feature.fromGeometry(Polygon.fromLngLats(listOf(circle(it.lat, it.lng, PointageRules.DISTANCE_MAX_M)))) }))
        val me = lastLocation
        style.getSourceAs<GeoJsonSource>("pointage-moi")?.setGeoJson(FeatureCollection.fromFeatures(
            listOfNotNull(me?.let { Feature.fromGeometry(Point.fromLngLat(it.longitude, it.latitude)) })))
        fitCameraOnce(villages, me)
    }

    /** Cercle de rayon [radiusM] : la zone dans laquelle le pointage est accepté. */
    private fun circle(lat: Double, lng: Double, radiusM: Double): List<Point> {
        val dLat = radiusM / 111_320.0
        val dLng = radiusM / (111_320.0 * cos(Math.toRadians(lat)))
        return (0..48).map {
            val angle = Math.toRadians(it * 360.0 / 48)
            Point.fromLngLat(lng + dLng * kotlin.math.cos(angle), lat + dLat * kotlin.math.sin(angle))
        }
    }

    private fun fitCameraOnce(villages: List<PointageRules.Village>, me: Location?) {
        val m = map ?: return
        if (cameraFitted) return
        val points = villages.map { LatLng(it.lat, it.lng) } + listOfNotNull(me?.let { LatLng(it.latitude, it.longitude) })
        if (points.isEmpty()) return
        cameraFitted = true
        if (points.size == 1) {
            m.moveCamera(CameraUpdateFactory.newLatLngZoom(points[0], 14.0))
        } else {
            val bounds = LatLngBounds.Builder().apply { points.forEach { include(it) } }.build()
            m.moveCamera(CameraUpdateFactory.newLatLngBounds(bounds, dp(48)))
        }
    }

    // ------------------------------------------------------------------------ GPS --

    private fun onLocation(location: Location) {
        val previous = lastLocation
        if (previous == null || location.time - previous.time > 20_000 ||
            (location.hasAccuracy() && location.accuracy <= previous.accuracy)
        ) lastLocation = location
        runOnUiThread {
            updateGpsStatus()
            updateMap()
        }
    }

    private fun updateGpsStatus() {
        updatePointButton()
        if (!::gpsStatus.isInitialized) return
        val loc = lastLocation
        if (loc == null) {
            gpsStatus.text = "Recherche du signal GPS…"
            gpsStatus.setTextColor(HydriaColors.textSecondary)
            return
        }
        val accuracy = if (loc.hasAccuracy()) loc.accuracy else Float.MAX_VALUE
        val villages = PointageRules.villagesDuJour(today)
        val nearest = villages.map { it to PointageRules.haversineM(loc.latitude, loc.longitude, it.lat, it.lng) }.minByOrNull { it.second }
        val precisionText = if (accuracy == Float.MAX_VALUE) "" else "±${accuracy.toInt()} m"
        when {
            accuracy > PointageRules.PRECISION_MAX_M -> {
                gpsStatus.text = "Signal GPS faible ($precisionText). Sortez à découvert pour pointer."
                gpsStatus.setTextColor(HydriaColors.warning)
            }
            nearest == null -> {
                gpsStatus.text = "Position trouvée $precisionText. Aucun village avec coordonnées pour votre planning."
                gpsStatus.setTextColor(HydriaColors.textSecondary)
            }
            nearest.second <= PointageRules.DISTANCE_MAX_M -> {
                gpsStatus.text = "Position $precisionText · à ${PointageRules.formatDistance(nearest.second)} de ${nearest.first.nom} : vous pouvez pointer."
                gpsStatus.setTextColor(HydriaColors.success)
            }
            else -> {
                gpsStatus.text = "Position $precisionText · à ${PointageRules.formatDistance(nearest.second)} de ${nearest.first.nom} : trop loin (limite 3 km)."
                gpsStatus.setTextColor(HydriaColors.error)
            }
        }
    }

    // -------------------------------------------------------------------- pointer --

    private fun onPointer() {
        val token = store.token
        if (token.isNullOrBlank()) { toast("Connectez-vous d'abord."); return }
        val loc = lastLocation
        if (loc == null) { showResult(Tone.WARNING, "Position GPS indisponible. Patientez quelques secondes."); return }
        val simulated = if (Build.VERSION.SDK_INT >= 31) loc.isMock else @Suppress("DEPRECATION") loc.isFromMockProvider
        if (simulated) {
            showResult(Tone.ERROR, "Position simulée détectée. Désactivez l'application de fausse position."); return
        }
        if (!loc.hasAccuracy() || loc.accuracy > PointageRules.PRECISION_MAX_M) {
            showResult(Tone.WARNING, "Signal GPS trop imprécis${if (loc.hasAccuracy()) " (±${loc.accuracy.toInt()} m)" else ""}. Sortez à découvert et réessayez.")
            return
        }
        tooFar()?.let { (village, distance) ->
            showResult(Tone.ERROR, "Vous êtes à ${PointageRules.formatDistance(distance)} de ${village.nom}. Rapprochez-vous à moins de 3 km pour pointer.")
            return
        }
        if (System.currentTimeMillis() - loc.time > FIX_MAX_AGE_MS) {
            showResult(Tone.WARNING, "La position GPS est trop ancienne. Patientez, elle va se mettre à jour."); return
        }

        val nowMs = System.currentTimeMillis()
        val localUuid = UUID.randomUUID().toString()
        val lat = loc.latitude
        val lng = loc.longitude
        val accuracy = loc.accuracy.toDouble()
        val online = isOnline()
        setBusy(true)
        io.execute {
            val base = JSONObject().put("local_uuid", localUuid).put("latitude", lat).put("longitude", lng)
                .put("precision_m", accuracy).put("position_simulee", false).put("_sync_account", account)

            // 1. En ligne : le serveur fait foi (heure serveur incluse), sans horodatage appareil.
            if (online) {
                val direct = runCatching { PointageSync.send(token, JSONObject(base.toString())) }.getOrNull()
                if (direct != null && direct.successful) {
                    val refused = direct.body.optBoolean("refused", false)
                    val message = direct.body.optString("message")
                    runOnUiThread {
                        setBusy(false)
                        showResult(if (refused) Tone.ERROR else Tone.SUCCESS, message)
                        if (!refused) markPointed(direct.body.optString("planning_id").ifBlank { null },
                            direct.body.optString("type").ifBlank { null }, lat, lng)
                        refresh()
                    }
                    return@execute
                }
            }

            // 2. Hors ligne (ou serveur injoignable) : contrôle local sans ambiguïté, sinon mise en file.
            val verdict = PointageRules.verdict(lat, lng, PointageRules.villagesDuJour(today), ZonedDateTime.now(PointageRules.ZONE))
            if (verdict is PointageRules.Verdict.Refuse) {
                runOnUiThread { setBusy(false); showResult(Tone.ERROR, verdict.message) }
                return@execute
            }
            val creneau = when (verdict) {
                is PointageRules.Verdict.Ok -> verdict.creneau
                is PointageRules.Verdict.Indetermine -> verdict.creneau
                else -> null
            }
            store.enqueue("pointage", base.put("captured_at_ms", nowMs))
            PointageStore.addPending(localUuid, account, creneau?.type, nowMs)
            runOnUiThread {
                setBusy(false)
                creneau?.let { markPointed(null, it.type, lat, lng) }
                showResult(Tone.WARNING,
                    "Pointage enregistré sur le téléphone. Il sera envoyé et validé dès que le réseau sera disponible.")
                renderToday()
            }
        }
    }

    /**
     * Après un clic sur « Pointer » : le planning est choisi automatiquement (réponse du
     * serveur, sinon même règle que lui en local) et sa case du créneau est cochée — le
     * serveur fait de même de son côté, y compris pour un pointage synchronisé plus tard.
     */
    private fun markPointed(serverPlanningId: String?, type: String?, lat: Double, lng: Double) {
        val t = today ?: return
        val creneauType = type ?: return
        val planningId = serverPlanningId ?: PointageRules.planningPourPointage(t, lat, lng, creneauType) ?: return
        pointedPlanningId = planningId
        val plannings = t.optJSONArray("plannings") ?: return
        for (i in 0 until plannings.length()) {
            val pl = plannings.getJSONObject(i)
            if (pl.optString("planning_id") != planningId) continue
            val creneaux = pl.optJSONArray("creneaux") ?: continue
            for (j in 0 until creneaux.length()) {
                val c = creneaux.getJSONObject(j)
                if (c.optString("type") == creneauType) c.put("prevu", true)
            }
        }
        PointageStore.saveToday(account, t)
        renderToday()
    }

    private fun declarePrevu(planning: JSONObject, creneau: JSONObject, prevu: Boolean) {
        val key = PointageRules.CRENEAUX.firstOrNull { it.type == creneau.optString("type") }?.prevuKey ?: return
        creneau.put("prevu", prevu)
        val statut = creneau.optString("statut")
        if (!prevu && statut != "ok") creneau.put("statut", "non_prevu")
        if (prevu && statut == "non_prevu") creneau.put("statut", "a_venir")
        today?.let { PointageStore.saveToday(account, it) }
        store.enqueue("pointage_prevu", JSONObject().put("planning_id", planning.optString("planning_id")).put(key, prevu))
        io.execute { flushPending(); runOnUiThread { refresh() } }
    }

    /** Envoie les opérations de pointage en attente (idempotent côté serveur : sans risque de doublon). */
    private fun flushPending() {
        val token = store.token ?: return
        if (!isOnline()) return
        val pending = store.pending()
        for (i in 0 until pending.length()) {
            val op = pending.getJSONObject(i)
            val type = op.optString("type")
            if (type != "pointage" && type != "pointage_prevu" && type != "save_planning") continue
            val uuid = op.getString("local_uuid")
            val payload = op.getJSONObject("payload")
            store.markSynchronizing(uuid)
            try {
                val result = when (type) {
                    "pointage" -> PointageSync.send(token, payload)
                    "save_planning" -> mg.hydria.app.sync.SyncDispatch.push(type, token, payload)
                        ?: HydriaApi.Result(0, JSONObject().put("success", false).put("error", "Synchro planning indisponible"))
                    else -> HydriaApi.pointageDeclarer(token, payload)
                }
                if (result.successful) store.remove(uuid) else store.markFailed(uuid, result.error)
            } catch (e: Exception) {
                store.markFailed(uuid, e.message ?: "Connexion interrompue")
            }
        }
    }

    // ------------------------------------------------------------------- données --

    private fun refresh() {
        val token = store.token ?: return
        io.execute {
            flushPending()
            val call = runCatching { HydriaApi.pointageToday(token) }
            val response = call.getOrNull()
            runOnUiThread {
                if (response != null && response.successful) {
                    today = response.body
                    offlineNote = ""
                    PointageStore.saveToday(account, response.body)
                    response.body.optJSONArray("calendrier")?.let { PointageReminders.schedule(applicationContext, account, it) }
                    if (response.body.optBoolean("est_superieur")) startTeamRefresh() else stopTeamRefresh()
                } else {
                    // Ne plus tout confondre avec « hors ligne » : un refus ou une panne serveur
                    // doit s'afficher tel quel, sinon l'agent croit à un problème de réseau.
                    offlineNote = PointageRules.refreshFailureNote(
                        status = response?.status, error = response?.error,
                        exception = call.exceptionOrNull()?.message, online = isOnline())
                }
                renderToday()
            }
        }
    }

    private var teamRunning = false
    private fun startTeamRefresh() {
        if (teamRunning) return
        teamRunning = true
        ui.post(teamRefresh)
    }

    private fun stopTeamRefresh() {
        teamRunning = false
        ui.removeCallbacks(teamRefresh)
        teamBox.removeAllViews()
    }

    private fun loadTeam() {
        val token = store.token ?: return
        if (!isOnline()) return
        io.execute {
            val response = runCatching { HydriaApi.pointageEquipe(token) }.getOrNull() ?: return@execute
            if (response.successful) runOnUiThread { team = response.body; renderTeam() }
        }
    }

    private fun renderTeam() {
        teamBox.removeAllViews()
        val t = team ?: return
        val employees = t.optJSONArray("employes") ?: return
        val rows = (0 until employees.length()).map { employees.getJSONObject(it) }
            .sortedWith(compareByDescending<JSONObject> { it.optInt("nb_manques") }.thenBy { it.optString("surnom") })
        val missed = t.optInt("total_manques")
        teamBox.addView(label("Mon équipe", 17f, HydriaColors.text, bold = true))
        teamBox.addView(label(
            (if (missed > 0) "$missed pointage(s) manqué(s) · " else "Aucun pointage manqué · ") + "actualisé à ${t.optString("actualise_a")}",
            12.5f, if (missed > 0) HydriaColors.error else HydriaColors.textSecondary))
        rows.forEach { teamBox.addView(teamRow(it)) }
    }

    private fun teamRow(employee: JSONObject): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(10), dp(14), dp(10))
            HydriaUi.card(this)
        }
        card.layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) }
        val name = employee.optString("surnom") + if (employee.optBoolean("moi")) " (moi)" else ""
        val missed = employee.optInt("nb_manques")
        card.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(label(name, 14.5f, HydriaColors.text, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
            addView(label(
                "${employee.optInt("nb_ok")}/${employee.optInt("nb_prevus")}",
                13f, if (missed > 0) HydriaColors.error else HydriaColors.textSecondary, bold = true))
        })
        val plannings = employee.optJSONArray("plannings") ?: JSONArray()
        if (plannings.length() == 0) {
            card.addView(label("Aucun planning aujourd'hui", 12.5f, HydriaColors.textSecondary))
        } else {
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(4), 0, 0) }
            PointageRules.CRENEAUX.forEach { creneau ->
                val (text, tone) = teamCell(plannings, creneau.type)
                line.addView(label("${creneau.label.take(3)}. $text", 12.5f, HydriaUi.toneTextColor(tone)),
                    LinearLayout.LayoutParams(0, -2, 1f))
            }
            card.addView(line)
        }
        return card
    }

    /** Résume un créneau sur tous les plannings du jour d'un employé : le pire état l'emporte. */
    private fun teamCell(plannings: JSONArray, type: String): Pair<String, Tone> {
        val cells = (0 until plannings.length()).flatMap { i ->
            val creneaux = plannings.getJSONObject(i).getJSONArray("creneaux")
            (0 until creneaux.length()).map { creneaux.getJSONObject(it) }.filter { it.optString("type") == type }
        }
        val statuts = cells.map { it.optString("statut") }
        return when {
            "manque" in statuts -> "✗" to Tone.ERROR
            "en_cours" in statuts -> "●" to Tone.WARNING
            "a_venir" in statuts -> "○" to Tone.NEUTRAL
            "ok" in statuts -> ("✓ " + cells.first { it.optString("statut") == "ok" }.optString("heure")).trim() to Tone.SUCCESS
            else -> "—" to Tone.NEUTRAL
        }
    }

    // ------------------------------------------------------------------- utilitaires --

    private fun isOnline(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        val caps = manager.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun toast(value: String) = Toast.makeText(this, value, Toast.LENGTH_SHORT).show()

    private fun label(value: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(color)
        typeface = HydriaType.display(if (bold) 700 else 400)
    }

    private fun note(value: String, tone: Tone) = label(value, 13f, HydriaUi.toneTextColor(tone)).apply {
        setPadding(dp(12), dp(10), dp(12), dp(10))
        background = HydriaUi.rounded(this@PointageActivity, HydriaUi.toneWash(tone), 12f)
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(10) }
    }

    private fun secondary(value: String, action: () -> Unit) = Button(this).apply {
        text = value
        HydriaUi.secondaryButton(this)
        minHeight = 0
        minimumHeight = 0
        setOnClickListener { action() }
    }

    // ----------------------------------------------------------------- cycle de vie --

    override fun onStart() { super.onStart(); mapView?.onStart() }

    override fun onResume() {
        super.onResume()
        mapView?.onResume()
        ui.removeCallbacks(clock)
        ui.post(clock)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            locationController.start()
        } else {
            locationPermission.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        if (today?.optBoolean("est_superieur") == true) startTeamRefresh()
        refresh()
    }

    override fun onPause() {
        ui.removeCallbacks(clock)
        locationController.stop()
        stopTeamRefresh()
        mapView?.onPause()
        super.onPause()
    }

    override fun onStop() { mapView?.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); mapView?.onLowMemory() }
    override fun onDestroy() { io.shutdownNow(); mapView?.onDestroy(); super.onDestroy() }
    override fun onSaveInstanceState(outState: Bundle) { super.onSaveInstanceState(outState); mapView?.onSaveInstanceState(outState) }

    private var mapSupported = false

    private fun mapCrashGuard() = getSharedPreferences("hydria_pointage_map", MODE_PRIVATE)

    /** OpenGL ES 3.0 minimum, requis par MapLibre Android 11+. */
    private fun supportsMap(): Boolean {
        val manager = getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
        // Les appareils « peu de RAM » (Android Go, entrée de gamme) plantent sur la carte : pas de carte.
        if (manager.isLowRamDevice) return false
        return manager.deviceConfigurationInfo.reqGlEsVersion >= 0x30000
    }
}
