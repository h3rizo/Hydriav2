package mg.hydria.app.search

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import mg.hydria.app.terrain.TerrainPhotoEncoder
import mg.hydria.app.terrain.TerrainRepository
import mg.hydria.shared.rules.terrain.TerrainEditRules
import mg.hydria.app.Tone
import mg.hydria.app.HydriaNetwork
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaType
import mg.hydria.app.HydriaUi
import mg.hydria.app.OfflineStore
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors

private val UUID_VALUE_PATTERN = Regex(
    "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
)

internal fun isTechnicalUuid(value: Any?): Boolean =
    value != null && UUID_VALUE_PATTERN.matches(value.toString().trim())

/** Fiche mobile commune utilisée par tous les résultats de Recherche. */
class SearchDetailActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var store: OfflineStore
    private lateinit var body: LinearLayout
    private lateinit var state: TextView
    private lateinit var progress: ProgressBar
    private var type = ""
    private var id = ""
    private var personMode = false
    private var fallbackItem: JSONObject? = null

    // Fiche Terrain (point d'eau / équipement) modifiable depuis la Recherche.
    private var currentPayload: JSONObject? = null
    private var currentOffline = false
    private var pendingPhotoFile: File? = null

    private val photoLauncher = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val file = pendingPhotoFile
        pendingPhotoFile = null
        if (success && file != null) {
            runCatching { TerrainPhotoEncoder.encode(file) }
                .onSuccess { encoded -> queuePhoto(encoded) }
                .onFailure { toast("Impossible de préparer la photo : ${it.message ?: "erreur inconnue"}") }
        }
        file?.delete()
    }
    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchCamera() else toast("Autorisez l'appareil photo pour photographier ce point.")
    }
    private val locationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) acquireLocation() else toast("Autorisez la localisation pour enregistrer les coordonnées.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        store = OfflineStore(this)
        type = intent.getStringExtra("entity_type").orEmpty()
        id = intent.getStringExtra("entity_id").orEmpty()
        personMode = intent.getBooleanExtra("person_mode", false)
        fallbackItem = intent.getStringExtra("cached_item")?.takeIf { it.isNotBlank() }?.let { JSONObject(it) }
        // L'appareil photo peut détruire le processus : retrouver le fichier en cours.
        pendingPhotoFile = savedInstanceState?.getString("pending_photo")?.let { File(it) }
        buildScreen(intent.getStringExtra("title").orEmpty())
        load(intent.getStringExtra("cached_item"))
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        pendingPhotoFile?.let { outState.putString("pending_photo", it.absolutePath) }
    }

    private fun buildScreen(initialTitle: String) {
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(HydriaColors.background) }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(10)); setBackgroundColor(HydriaColors.backgroundDeep)
        }
        header.addView(Button(this).apply {
            text = "‹"; contentDescription = "Retour"; HydriaUi.styleSecondary(this)
            setOnClickListener { finish() }
        }, LinearLayout.LayoutParams(dp(52), dp(48)))
        header.addView(text(initialTitle.ifBlank { "Fiche" }, 19f, true, HydriaColors.text), LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(10) })
        state = text("", 11f, true, HydriaColors.textSecondary).apply { gravity = Gravity.END }
        header.addView(state)
        root.addView(header)
        // Fiche ouverte depuis la page de navigation carte : retour direct à la carte
        if (intent.getBooleanExtra("from_navigation", false)) {
            root.addView(Button(this).apply {
                text = "← Retour à la carte"
                contentDescription = "Retourner à la page de navigation carte"
                HydriaUi.stylePrimary(this)
                setOnClickListener { finish() }
            }, LinearLayout.LayoutParams(-1, dp(48)).apply { setMargins(dp(12), dp(8), dp(12), 0) })
        }
        progress = ProgressBar(this).apply { visibility = android.view.View.GONE }
        root.addView(progress, LinearLayout.LayoutParams(dp(38), dp(38)).apply { gravity = Gravity.CENTER_HORIZONTAL; topMargin = dp(12) })
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(8), dp(14), dp(30)) }
        root.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
    }

    private fun cacheKey() = "detail:$type:$id"

    private fun load(fallbackRaw: String?) {
        val cached = store.searchCache(cacheKey())
        if (!isOnline()) {
            when {
                cached != null -> if (personMode) renderPerson(cached, true) else render(cached, true)
                !fallbackRaw.isNullOrBlank() -> renderFallback(JSONObject(fallbackRaw))
                else -> message("Cette fiche n’a pas encore été téléchargée.")
            }
            return
        }
        progress.visibility = android.view.View.VISIBLE
        executor.execute {
            val response = runCatching {
                if (personMode) HydriaNetwork.personDetail(store.token.orEmpty(), type, id)
                else HydriaNetwork.searchDetail(store.token.orEmpty(), type, id)
            }
            runOnUiThread {
                progress.visibility = android.view.View.GONE
                response.onSuccess {
                    if (it.successful) {
                        store.saveSearchCache(cacheKey(), it.body)
                        if (personMode) renderPerson(it.body, false) else render(it.body, false)
                    } else if (cached != null) {
                        if (personMode) renderPerson(cached, true) else render(cached, true)
                    } else message(it.error)
                }.onFailure {
                    if (cached != null) {
                        if (personMode) renderPerson(cached, true) else render(cached, true)
                    }
                    else if (!fallbackRaw.isNullOrBlank()) renderFallback(JSONObject(fallbackRaw))
                    else message("Fiche indisponible : ${it.message ?: "erreur réseau"}")
                }
            }
        }
    }

    private fun render(payload: JSONObject, offline: Boolean) {
        body.removeAllViews()
        state.text = if (offline) "HORS LIGNE" else "SYNCHRONISÉ"
        state.setTextColor(if (offline) HydriaColors.warning else HydriaColors.success)
        val typeDisplay = payload.optString("type_display", type.replace('_', ' '))
        val title = payload.optString("title", "Sans titre").takeUnless(::isTechnicalUuid) ?: typeDisplay
        body.addView(HydriaUi.badge(this, typeDisplay, Tone.INFO))
        body.addView(text(title, 25f, true, HydriaColors.text), margin(top = 12, bottom = 12))
        currentPayload = payload
        currentOffline = offline
        payload.optJSONObject("terrain")?.let { renderTerrainCard(it) }
        val fields = payload.optJSONArray("fields") ?: JSONArray()
        for (index in 0 until fields.length()) {
            val field = fields.getJSONObject(index)
            val value = field.optString("value")
            if (value.isBlank() || isTechnicalUuid(value)) continue
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(11), dp(14), dp(11)); HydriaUi.card(this)
            }
            row.addView(text(field.optString("label"), 11f, true, HydriaColors.textSecondary))
            row.addView(text(value, 15f, false, HydriaColors.text), margin(top = 4))
            body.addView(row, margin(bottom = 8))
        }
        payload.optJSONObject("details")?.let {
            body.addView(text("Détails opérationnels", 18f, true, HydriaColors.text), margin(top = 14, bottom = 8))
            if (type == "commune") {
                // Fiche commune : synthèse, ouvrages / points d'eau par type, diagramme de flux, listes cliquables
                CommuneDetailRenderer(this, body, ::renderPointsEauTile, ::openEntityDetail).render(it)
            } else if (type == "village") {
                // Fiche village : population desservie, localisation, profil, points d'eau par type, ouvrages, parcelles
                VillageDetailRenderer(this, body, ::renderPointsEauTile, ::openEntityDetail).render(it)
            } else {
                it.optJSONObject("repartition_points_eau")?.let(::renderPointsEauTile)
                renderJsonObject(it)
            }
        }
        val actions = payload.optJSONObject("actions") ?: JSONObject()
        if (actions.optBoolean("capture_gps") && payload.optJSONObject("terrain") == null) body.addView(text(
            "Mettez à jour le serveur Hydria pour compléter cette fiche depuis la Recherche.",
            13f, false, HydriaColors.cyan,
        ), margin(top = 12))
        body.addView(text(
            "Dernière mise à jour : ${payload.optString("updated_at", "non renseignée")}",
            11f, false, HydriaColors.textSecondary,
        ), margin(top = 18))
    }

    // ── Fiche Terrain : photo, abonné, téléphone, GPS ──────────────────────────

    private fun terrainKind(): String = if (type == "equipement") "equipement" else "point_eau"

    private fun renderTerrainCard(terrain: JSONObject) {
        val isPoint = terrainKind() == "point_eau"
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(14)); HydriaUi.card(this, emphasized = true)
        }
        card.addView(text("FICHE TERRAIN", 11f, true, HydriaColors.cyan))

        // Photo : aperçu si le serveur l'a renvoyée en base64.
        val preview = TerrainPhotoEncoder.decodePreview(terrain.optString("photo"))
        if (preview != null) {
            card.addView(ImageView(this).apply {
                setImageBitmap(preview)
                scaleType = ImageView.ScaleType.CENTER_CROP
                contentDescription = "Photo du ${if (isPoint) "point d'eau" else "l'équipement"}"
            }, LinearLayout.LayoutParams(-1, dp(190)).apply { topMargin = dp(8) })
        }
        fun info(label: String, value: String, missing: Boolean) {
            card.addView(text(label, 11f, true, HydriaColors.textSecondary), margin(top = 10))
            card.addView(text(value, 15f, !missing, if (missing) HydriaColors.warning else HydriaColors.text), margin(top = 2))
        }
        if (isPoint) {
            val subscriber = terrain.optString("subscriber_name")
            info("Abonné", subscriber.ifBlank { "Non renseigné" }, subscriber.isBlank())
            val phone = terrain.optString("telephone")
            info("Téléphone", phone.ifBlank { "Non renseigné" }, phone.isBlank())
        }
        val hasGps = terrain.optBoolean("has_coordinates")
        info("Coordonnées GPS", if (hasGps) String.format(Locale.US, "%.6f, %.6f",
            terrain.optDouble("latitude"), terrain.optDouble("longitude")) else "Non renseignées", !hasGps)
        val hasPhoto = terrain.optBoolean("has_photo")
        info("Photo", when {
            preview != null -> "Présente"
            hasPhoto -> "Présente (aperçu sur le web)"
            else -> "Manquante"
        }, !hasPhoto)

        val pendingLabels = TerrainEditRules.pendingLabels(store.pending(), terrainKind(), id)
        if (pendingLabels.isNotEmpty()) card.addView(text(
            "En attente d'envoi : ${pendingLabels.joinToString(", ")}", 12.5f, true, HydriaColors.warning,
        ), margin(top = 10))

        fun action(label: String, onClick: () -> Unit) = Button(this).apply {
            text = label; HydriaUi.styleSecondary(this); setOnClickListener { onClick() }
        }
        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        row1.addView(action(if (hasGps) "Mettre à jour le GPS" else "Capturer le GPS") { requestLocation() },
            LinearLayout.LayoutParams(0, dp(52), 1f))
        row1.addView(action(if (hasPhoto) "Remplacer la photo" else "Prendre une photo") { requestPhoto() },
            LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginStart = dp(8) })
        card.addView(row1, margin(top = 12))
        if (isPoint) {
            val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            row2.addView(action("Nom de l'abonné") {
                editText("Nom de l'abonné", terrain.optString("subscriber_name"), android.text.InputType.TYPE_CLASS_TEXT or
                    android.text.InputType.TYPE_TEXT_FLAG_CAP_WORDS, ::subscriberError) { value ->
                    queueUpdate(JSONObject().put("subscriber_name", value), "Nom de l'abonné") { it.put("subscriber_name", value) }
                }
            }, LinearLayout.LayoutParams(0, dp(52), 1f))
            row2.addView(action("Téléphone") {
                editText("Téléphone de l'abonné", terrain.optString("telephone"), android.text.InputType.TYPE_CLASS_PHONE, ::phoneError) { value ->
                    queueUpdate(JSONObject().put("telephone", value), "Téléphone") { it.put("telephone", value) }
                    TerrainRepository.applyLocalReadingPointEnrichment(store, id, telephone = value)
                }
            }, LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginStart = dp(8) })
            card.addView(row2, margin(top = 8))
        }
        body.addView(card, margin(bottom = 12))
    }

    private fun subscriberError(value: String): String? =
        if (value.isBlank()) "Nom requis" else if (value.length > 255) "Nom trop long" else null

    private fun phoneError(value: String): String? {
        val digits = value.count { it.isDigit() }
        return if (digits < 9 || digits > 13 || value.length > 20) "Numéro invalide (9 à 13 chiffres)" else null
    }

    private fun editText(title: String, initial: String, inputType: Int, validate: (String) -> String?, onSave: (String) -> Unit) {
        val field = EditText(this).apply {
            this.inputType = inputType
            setText(initial)
            setSelection(text.length)
            HydriaUi.styleInput(this)
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle(title)
            .setView(LinearLayout(this).apply { setPadding(dp(18), dp(8), dp(18), 0); addView(field, LinearLayout.LayoutParams(-1, dp(56))) })
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Enregistrer", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val value = field.text.toString().trim()
                val error = validate(value)
                if (error != null) { field.error = error; return@setOnClickListener }
                dialog.dismiss()
                onSave(value)
            }
        }
        dialog.show()
    }

    /** Mise à jour du point d'eau (abonné / téléphone / GPS) ou du GPS de l'équipement. */
    private fun queueUpdate(fields: JSONObject, what: String, applyLocal: (JSONObject) -> Unit) {
        val isPoint = terrainKind() == "point_eau"
        val payload = JSONObject(fields.toString())
            .put("operation_type", if (isPoint) "update_point" else "update_equipment")
            .put(if (isPoint) "point_id" else "equipment_id", id)
        enqueueTerrain("terrain_data", payload, what, applyLocal)
    }

    private fun queuePhoto(encoded: String) {
        val isPoint = terrainKind() == "point_eau"
        val payload = JSONObject()
            .put("operation_type", if (isPoint) "photo_point" else "photo_equipment")
            .put(if (isPoint) "point_id" else "equipment_id", id)
            .put("photo_data", encoded)
            .put("content_type", "image/jpeg")
            .put("filename", if (isPoint) "point-eau-terrain.jpg" else "equipement-terrain.jpg")
        if (isPoint) TerrainRepository.applyLocalReadingPointEnrichment(store, id, photoCaptured = true)
        enqueueTerrain("terrain_photo", payload, "Photo") {
            it.put("has_photo", true).put("photo", "data:image/jpeg;base64,$encoded")
        }
    }

    /**
     * File hors ligne d'abord (rien n'est perdu), puis envoi immédiat si le réseau
     * est là ; sinon l'écran principal l'enverra à la prochaine synchronisation.
     */
    private fun enqueueTerrain(type: String, payload: JSONObject, what: String, applyLocal: (JSONObject) -> Unit) {
        val terrain = currentPayload?.optJSONObject("terrain") ?: return
        val localUuid = UUID.randomUUID().toString()
        payload.put("local_uuid", localUuid)
            .put("base_updated_at", TerrainEditRules.baseVersion(store.pending(), terrainKind(), id, terrain.optString("updated_at")))
        store.enqueue(type, payload)
        applyLocal(terrain)
        rerender()
        val token = store.token
        if (token.isNullOrBlank() || !isOnline()) {
            toast("$what enregistré hors ligne · envoi à la prochaine synchronisation.")
            return
        }
        toast("$what enregistré · envoi en cours…")
        executor.execute {
            store.markSynchronizing(localUuid)
            val response = runCatching { mg.hydria.app.HydriaNetwork.saveTerrainItem(token, payload) }.getOrNull()
            if (response?.successful == true) store.remove(localUuid)
            else store.markFailed(localUuid, response?.error ?: "Envoi impossible")
            runOnUiThread {
                if (response?.successful == true) {
                    // Nouvelle version serveur : la prochaine modification ne sera pas vue comme un conflit.
                    response.body.optString("server_updated_at").takeIf { it.isNotBlank() }?.let { terrain.put("updated_at", it) }
                    toast("$what synchronisé.")
                } else toast("$what conservé en file : ${response?.error ?: "réseau indisponible"}")
                rerender()
            }
        }
    }

    private fun rerender() {
        val payload = currentPayload ?: return
        store.saveSearchCache(cacheKey(), payload)
        render(payload, currentOffline)
    }

    private fun requestPhoto() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) launchCamera()
        else cameraPermission.launch(Manifest.permission.CAMERA)
    }

    private fun launchCamera() {
        val file = File.createTempFile("hydria_search_", ".jpg", cacheDir)
        pendingPhotoFile = file
        photoLauncher.launch(FileProvider.getUriForFile(this, "$packageName.fileprovider", file))
    }

    private fun requestLocation() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) acquireLocation()
        else locationPermission.launch(Manifest.permission.ACCESS_FINE_LOCATION)
    }

    @Suppress("MissingPermission", "DEPRECATION")
    private fun acquireLocation() {
        val manager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> null
        }
        if (provider == null) { toast("Activez la localisation GPS du téléphone."); return }
        toast("Recherche de la position GPS en cours…")
        val save: (Location?) -> Unit = { location ->
            if (location == null) toast("Position GPS indisponible. Réessayez à l'extérieur.")
            else AlertDialog.Builder(this)
                .setTitle("Enregistrer cette position ?")
                .setMessage(String.format(Locale.FRANCE, "%.6f, %.6f\nPrécision ±%d m\n\nVérifiez que vous êtes bien au %s.",
                    location.latitude, location.longitude, location.accuracy.toInt(),
                    if (terrainKind() == "point_eau") "point d'eau" else "l'équipement"))
                .setNegativeButton("Annuler", null)
                .setPositiveButton("Enregistrer") { _, _ ->
                    queueUpdate(JSONObject().put("latitude", location.latitude).put("longitude", location.longitude)
                        .put("accuracy", location.accuracy.toDouble()), "GPS") {
                        it.put("has_coordinates", true).put("latitude", location.latitude).put("longitude", location.longitude)
                    }
                    if (terrainKind() == "point_eau") TerrainRepository.applyLocalReadingPointEnrichment(
                        store, id, location.latitude, location.longitude, location.accuracy.toDouble())
                }
                .show()
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            manager.getCurrentLocation(provider, null, ContextCompat.getMainExecutor(this), save)
        } else {
            manager.requestSingleUpdate(provider, object : LocationListener {
                override fun onLocationChanged(location: Location) = save(location)
            }, mainLooper)
        }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    private fun renderPerson(payload: JSONObject, offline: Boolean) {
        body.removeAllViews()
        state.text = if (offline) "HORS LIGNE" else "SYNCHRONISÉ"
        state.setTextColor(if (offline) HydriaColors.warning else HydriaColors.success)
        val summary = fallbackItem ?: JSONObject()
        val typeDisplay = summary.optString("type_display", type)
        val title = summary.optString("nom", summary.optString("title", "Personne")).takeUnless(::isTechnicalUuid) ?: typeDisplay
        body.addView(HydriaUi.badge(this, typeDisplay, Tone.INFO))
        body.addView(text(title, 25f, true, HydriaColors.text), margin(top = 12, bottom = 12))
        val details = payload.optJSONObject("details") ?: JSONObject()
        renderJsonObject(details)
    }

    /** Ouvre la fiche d'un village ou d'un ouvrage depuis une liste de la fiche commune. */
    private fun openEntityDetail(entityType: String, entityId: String, title: String) {
        startActivity(Intent(this, SearchDetailActivity::class.java).apply {
            putExtra("entity_type", entityType)
            putExtra("entity_id", entityId)
            putExtra("title", title)
        })
    }

    // Tuile « Points d'eau par type » : points existants (branchés, non coupés) par type, kiosques détaillés par type
    // d'abonné ; les points SANS date de branchement (pas encore des points d'eau) sont présentés à part.
    private fun renderPointsEauTile(repartition: JSONObject) {
        val actifs = repartition.optJSONArray("actifs") ?: JSONArray()
        val sansDate = repartition.optJSONArray("sans_date") ?: JSONArray()
        val tile = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12)); HydriaUi.card(this, emphasized = true)
        }
        tile.addView(text("POINTS D'EAU PAR TYPE", 11f, true, HydriaColors.cyan))
        tile.addView(text("${repartition.optInt("actifs_total")} point(s) d'eau en service", 20f, true, HydriaColors.text), margin(top = 4, bottom = 6))
        if (actifs.length() == 0) tile.addView(text("Aucun point d'eau branché.", 13f, false, HydriaColors.textSecondary))
        for (i in 0 until actifs.length()) {
            val row = actifs.getJSONObject(i)
            tile.addView(text("${row.optString("type")} : ${row.optInt("count")}", 15f, true, HydriaColors.text), margin(top = 6))
            val abonnes = row.optJSONArray("abonnes") ?: JSONArray()
            for (j in 0 until abonnes.length()) {
                val abonne = abonnes.getJSONObject(j)
                val anomalie = abonne.optBoolean("anomalie")
                tile.addView(text(
                    "   ↳ ${abonne.optString("libelle")} : ${abonne.optInt("count")}" + if (anomalie) "  ⚠ à corriger" else "",
                    13f, anomalie, if (anomalie) HydriaColors.error else HydriaColors.textSecondary,
                ), margin(top = 2))
            }
        }
        val coupes = repartition.optInt("coupes", 0)
        if (coupes > 0) tile.addView(text("Coupés : $coupes (comptés à part)", 13f, true, HydriaColors.warning), margin(top = 10))
        body.addView(tile, margin(bottom = 8))

        val sansDateTotal = repartition.optInt("sans_date_total", 0)
        if (sansDateTotal > 0) {
            val warn = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(12))
                background = HydriaUi.rounded(this@SearchDetailActivity, HydriaColors.warningWash, 14f, HydriaColors.warning)
            }
            warn.addView(text("SANS DATE DE BRANCHEMENT : $sansDateTotal", 13f, true, HydriaColors.warning))
            warn.addView(text("Pas encore des points d'eau : ils ne sont pas comptés ci-dessus.", 12f, false, HydriaColors.textSecondary), margin(top = 3, bottom = 4))
            for (i in 0 until sansDate.length()) {
                val row = sansDate.getJSONObject(i)
                warn.addView(text("${row.optString("type")} : ${row.optInt("count")}", 14f, false, HydriaColors.text), margin(top = 3))
            }
            body.addView(warn, margin(bottom = 8))
        }
    }

    private fun renderJsonObject(value: JSONObject) {
        value.keys().forEach { key ->
            if (key == "repartition_points_eau") return@forEach     // déjà affichée par renderPointsEauTile
            val item = value.opt(key)
            when (item) {
                is JSONArray -> {
                    val visibleRows = buildList {
                        for (index in 0 until item.length()) {
                            val row = item.opt(index)
                            val displayValue = if (row is JSONObject) {
                                row.keys().asSequence()
                                    .mapNotNull { child ->
                                        val childValue = row.opt(child)
                                        if (isTechnicalUuid(childValue)) null
                                        else "${humanize(child)} : $childValue"
                                    }
                                    .joinToString(" · ")
                            } else {
                                row?.toString()?.takeUnless(::isTechnicalUuid).orEmpty()
                            }
                            if (displayValue.isNotBlank()) add(displayValue)
                        }
                    }
                    if (visibleRows.isEmpty()) return@forEach
                    val section = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(11), dp(14), dp(11)); HydriaUi.card(this)
                    }
                    section.addView(text("${humanize(key)} (${visibleRows.size})", 13f, true, HydriaColors.cyan))
                    visibleRows.forEach { row ->
                        section.addView(text(row, 13f, false, HydriaColors.text), margin(top = 7))
                    }
                    body.addView(section, margin(bottom = 8))
                }
                is JSONObject -> renderJsonObject(item)
                else -> if (item != null && item.toString().isNotBlank() && item.toString() != "null" && !isTechnicalUuid(item)) {
                    val row = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(10), dp(14), dp(10)); HydriaUi.card(this)
                    }
                    row.addView(text(humanize(key), 11f, true, HydriaColors.textSecondary))
                    row.addView(text(item.toString(), 15f, false, HydriaColors.text), margin(top = 3))
                    body.addView(row, margin(bottom = 8))
                }
            }
        }
    }

    private fun humanize(key: String): String = key.replace('_', ' ').replaceFirstChar { it.uppercase() }

    private fun renderFallback(item: JSONObject) {
        body.removeAllViews(); state.text = "APERÇU HORS LIGNE"; state.setTextColor(HydriaColors.warning)
        val typeDisplay = item.optString("type_display", type)
        val title = item.optString("title", item.optString("name", "Sans titre")).takeUnless(::isTechnicalUuid) ?: typeDisplay
        body.addView(HydriaUi.badge(this, typeDisplay, Tone.WARNING))
        body.addView(text(title, 24f, true, HydriaColors.text), margin(top = 12))
        val details = item.optJSONObject("details")
        if (details != null) details.keys().forEach { key ->
            val value = details.opt(key)?.toString().orEmpty()
            if (value.isNotBlank() && !value.startsWith("[") && !value.startsWith("{") && !isTechnicalUuid(value)) {
                body.addView(text("${key.replace('_', ' ').replaceFirstChar { it.uppercase() }}\n$value", 14f, false, HydriaColors.text), margin(top = 10))
            }
        }
    }

    private fun message(value: String) { body.removeAllViews(); body.addView(text(value, 15f, false, HydriaColors.textSecondary), margin(top = 30)) }
    private fun isOnline(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        return manager.getNetworkCapabilities(network)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }
    private fun text(value: String, size: Float, bold: Boolean, color: Int) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }
    private fun margin(top: Int = 0, bottom: Int = 0) = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top); bottomMargin = dp(bottom) }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
