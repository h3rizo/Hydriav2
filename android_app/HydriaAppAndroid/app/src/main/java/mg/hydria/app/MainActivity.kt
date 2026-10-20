package mg.hydria.app

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Rect
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.util.TypedValue
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.activity.addCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.widget.TextViewCompat
import org.json.JSONArray
import org.json.JSONObject
import mg.hydria.shared.rules.forms.ActivityCascadeTree
import mg.hydria.shared.rules.forms.ActivityTargetRules
import mg.hydria.shared.rules.forms.WorkTarget
import mg.hydria.shared.rules.readings.ReadingPointListRules
import java.io.ByteArrayOutputStream
import java.io.File
import java.text.SimpleDateFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Date
import java.util.Locale
import java.util.concurrent.Executors
import mg.hydria.app.navigation.NavigationTerrainActivity
import mg.hydria.app.navigation.data.GeoRepository
import mg.hydria.app.calculator.AdvancedCalculatorActivity
import mg.hydria.app.calculator.SalaryConfigRepository
import mg.hydria.shared.calculator.SalaryConfigUpdate
import mg.hydria.app.search.SearchActivity
import mg.hydria.app.repairs.RepairRules
import mg.hydria.app.repairs.RepairsRepository
import mg.hydria.app.sync.SyncDispatch
import mg.hydria.app.planning.PlanningRules
import mg.hydria.app.planning.PlanningsRepository
import mg.hydria.app.planning.PlanningDayState
import mg.hydria.app.terrain.TerrainRules
import mg.hydria.app.terrain.TerrainBatchTask
import mg.hydria.app.terrain.TerrainRepository
import mg.hydria.app.readings.ReadingsRules
import mg.hydria.shared.readings.ReadingValidation
import mg.hydria.shared.readings.ReadingError
import mg.hydria.shared.readings.ReadingDraftBook
import mg.hydria.shared.readings.ReadingDraftCard
import mg.hydria.shared.readings.ReadingFormLayout
import mg.hydria.shared.readings.ReadingFormSignature
import mg.hydria.shared.readings.ReadingNextPoint

class MainActivity : AppCompatActivity() {
    // POINTAGE en tête : première position de la barre du bas et du rail tablette.
    // C'est un raccourci vers PointageActivity (carte plein écran), jamais un écran courant.
    private enum class Screen { POINTAGE, TERRAIN, READINGS, REPAIRS, PLANNINGS }
    private data class PointEnrichment(
        var latitude: Double? = null,
        var longitude: Double? = null,
        var gpsQueued: Boolean = false,
        var photoQueued: Boolean = false,
        var phoneQueued: Boolean = false,
        var photoName: String = "point-eau-terrain.jpg",
    )

    private val executor = Executors.newSingleThreadExecutor()
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private lateinit var store: OfflineStore
    private lateinit var content: FrameLayout
    private lateinit var loadingOverlay: View
    private lateinit var syncStatus: TextView
    private data class NavItem(
        val container: LinearLayout,
        val icon: ImageView,
        val label: TextView,
        val badge: TextView,
    )
    private var currentScreen = Screen.TERRAIN
    private var terrainMode = "todo"
    /** Ouvrage dont la fiche (points d'eau + équipements) est ouverte dans « Par ouvrage ». */
    private var terrainOpenWorkId: String? = null
    private var terrainWorkQuery = ""
    private var terrainItemQuery = ""
    private var terrainCategory: String? = null
    private var syncing = false
    private var pointsGainedInSync = 0
    private var pointsRefreshedAt = 0L
    /** Classe de largeur de fenêtre courante (téléphone / tablette). Recalculée dans onConfigurationChanged(). */
    private var windowWidth: WindowWidth = WindowWidth.COMPACT
    /** Volet de détail (EXPANDED uniquement). Null en téléphone et en tablette medium. */
    private var detailPane: FrameLayout? = null
    /** Sélection multiple du tableau tablette — toujours vide hors EXPANDED. */
    private val selectedIds = mutableSetOf<String>()
    private val repairModel by lazy {
        androidx.lifecycle.ViewModelProvider(this)[mg.hydria.app.repairs.RepairScreenModel::class.java]
    }
    private val planningModel by lazy {
        androidx.lifecycle.ViewModelProvider(this)[mg.hydria.app.planning.PlanningScreenModel::class.java].planning
    }
    private var showRepairsOutsidePerimeter = false
    private var showCompletedRepairs = false
    /** Par defaut, l'ecran Terrain n'affiche que les ouvrages dont l'employe est
     * directement responsable ('responsable_direct'). Ce bouton elargit au
     * perimetre complet (hierarchie/role de support) renvoye par le serveur. */
    private var terrainPerimetreEtendu = false
    private val navItems = mutableMapOf<Screen, NavItem>()
    private val pointEnrichments = mutableMapOf<String, PointEnrichment>()
    private var readingEnrichmentRefresh: (() -> Unit)? = null
    private var pendingPhotoPointId: String? = null
    private var pendingPhotoFile: File? = null
    private var pendingRepairPhotoId: String? = null
    private var pendingRepairPhotoFile: File? = null
    /** Photos de reparation mises en file localement mais pas encore reflétées
     * par la tournée rechargée (nb_photos du snapshot) : additionné pour que le
     * badge se mette à jour immédiatement, avant confirmation serveur. */
    private val repairPhotoQueuedCounts = mutableMapOf<String, Int>()
    private var pendingLocationPointId: String? = null
    private var pendingTerrainItem: JSONObject? = null
    private var pendingTerrainWork: JSONObject? = null
    private var pendingTerrainCategory: String? = null
    private var pendingReadingAgentLocation = false
    private var readingAgentLocation: Location? = null
    private var readingLocationRefresh: (() -> Unit)? = null
    /** Vrai si le formulaire de relevé affiché contient une saisie non enregistrée (null hors formulaire). */
    private var readingFormDirty: (() -> Boolean)? = null
    // Cartes sociales du relevé en cours (kiosques). Chaque entrée =
    // {id?, numero_carte?, beneficiaire, quantite_bidons, volume_total}.
    private val readingSocialCards = mutableListOf<JSONObject>()
    private var pendingNearbyLocation = false
    private var nearbyLocation: Location? = null
    private var nearbyRadiusMeters = 500
    private val terrainBatchQueue = mutableListOf<TerrainBatchTask>()
    private var terrainBatchTotal = 0

    // Campagne de relevé — état de la session en cours
    private var campaignOuvrageId: String? = null
    private var campaignOuvrageNom: String? = null
    private var campaignDate: String? = null
    private var campaignShowDone: Boolean = false
    /** Dernier ticket 80 mm (en mémoire) : permet de relancer l'impression si l'imprimante n'était pas prête. */
    private var lastReadingTicket: mg.hydria.shared.readings.ReadingTicket? = null

    private fun printLastTicket() {
        val ticket = lastReadingTicket ?: return toast("Aucun ticket à réimprimer.")
        try {
            mg.hydria.app.readings.ReadingTicketPrinter.print(this, ticket)
        } catch (error: Exception) {
            toast("Impression impossible : ${error.message ?: "service d'impression indisponible"}")
        }
    }
    private var campaignShowAlreadyRead: Boolean = false
    // Filtre Parcelle (ouvrages > 20 points) et tri des points par distance au téléphone.
    private var campaignParcelId: String = ReadingPointListRules.ALL_PARCELS
    private var campaignSearchQuery: String = ""
    private var campaignSearchRefocus = false
    private val campaignSearchHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private var campaignNearbyMode: Boolean = false
    /** Point à rouvrir en priorité dans la saisie (« Corriger » depuis le centre de synchronisation). */
    private var campaignFocusPointId: String? = null
    /** Date (ISO) choisie à l'écran de départ de campagne : conservée quand l'écran est reconstruit (fin de synchro). */
    private var campaignSetupDate: String? = null
    /** Dernier appui sur Retour à la racine : un second appui sous 2 s quitte l'application. */
    private var lastBackPressAt = 0L

    // ── Formulaire de relevé : brouillon de saisie, focus et sections repliables (chantier L2-1) ──
    /** Brouillons de la campagne ouverte (un par point). Null hors campagne ; relu du store à l'ouverture. */
    private var readingDraftBook: ReadingDraftBook? = null
    /** Point dont les valeurs sont dans les champs du formulaire affiché (null hors formulaire). */
    private var readingCurrentPointId: String? = null
    /**
     * Garde tout de suite la saisie en cours dans le brouillon (et le store). Posée par renderCampaignReading,
     * appelée avant toute reconstruction de l'écran, à l'arrêt de l'activité et en quittant la campagne.
     */
    private var readingDraftFlush: (() -> Unit)? = null
    /** Arrête le brouillon du formulaire affiché : plus aucune écriture, même différée. Ne garde pas la saisie. */
    private var readingDraftClose: (() -> Unit)? = null
    /** Vrai : à la prochaine construction du formulaire, l'index prend le focus (et le clavier sur téléphone). */
    private var readingFocusIndex = false
    /** « Plus de détails » ouvert par l'agent sur le point courant : reste ouvert quand la page est reconstruite. */
    private var readingDetailsExpanded = false
    /** « Choisir un point » ouvert par l'agent, ou parce qu'il vient de s'en servir (un choix reconstruit la page). */
    private var readingPickerExpanded = false
    /** En-tête, filet et barre d'onglets du téléphone : masqués pendant la saisie au clavier d'un relevé. */
    private var phoneChrome: List<View> = emptyList()

    private val pointPhotoLauncher = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        onPointPhotoResult(success, fromCamera = true)
    }

    /** Photo déjà présente sur le téléphone : copiée dans un fichier temporaire puis traitée comme une prise de vue. */
    private val pointGalleryLauncher = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) {
            pendingPhotoPointId = null
            pendingTerrainItem = null
            pendingTerrainWork = null
            pendingTerrainCategory = null
        } else {
            val copy = runCatching {
                File.createTempFile("hydria_gallery_", ".jpg", cacheDir).also { target ->
                    contentResolver.openInputStream(uri)?.use { input -> target.outputStream().use { input.copyTo(it) } }
                        ?: error("Photo illisible")
                }
            }.getOrNull()
            if (copy == null) {
                pendingPhotoPointId = null
                pendingTerrainItem = null
                pendingTerrainWork = null
                pendingTerrainCategory = null
                toast("Impossible de lire cette photo.")
            } else {
                pendingPhotoFile = copy
                onPointPhotoResult(true, fromCamera = false)
            }
        }
    }

    /** Version de base d'une fiche Terrain : vide si une modification est déjà en file (évite un faux conflit 409). */
    private fun terrainBaseVersion(item: JSONObject, equipment: Boolean): String =
        mg.hydria.shared.rules.terrain.TerrainEditRules.baseVersion(
            store.pending(), if (equipment) "equipement" else "point_eau", item.optString("id"), item.optString("updated_at"))

    private fun onPointPhotoResult(success: Boolean, fromCamera: Boolean) {
        val pointId = pendingPhotoPointId
        val photoFile = pendingPhotoFile
        var autoGps: Pair<JSONObject, JSONObject>? = null
        var autoSubscriber: Triple<JSONObject, JSONObject, String>? = null
        if (success && pointId != null && photoFile != null) {
            runCatching { compressPointPhoto(photoFile) }
                .onSuccess { encoded ->
                    val terrainItem = pendingTerrainItem
                    val terrainWork = pendingTerrainWork
                    val category = pendingTerrainCategory
                    if (terrainItem != null && terrainWork != null && category != null) {
                        val equipment = category == "equipment_photo"
                        store.enqueue("terrain_photo", JSONObject()
                            .put("operation_type", if (equipment) "photo_equipment" else "photo_point")
                            .put(if (equipment) "equipment_id" else "point_id", terrainItem.getString("id"))
                            .put("photo_data", encoded)
                            .put("content_type", "image/jpeg")
                            .put("filename", if (equipment) "equipement-terrain.jpg" else "point-eau-terrain.jpg")
                            .put("base_updated_at", terrainBaseVersion(terrainItem, equipment)))
                        updateStatus()
                        if (TerrainRepository.applyLocalTerrainCompletion(store, terrainItem, terrainWork, category)) updateStatus()
                        toast("Photo enregistrée · ${store.pendingCount()} action(s) en attente.")
                        // Équipement photographié sur place sans coordonnées : on vérifie et on enregistre le GPS.
                        if (equipment && fromCamera && !terrainItem.optBoolean("has_coordinates")) autoGps = terrainItem to terrainWork
                        // Point d'eau photographié : on propose dans la foulée le nom d'abonné et le téléphone
                        // s'ils manquent. La série (s'il y en a une) reprend à la fermeture du formulaire.
                        val askSubscriber = !equipment &&
                            (!terrainItem.optBoolean("has_subscriber_name") || terrainItem.optString("telephone").isBlank())
                        if (askSubscriber) autoSubscriber = Triple(terrainItem, terrainWork, category)
                        else finishTerrainBatchTask(terrainItem, category)
                    } else {
                        val baseUpdatedAt = mg.hydria.shared.rules.terrain.TerrainEditRules.baseVersion(
                            store.pending(), "point_eau", pointId,
                            TerrainRepository.findTerrainPoint(store, pointId)?.optString("updated_at").orEmpty())
                        store.enqueue("terrain_photo", JSONObject()
                            .put("operation_type", "photo_point")
                            .put("point_id", pointId)
                            .put("photo_data", encoded)
                            .put("content_type", "image/jpeg")
                            .put("filename", "point-eau-terrain.jpg")
                            .put("base_updated_at", baseUpdatedAt))
                        pointEnrichments.getOrPut(pointId) { PointEnrichment() }.photoQueued = true
                        TerrainRepository.applyLocalReadingPointEnrichment(store, pointId, photoCaptured = true)
                        updateStatus()
                        toast("Photo enregistrée · ${store.pendingCount()} action(s) en attente.")
                    }
                }
                .onFailure { toast("Impossible de préparer la photo : ${it.message ?: "erreur inconnue"}") }
        }
        photoFile?.delete()
        pendingPhotoPointId = null
        pendingPhotoFile = null
        pendingTerrainItem = null
        pendingTerrainWork = null
        pendingTerrainCategory = null
        readingEnrichmentRefresh?.invoke()
        if (terrainOpenWorkId != null && currentScreen == Screen.TERRAIN && terrainBatchQueue.isEmpty()) renderCurrentScreen()
        autoGps?.let { (item, work) -> captureEquipmentGps(item, work, onlyIfPermitted = true) }
        autoSubscriber?.let { (item, work, category) ->
            showSubscriberForm(item, work) {
                if (!finishTerrainBatchTask(item, category)) renderCurrentScreen()
            }
        }
        if (success && isOnline() && store.pendingCount() > 0) synchronize()
    }

    private var pendingEquipmentGps: Pair<JSONObject, JSONObject>? = null
    private val equipmentGpsPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val target = pendingEquipmentGps
        pendingEquipmentGps = null
        if (granted && target != null) acquireEquipmentGps(target.first, target.second)
        else toast("Autorisez la localisation pour enregistrer le GPS de l'équipement.")
    }

    /** GPS d'un équipement : bouton de la fiche, ou vérification automatique après une photo prise sur place. */
    private fun captureEquipmentGps(item: JSONObject, work: JSONObject, onlyIfPermitted: Boolean = false) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            acquireEquipmentGps(item, work)
        } else if (!onlyIfPermitted) {
            pendingEquipmentGps = item to work
            equipmentGpsPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    /** Autonome (n'utilise pas les variables « pending » partagées) pour ne jamais perturber une série en cours. */
    @Suppress("MissingPermission", "DEPRECATION")
    private fun acquireEquipmentGps(item: JSONObject, work: JSONObject) {
        val manager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> null
        }
        if (provider == null) {
            toast("Activez la localisation GPS du téléphone.")
            return
        }
        toast("Recherche de la position GPS de l'équipement…")
        val save: (Location?) -> Unit = save@{ location ->
            if (location == null) {
                toast("Position GPS indisponible. Réessayez à l'extérieur.")
                return@save
            }
            store.enqueue("terrain_data", JSONObject()
                .put("operation_type", "update_equipment")
                .put("equipment_id", item.getString("id"))
                .put("latitude", location.latitude)
                .put("longitude", location.longitude)
                .put("accuracy", location.accuracy.toDouble())
                .put("base_updated_at", terrainBaseVersion(item, equipment = true)))
            item.put("latitude", location.latitude)
                .put("longitude", location.longitude)
                .put("coordinates_accuracy", location.accuracy.toDouble())
            TerrainRepository.applyLocalTerrainCompletion(store, item, work, "equipment_gps")
            updateStatus()
            toast("GPS de l'équipement enregistré · précision ±${location.accuracy.toInt()} m.")
            if (currentScreen == Screen.TERRAIN && terrainBatchQueue.isEmpty()) renderCurrentScreen()
            if (isOnline() && store.pendingCount() > 0) synchronize()
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            manager.getCurrentLocation(provider, null, ContextCompat.getMainExecutor(this), save)
        } else {
            manager.requestSingleUpdate(provider, object : LocationListener {
                override fun onLocationChanged(location: Location) = save(location)
            }, mainLooper)
        }
    }

    private val cameraPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val pointId = pendingPhotoPointId
        if (granted && pointId != null) launchPointPhoto(pointId)
        else {
            pendingPhotoPointId = null
            pendingTerrainItem = null
            pendingTerrainWork = null
            pendingTerrainCategory = null
            toast("Autorisez l'appareil photo pour compléter la fiche du point d'eau.")
        }
    }

    private val repairPhotoLauncher = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val repairId = pendingRepairPhotoId
        val photoFile = pendingRepairPhotoFile
        if (success && repairId != null && photoFile != null) {
            runCatching { compressPointPhoto(photoFile) }
                .onSuccess { encoded ->
                    RepairsRepository.enqueuePhoto(store, repairId, encoded, "image/jpeg", "reparation-terrain.jpg")
                    repairPhotoQueuedCounts[repairId] = (repairPhotoQueuedCounts[repairId] ?: 0) + 1
                    updateStatus()
                    renderCurrentScreen()
                    toast("Photo enregistrée · ${store.pendingCount()} action(s) en attente.")
                }
                .onFailure { toast("Impossible de préparer la photo : ${it.message ?: "erreur inconnue"}") }
        }
        photoFile?.delete()
        pendingRepairPhotoId = null
        pendingRepairPhotoFile = null
        if (success && isOnline() && store.pendingCount() > 0) synchronize()
    }

    /** Photos déjà présentes sur le téléphone : sélection multiple, chacune compressée puis mise en file. */
    private val repairGalleryLauncher = registerForActivityResult(ActivityResultContracts.GetMultipleContents()) { uris ->
        val repairId = pendingRepairPhotoId
        pendingRepairPhotoId = null
        if (repairId == null || uris.isEmpty()) return@registerForActivityResult
        var added = 0
        uris.forEachIndexed { index, uri ->
            val copy = runCatching {
                File.createTempFile("hydria_repair_gallery_", ".jpg", cacheDir).also { target ->
                    contentResolver.openInputStream(uri)?.use { input -> target.outputStream().use { input.copyTo(it) } }
                        ?: error("Photo illisible")
                }
            }.getOrNull() ?: return@forEachIndexed
            runCatching { compressPointPhoto(copy) }.onSuccess { encoded ->
                RepairsRepository.enqueuePhoto(store, repairId, encoded, "image/jpeg", "reparation-galerie-${index + 1}.jpg")
                repairPhotoQueuedCounts[repairId] = (repairPhotoQueuedCounts[repairId] ?: 0) + 1
                added++
            }
            copy.delete()
        }
        updateStatus()
        renderCurrentScreen()
        toast(if (added == uris.size) "$added photo(s) enregistrée(s) · ${store.pendingCount()} action(s) en attente."
            else "$added photo(s) sur ${uris.size} enregistrée(s) ; les autres sont illisibles ou trop lourdes.")
        if (added > 0 && isOnline() && store.pendingCount() > 0) synchronize()
    }

    private fun chooseRepairPhotoSource(repairId: String) {
        AlertDialog.Builder(this)
            .setTitle("Ajouter des photos")
            .setItems(arrayOf("Prendre une photo", "Choisir dans la galerie (plusieurs)")) { _, which ->
                if (which == 0) captureRepairPhoto(repairId)
                else {
                    pendingRepairPhotoId = repairId
                    repairGalleryLauncher.launch("image/*")
                }
            }
            .setNegativeButton("Annuler", null)
            .show()
    }

    private val repairCameraPermissionLauncher =registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val repairId = pendingRepairPhotoId
        if (granted && repairId != null) launchRepairPhoto(repairId)
        else {
            pendingRepairPhotoId = null
            toast("Autorisez l'appareil photo pour joindre une photo à la réparation.")
        }
    }

    private val locationPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val pointId = pendingLocationPointId
        if (granted && pointId != null) acquirePointLocation(pointId)
        else {
            pendingLocationPointId = null
            pendingReadingAgentLocation = false
            pendingNearbyLocation = false
            pendingTerrainItem = null
            pendingTerrainWork = null
            pendingTerrainCategory = null
            toast("Autorisez la localisation pour enregistrer les coordonnées du point d'eau.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        store = OfflineStore(this)
        restorePendingPhoto(savedInstanceState)
        registerBackNavigation()
        if (store.token.isNullOrBlank()) showLogin() else {
            restoreCampaign()
            showApplication()
        }
        registerAutomaticSynchronization()
    }

    override fun onStop() {
        // L'appareil photo ou une autre appli peut faire mourir le processus : la saisie du relevé part dans le
        // brouillon avant que l'activité ne soit mise en arrière-plan.
        readingDraftFlush?.let { runCatching { it() } }
        super.onStop()
    }

    /**
     * Retour système : remonte d'un niveau au lieu de quitter l'application. Campagne de relevé active,
     * puis catégorie / fiche ouvrage Terrain ouverte, puis retour à l'onglet Terrain depuis un autre
     * onglet. À la racine : « Appuyez encore pour quitter », double appui sous 2 s.
     */
    private fun registerBackNavigation() {
        onBackPressedDispatcher.addCallback(this) {
            if (navigateBack()) return@addCallback
            val now = android.os.SystemClock.elapsedRealtime()
            if (!store.token.isNullOrBlank() && now - lastBackPressAt > 2000L) {
                lastBackPressAt = now
                Toast.makeText(this@MainActivity, "Appuyez encore pour quitter", Toast.LENGTH_SHORT).show()
                return@addCallback
            }
            // Second appui sous 2 s (ou écran de connexion) : comportement système habituel.
            isEnabled = false
            onBackPressedDispatcher.onBackPressed()
            isEnabled = true
        }
    }

    /** Remonte d'un niveau. false = racine (onglet Terrain, rien d'ouvert) ou pas de session. */
    private fun navigateBack(): Boolean {
        if (store.token.isNullOrBlank()) return false
        when (currentScreen) {
            Screen.READINGS -> if (campaignOuvrageId != null) {
                requestLeaveCampaign()
                return true
            }
            Screen.TERRAIN -> {
                when {
                    terrainCategory != null -> terrainCategory = null
                    terrainOpenWorkId != null -> { terrainOpenWorkId = null; terrainItemQuery = "" }
                    terrainMode != "todo" -> terrainMode = "todo"
                    else -> return false
                }
                renderCurrentScreen()
                return true
            }
            else -> Unit
        }
        if (currentScreen != Screen.TERRAIN) {
            showTerrainTab()
            return true
        }
        return false
    }

    /** Ferme la campagne active et revient au choix de l'ouvrage. */
    private fun leaveCampaign() {
        closeCampaign()
        renderCurrentScreen()
    }

    /**
     * Ferme la campagne active (Retour et « Changer »). Une saisie non enregistrée n'est pas perdue et ne
     * demande rien : elle est gardée en brouillon, puis reprise (« Brouillon repris ») à la réouverture du point.
     */
    private fun requestLeaveCampaign() {
        val unsaved = readingFormDirty?.invoke() == true
        // Avant closeCampaign(), qui remet à zéro l'état de la campagne et désarme le brouillon.
        readingDraftFlush?.let { runCatching { it() } }
        leaveCampaign()
        if (unsaved) toast("Saisie gardée en brouillon")
    }

    /**
     * « Abandonner la saisie ? » (éditeurs de planning et de réparation) : « Continuer la saisie » est le
     * bouton principal (positif, à droite), « Abandonner » demande un geste volontaire. Un toucher à côté ferme
     * la boîte = on continue la saisie.
     */
    private fun confirmAbandon(message: String, onAbandon: () -> Unit) {
        AlertDialog.Builder(this)
            .setTitle("Abandonner la saisie ?")
            .setMessage(message)
            .setPositiveButton("Continuer la saisie", null)
            .setNegativeButton("Abandonner") { _, _ -> onAbandon() }
            .show()
    }

    /** Même effet qu'un appui sur l'onglet Terrain (barre du bas en téléphone, rail en tablette). */
    private fun showTerrainTab() {
        HydriaFeedback.tap()
        currentScreen = Screen.TERRAIN
        terrainCategory = null
        if (windowWidth.isTablet) {
            selectedIds.clear()
            withScreenTransition { showApplication(initial = false) }
        } else withScreenTransition { renderCurrentScreen() }
    }

    /** Mémorise la campagne active (ouvrage, nom, date) pour la retrouver après une fermeture ou une mort du processus. */
    private fun persistCampaign() = store.saveCampaign(campaignOuvrageId, campaignOuvrageNom, campaignDate)

    /** Ferme la campagne active (effet de « Changer ») : état en mémoire remis à zéro, mémorisation effacée. */
    private fun closeCampaign() {
        campaignOuvrageId = null
        campaignOuvrageNom = null
        campaignDate = null
        campaignSetupDate = null
        campaignShowDone = false
        campaignShowAlreadyRead = false
        campaignFocusPointId = null
        campaignParcelId = ReadingPointListRules.ALL_PARCELS
        campaignSearchQuery = ""
        campaignNearbyMode = false
        readingAgentLocation = null
        readingSocialCards.clear()
        // Brouillon désarmé sans rien écrire : à la déconnexion, la saisie ne doit pas être réécrite après coup.
        // (Retour et « Changer » l'ont déjà gardée avant d'arriver ici.)
        readingDraftClose?.let { runCatching { it() } }
        readingDraftClose = null
        readingDraftFlush = null
        readingFormDirty = null
        readingCurrentPointId = null
        readingDraftBook = null
        readingFocusIndex = false
        readingDetailsExpanded = false
        readingPickerExpanded = false
        persistCampaign()
        // Tablette 2 volets : le formulaire de relevé du volet de détail ne doit pas survivre à la campagne
        // (son « Enregistrer » resterait actif avec une date de campagne vide). Retour au volet vide.
        detailPane?.let { renderDetailPlaceholder(it) }
    }

    /** Au démarrage : retrouve la campagne mémorisée si l'ouvrage existe toujours dans la tournée locale. */
    private fun restoreCampaign() {
        val saved = store.savedCampaign() ?: return
        val snapshot = store.snapshot ?: return
        val stillThere = jsonObjects(snapshot.optJSONArray("ouvrages") ?: JSONArray())
            .any { it.optString("id") == saved.first }
        if (!stillThere) {
            store.saveCampaign(null, null, null)
            return
        }
        campaignOuvrageId = saved.first
        campaignOuvrageNom = saved.second.ifBlank { null }
        campaignDate = saved.third
    }

    override fun onSaveInstanceState(outState: Bundle) {
        // L'appareil photo peut provoquer la destruction du processus Hydria.
        // Garder uniquement le chemin et les identifiants, jamais l'image ni
        // le snapshot complet dans le Bundle (taille limitee par Android).
        pendingPhotoPointId?.let { pointId ->
            outState.putBundle("pending_point_photo", Bundle().apply {
                putString("point_id", pointId)
                putString("file_path", pendingPhotoFile?.absolutePath)
                putString("category", pendingTerrainCategory)
                putString("item_id", pendingTerrainItem?.optString("id"))
                putString("base_updated_at", pendingTerrainItem?.optString("updated_at"))
                putString("work_id", pendingTerrainWork?.optString("id"))
            })
        }
        pendingRepairPhotoId?.let { repairId ->
            outState.putBundle("pending_repair_photo", Bundle().apply {
                putString("repair_id", repairId)
                putString("file_path", pendingRepairPhotoFile?.absolutePath)
            })
        }
        super.onSaveInstanceState(outState)
    }

    private fun restorePendingPhoto(savedInstanceState: Bundle?) {
        savedInstanceState?.getBundle("pending_repair_photo")?.let { photo ->
            pendingRepairPhotoId = photo.getString("repair_id")
            pendingRepairPhotoFile = photo.getString("file_path")?.let { File(it) }
        }
        val photo = savedInstanceState?.getBundle("pending_point_photo") ?: return
        pendingPhotoPointId = photo.getString("point_id")
        pendingPhotoFile = photo.getString("file_path")?.let { File(it) }
        pendingTerrainCategory = photo.getString("category")
        // Les traitements de photo utilisent uniquement ces champs. Le repository
        // retrouve ensuite l'ouvrage et l'element complets dans le snapshot local.
        pendingTerrainItem = photo.getString("item_id")?.let { id ->
            JSONObject().put("id", id).put("updated_at", photo.getString("base_updated_at").orEmpty())
        }
        pendingTerrainWork = photo.getString("work_id")?.let { id -> JSONObject().put("id", id) }
    }

    private fun registerAutomaticSynchronization() {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: android.net.Network) {
                runOnUiThread {
                    if (!store.token.isNullOrBlank()) synchronize()
                }
            }
        }
        networkCallback = callback
        runCatching { manager.registerDefaultNetworkCallback(callback) }
    }

    private fun showLogin() {
        val page = vertical(padding = 30).apply {
            gravity = Gravity.CENTER
            setBackgroundColor(HydriaColors.background)
        }
        page.addView(ImageView(this).apply {
            setImageResource(R.drawable.hydria_vase_foreground)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            contentDescription = "Icône Hydria, vase orange"
        }, matchWrap(104))
        page.addView(text("Hydria Terrain", 30f, true, HydriaColors.text).apply { gravity = Gravity.CENTER })
        page.addView(text("L’eau, les ouvrages et vos tournées dans une seule application", 15f, false, HydriaColors.textSecondary).apply {
            gravity = Gravity.CENTER
            setPadding(0, dp(7), 0, dp(30))
        })
        val username = field("Nom d’utilisateur")
        val password = field("Mot de passe").apply { inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
        val error = text("", 14f, false, HydriaColors.error).apply { visibility = View.GONE }
        val progress = ProgressBar(this).apply { visibility = View.GONE }
        val login = primaryButton("Se connecter")
        page.addView(username, matchWrap(52))
        page.addView(password, matchWrap(52, top = 12))
        page.addView(error, matchWrap(top = 10))
        page.addView(progress, wrapWrap(top = 12).apply { gravity = Gravity.CENTER_HORIZONTAL })
        page.addView(login, matchWrap(54, top = 12))
        page.addView(text("Utilisez les mêmes identifiants que sur hydria.mg.", 13f, false, HydriaColors.textSecondary).apply {
            gravity = Gravity.CENTER
        }, matchWrap(top = 18))
        setContentView(page)

        login.setOnClickListener {
            val user = username.text.toString().trim()
            val pass = password.text.toString()
            if (user.isBlank() || pass.isBlank()) {
                error.text = "Nom d’utilisateur et mot de passe requis"
                error.visibility = View.VISIBLE
                return@setOnClickListener
            }
            if (!isOnline()) {
                error.text = "Une connexion est nécessaire pour la première authentification."
                error.visibility = View.VISIBLE
                return@setOnClickListener
            }
            login.isEnabled = false
            progress.visibility = View.VISIBLE
            error.visibility = View.GONE
            executor.execute {
                val deviceLabel = "Android - ${android.os.Build.MODEL}"
                // Phase 1 KMP : tente d'abord le nouveau client Ktor (shared/auth),
                // et si ça échoue techniquement (réseau, parsing...) retombe sur
                // l'ancien HydriaApi.login() en secours - même contrat de résultat.
                val result = runCatching { mg.hydria.shared.auth.HydriaAuthGateway.loginBlocking(user, pass, deviceLabel) }
                    .recoverCatching {
                        val legacy = HydriaApi.login(user, pass, deviceLabel)
                        mg.hydria.shared.auth.HydriaAuthGateway.Result(legacy.status, legacy.body)
                    }
                runOnUiThread {
                    login.isEnabled = true
                    progress.visibility = View.GONE
                    result.onSuccess { response ->
                        if (response.successful) {
                            store.token = response.body.getString("token")
                            store.accountKey = response.body.optString("user", user).ifBlank { user }
                            store.employeeName = response.body.optString("employe_nom", user).ifBlank { user }
                            showApplication()
                        } else {
                            error.text = response.error
                            error.visibility = View.VISIBLE
                        }
                    }.onFailure {
                        error.text = "Connexion impossible : ${it.message ?: "réseau indisponible"}"
                        error.visibility = View.VISIBLE
                    }
                }
            }
        }
    }

    private fun screenLabel(screen: Screen): String = when (screen) {
        Screen.POINTAGE -> "Pointage"
        Screen.TERRAIN -> "Terrain"
        Screen.READINGS -> "Relevés"
        Screen.REPAIRS -> "Réparations"
        Screen.PLANNINGS -> "Planning"
    }

    private fun screenIcon(screen: Screen): Int = when (screen) {
        Screen.POINTAGE -> R.drawable.ic_pointage
        Screen.TERRAIN -> R.drawable.ic_terrain
        Screen.READINGS -> R.drawable.ic_readings
        Screen.REPAIRS -> R.drawable.ic_repairs
        Screen.PLANNINGS -> R.drawable.ic_planning
    }

    /**
     * Construit la coquille de l'application selon la largeur de fenêtre.
     * COMPACT : en-tête + volet unique + barre d'onglets basse.
     * MEDIUM/EXPANDED : rail vertical à gauche + volet(s), pas d'en-tête (logo et
     * pastille de sync vivent dans le rail).
     *
     * [initial] : lancer la synchro d'ouverture (false lors d'un simple relayout).
     */
    private fun showApplication(initial: Boolean = true) {
        navItems.clear()
        phoneChrome = emptyList()
        windowWidth = HydriaWindow.of(this)

        syncStatus = TextView(this).apply {
            typeface = HydriaType.display(600)
            gravity = Gravity.CENTER
            // Zone tactile de 48 dp ; la pastille visible (38 dp) est inscrite par updateStatus().
            minHeight = dp(48)
            minWidth = dp(48)
            setPadding(dp(13), 0, dp(13), 0)
            setOnClickListener { showSyncCenter() }
        }
        content = FrameLayout(this).apply { setBackgroundColor(HydriaColors.background) }
        detailPane = if (windowWidth.isTwoPane) FrameLayout(this).apply {
            setBackgroundColor(HydriaColors.background)
        } else null

        val shell: View = if (windowWidth.isTablet) {
            val rail = HydriaWindow.navigationRail(
                this,
                Screen.entries.map { screen ->
                    HydriaWindow.RailTab(
                        id = screen.name,
                        label = screenLabel(screen),
                        iconRes = screenIcon(screen),
                        badge = if (screen == Screen.REPAIRS) repairsBadgeCount() else 0,
                    ) {
                        if (screen == Screen.POINTAGE) {
                            HydriaFeedback.tap()
                            openPointage()
                        } else if (currentScreen != screen) {
                            HydriaFeedback.tap()
                            currentScreen = screen
                            terrainCategory = null
                            selectedIds.clear()
                            withScreenTransition { showApplication(initial = false) }
                        }
                    }
                },
                currentScreen.name,
                footer = buildRailFooter(),
            )
            HydriaWindow.paneScaffold(this, windowWidth, rail, content, detailPane)
        } else {
            val header = buildPhoneHeader()
            val divider = View(this@MainActivity).apply { setBackgroundColor(HydriaColors.outline) }
            val tabs = buildBottomNav()
            // Masqués pendant la saisie au clavier d'un relevé de campagne (updateKeyboardChrome) : la place
            // revient au formulaire.
            phoneChrome = listOf(header, divider, tabs)
            vertical().apply {
                setBackgroundColor(HydriaColors.background)
                addView(header, matchWrap())
                addView(content, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
                addView(divider, matchWrap(1))
                addView(tabs, matchWrap(74))
            }
        }
        loadingOverlay = HydriaUi.loadingOverlay(this)
        val root = FrameLayout(this).apply {
            addView(shell, FrameLayout.LayoutParams(-1, -1))
            addView(loadingOverlay, FrameLayout.LayoutParams(-1, -1))
        }
        setContentView(root)
        root.viewTreeObserver.addOnGlobalLayoutListener { updateKeyboardChrome(root) }
        detailPane?.let { renderDetailPlaceholder(it) }
        renderCurrentScreen()
        updateStatus()
        if (initial && isOnline()) synchronize()
    }

    /**
     * Masque l'en-tête et la barre d'onglets du téléphone tant que le clavier est ouvert sur le formulaire de
     * relevé d'une campagne (décision 5 ter n°5) : la place revient à l'index et à la barre « Enregistrer ».
     * Le clavier est détecté par la variation de hauteur de la fenêtre (rectangle visible contre hauteur totale),
     * car minSdk est 26 et WindowInsets.isVisible(ime()) n'y est pas fiable. Sans effet en tablette (rail).
     */
    private fun updateKeyboardChrome(root: View) {
        if (phoneChrome.isEmpty()) return
        var hide = false
        if (currentScreen == Screen.READINGS && campaignOuvrageId != null) {
            val visible = Rect().also { root.getWindowVisibleDisplayFrame(it) }
            hide = mg.hydria.app.readings.ReadingKeyboardRules.isOpen(
                root.rootView.height, visible.bottom, resources.displayMetrics.density,
            )
        }
        val target = if (hide) View.GONE else View.VISIBLE
        phoneChrome.forEach { if (it.visibility != target) it.visibility = target }
    }

    /**
     * Affiche le voile de chargement, laisse un frame s'écouler pour qu'il
     * soit réellement dessiné, exécute [block] (reconstruction d'écran,
     * potentiellement coûteuse et synchrone), puis le masque. Utilisé sur
     * les changements d'écran (barre du bas, rail tablette) pour que l'appli
     * ne paraisse jamais figée pendant la reconstruction de la vue.
     */
    private fun withScreenTransition(block: () -> Unit) {
        if (!::loadingOverlay.isInitialized) { block(); return }
        loadingOverlay.visibility = View.VISIBLE
        loadingOverlay.post {
            try {
                block()
            } finally {
                loadingOverlay.visibility = View.GONE
            }
        }
    }

    private fun buildPhoneHeader(): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dp(16), dp(6), dp(12), dp(12))
        setBackgroundColor(HydriaColors.backgroundDeep)
        addView(ImageView(this@MainActivity).apply {
            setImageResource(R.drawable.hydria_vase_foreground)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(dp(36), dp(36)).apply { marginEnd = dp(10) })
        addView(vertical().apply {
            addView(TextView(this@MainActivity).apply {
                text = "Terrain"
                textSize = 19f
                typeface = HydriaType.display(700)
                setTextColor(HydriaColors.text)
                letterSpacing = -0.02f
                includeFontPadding = false
            })
            addView(TextView(this@MainActivity).apply {
                text = "${store.employeeName} · ${perimeterLabel()}"
                textSize = 11.5f
                typeface = HydriaType.display(400)
                setTextColor(HydriaColors.textSecondary)
                includeFontPadding = false
                maxLines = 1
            })
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        addView(secondaryButton("Recherche").apply {
            contentDescription = "Ouvrir la recherche Hydria"
            setOnClickListener { startActivity(Intent(this@MainActivity, SearchActivity::class.java)) }
        }, wrapWrap().apply { marginEnd = dp(6) })
        addView(syncStatus, wrapWrap().apply { marginEnd = dp(6) })
        addView(secondaryButton("⋮").apply {
            contentDescription = "Ouvrir le menu de la session"
            minHeight = dp(48)
            minimumHeight = dp(48)
            // Fond visible de 38 dp inscrit dans une zone tactile de 48 dp (TRANSVERSE-05).
            background = HydriaUi.withTouchInset(this@MainActivity, background, 5f, 5f)
            setPadding(0, 0, 0, 0)
            setOnClickListener { showSessionMenu() }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
    }

    private fun buildBottomNav(): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        clipChildren = false
        setPadding(dp(6), 0, dp(6), 0)
        setBackgroundColor(HydriaColors.backgroundDeep)
        Screen.entries.forEach { screen ->
            val item = buildNavItem(screen, screenLabel(screen), screenIcon(screen))
            navItems[screen] = item
            addView(item.container, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                marginStart = dp(3); marginEnd = dp(3)
            })
        }
    }

    /**
     * Bas du rail tablette : recherche, pastille de sync, menu de session. Les trois zones
     * tactiles font 48 dp (TRANSVERSE-05) ; les icônes gardent 24 dp, centrées par le padding.
     * Pas de marge entre elles : les zones se touchent sans se chevaucher, ce qui limite la
     * hauteur prise par le pied du rail sur une tablette de faible hauteur.
     */
    private fun buildRailFooter(): View = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_HORIZONTAL
        addView(ImageView(this@MainActivity).apply {
            setImageResource(android.R.drawable.ic_menu_search)
            imageTintList = android.content.res.ColorStateList.valueOf(HydriaColors.textSecondary)
            contentDescription = "Ouvrir la recherche Hydria"
            setPadding(dp(12), dp(12), dp(12), dp(12))
            isClickable = true
            isFocusable = true
            setOnClickListener { startActivity(Intent(this@MainActivity, SearchActivity::class.java)) }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        addView(syncStatus, LinearLayout.LayoutParams(-2, -2))
        addView(ImageView(this@MainActivity).apply {
            setImageResource(android.R.drawable.ic_menu_more)
            imageTintList = android.content.res.ColorStateList.valueOf(HydriaColors.textSecondary)
            contentDescription = "Ouvrir le menu de la session"
            setPadding(dp(12), dp(12), dp(12), dp(12))
            isClickable = true
            isFocusable = true
            setOnClickListener { showSessionMenu() }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
    }

    private fun renderDetailPlaceholder(pane: FrameLayout) {
        pane.removeAllViews()
        pane.addView(vertical(padding = 28).apply {
            gravity = Gravity.CENTER
            addView(text("Volet de détail", 16f, true, HydriaColors.text).apply { gravity = Gravity.CENTER })
            addView(text(
                "Sélectionnez un ouvrage, un point ou une intervention pour l'ouvrir ici.",
                13f, false, HydriaColors.textSecondary,
            ).apply { gravity = Gravity.CENTER; setPadding(0, dp(8), 0, 0) })
        }, FrameLayout.LayoutParams(-1, -1))
    }

    /**
     * Nombre de colonnes pour une liste de cartes (règle : les cibles ne grandissent
     * pas, c'est la densité qui augmente). 2 colonnes en tablette medium, 1 sinon
     * (téléphone, et volet de 400 dp en EXPANDED).
     */
    private fun paneColumns(): Int = if (windowWidth == WindowWidth.MEDIUM) 2 else 1

    /**
     * Pavé numérique 3×4 intégré (tablette) : chiffres Roboto Mono, cases rayon 13 dp.
     * [onKey] reçoit « 0 »–« 9 » ou « , » ; [onDelete] gère l'effacement.
     */
    private fun numericKeypad(onKey: (String) -> Unit, onDelete: () -> Unit): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            listOf(
                listOf("7", "8", "9"),
                listOf("4", "5", "6"),
                listOf("1", "2", "3"),
                listOf(",", "0", "⌫"),
            ).forEach { row ->
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    row.forEachIndexed { i, key ->
                        addView(Button(this@MainActivity).apply {
                            text = key
                            isAllCaps = false
                            typeface = HydriaType.numeral(600)
                            textSize = 24f
                            setTextColor(if (key == "⌫") HydriaColors.textSecondary else HydriaColors.text)
                            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surface, 13f, HydriaColors.outline)
                            stateListAnimator = null
                            elevation = 0f
                            setPadding(0, 0, 0, 0)
                            setOnClickListener { if (key == "⌫") onDelete() else onKey(key) }
                        }, LinearLayout.LayoutParams(0, dp(56), 1f).apply {
                            if (i < row.size - 1) marginEnd = dp(6)
                        })
                    }
                }, matchWrap(top = 6))
            }
        }

    /** Dépose [views] en lignes de [columns] colonnes de largeur égale dans [root]. */
    private fun addInColumns(root: LinearLayout, views: List<View>, columns: Int, gap: Int = 8) {
        if (columns <= 1) {
            views.forEach { root.addView(it, matchWrap(top = gap)) }
            return
        }
        var i = 0
        while (i < views.size) {
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for (c in 0 until columns) {
                val cell = views.getOrNull(i + c)
                if (cell != null) {
                    line.addView(cell, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                        if (c > 0) marginStart = dp(gap)
                    })
                } else {
                    line.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
                }
            }
            root.addView(line, matchWrap(top = gap))
            i += columns
        }
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        if (store.token.isNullOrBlank()) return
        if (HydriaWindow.of(this) != windowWidth) {
            selectedIds.clear()
            showApplication(initial = false)
        }
    }

    private fun buildNavItem(screen: Screen, label: String, iconRes: Int): NavItem {
        val icon = ImageView(this).apply {
            setImageDrawable(ContextCompat.getDrawable(this@MainActivity, iconRes)?.mutate())
            scaleType = ImageView.ScaleType.FIT_CENTER
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        val badge = TextView(this).apply {
            textSize = 9.5f
            typeface = HydriaType.numeral(700)
            setTextColor(HydriaColors.onAccent)
            gravity = Gravity.CENTER
            minWidth = dp(17)
            minHeight = dp(17)
            setPadding(dp(4), 0, dp(4), 0)
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.error, 9f)
            visibility = View.GONE
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        val iconWrap = FrameLayout(this).apply {
            // Le badge déborde de l'icône (marginEnd négatif) : sans clipChildren=false le parent
            // le rogne et « 99+ » s'affiche « 99 » (REP_PLAN-14).
            clipChildren = false
            addView(icon, FrameLayout.LayoutParams(dp(22), dp(22), Gravity.CENTER))
            addView(badge, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, dp(17), Gravity.TOP or Gravity.END,
            ).apply { marginEnd = dp(-8) })
        }
        val text = TextView(this).apply {
            this.text = label
            textSize = 10.5f
            typeface = HydriaType.display(500)
            gravity = Gravity.CENTER
            includeFontPadding = false
            setPadding(0, dp(4), 0, 0)
        }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            isClickable = true
            isFocusable = true
            clipChildren = false
            setPadding(0, dp(9), 0, dp(9))
            addView(iconWrap, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT,
            ))
            addView(text, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT,
            ))
            setOnClickListener {
                if (screen == Screen.POINTAGE) {
                    HydriaFeedback.tap()
                    openPointage()
                } else if (currentScreen != screen) {
                    HydriaFeedback.tap()
                    currentScreen = screen
                    terrainCategory = null
                    withScreenTransition { renderCurrentScreen() }
                }
            }
        }
        return NavItem(container, icon, text, badge)
    }

    private fun openPointage() {
        startActivity(Intent(this, mg.hydria.app.pointage.PointageActivity::class.java))
    }

    /** Raccourci visible dès l'accueil : prochain créneau à pointer + accès direct à l'écran de pointage. */
    private fun pointageShortcut(): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(dp(14), dp(12), dp(14), dp(12))
        HydriaUi.accentedCard(this, Tone.INFO)
        isClickable = true
        isFocusable = true
        contentDescription = "Ouvrir le pointage GPS"
        setOnClickListener { HydriaFeedback.tap(); openPointage() }
        val pending = mg.hydria.app.pointage.PointageStore.pendingCount(store.accountKey)
        addView(ImageView(this@MainActivity).apply {
            setImageResource(R.drawable.ic_pointage)
            setColorFilter(HydriaColors.cyan)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(dp(26), dp(26)).apply { marginEnd = dp(12) })
        addView(vertical().apply {
            addView(TextView(this@MainActivity).apply {
                text = "Pointer ma position"
                textSize = 15f
                typeface = HydriaType.display(700)
                setTextColor(HydriaColors.text)
            })
            addView(TextView(this@MainActivity).apply {
                text = if (pending > 0) "$pending pointage(s) en attente d'envoi"
                else mg.hydria.app.pointage.PointageRules.libelleFenetres()
                textSize = 12f
                typeface = HydriaType.display(400)
                setTextColor(HydriaColors.textSecondary)
            })
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        addView(TextView(this@MainActivity).apply {
            text = "›"
            textSize = 22f
            setTextColor(HydriaColors.textSecondary)
        })
    }

    private fun updateNavigationState() {
        val repairsBadge = repairsBadgeCount()
        navItems.forEach { (screen, item) ->
            val selected = currentScreen == screen
            val wasSelected = item.container.isSelected
            val accent = if (selected) HydriaColors.cyan else HydriaColors.textSecondary
            item.icon.setColorFilter(accent)
            item.label.setTextColor(accent)
            item.label.typeface = HydriaType.display(if (selected) 600 else 500)
            item.container.background =
                if (selected) HydriaUi.rounded(this, HydriaColors.surfaceRaised, 14f) else null
            item.container.isSelected = selected
            if (selected && !wasSelected) {
                item.container.alpha = 0f
                item.container.animate().alpha(1f).setDuration(140).start()
            }
            val name = item.label.text
            val extra = if (screen == Screen.REPAIRS && repairsBadge > 0) ", $repairsBadge en retard" else ""
            item.container.contentDescription =
                if (selected) "$name, onglet sélectionné$extra" else "$name, onglet$extra"
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                item.container.stateDescription = if (selected) "Sélectionné" else "Non sélectionné"
            }
            if (screen == Screen.REPAIRS) {
                item.badge.visibility = if (repairsBadge > 0) View.VISIBLE else View.GONE
                item.badge.text = if (repairsBadge > 99) "99+" else repairsBadge.toString()
            }
        }
    }

    /** Réparations ÉCHUES (au moins 1 jour de retard), non terminées, dans le périmètre — pas toutes celles à faire. */
    private fun repairsBadgeCount(): Int {
        val repairs = RepairsRepository.list(store) ?: return 0
        val done = RepairRules.pendingCompletionIds(store.pending())
        return jsonObjects(repairs).count { repair ->
            RepairRules.countsOnTabBadge(repair, RepairRules.isCompleted(repair) || repair.optString("id") in done)
        }
    }

    private fun perimeterLabel(): String {
        val terrain = store.snapshot?.optJSONObject("terrain")
        val candidates = listOf(
            terrain?.optString("perimetre_nom"),
            terrain?.optJSONObject("perimetre")?.optString("nom"),
            terrain?.optString("base_nom"),
            store.snapshot?.optString("perimetre_nom"),
        )
        return candidates.firstOrNull { !it.isNullOrBlank() } ?: "v${appVersionName()}"
    }

    private fun synchronize() {
        val token = store.token ?: return
        if (syncing || !isOnline()) {
            updateStatus()
            return
        }
        syncing = true
        updateStatus()
        // Écran de choix de campagne : sa progression du mois ne change que si le snapshot ou la file changent.
        val setupSnapshot = store.snapshot
        val setupPendingCount = store.pendingCount()
        executor.execute {
            val failure = mg.hydria.shared.sync.QueueSyncEngine.run(
                operations = {
                    val pendingBatch = store.pending()
                    // Decode lazily so malformed rows fail at their original position in the batch.
                    Iterable { (0 until pendingBatch.length()).asSequence()
                        .map { pendingBatch.getJSONObject(it) }.iterator() }
                },
                id = { operation: JSONObject -> operation.getString("local_uuid") },
                isVolume = { it.optString("type") == "volume" },
                syncVolume = { operation ->
                    val response = mg.hydria.app.volume.VolumeRepository(store)
                        .syncOne(token, operation.getJSONObject("payload"))
                    mg.hydria.shared.sync.QueueResponse(response.successful, response.status, response.error, response.body)
                },
                markSynchronizing = store::markSynchronizing,
                payload = { it.getJSONObject("payload") },
                send = { operation, payload ->
                    // Relevé refusé par le serveur (HTTP 400, hors conflit) : on le marque pour que le centre de
                    // synchronisation propose « Corriger ». Le marqueur suit le DERNIER envoi : toute autre issue
                    // (succès, 409, 5xx, timeout, coupure) le retire, pour qu'une panne passagère ne passe pas
                    // pour un refus.
                    fun alignRefusalMarker(status: Int) {
                        if (operation.optString("type") != "reading") return
                        val refused = mg.hydria.shared.sync.QueueOverviewRules.isRefusalResponse("reading", status)
                        if (refused == payload.has(mg.hydria.shared.sync.QueueOverviewRules.REFUSED_KEY)) return
                        runCatching {
                            if (refused) payload.put(mg.hydria.shared.sync.QueueOverviewRules.REFUSED_KEY, true)
                            else payload.remove(mg.hydria.shared.sync.QueueOverviewRules.REFUSED_KEY)
                            store.updatePayload(operation.getString("local_uuid"), payload)
                        }
                    }
                    val response = try {
                        SyncDispatch.push(operation.getString("type"), token, payload)
                            ?: HydriaApi.Result(400, JSONObject().put("success", false).put("error", "Action inconnue"))
                    } catch (exception: Exception) {
                        alignRefusalMarker(0) // coupure / timeout : l'engine marque l'échec, ce n'est pas un refus
                        throw exception
                    }
                    if (response.successful && operation.optString("type") in setOf("terrain_data", "terrain_photo")) {
                        runCatching { TerrainRepository.applyServerVersion(store, payload, response.body) }
                        if (response.body.has("points_total")) {
                            store.terrainPoints = response.body.optInt("points_total")
                            pointsGainedInSync += response.body.optInt("points_gagnes")
                        }
                    }
                    alignRefusalMarker(response.status)
                    mg.hydria.shared.sync.QueueResponse(response.successful, response.status, response.error, response.body)
                },
                recordConflict = { operation, payload, body ->
                    payload.put("_sync_conflict", JSONObject(body.toString()))
                    store.updatePayload(operation.getString("local_uuid"), payload)
                    GeoRepository(store).markOperationConflict(operation.getString("type"), payload)
                },
                confirmationError = { operation, payload, body ->
                    validateServerConfirmation(operation.optString("type"), payload, body)
                },
                markSynced = { operation, payload ->
                    GeoRepository(store).markOperationSynced(operation.getString("type"), payload)
                },
                remove = store::remove,
                markFailed = store::markFailed,
                afterQueue = {
                    var refreshFailure: String? = null
                    val currentVersion = store.snapshot?.optString("snapshot_version")
                    val tour = fetchTour(token, currentVersion)
                    if (tour.successful) {
                        if (!tour.body.optBoolean("not_modified", false)) store.snapshot = tour.body
                    } else refreshFailure = tour.error
                    // Rappels de pointage : calendrier des créneaux prévus (échec sans conséquence).
                    runCatching {
                        mg.hydria.app.pointage.PointageReminders.refreshFromServer(applicationContext, token, store.accountKey)
                    }
                    val salaryRepository = SalaryConfigRepository(store, store.accountKey)
                    val salaryResponse = HydriaNetwork.salaryCalculationConfig(token, salaryRepository.checksum())
                    if (salaryResponse.successful) {
                        if (!salaryResponse.body.optBoolean("unchanged", false)) {
                            when (val update = salaryRepository.validateAndActivate(salaryResponse.body.getJSONObject("configuration"))) {
                                is SalaryConfigUpdate.Updated -> store.salaryConfigNotice = ""
                                is SalaryConfigUpdate.Rejected -> store.salaryConfigNotice = update.reason
                            }
                        } else store.salaryConfigNotice = ""
                    } else {
                        store.salaryConfigNotice = if (salaryRepository.current() == null) "sync_required" else "offline_stale"
                    }
                    refreshFailure
                },
            )
            runOnUiThread {
                syncing = false
                if (pointsGainedInSync > 0) {
                    toast("🎉 +$pointsGainedInSync points gagnés !")
                    pointsGainedInSync = 0
                }
                // Saisie de relevé en cours : ne jamais reconstruire l'écran (l'index, la remarque et le point
                // choisi seraient perdus). Le snapshot est déjà à jour dans le store ; l'écran sera reconstruit
                // à la prochaine navigation. Seule la pastille de synchro est rafraîchie.
                val readingInProgress = currentScreen == Screen.READINGS && campaignOuvrageId != null
                // Choix de la campagne en cours (date, ouvrage) : rien à reconstruire si rien n'a changé.
                // Sinon l'écran est refait pour la progression du mois ; la date choisie est reprise de campaignSetupDate.
                val setupUnchanged = currentScreen == Screen.READINGS && campaignOuvrageId == null &&
                    store.snapshot === setupSnapshot && store.pendingCount() == setupPendingCount
                if (!readingInProgress && !setupUnchanged) {
                    // Tablette : reconstruire la coquille pour rafraîchir le badge du rail.
                    if (windowWidth.isTablet && !store.token.isNullOrBlank()) showApplication(initial = false)
                    else renderCurrentScreen()
                }
                updateStatus(failure?.let { "Synchronisation reportée : $it" })
            }
        }
    }

    /**
     * Prechargement de la tournee (GET /plannings/api/preparer-tournee/) : passe
     * par le client Ktor partage (HydriaTerrainGateway) quand le transport
     * Terrain est actif, avec repli HydriaApi (HttpURLConnection) - et extinction
     * du transport Ktor pour toute la session - si l'appel Ktor jette. Une erreur
     * HTTP renvoyee proprement (Result non successful) n'eteint pas le flag.
     * Voir OfflineStore.useNewTerrainNetwork.
     */
    private fun fetchTour(token: String, snapshotVersion: String?): HydriaApi.Result =
        HydriaNetwork.prepareTour(token, snapshotVersion)

    private fun validateServerConfirmation(type: String, payload: JSONObject, body: JSONObject): String? =
        mg.hydria.shared.terrain.TerrainConfirmationGateway.error(type, payload, body)

    private fun renderCurrentScreen() {
        if (!::content.isInitialized) return
        // Formulaire de relevé affiché : la saisie part dans le brouillon AVANT que les vues soient détruites, et
        // le même point est rouvert à la reconstruction (sauf si l'appelant en a désigné un autre).
        readingDraftFlush?.let { flush ->
            val editedPointId = readingCurrentPointId
            runCatching { flush() }
            if (campaignOuvrageId != null && campaignFocusPointId == null) campaignFocusPointId = editedPointId
        }
        readingDraftClose?.let { runCatching { it() } }
        readingDraftFlush = null
        readingDraftClose = null
        readingCurrentPointId = null
        updateNavigationState()
        readingEnrichmentRefresh = null
        readingLocationRefresh = null
        readingFormDirty = null
        content.removeAllViews()
        when (currentScreen) {
            Screen.POINTAGE -> Unit // jamais courant : ouvre PointageActivity
            Screen.TERRAIN -> renderTerrain()
            Screen.READINGS -> renderReadings()
            Screen.REPAIRS -> renderRepairs()
            Screen.PLANNINGS -> renderPlannings()
        }
    }

    /**
     * Applique le bouton "Elargir" de l'ecran Terrain : par defaut, ne garde
     * que les ouvrages marques 'responsable_direct' par le serveur (perimetre
     * propre de l'employe) et les stats 'stats' (deja calculees sur ce
     * sous-ensemble cote serveur) ; si elargi, renvoie le terrain complet
     * (tous les ouvrages autorises) avec 'stats_perimetre_etendu' comme stats.
     */
    private fun terrainForPerimetre(terrain: JSONObject): JSONObject =
        TerrainRules.perimeter(terrain, terrainPerimetreEtendu)

    private fun renderTerrain() {
        val root = vertical(padding = 16).apply { setBackgroundColor(HydriaColors.background) }
        val rawTerrain = store.snapshot?.optJSONObject("terrain")
        if (rawTerrain == null) {
            root.addView(emptyState(
                "Suivi terrain indisponible",
                "Connectez-vous et synchronisez pour charger votre périmètre autorisé."
            ))
            content.addView(scroll(root))
            return
        }
        val terrain = terrainForPerimetre(rawTerrain)
        val perimetreElargiDisponible = rawTerrain.optBoolean("perimetre_elargi_disponible", false)

        val stats = terrain.optJSONObject("stats") ?: JSONObject()
        val completion = stats.optInt("completion_score", 100).coerceIn(0, 100)
        val remaining = TerrainRules.remainingTasks(stats)

        // ── Carte de complétude du périmètre ──
        val completionCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(16))
            HydriaUi.card(this)
        }
        completionCard.addView(HydriaUi.overline(this, if (terrainPerimetreEtendu) "COMPLÉTUDE — SECTEUR ÉLARGI" else "COMPLÉTUDE DE MON PÉRIMÈTRE"))
        completionCard.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.BOTTOM
            addView(TextView(this@MainActivity).apply {
                text = completion.toString()
                typeface = HydriaType.numeral(700)
                textSize = 44f
                letterSpacing = -0.03f
                setTextColor(HydriaColors.text)
                includeFontPadding = false
            })
            addView(TextView(this@MainActivity).apply {
                text = "%"
                typeface = HydriaType.display(600)
                textSize = 20f
                setTextColor(HydriaColors.cyan)
                includeFontPadding = false
                setPadding(dp(3), 0, 0, dp(6))
            })
            addView(TextView(this@MainActivity).apply {
                text = if (remaining > 0) "$remaining tâche${if (remaining > 1) "s" else ""} restante${if (remaining > 1) "s" else ""}" else "Périmètre complet"
                typeface = HydriaType.display(500)
                textSize = 12.5f
                setTextColor(if (remaining > 0) HydriaColors.textSecondary else HydriaColors.success)
                gravity = Gravity.END or Gravity.BOTTOM
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { bottomMargin = dp(6) })
        }, matchWrap(top = 6))
        completionCard.addView(HydriaUi.progressBar(this, completion), matchWrap(10, top = 12))
        completionCard.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(terrainCounter("${stats.optInt("total_ouvrages")} ouvrages"))
            addView(terrainCounter("${stats.optInt("total_points_eau")} points"))
            addView(terrainCounter("${stats.optInt("total_equipements")} équip."))
        }, matchWrap(top = 12))
        root.addView(completionCard, matchWrap(top = 4))
        root.addView(terrainPointsCard(), matchWrap(top = 10))

        if (perimetreElargiDisponible || terrainPerimetreEtendu) {
            root.addView(card().apply {
                addView(SwitchCompat(this@MainActivity).apply {
                    text = "Afficher tout le secteur (au-delà de mon périmètre)"
                    setTextColor(HydriaColors.text)
                    textSize = 14f
                    isChecked = terrainPerimetreEtendu
                    setOnCheckedChangeListener { _, checked ->
                        HydriaFeedback.tap()
                        terrainPerimetreEtendu = checked
                        renderCurrentScreen()
                    }
                }, matchWrap())
            }, matchWrap(top = 10))
        }

        // ── Rangée de filtres ──
        val filters = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        filters.addView(TextView(this).apply {
            text = "À compléter"
            typeface = HydriaType.display(600)
            textSize = 15f
            setTextColor(HydriaColors.text)
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        listOf("todo" to "Tout", "works" to "Par ouvrage", "nearby" to "Autour").forEach { (id, label) ->
            // Hauteur libre : la puce mesure 48 dp (zone tactile), sa pastille visible 34 dp.
            filters.addView(HydriaUi.chip(this, label, terrainMode == id && terrainCategory == null).apply {
                setOnClickListener { terrainMode = id; terrainCategory = null; terrainOpenWorkId = null; renderCurrentScreen() }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(8) })
        }
        root.addView(filters, matchWrap(top = 12))

        val twoPane = windowWidth.isTwoPane && detailPane != null
        var taskAction: View? = null
        when {
            // En téléphone (ou tablette medium), la liste de catégorie remplace l'écran.
            !twoPane && terrainCategory != null -> taskAction = renderTerrainTaskList(root, terrain, terrainCategory!!)
            terrainMode == "works" && terrainOpenWorkId != null &&
                (terrain.optJSONArray("ouvrages")?.let { arr -> (0 until arr.length()).any { arr.getJSONObject(it).optString("id") == terrainOpenWorkId } } == true) ->
                renderTerrainWorkDetail(root, terrain, terrainOpenWorkId!!)
            terrainMode == "works" -> renderTerrainWorks(root, terrain.optJSONArray("ouvrages") ?: JSONArray())
            terrainMode == "nearby" -> renderTerrainNearby(root, terrain)
            else -> renderTerrainTodo(root, terrain, stats)
        }
        // Mesures rapides toujours visibles, quel que soit le défilement (sauf dans une
        // liste de tâches, qui a déjà sa propre action en bas).
        if (taskAction == null) taskAction = terrainMeasureBar(terrain)
        content.addView(terrainTaskPage(root, taskAction))

        // EXPANDED : la liste de la catégorie sélectionnée remplit le volet de droite.
        if (twoPane) {
            val pane = detailPane!!
            pane.removeAllViews()
            val detailRoot = vertical(padding = 16).apply { setBackgroundColor(HydriaColors.background) }
            val category = terrainCategory
            var detailAction: View? = null
            if (category != null) {
                detailRoot.addView(LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(HydriaUi.overline(this@MainActivity, "À COMPLÉTER"),
                        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                    addView(Button(this@MainActivity).apply {
                        text = "Fermer"
                        HydriaUi.secondaryButton(this)
                        setOnClickListener { terrainCategory = null; renderCurrentScreen() }
                    }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(40)))
                }, matchWrap())
                detailAction = renderTerrainTaskList(detailRoot, terrain, category)
            } else {
                detailRoot.gravity = Gravity.CENTER
                detailRoot.addView(text("Choisissez une tâche à gauche pour la traiter ici.",
                    13f, false, HydriaColors.textSecondary).apply { gravity = Gravity.CENTER })
            }
            pane.addView(terrainTaskPage(detailRoot, detailAction))
        }
    }

    /** Somme des informations terrain restant à compléter (surtitre de la carte). */
    private fun terrainCounter(value: String): View = TextView(this).apply {
        text = value
        typeface = HydriaType.numeral(600)
        textSize = 13f
        setTextColor(HydriaColors.textSecondary)
        setPadding(0, 0, dp(16), 0)
    }

    private data class TerrainTaskDef(val key: String, val title: String, val subtitle: String, val statKey: String, val tone: Tone)

    /** « Débit source » / « Compteur de tête », fixés en bas de l'écran Terrain (hors défilement). */
    private fun terrainMeasureBar(terrain: JSONObject): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        addView(secondaryButton("Débit source").apply {
            textSize = 12f
            setOnClickListener { showFlowMeasurementForm(terrain) }
        }, weighted().apply { marginEnd = dp(4) })
        addView(secondaryButton("Consulter débits").apply {
            textSize = 12f
            setOnClickListener { showFlowHistory(terrain) }
        }, weighted().apply { marginStart = dp(4); marginEnd = dp(4) })
        addView(secondaryButton("Compteur de tête").apply {
            textSize = 12f
            setOnClickListener { showHeadMeterForm(terrain) }
        }, weighted().apply { marginStart = dp(4) })
    }

    private fun renderTerrainTodo(root: LinearLayout, terrain: JSONObject, stats: JSONObject) {
        val defs = listOf(
            TerrainTaskDef("flow_overdue", "Mesures de débit en retard", "Échéance de mesure dépassée", "captages_mesure_en_retard", Tone.ERROR),
            TerrainTaskDef("flow_none", "Captages sans mesure", "Débit source jamais relevé", "captages_sans_mesure", Tone.WARNING),
            TerrainTaskDef("gps", "Coordonnées à compléter", "Points d'eau sans position GPS", "points_sans_coordonnees", Tone.WARNING),
            TerrainTaskDef("subscriber", "Noms d'abonnés à renseigner", "Fiches sans nom d'abonné", "points_sans_nom_abonne", Tone.WARNING),
            TerrainTaskDef("point_photo", "Photos de points manquantes", "Prises de vue à enchaîner", "points_sans_photo", Tone.WARNING),
            TerrainTaskDef("equipment_photo", "Photos d'équipements manquantes", "Équipements sans photo", "equipements_sans_photo", Tone.WARNING),
        )
        val rows = defs.map { def ->
            val count = stats.optInt(def.statKey).coerceAtLeast(0)
            val onClick: (() -> Unit)? =
                if (count > 0) ({ terrainCategory = def.key; renderCurrentScreen() }) else null
            HydriaUi.taskRow(
                this, count, def.title,
                if (count > 0) def.subtitle else "Terminé",
                def.tone, onClick,
            )
        }
        addInColumns(root, rows, paneColumns())
    }

    private fun renderTerrainWorks(root: LinearLayout, works: JSONArray) {
        root.addView(text("Complétude par ouvrage", 18f, true, HydriaColors.text), matchWrap(top = 20))
        val workSearch = field("Rechercher un ouvrage (nom ou code)").apply {
            setSingleLine(true)
            setText(terrainWorkQuery)
        }
        root.addView(workSearch, matchWrap(52, top = 10))
        val workList = vertical()
        root.addView(workList, matchWrap())
        val workRows = mutableListOf<Pair<View, String>>()
        for (index in 0 until works.length()) {
            val work = works.getJSONObject(index)
            val workStats = work.optJSONObject("stats") ?: JSONObject()
            val details = listOf(
                workStats.optInt("points_sans_coordonnees") to "GPS",
                workStats.optInt("points_sans_nom_abonne") to "nom(s)",
                workStats.optInt("points_sans_photo") to "photo(s) PE",
                workStats.optInt("equipements_sans_photo") to "photo(s) équipement",
                (workStats.optInt("captages_sans_mesure") + workStats.optInt("captages_mesure_en_retard")) to "débit(s)",
            ).filter { it.first > 0 }.joinToString(" · ") { "${it.first} ${it.second}" }
            val workCard = card().apply {
                val completion = work.optInt("completion_score", 100).coerceIn(0, 100)
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(text(work.optString("nom"), 16f, true, HydriaColors.text), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                    addView(HydriaUi.badge(this@MainActivity, "$completion %", if (completion == 100) Tone.SUCCESS else Tone.INFO), wrapWrap())
                })
                val ageYears = TerrainRules.ouvrageAgeYears(work)
                addView(text(
                    if (ageYears != null) "Âge de l’ouvrage : $ageYears an${if (ageYears > 1) "s" else ""}"
                    else "Âge de l’ouvrage non renseigné",
                    12f, false, HydriaColors.textSecondary
                ))
                addView(text(details.ifBlank { "Toutes les données attendues sont complètes" }, 12f, false, HydriaColors.textSecondary), matchWrap(top = 5))
                val history = work.optJSONArray("debits_source_recents") ?: JSONArray()
                val flowValues = (0 until history.length()).map { history.optJSONObject(it)?.optDouble("debit_l_s") ?: 0.0 }.reversed()
                if (flowValues.size >= 2) {
                    addView(text("Débit récent", 11f, true, HydriaColors.textSecondary), matchWrap(top = 10))
                    addView(SparklineView(this@MainActivity).apply { values = flowValues }, matchWrap(58, top = 4))
                }
                setOnClickListener {
                    terrainOpenWorkId = work.optString("id")
                    terrainItemQuery = ""
                    renderCurrentScreen()
                }
            }
            workRows.add(workCard to "${work.optString("nom")} ${work.optString("code")}")
            workList.addView(workCard, matchWrap(top = 8))
        }
        val noWork = emptyState("Aucun ouvrage", "Essayez un autre nom ou code d'ouvrage.")
        root.addView(noWork, matchWrap(top = 12))
        fun filterWorks() {
            terrainWorkQuery = workSearch.text.toString()
            val terms = normalizeSearch(terrainWorkQuery).split(Regex("\\s+")).filter { it.isNotBlank() }
            var visible = 0
            workRows.forEach { (row, label) ->
                val show = terms.all { normalizeSearch(label).contains(it) }
                row.visibility = if (show) View.VISIBLE else View.GONE
                if (show) visible++
            }
            noWork.visibility = if (visible == 0) View.VISIBLE else View.GONE
        }
        workSearch.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { filterWorks() }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        filterWorks()
    }

    private fun normalizeSearch(value: String): String = java.text.Normalizer.normalize(
        value, java.text.Normalizer.Form.NFD,
    ).replace(Regex("\\p{M}+"), "").lowercase(Locale.ROOT).trim()

    /** Action directe sur une fiche (point d'eau ou équipement), sans passer par la liste « À compléter ». */
    private fun startTerrainItemAction(item: JSONObject, work: JSONObject, category: String) {
        when (category) {
            "subscriber" -> showSubscriberForm(item, work)
            "gps" -> {
                pendingTerrainItem = item
                pendingTerrainWork = work
                pendingTerrainCategory = category
                capturePointLocation(item.getString("id"))
            }
            "point_photo", "equipment_photo" -> choosePhotoSource(item, work, category)
            "equipment_gps" -> captureEquipmentGps(item, work)
        }
    }

    /** Photo : appareil photo, ou image déjà enregistrée sur le téléphone. */
    private fun choosePhotoSource(item: JSONObject, work: JSONObject, category: String) {
        val title = item.optString("code").ifBlank { item.optString("nom") }
        AlertDialog.Builder(this)
            .setTitle(title)
            .setItems(arrayOf("Prendre une photo", "Choisir dans la galerie")) { _, which ->
                pendingTerrainItem = item
                pendingTerrainWork = work
                pendingTerrainCategory = category
                if (which == 0) capturePointPhoto(item.getString("id"))
                else {
                    pendingPhotoPointId = item.getString("id")
                    pointGalleryLauncher.launch("image/*")
                }
            }
            .setNegativeButton("Annuler", null)
            .show()
    }

    /** Fiche d'un ouvrage : points d'eau (GPS, abonné + téléphone, photo) et équipements (photo). */
    private fun renderTerrainWorkDetail(root: LinearLayout, terrain: JSONObject, workId: String) {
        val works = terrain.optJSONArray("ouvrages") ?: JSONArray()
        val work = (0 until works.length()).map { works.getJSONObject(it) }.first { it.optString("id") == workId }
        root.addView(secondaryButton("← Tous les ouvrages").apply {
            setOnClickListener { terrainOpenWorkId = null; terrainItemQuery = ""; renderCurrentScreen() }
        }, matchWrap(48, top = 14))
        root.addView(text(work.optString("nom"), 20f, true, HydriaColors.text), matchWrap(top = 10))
        root.addView(text("${work.optInt("completion_score", 100)} % complet · ${TerrainRules.ouvrageAgeLabel(work)}",
            12f, false, HydriaColors.textSecondary))
        if (work.optBoolean("debit_source_applicable")) {
            root.addView(secondaryButton("Mesurer le débit").apply {
                setOnClickListener { showFlowMeasurementForm(terrain, workId) }
            }, matchWrap(48, top = 10))
            root.addView(secondaryButton("Consulter les débits et la criticité").apply {
                setOnClickListener { showFlowHistory(terrain, workId) }
            }, matchWrap(48, top = 8))
        }
        val search = field("Rechercher un point d'eau, un abonné ou un équipement").apply {
            setSingleLine(true)
            setText(terrainItemQuery)
        }
        root.addView(search, matchWrap(52, top = 12))
        val list = vertical()
        root.addView(list, matchWrap())

        fun statusButton(label: String, done: Boolean, action: () -> Unit) = Button(this).apply {
            text = if (done) "✓ $label" else label
            textSize = 12f
            isAllCaps = false
            if (done) HydriaUi.secondaryButton(this) else HydriaUi.primaryButton(this, HydriaColors.cyan)
            setOnClickListener { action() }
        }
        val rows = mutableListOf<Pair<View, String>>()
        val points = work.optJSONArray("points_eau") ?: JSONArray()
        val equipments = work.optJSONArray("equipements") ?: JSONArray()
        list.addView(text("Points d'eau (${points.length()})", 16f, true, HydriaColors.text), matchWrap(top = 16))
        // Ordre numérique de l'idxls (2 avant 10) ; sans idxls : à la fin.
        val sortedPoints = ReadingPointListRules.sortedByIdxls(jsonObjects(points), 2)
        for (point in sortedPoints) {
            val idxls = point.optString("idxls").trim()
            val title = (if (idxls.isNotEmpty()) "$idxls · " else "") +
                point.optString("code").ifBlank { point.optString("nom") }
            val subscriber = if (point.optBoolean("has_subscriber_name")) point.optString("nom") else "Nom d'abonné manquant"
            val phone = point.optString("telephone")
            val card = card().apply {
                addView(text(title, 16f, true, HydriaColors.text))
                addView(text(listOf(point.optString("type"), subscriber, phone).filter { it.isNotBlank() }.joinToString(" · "),
                    12f, false, HydriaColors.textSecondary))
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    addView(statusButton("GPS", point.optBoolean("has_coordinates")) { startTerrainItemAction(point, work, "gps") },
                        LinearLayout.LayoutParams(0, dp(44), 1f).apply { marginEnd = dp(4) })
                    addView(statusButton("Abonné", point.optBoolean("has_subscriber_name")) { startTerrainItemAction(point, work, "subscriber") },
                        LinearLayout.LayoutParams(0, dp(44), 1f).apply { marginEnd = dp(4) })
                    addView(statusButton("Photo", point.optBoolean("has_photo")) { startTerrainItemAction(point, work, "point_photo") },
                        LinearLayout.LayoutParams(0, dp(44), 1f))
                }, matchWrap(top = 10))
            }
            rows.add(card to "$title ${point.optString("nom")} ${point.optString("telephone")} ${point.optString("subscriber_name")}")
            list.addView(card, matchWrap(top = 8))
        }
        list.addView(text("Équipements (${equipments.length()})", 16f, true, HydriaColors.text), matchWrap(top = 20))
        for (i in 0 until equipments.length()) {
            val equipment = equipments.getJSONObject(i)
            val card = card().apply {
                addView(text(equipment.optString("nom"), 16f, true, HydriaColors.text))
                addView(text(equipment.optString("type").ifBlank { "Équipement" }, 12f, false, HydriaColors.textSecondary))
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    addView(statusButton("GPS", equipment.optBoolean("has_coordinates")) { startTerrainItemAction(equipment, work, "equipment_gps") },
                        LinearLayout.LayoutParams(0, dp(44), 1f).apply { marginEnd = dp(4) })
                    addView(statusButton("Photo", equipment.optBoolean("has_photo")) { startTerrainItemAction(equipment, work, "equipment_photo") },
                        LinearLayout.LayoutParams(0, dp(44), 1f))
                }, matchWrap(top = 10))
            }
            rows.add(card to "${equipment.optString("nom")} ${equipment.optString("type")}")
            list.addView(card, matchWrap(top = 8))
        }
        if (points.length() == 0 && equipments.length() == 0) {
            list.addView(emptyState("Aucune fiche", "Cet ouvrage n'a ni point d'eau ni équipement dans votre périmètre."))
        }
        fun filterItems() {
            terrainItemQuery = search.text.toString()
            val terms = normalizeSearch(terrainItemQuery).split(Regex("\\s+")).filter { it.isNotBlank() }
            rows.forEach { (row, label) ->
                row.visibility = if (terms.all { normalizeSearch(label).contains(it) }) View.VISIBLE else View.GONE
            }
        }
        search.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { filterItems() }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        filterItems()
    }

    private fun showFlowMeasurementForm(
        terrain: JSONObject,
        selectedWorkId: String? = null,
        onSaved: (() -> Unit)? = null,
    ) {
        val works = terrain.optJSONArray("ouvrages") ?: JSONArray()
        val sources = (0 until works.length()).map { works.getJSONObject(it) }
            .filter { it.optBoolean("debit_source_applicable") }
            // Une mesure en serie reste rattachee au captage selectionne.
            .filter { onSaved == null || it.optString("id") == selectedWorkId }
        if (sources.isEmpty()) {
            toast("Aucun captage autorisé dans votre périmètre.")
            return
        }
        val form = vertical(padding = 16)
        val workPicker = HydriaAutocomplete(this, sources.map { it.optString("nom") })
        val wantedIndex = selectedWorkId?.let { wantedId -> sources.indexOfFirst { it.optString("id") == wantedId } } ?: -1
        workPicker.select(if (wantedIndex >= 0) wantedIndex else if (sources.size == 1) 0 else -1)
        // Date au sélecteur (JJ/MM/AAAA, aujourd'hui à Madagascar par défaut, pas de date future) : plus de saisie ISO au clavier.
        val dateField = HydriaUi.dateField(this, null)
        val direct = field("Débit direct (L/s)").apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL }
        val volume = field("Volume mesuré (litres)").apply { inputType = direct.inputType }
        val duration = field("Temps (secondes)").apply { inputType = direct.inputType }
        val remark = field("Remarque")
        val directMode = RadioButton(this).apply {
            text = "Débit direct"
            id = View.generateViewId()
            isChecked = true
        }
        val timedMode = RadioButton(this).apply {
            text = "Volume + temps"
            id = View.generateViewId()
        }
        val measurementMode = RadioGroup(this).apply {
            orientation = RadioGroup.HORIZONTAL
            addView(directMode, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(timedMode, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        }
        fun applyMeasurementMode(useDirect: Boolean) {
            direct.isEnabled = useDirect
            direct.alpha = if (useDirect) 1f else 0.45f
            volume.isEnabled = !useDirect
            duration.isEnabled = !useDirect
            volume.alpha = if (useDirect) 0.45f else 1f
            duration.alpha = if (useDirect) 0.45f else 1f
            if (useDirect) {
                volume.text.clear()
                duration.text.clear()
            } else direct.text.clear()
        }
        measurementMode.setOnCheckedChangeListener { _, checkedId ->
            applyMeasurementMode(checkedId == directMode.id)
        }
        applyMeasurementMode(true)
        form.addView(workPicker, matchWrap(56))
        form.addView(label("Date de la mesure"))
        form.addView(dateField, matchWrap(52))
        form.addView(text("Choisissez une seule méthode de mesure.", 12f, false, HydriaColors.textSecondary), matchWrap(top = 8))
        form.addView(measurementMode, matchWrap(top = 4))
        form.addView(direct, matchWrap(52, top = 6))
        form.addView(volume, matchWrap(52, top = 6))
        form.addView(duration, matchWrap(52, top = 6))
        form.addView(remark, matchWrap(52, top = 6))
        val dialog = AlertDialog.Builder(this).setTitle("Mesure du débit source")
            .setView(form).setNegativeButton("Annuler", null).setPositiveButton("Calculer", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val work = sources.getOrNull(workPicker.selectedIndex) ?: run {
                    workPicker.error = "Choisissez un ouvrage dans la liste"
                    return@setOnClickListener
                }
                val measurementDate = LocalDate.parse(dateField.iso)
                val directValue = direct.text.toString().replace(',', '.').toDoubleOrNull()
                val volumeValue = volume.text.toString().replace(',', '.').toDoubleOrNull()
                val durationValue = duration.text.toString().replace(',', '.').toDoubleOrNull()
                val useDirect = measurementMode.checkedRadioButtonId == directMode.id
                val flow = if (useDirect) directValue else if (volumeValue != null && durationValue != null) {
                    runCatching { TerrainMeasurementEngine.flowFromVolume(volumeValue, durationValue) }.getOrNull()
                } else null
                if (flow == null || flow < 0) {
                    toast("Renseignez un débit, ou un volume avec un temps supérieur à zéro.")
                    return@setOnClickListener
                }
                val history = work.optJSONArray("debits_source_recents") ?: JSONArray()
                val recentValues = (0 until history.length()).map { history.getJSONObject(it).optDouble("debit_l_s") }
                val analysis = TerrainMeasurementEngine.trend(flow, recentValues)
                val summary = buildString {
                    append("Débit actuel : ${formatDecimal(flow, 3)} L/s")
                    analysis.previous?.let { append("\nDébit précédent : ${formatDecimal(it, 3)} L/s") }
                    analysis.variationPercent?.let { append("\nVariation : ${formatDecimal(it, 1)} %") }
                    append("\nMoyenne récente : ${formatDecimal(analysis.recentAverage, 3)} L/s\n\n${analysis.trend}")
                }
                AlertDialog.Builder(this).setTitle("Résultat immédiat").setMessage(summary)
                    .setNegativeButton("Corriger", null)
                    .setPositiveButton("Enregistrer offline") { _, _ ->
                        store.enqueue("terrain_data", JSONObject()
                            .put("operation_type", "flow_measure")
                            .put("ouvrage_id", work.getString("id"))
                            .put("date", measurementDate.toString())
                            .put("debit_l_s", flow)
                            .put("remarque", remark.text.toString().trim()))
                        TerrainRepository.applyLocalFlowMeasurement(store, work.getString("id"), measurementDate.toString(), flow)
                        updateStatus()
                        dialog.dismiss()
                        toast("Mesure enregistrée hors ligne.")
                        if (onSaved != null) onSaved() else renderCurrentScreen()
                        if (isOnline()) synchronize()
                    }.show()
            }
        }
        dialog.show()
    }

    /** Points qu'une saisie en attente rapportera au maximum (le serveur ne paie que les champs vides). */
    private fun pendingPotentialPoints(): Int {
        val pending = store.pending()
        var total = 0
        for (i in 0 until pending.length()) {
            val item = pending.getJSONObject(i)
            val payload = item.optJSONObject("payload") ?: continue
            when (item.optString("type")) {
                "terrain_photo" -> total += 10
                "terrain_data" -> {
                    if (payload.optString("operation_type") !in setOf("update_point", "update_equipment")) continue
                    if (payload.has("latitude")) total += 10
                    if (payload.has("subscriber_name")) total += 5
                    if (payload.has("telephone")) total += 5
                }
            }
        }
        return total
    }

    /** Compteur de points qui défile jusqu'au total courant, avec rang et accès au classement. */
    private fun terrainPointsCard(): View {
        val counter = TextView(this).apply {
            typeface = HydriaType.numeral(700)
            textSize = 34f
            setTextColor(HydriaColors.vase)
            includeFontPadding = false
        }
        val detail = TextView(this).apply {
            textSize = 12f
            typeface = HydriaType.display(500)
            setTextColor(HydriaColors.textSecondary)
        }
        fun refreshDetail() {
            val waiting = pendingPotentialPoints()
            detail.text = listOfNotNull(
                store.terrainRank.takeIf { it > 0 }?.let { "Rang n°$it" },
                waiting.takeIf { it > 0 }?.let { "jusqu'à +$it en attente" },
                "photo, GPS = 10 pts · nom, téléphone = 5 pts",
            ).joinToString(" · ")
        }
        refreshDetail()
        val target = store.terrainPoints
        val from = store.terrainPointsShown.coerceAtMost(target)
        counter.text = formatNumber(from.toDouble())
        if (from != target) {
            android.animation.ValueAnimator.ofInt(from, target).apply {
                duration = 900
                addUpdateListener { counter.text = formatNumber((it.animatedValue as Int).toDouble()) }
                start()
            }
            store.terrainPointsShown = target
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(12))
            HydriaUi.card(this)
            isClickable = true
            contentDescription = "Ouvrir le classement des contributeurs"
            setOnClickListener { HydriaFeedback.tap(); showLeaderboard() }
        }
        box.addView(TextView(this).apply { text = "⭐"; textSize = 26f }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(12) })
        box.addView(vertical().apply {
            addView(HydriaUi.overline(this@MainActivity, "MES POINTS TERRAIN"))
            addView(counter)
            addView(detail)
        }, LinearLayout.LayoutParams(0, -2, 1f))
        box.addView(TextView(this).apply { text = "Classement ›"; textSize = 13f; setTextColor(HydriaColors.cyan); typeface = HydriaType.display(600) })

        // Rafraîchit en arrière-plan (au plus une fois par minute) : le compteur défile jusqu'à la vraie valeur.
        val token = store.token
        if (token != null && isOnline() && System.currentTimeMillis() - pointsRefreshedAt > 60_000) {
            pointsRefreshedAt = System.currentTimeMillis()
            executor.execute {
                val result = runCatching { HydriaApi.terrainRanking(token, "absolu") }.getOrNull()
                if (result != null && result.successful) {
                    val me = result.body.optJSONObject("moi")
                    runOnUiThread {
                        val total = me?.optInt("points_total", store.terrainPoints) ?: store.terrainPoints
                        store.terrainRank = me?.optInt("rang", 0) ?: 0
                        val shown = store.terrainPointsShown
                        store.terrainPoints = total
                        if (total != shown) {
                            android.animation.ValueAnimator.ofInt(shown, total).apply {
                                duration = 900
                                addUpdateListener { counter.text = formatNumber((it.animatedValue as Int).toDouble()) }
                                start()
                            }
                            store.terrainPointsShown = total
                        }
                        refreshDetail()
                    }
                }
            }
        }
        return box
    }

    /** Classement des contributeurs : absolu / mensuel / hebdomadaire / journalier, avec évolution. */
    private fun showLeaderboard() {
        val token = store.token ?: return
        val periods = listOf("absolu" to "Absolu", "mois" to "Mois", "semaine" to "Semaine", "jour" to "Jour")
        val form = vertical(padding = 16)
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val body = vertical()
        form.addView(chips, matchWrap())
        form.addView(body, matchWrap(top = 10))

        fun render(result: HydriaApi.Result) {
            body.removeAllViews()
            if (!result.successful) {
                body.addView(text(result.error, 13f, false, HydriaColors.error))
                return
            }
            val data = result.body
            val me = data.optJSONObject("moi")
            body.addView(text(
                "${me?.optInt("points_periode") ?: 0} pts sur la période · rang " +
                    (me?.takeIf { !it.isNull("rang") }?.optInt("rang")?.let { "n°$it / ${data.optInt("participants")}" } ?: "—") +
                    " · aujourd'hui +${me?.optInt("points_aujourdhui") ?: 0}",
                13f, true, HydriaColors.cyan))
            val evolution = data.optJSONObject("evolution")
            val series = jsonObjects(evolution?.optJSONArray("series") ?: JSONArray()).map { s ->
                HydriaTrendChartView.Series(
                    s.optString("nom"),
                    (0 until (s.optJSONArray("points")?.length() ?: 0)).map { s.getJSONArray("points").optInt(it) },
                    s.optBoolean("moi"))
            }
            val labels = (0 until (evolution?.optJSONArray("labels")?.length() ?: 0)).map { evolution!!.getJSONArray("labels").optString(it) }
            if (series.isNotEmpty() && labels.isNotEmpty()) {
                body.addView(text("Évolution (3 premiers + moi)", 13f, true, HydriaColors.text), matchWrap(top = 12))
                body.addView(HydriaTrendChartView(this).apply { setData(labels, series) }, matchWrap(190, top = 4))
            }
            body.addView(text("Classement", 15f, true, HydriaColors.text), matchWrap(top = 12))
            val ranking = jsonObjects(data.optJSONArray("classement") ?: JSONArray())
            if (ranking.isEmpty()) body.addView(text("Personne n'a encore marqué de points sur cette période. Soyez le premier !", 12.5f, false, HydriaColors.textSecondary))
            ranking.forEach { row ->
                val rank = row.optInt("rang")
                val medal = when (rank) { 1 -> "🥇"; 2 -> "🥈"; 3 -> "🥉"; else -> "$rank." }
                val mine = row.optBoolean("moi")
                body.addView(text("$medal  ${row.optString("nom")}${if (mine) "  (moi)" else ""}  —  ${formatNumber(row.optDouble("points"))} pts",
                    14f, mine, if (mine) HydriaColors.cyan else HydriaColors.text), matchWrap(top = 6))
            }
        }
        fun load(period: String) {
            chips.removeAllViews()
            periods.forEach { (id, label) ->
                chips.addView(HydriaUi.chip(this, label, id == period).apply {
                    setOnClickListener { load(id) }
                }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
            }
            body.removeAllViews()
            body.addView(text("Chargement…", 13f, false, HydriaColors.textSecondary))
            if (!isOnline()) {
                body.removeAllViews()
                body.addView(text("Connexion requise pour afficher le classement.", 13f, false, HydriaColors.error))
                return
            }
            executor.execute {
                val result = runCatching { HydriaApi.terrainRanking(token, period) }
                runOnUiThread {
                    result.onSuccess { render(it) }.onFailure {
                        body.removeAllViews()
                        body.addView(text("Impossible de charger le classement.", 13f, false, HydriaColors.error))
                    }
                }
            }
        }
        load("absolu")
        AlertDialog.Builder(this).setTitle("🏆 Classement Terrain")
            .setView(ScrollView(this).apply { addView(form) })
            .setPositiveButton("Fermer", null).show()
    }

    /**
     * Consultation des débits d'un ouvrage choisi : niveau de criticité, seuil, historique
     * (mêmes calculs que la page web /plannings/debits-source/, via l'API mobile).
     */
    private fun showFlowHistory(terrain: JSONObject, selectedWorkId: String? = null) {
        val works = terrain.optJSONArray("ouvrages") ?: JSONArray()
        val sources = jsonObjects(works).filter { it.optBoolean("debit_source_applicable") }
        if (sources.isEmpty()) {
            toast("Aucun captage autorisé dans votre périmètre.")
            return
        }
        val form = vertical(padding = 16)
        val picker = HydriaAutocomplete(this, sources.map { it.optString("nom") })
        val body = vertical()
        form.addView(picker, matchWrap(56))
        form.addView(body, matchWrap(top = 10))

        fun levelText(level: String) = when (level) {
            "critique" -> "🔴 CRITIQUE"
            "vigilance" -> "🟠 Vigilance"
            "normal" -> "🟢 Normal"
            else -> "⚪ Aucune mesure"
        }
        fun levelColor(level: String) = when (level) {
            "critique" -> HydriaColors.error
            "vigilance" -> HydriaColors.warning
            else -> HydriaColors.text
        }
        fun statusText(status: String) = when (status) {
            "critique" -> "sous le seuil"
            "surveille" -> "à surveiller"
            "baisse" -> "en baisse"
            "hausse" -> "en hausse"
            "stable" -> "stable"
            "normal" -> "normal"
            else -> ""
        }
        fun show(result: HydriaApi.Result) {
            body.removeAllViews()
            if (!result.successful) {
                body.addView(text(result.error, 13f, false, HydriaColors.error))
                return
            }
            val data = result.body
            val level = data.optString("niveau")
            body.addView(text(levelText(level), 18f, true, levelColor(level)))
            if (!data.isNull("ratio_pct")) {
                body.addView(text("${data.optInt("ratio_pct")} % du seuil", 12.5f, false, HydriaColors.textSecondary))
            }
            if (!data.isNull("seuil_l_s")) {
                val mode = if (data.optString("mode_paiement") == "forfaitaire") "forfaitaire" else "volumétrique"
                body.addView(text("Seuil minimum : ${formatDecimal(data.optDouble("seuil_l_s"), 3)} L/s ($mode)",
                    13f, true, HydriaColors.text), matchWrap(top = 8))
            }
            data.optString("comparatif").takeIf { it.isNotBlank() }?.let {
                body.addView(text(it, 12f, false, HydriaColors.textSecondary))
            }
            if (!data.isNull("dernier_debit_l_s")) {
                body.addView(text("Dernier débit : ${formatDecimal(data.optDouble("dernier_debit_l_s"), 3)} L/s", 13f, false, HydriaColors.text), matchWrap(top = 6))
            }
            if (!data.isNull("plus_bas_debit_l_s")) {
                body.addView(text("Plus bas relevé : ${formatDecimal(data.optDouble("plus_bas_debit_l_s"), 3)} L/s", 13f, false, HydriaColors.text))
            }
            val measures = jsonObjects(data.optJSONArray("mesures") ?: JSONArray())
            val threshold = if (data.isNull("seuil_l_s")) null else data.optDouble("seuil_l_s")
            val valued = measures.filter { !it.isNull("debit_l_s") }
            if (valued.isNotEmpty()) {
                val chart = HydriaFlowChartView(this).apply {
                    setData(valued.reversed().map {
                        HydriaFlowChartView.Point(displayIsoDate(it.optString("date_visite")).take(5), it.optDouble("debit_l_s"))
                    }, threshold)
                }
                body.addView(chart, matchWrap(180, top = 12))
                // Analyse de comparaison avec le seuil (mêmes critères que la page web).
                if (threshold != null && threshold > 0) {
                    val below = valued.count { it.optDouble("debit_l_s") < threshold }
                    val last = valued.first().optDouble("debit_l_s")
                    val trend = valued.getOrNull(1)?.let { last - it.optDouble("debit_l_s") }
                    body.addView(text(buildString {
                        append("$below mesure(s) sous le seuil sur ${valued.size}. ")
                        append("Dernier débit à ${(last / threshold * 100).toInt()} % du seuil")
                        if (trend != null) append(if (trend < 0) ", en baisse depuis la mesure précédente." else if (trend > 0) ", en hausse depuis la mesure précédente." else ", stable.")
                        else append(".")
                        data.optString("interpretation").takeIf { it.isNotBlank() }?.let { append("\n$it") }
                    }, 12.5f, false, if (last < threshold) HydriaColors.error else HydriaColors.textSecondary), matchWrap(top = 6))
                }
            }
            body.addView(text("Historique (${measures.size})", 15f, true, HydriaColors.text), matchWrap(top = 14))
            if (measures.isEmpty()) body.addView(text("Aucune mesure enregistrée.", 12.5f, false, HydriaColors.textSecondary))
            measures.forEach { m ->
                val delta = if (m.isNull("delta_l_s")) "" else
                    " (${if (m.optDouble("delta_l_s") >= 0) "+" else ""}${formatDecimal(m.optDouble("delta_l_s"), 3)})"
                val period = if (m.optString("periode") == "etiage") " · étiage" else ""
                val status = statusText(m.optString("statut"))
                val line1 = "${displayIsoDate(m.optString("date_visite"))} · ${formatDecimal(m.optDouble("debit_l_s"), 3)} L/s$delta"
                val line2 = listOf(status, m.optString("employe"), m.optString("remarque"))
                    .filter { it.isNotBlank() }.joinToString(" · ") + period
                body.addView(text(line1, 13.5f, true,
                    if (m.optBoolean("sous_seuil")) HydriaColors.error else HydriaColors.text), matchWrap(top = 8))
                if (line2.isNotBlank()) body.addView(text(line2, 12f, false, HydriaColors.textSecondary))
            }
        }
        fun load(index: Int) {
            val work = sources.getOrNull(index) ?: return
            val token = store.token
            body.removeAllViews()
            if (token == null || !isOnline()) {
                body.addView(text("Connexion requise pour consulter l'historique des débits.", 13f, false, HydriaColors.error))
                return
            }
            body.addView(text("Chargement…", 13f, false, HydriaColors.textSecondary))
            executor.execute {
                val result = runCatching { HydriaApi.ouvrageDebits(token, work.getString("id")) }
                runOnUiThread {
                    result.onSuccess { show(it) }.onFailure {
                        body.removeAllViews()
                        body.addView(text("Impossible de charger les débits.", 13f, false, HydriaColors.error))
                    }
                }
            }
        }
        picker.onSelected = { if (it >= 0) load(it) else body.removeAllViews() }
        val wantedIndex = selectedWorkId?.let { id -> sources.indexOfFirst { it.optString("id") == id } } ?: -1
        val initial = if (wantedIndex >= 0) wantedIndex else if (sources.size == 1) 0 else -1
        if (initial >= 0) { picker.select(initial); load(initial) }
        AlertDialog.Builder(this).setTitle("Débits de l'ouvrage")
            .setView(ScrollView(this).apply { addView(form) })
            .setPositiveButton("Fermer", null).show()
    }

    private fun showHeadMeterForm(terrain: JSONObject) {
        val works = terrain.optJSONArray("ouvrages") ?: JSONArray()
        val choices = mutableListOf<Pair<JSONObject, JSONObject>>()
        for (wi in 0 until works.length()) {
            val work = works.getJSONObject(wi)
            val meters = work.optJSONArray("compteurs_tete") ?: JSONArray()
            for (mi in 0 until meters.length()) choices.add(work to meters.getJSONObject(mi))
        }
        if (choices.isEmpty()) {
            toast("Aucun compteur de tête autorisé dans votre périmètre.")
            return
        }
        val form = vertical(padding = 16)
        val meterPicker = HydriaAutocomplete(this, choices.map { "${it.first.optString("nom")} · ${it.second.optString("numero")}" },
            "Rechercher un ouvrage ou un compteur…")
        // Date au sélecteur (JJ/MM/AAAA, aujourd'hui à Madagascar par défaut, pas de date future).
        val dateField = HydriaUi.dateField(this, null)
        val newIndex = field("Nouvel index").apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL }
        val previousInfo = text("", 13f, true, HydriaColors.cyan)
        val explanation = field("Explication éventuelle")
        fun refreshPrevious(position: Int) {
            val meter = choices[position.coerceIn(0, choices.lastIndex)].second
            val history = meter.optJSONArray("historique_recent") ?: JSONArray()
            val previous = if (history.length() > 0) history.getJSONObject(0) else null
            previousInfo.text = if (previous != null) "Index précédent : ${previous.optDouble("nouvel_index")} · ${previous.optString("date")}" else "Index initial : ${meter.optDouble("index_initial")}"
        }
        meterPicker.onSelected = { if (it >= 0) refreshPrevious(it) else previousInfo.text = "" }
        if (choices.size == 1) { meterPicker.select(0); refreshPrevious(0) }
        form.addView(meterPicker, matchWrap(56))
        form.addView(previousInfo, matchWrap(top = 8))
        form.addView(label("Date du relevé"))
        form.addView(dateField, matchWrap(52))
        form.addView(newIndex, matchWrap(52, top = 8))
        form.addView(explanation, matchWrap(52, top = 8))
        val dialog = AlertDialog.Builder(this).setTitle("Relevé compteur de tête")
            .setView(form).setNegativeButton("Annuler", null).setPositiveButton("Calculer", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val (work, meter) = choices.getOrNull(meterPicker.selectedIndex) ?: run {
                    meterPicker.error = "Choisissez un compteur dans la liste"
                    return@setOnClickListener
                }
                val selectedDate = LocalDate.parse(dateField.iso)
                val indexValue = newIndex.text.toString().replace(',', '.').toDoubleOrNull()
                val history = meter.optJSONArray("historique_recent") ?: JSONArray()
                val previous = if (history.length() > 0) history.getJSONObject(0) else null
                val previousIndex = previous?.optDouble("nouvel_index") ?: meter.optDouble("index_initial")
                val previousDate = previous?.optString("date")?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
                if (indexValue == null || indexValue < previousIndex || (previousDate != null && selectedDate.isBefore(previousDate))) {
                    toast("Date ou index invalide. Le nouvel index doit être supérieur ou égal au précédent.")
                    return@setOnClickListener
                }
                val downstream = TerrainRules.localDownstream(work, meter.getString("id"), previousDate, selectedDate)
                val days = if (previousDate != null) ChronoUnit.DAYS.between(previousDate, selectedDate).coerceAtLeast(1) else 0
                val analysis = TerrainMeasurementEngine.headMeter(previousIndex, indexValue, downstream, days)
                val summary = "Compteur de tête : ${formatDecimal(analysis.volumeHead, 2)} m³\nMesures aval : ${formatDecimal(analysis.volumeDownstream, 2)} m³\nÉcart : ${formatDecimal(analysis.gap, 2)} m³ (${formatDecimal(analysis.gapPercent, 1)} %)\nMoyenne : ${formatDecimal(analysis.dailyAverage, 2)} m³/jour\n\n${analysis.classification} · ${analysis.recommendation}"
                AlertDialog.Builder(this).setTitle("Comparaison immédiate").setMessage(summary)
                    .setNegativeButton("Corriger", null)
                    .setPositiveButton("Enregistrer offline") { _, _ ->
                        store.enqueue("terrain_data", JSONObject()
                            .put("operation_type", "head_meter_reading")
                            .put("meter_id", meter.getString("id"))
                            .put("date", selectedDate.toString())
                            .put("new_index", indexValue)
                            .put("explanation", explanation.text.toString().trim()))
                        TerrainRepository.applyLocalHeadReading(store, work.getString("id"), meter.getString("id"), selectedDate.toString(), previousIndex, indexValue, analysis.volumeHead, downstream, analysis.gap)
                        updateStatus()
                        dialog.dismiss()
                        toast("Relevé compteur enregistré hors ligne.")
                        renderCurrentScreen()
                        if (isOnline()) synchronize()
                    }.show()
            }
        }
        dialog.show()
    }

    private fun formatDecimal(value: Double, decimals: Int): String = String.format(Locale.FRANCE, "%.${decimals}f", value)

    private fun renderTerrainNearby(root: LinearLayout, terrain: JSONObject) {
        root.addView(text("Autour de moi", 18f, true, HydriaColors.text), matchWrap(top = 18))
        val radii = listOf(250, 500, 1000, 2000, 5000)
        val controls = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val radiusSpinner = spinner(radii.map { if (it < 1000) "$it m" else "${it / 1000} km" }).apply {
            setSelection(radii.indexOf(nearbyRadiusMeters).coerceAtLeast(0))
            onItemSelectedListener = SimpleItemSelectedListener {
                val selected = radii[it]
                if (selected != nearbyRadiusMeters) { nearbyRadiusMeters = selected; renderCurrentScreen() }
            }
        }
        controls.addView(radiusSpinner, LinearLayout.LayoutParams(0, dp(52), 1f))
        controls.addView(secondaryButton("Ma position").apply {
            setOnClickListener {
                pendingNearbyLocation = true
                pendingLocationPointId = "nearby"
                if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) acquirePointLocation("nearby")
                else locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
            }
        }, LinearLayout.LayoutParams(0, dp(52), 1f))
        root.addView(controls, matchWrap(top = 8))
        val location = nearbyLocation
        if (location == null) {
            root.addView(emptyState("Position nécessaire", "Touchez MA POSITION. Le classement utilise uniquement les données locales et fonctionne sans Internet."))
            return
        }
        data class NearbyTask(val distance: Float, val title: String, val detail: String, val item: JSONObject, val work: JSONObject, val category: String)
        val tasks = mutableListOf<NearbyTask>()
        val works = terrain.optJSONArray("ouvrages") ?: JSONArray()
        for (wi in 0 until works.length()) {
            val work = works.getJSONObject(wi)
            val points = work.optJSONArray("points_eau") ?: JSONArray()
            for (pi in 0 until points.length()) {
                val point = points.getJSONObject(pi)
                if (!point.optBoolean("has_coordinates")) continue
                val result = FloatArray(1)
                Location.distanceBetween(location.latitude, location.longitude, point.optDouble("latitude"), point.optDouble("longitude"), result)
                if (result[0] > nearbyRadiusMeters) continue
                val categories = mutableListOf<String>()
                if (!point.optBoolean("has_subscriber_name")) categories.add("subscriber")
                if (!point.optBoolean("has_photo")) categories.add("point_photo")
                categories.forEach { category ->
                    tasks.add(NearbyTask(result[0], point.optString("code").ifBlank { point.optString("nom") }, if (category == "subscriber") "Nom manquant" else "Photo manquante", point, work, category))
                }
            }
            val equipments = work.optJSONArray("equipements") ?: JSONArray()
            for (ei in 0 until equipments.length()) {
                val equipment = equipments.getJSONObject(ei)
                if (equipment.optBoolean("has_photo") || !equipment.optBoolean("has_coordinates")) continue
                val result = FloatArray(1)
                Location.distanceBetween(location.latitude, location.longitude, equipment.optDouble("latitude"), equipment.optDouble("longitude"), result)
                if (result[0] <= nearbyRadiusMeters) tasks.add(NearbyTask(result[0], equipment.optString("nom"), "Photo équipement manquante", equipment, work, "equipment_photo"))
            }
        }
        tasks.sortBy { it.distance }
        root.addView(text("${tasks.size} action(s) à moins de ${if (nearbyRadiusMeters < 1000) "$nearbyRadiusMeters m" else "${nearbyRadiusMeters / 1000} km"}", 14f, true, HydriaColors.textSecondary), matchWrap(top = 12))
        tasks.forEach { task ->
            root.addView(terrainTaskCard(task.title, "${task.distance.toInt()} m · ${task.detail} · ${task.work.optString("nom")}") {
                showTerrainItem(task.item, task.work, task.category)
            }, matchWrap(top = 8))
        }
        if (tasks.isEmpty()) root.addView(emptyState("Aucune action proche", "Élargissez le rayon ou actualisez votre position."))
    }

    /** La liste defile, mais son action reste accessible sur telephone et tablette. */
    private fun terrainTaskPage(root: LinearLayout, action: View?): View {
        if (action == null) return scroll(root)
        return vertical().apply {
            addView(scroll(root), LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(vertical(padding = 12).apply {
                setBackgroundColor(HydriaColors.background)
                addView(action, matchWrap(56))
            }, matchWrap())
        }
    }

    private fun renderTerrainTaskList(root: LinearLayout, terrain: JSONObject, category: String): View? {
        val labels = mapOf(
            "flow_none" to "Captages sans mesure", "gps" to "Coordonnées manquantes",
            "subscriber" to "Noms d’abonnés manquants", "point_photo" to "Photos de points manquantes",
            "equipment_photo" to "Photos d’équipements manquantes", "flow_overdue" to "Débits à renouveler",
        )
        root.addView(secondaryButton("← Retour").apply {
            setOnClickListener { terrainCategory = null; renderCurrentScreen() }
        }, matchWrap(48, top = 14))
        root.addView(text(labels[category] ?: "À compléter", 18f, true, HydriaColors.text), matchWrap(top = 10))
        val works = terrain.optJSONArray("ouvrages") ?: JSONArray()
        val perItem = category != "flow_none" && category != "flow_overdue"

        val allTasks = mutableListOf<TerrainBatchTask>()
        val selectedTasks = mutableListOf<TerrainBatchTask>()
        val checks = mutableListOf<CheckBox>()
        val taskRows = mutableListOf<Pair<View, String>>()
        val visibleTasks = mutableListOf<TerrainBatchTask>()
        val search = field("Rechercher un code, un nom ou un ouvrage").apply { setSingleLine(true) }
        val searchCount = text("", 12f, false, HydriaColors.textSecondary)
        root.addView(search, matchWrap(52, top = 12))
        root.addView(searchCount, matchWrap(top = 6))
        val selectionCount = TextView(this).apply {
            typeface = HydriaType.display(600)
            textSize = 13f
            setTextColor(HydriaColors.textSecondary)
        }
        val processButton = Button(this).apply { HydriaUi.primaryButton(this, HydriaColors.cyan) }
        fun refreshSelectionBar() {
            val n = selectedTasks.size
            selectionCount.text = if (n > 0) "$n sélectionné${if (n > 1) "s" else ""}" else "Aucune sélection"
            processButton.text = if (n > 0) "Traiter la sélection ($n)" else "Tout traiter en série (${visibleTasks.size})"
            processButton.isEnabled = n > 0 || visibleTasks.isNotEmpty()
        }

        // ── Barre de sélection multiple (raccourci, jamais le seul chemin) ──
        val asTable = windowWidth.isTwoPane && perItem
        var tableHeader: View? = null
        val selectionBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            // Les puces mesurent 48 dp (zone tactile) : la marge verticale est réduite d'autant.
            setPadding(dp(12), dp(4), dp(12), dp(4))
            HydriaUi.card(this)
            addView(selectionCount, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(HydriaUi.chip(this@MainActivity, "Tout", false).apply {
                setOnClickListener { checks.forEachIndexed { index, check ->
                    if (taskRows[index].first.visibility == View.VISIBLE) check.isChecked = true
                } }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(6) })
            addView(HydriaUi.chip(this@MainActivity, "Aucun", false).apply {
                setOnClickListener { checks.forEach { it.isChecked = false } }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(6) })
        }
        root.addView(selectionBar, matchWrap(top = 12))
        if (asTable) {
            tableHeader = terrainTableHeader()
            root.addView(tableHeader, matchWrap(top = 8))
        }

        val stateTag = when (category) {
            "gps" -> "GPS"
            "subscriber" -> "Abonné"
            "point_photo", "equipment_photo" -> "Photo"
            else -> "À faire"
        }

        var displayed = 0
        for (wi in 0 until works.length()) {
            val work = works.getJSONObject(wi)
            if (!perItem) {
                val matches = if (category == "flow_none") {
                    work.optBoolean("debit_source_applicable") && (work.optJSONArray("debits_source_recents")?.length() ?: 0) == 0
                } else work.optBoolean("flow_measurement_overdue")
                if (matches) {
                    displayed++
                    val task = TerrainBatchTask(work, work, category)
                    allTasks.add(task)
                    val row = terrainBatchTaskCard(task, work.optString("nom"),
                        "Ouvrage · ${TerrainRules.ouvrageAgeLabel(work)} · Mesurer le débit",
                        selectedTasks, checks) { refreshSelectionBar() }
                    taskRows.add(row to "${work.optString("code")} ${work.optString("nom")}")
                    root.addView(row, matchWrap(top = 8))
                }
                continue
            }
            val arrayKey = if (category == "equipment_photo") "equipements" else "points_eau"
            val items = work.optJSONArray(arrayKey) ?: JSONArray()
            for (ii in 0 until items.length()) {
                val item = items.getJSONObject(ii)
                val matches = when (category) {
                    "gps" -> !item.optBoolean("has_coordinates")
                    "subscriber" -> !item.optBoolean("has_subscriber_name")
                    "point_photo", "equipment_photo" -> !item.optBoolean("has_photo")
                    else -> false
                }
                if (!matches) continue
                displayed++
                val itemName = item.optString("code").ifBlank { item.optString("nom") }
                val task = TerrainBatchTask(item, work, category)
                allTasks.add(task)
                val row = if (asTable) {
                    terrainTaskTableRow(task, itemName, work.optString("nom"), stateTag,
                        selectedTasks, checks) { refreshSelectionBar() }
                } else {
                    terrainBatchTaskCard(task, itemName, "${work.optString("nom")} · ${TerrainRules.ouvrageAgeLabel(work)} · Renseigner",
                        selectedTasks, checks) { refreshSelectionBar() }
                }
                val searchText = listOf(item.optString("code"), item.optString("nom"),
                    item.optString("subscriber_name"), work.optString("nom"), work.optString("code")).joinToString(" ")
                taskRows.add(row to searchText)
                root.addView(row, matchWrap(top = if (asTable) 6 else 8))
            }
        }
        if (displayed > 0) {
            val noResults = emptyState("Aucun résultat", "Essayez un autre code, nom ou ouvrage.")
            root.addView(noResults, matchWrap(top = 12))
            fun normalize(value: String): String = java.text.Normalizer.normalize(
                value, java.text.Normalizer.Form.NFD,
            ).replace(Regex("\\p{M}+"), "").lowercase(Locale.ROOT)
            val searchIndex = taskRows.map { normalize(it.second) }
            fun filterTasks() {
                val terms = normalize(search.text.toString()).trim().split(Regex("\\s+")).filter { it.isNotBlank() }
                visibleTasks.clear()
                taskRows.forEachIndexed { index, (row, _) ->
                    val matches = terms.all { searchIndex[index].contains(it) }
                    row.visibility = if (matches) View.VISIBLE else View.GONE
                    if (matches) visibleTasks.add(allTasks[index])
                    else checks[index].isChecked = false
                }
                searchCount.text = "${visibleTasks.size} résultat(s) sur ${allTasks.size}"
                noResults.visibility = if (visibleTasks.isEmpty()) View.VISIBLE else View.GONE
                tableHeader?.visibility = if (visibleTasks.isEmpty()) View.GONE else View.VISIBLE
                refreshSelectionBar()
            }
            search.addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { filterTasks() }
                override fun afterTextChanged(s: android.text.Editable?) {}
            })
            filterTasks()
            processButton.setOnClickListener {
                startTerrainBatch(if (selectedTasks.isEmpty()) visibleTasks.toList() else selectedTasks.toList())
            }
            return processButton
        } else {
            root.removeView(selectionBar)
            tableHeader?.let { root.removeView(it) }
        }
        if (displayed == 0) root.addView(emptyState("Tout est complété", "Aucune action restante dans cette catégorie."))
        return null
    }

    private fun terrainBatchTaskCard(
        task: TerrainBatchTask,
        title: String,
        subtitle: String,
        selected: MutableList<TerrainBatchTask>,
        checks: MutableList<CheckBox>,
        onChange: () -> Unit,
    ): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
            HydriaUi.card(this)
            isClickable = true
        }
        val check = CheckBox(this).apply {
            buttonTintList = android.content.res.ColorStateList.valueOf(HydriaColors.cyan)
        }
        checks.add(check)
        container.addView(check, wrapWrap())
        container.addView(vertical().apply {
            addView(text(title, 15.5f, true, HydriaColors.text))
            addView(text(subtitle, 12f, false, HydriaColors.textSecondary))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(6) })
        check.setOnCheckedChangeListener { _, checked ->
            val id = task.item.optString("id")
            if (checked) {
                HydriaFeedback.tap()
                HydriaFeedback.pulse(check)
                if (selected.none { it.item.optString("id") == id && it.category == task.category }) selected.add(task)
            } else {
                selected.removeAll { it.item.optString("id") == id && it.category == task.category }
            }
            onChange()
        }
        container.setOnClickListener { check.isChecked = !check.isChecked }
        container.setOnLongClickListener { showTerrainItem(task.item, task.work, task.category); true }
        return container
    }

    /** En-tête du tableau des points (tablette) — colonnes ☐ · point · ouvrage · état · action. */
    private fun terrainTableHeader(): View = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        setPadding(dp(8), dp(2), dp(8), dp(2))
        fun col(t: String) = TextView(this@MainActivity).apply {
            text = t
            textSize = 10f
            typeface = HydriaType.display(600)
            letterSpacing = 0.06f
            setTextColor(HydriaColors.textMuted)
        }
        addView(View(this@MainActivity), LinearLayout.LayoutParams(dp(34), 1))
        addView(col("POINT"), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.6f))
        addView(col("OUVRAGE"), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        addView(col("ÉTAT"), LinearLayout.LayoutParams(dp(92), LinearLayout.LayoutParams.WRAP_CONTENT))
        addView(View(this@MainActivity), LinearLayout.LayoutParams(dp(128), 1))
    }

    /** Ligne du tableau des points (tablette). Même sélection multiple que les cartes. */
    private fun terrainTaskTableRow(
        task: TerrainBatchTask,
        name: String,
        ouvrage: String,
        stateTag: String,
        selected: MutableList<TerrainBatchTask>,
        checks: MutableList<CheckBox>,
        onChange: () -> Unit,
    ): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(4), dp(8), dp(4))
            minimumHeight = dp(48)
            isClickable = true
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surface, 10f, HydriaColors.outlineSoft)
        }
        val check = CheckBox(this).apply {
            buttonTintList = android.content.res.ColorStateList.valueOf(HydriaColors.cyan)
        }
        checks.add(check)
        row.addView(check, LinearLayout.LayoutParams(dp(34), LinearLayout.LayoutParams.WRAP_CONTENT))
        row.addView(text(name, 13.5f, true, HydriaColors.text).apply { maxLines = 1 },
            LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.6f))
        row.addView(text(ouvrage, 12f, false, HydriaColors.textSecondary).apply { maxLines = 1 },
            LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(6) })
        row.addView(TextView(this).apply {
            text = stateTag
            textSize = 10.5f
            typeface = HydriaType.display(600)
            setTextColor(HydriaColors.warning)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(dp(92), LinearLayout.LayoutParams.WRAP_CONTENT))
        row.addView(Button(this).apply {
            text = "Ouvrir"
            HydriaUi.secondaryButton(this)
            minHeight = dp(40)
            minimumHeight = dp(40)
            setPadding(0, 0, 0, 0)
            setOnClickListener { showTerrainItem(task.item, task.work, task.category) }
        }, LinearLayout.LayoutParams(dp(128), dp(40)))
        check.setOnCheckedChangeListener { _, checked ->
            val id = task.item.optString("id")
            if (checked) {
                HydriaFeedback.tap()
                HydriaFeedback.pulse(check)
                if (selected.none { it.item.optString("id") == id && it.category == task.category }) selected.add(task)
            } else {
                selected.removeAll { it.item.optString("id") == id && it.category == task.category }
            }
            onChange()
        }
        row.setOnClickListener { check.isChecked = !check.isChecked }
        row.setOnLongClickListener { showTerrainItem(task.item, task.work, task.category); true }
        return row
    }

    private fun terrainTaskCard(title: String, subtitle: String, action: () -> Unit): View = card().apply {
        addView(text(title, 16f, true, HydriaColors.text))
        addView(text(subtitle, 12f, false, HydriaColors.textSecondary))
        setOnClickListener { action() }
    }

    private fun showTerrainWork(terrain: JSONObject?, work: JSONObject) {
        val points = work.optJSONArray("points_eau")?.length() ?: 0
        val equipments = work.optJSONArray("equipements")?.length() ?: 0
        val builder = AlertDialog.Builder(this)
            .setTitle(work.optString("nom"))
            .setMessage("${work.optInt("completion_score", 100)} % complet\n$points point(s) d’eau · $equipments équipement(s)")
            .setNegativeButton("Fermer", null)
        if (terrain != null && work.optBoolean("debit_source_applicable")) {
            builder.setPositiveButton("MESURER LE DÉBIT") { _, _ ->
                showFlowMeasurementForm(terrain, work.optString("id"))
            }
        } else builder.setPositiveButton("OK", null)
        builder.show()
    }

    private fun showTerrainItem(item: JSONObject, work: JSONObject, category: String) {
        if (category == "flow_none" || category == "flow_overdue") {
            val terrain = store.snapshot?.optJSONObject("terrain") ?: return
            showFlowMeasurementForm(terrain, work.getString("id")) {
                if (!finishTerrainBatchTask(item, category)) renderCurrentScreen()
            }
            return
        }
        val action = when (category) {
            "gps" -> "Capturer GPS"
            "subscriber" -> "Ajouter le nom"
            else -> "Photographier"
        }
        val batchPosition = if (terrainBatchQueue.isNotEmpty()) terrainBatchTotal - terrainBatchQueue.size + 1 else 0
        val baseTitle = item.optString("code").ifBlank { item.optString("nom") }
        AlertDialog.Builder(this)
            .setTitle(if (batchPosition > 0) "$baseTitle · $batchPosition / $terrainBatchTotal" else baseTitle)
            .setMessage("${work.optString("nom")}\n${item.optString("type")}\n\nAction : $action")
            .setPositiveButton("Continuer") { _, _ ->
                when (category) {
                    "subscriber" -> showSubscriberForm(item, work)
                    "gps" -> {
                        pendingTerrainItem = item
                        pendingTerrainWork = work
                        pendingTerrainCategory = category
                        capturePointLocation(item.getString("id"))
                    }
                    "point_photo", "equipment_photo" -> choosePhotoSource(item, work, category)
                }
            }
            .setNegativeButton("Fermer", null)
            .show()
    }

    private fun startTerrainBatch(tasks: List<TerrainBatchTask>) {
        terrainBatchQueue.clear()
        terrainBatchQueue.addAll(tasks.distinctBy { "${it.category}:${it.item.optString("id")}" })
        terrainBatchTotal = terrainBatchQueue.size
        if (terrainBatchQueue.isEmpty()) {
            toast("Sélectionnez au moins un élément.")
            return
        }
        val first = terrainBatchQueue.first()
        showTerrainItem(first.item, first.work, first.category)
    }

    private fun finishTerrainBatchTask(item: JSONObject, category: String): Boolean {
        val first = terrainBatchQueue.firstOrNull() ?: return false
        if (first.item.optString("id") != item.optString("id") || first.category != category) return false
        terrainBatchQueue.removeAt(0)
        if (terrainBatchQueue.isEmpty()) {
            val completed = terrainBatchTotal
            terrainBatchTotal = 0
            toast("Série terminée · $completed élément(s) enregistrés.")
            renderCurrentScreen()
        } else {
            val next = terrainBatchQueue.first()
            showTerrainItem(next.item, next.work, next.category)
        }
        return true
    }

    /**
     * [onDone] : appelé une seule fois quand le formulaire se ferme (enregistré ou passé). Utilisé pour
     * enchaîner après une photo ; sans lui, comportement habituel de la liste « Abonné ».
     */
    private fun showSubscriberForm(item: JSONObject, work: JSONObject, onDone: (() -> Unit)? = null) {
        var finished = false
        val finishOnce = { if (!finished) { finished = true; onDone?.invoke() } }
        val form = vertical(padding = 18)
        val name = field("Nom de l’abonné").apply { setText(item.optString("nom")) }
        val phone = field("Téléphone").apply {
            inputType = InputType.TYPE_CLASS_PHONE
            setText(item.optString("telephone"))
        }
        form.addView(name, matchWrap(52))
        form.addView(phone, matchWrap(52, top = 10))
        val dialog = AlertDialog.Builder(this)
            .setTitle(item.optString("code"))
            .setView(form)
            .setNegativeButton(if (onDone != null) "Plus tard" else "Annuler") { _, _ -> finishOnce() }
            .setPositiveButton("Enregistrer", null)
            .create()
        if (onDone != null) dialog.setOnCancelListener { finishOnce() }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val subscriberName = name.text.toString().trim()
                if (subscriberName.isBlank()) {
                    name.error = "Nom requis"
                    return@setOnClickListener
                }
                store.enqueue("terrain_data", JSONObject()
                    .put("operation_type", "update_point")
                    .put("point_id", item.getString("id"))
                    .put("subscriber_name", subscriberName)
                    .put("telephone", phone.text.toString().trim())
                    .put("base_updated_at", terrainBaseVersion(item, equipment = false)))
                item.put("nom", subscriberName).put("telephone", phone.text.toString().trim())
                if (TerrainRepository.applyLocalTerrainCompletion(store, item, work, "subscriber")) updateStatus()
                dialog.dismiss()
                toast("Nom enregistré · la liste locale est à jour.")
                if (onDone != null) finishOnce()
                else if (!finishTerrainBatchTask(item, "subscriber")) renderCurrentScreen()
                if (isOnline()) synchronize()
            }
        }
        dialog.show()
    }

    private fun capturePointPhoto(pointId: String) {
        pendingPhotoPointId = pointId
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            launchPointPhoto(pointId)
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun launchPointPhoto(pointId: String) {
        val photoFile = File.createTempFile("hydria_point_", ".jpg", cacheDir)
        pendingPhotoPointId = pointId
        pendingPhotoFile = photoFile
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", photoFile)
        pointPhotoLauncher.launch(uri)
    }

    private fun captureRepairPhoto(repairId: String) {
        pendingRepairPhotoId = repairId
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            launchRepairPhoto(repairId)
        } else {
            repairCameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun launchRepairPhoto(repairId: String) {
        val photoFile = File.createTempFile("hydria_repair_", ".jpg", cacheDir)
        pendingRepairPhotoId = repairId
        pendingRepairPhotoFile = photoFile
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", photoFile)
        repairPhotoLauncher.launch(uri)
    }

    private fun compressPointPhoto(photoFile: File): String {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(photoFile.absolutePath, bounds)
        var sampleSize = 1
        while (bounds.outWidth / sampleSize > 1600 || bounds.outHeight / sampleSize > 1600) sampleSize *= 2
        val bitmap = BitmapFactory.decodeFile(
            photoFile.absolutePath,
            BitmapFactory.Options().apply { inSampleSize = sampleSize },
        ) ?: error("Photo illisible")
        val ratio = minOf(1f, 1280f / maxOf(bitmap.width, bitmap.height).toFloat())
        val resized = if (ratio < 1f) Bitmap.createScaledBitmap(
            bitmap,
            (bitmap.width * ratio).toInt().coerceAtLeast(1),
            (bitmap.height * ratio).toInt().coerceAtLeast(1),
            true,
        ) else bitmap
        val output = ByteArrayOutputStream()
        resized.compress(Bitmap.CompressFormat.JPEG, 80, output)
        if (resized !== bitmap) resized.recycle()
        bitmap.recycle()
        val bytes = output.toByteArray()
        if (bytes.size > 5 * 1024 * 1024) error("Photo trop volumineuse")
        return Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun capturePointLocation(pointId: String) {
        pendingLocationPointId = pointId
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            acquirePointLocation(pointId)
        } else {
            locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    private fun captureReadingAgentLocation(pointId: String) {
        pendingReadingAgentLocation = true
        capturePointLocation(pointId)
    }

    @Suppress("MissingPermission", "DEPRECATION")
    private fun acquirePointLocation(pointId: String) {
        val manager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> null
        }
        if (provider == null) {
            pendingLocationPointId = null
            toast("Activez la localisation GPS du téléphone.")
            return
        }
        toast("Recherche de la position GPS en cours…")
        val saveLocation: (Location?) -> Unit = { location ->
            if (location == null) {
                toast("Position GPS indisponible. Réessayez à l'extérieur.")
            } else if (pendingLocationPointId == pointId) {
                val terrainItem = pendingTerrainItem
                val terrainWork = pendingTerrainWork
                if (pendingNearbyLocation) {
                    nearbyLocation = location
                    toast("Position obtenue. Classement local actualisé.")
                } else if (pendingReadingAgentLocation) {
                    readingAgentLocation = location
                    toast("Position du relevé obtenue (précision ±${location.accuracy.toInt()} m).")
                } else if (terrainItem != null && terrainWork != null && pendingTerrainCategory == "gps") {
                    store.enqueue("terrain_data", JSONObject()
                        .put("operation_type", "update_point")
                        .put("point_id", pointId)
                        .put("latitude", location.latitude)
                        .put("longitude", location.longitude)
                        .put("accuracy", location.accuracy.toDouble())
                        .put("base_updated_at", terrainBaseVersion(terrainItem, equipment = false)))
                    updateStatus()
                    terrainItem.put("latitude", location.latitude)
                        .put("longitude", location.longitude)
                        .put("coordinates_accuracy", location.accuracy.toDouble())
                    if (TerrainRepository.applyLocalTerrainCompletion(store, terrainItem, terrainWork, "gps")) updateStatus()
                    toast("GPS enregistré · ${store.pendingCount()} action(s) en attente · précision ±${location.accuracy.toInt()} m.")
                    finishTerrainBatchTask(terrainItem, "gps")
                } else {
                    val enrichment = pointEnrichments.getOrPut(pointId) { PointEnrichment() }.apply {
                        latitude = location.latitude
                        longitude = location.longitude
                        gpsQueued = true
                    }
                    val baseUpdatedAt = mg.hydria.shared.rules.terrain.TerrainEditRules.baseVersion(
                            store.pending(), "point_eau", pointId,
                            TerrainRepository.findTerrainPoint(store, pointId)?.optString("updated_at").orEmpty())
                    store.enqueue("terrain_data", JSONObject()
                        .put("operation_type", "update_point")
                        .put("point_id", pointId)
                        .put("latitude", enrichment.latitude)
                        .put("longitude", enrichment.longitude)
                        .put("accuracy", location.accuracy.toDouble())
                        .put("base_updated_at", baseUpdatedAt))
                    TerrainRepository.applyLocalReadingPointEnrichment(
                        store, pointId, location.latitude, location.longitude, location.accuracy.toDouble()
                    )
                    updateStatus()
                    toast("GPS enregistré · ${store.pendingCount()} action(s) en attente.")
                }
            }
            pendingLocationPointId = null
            pendingReadingAgentLocation = false
            val refreshNearby = pendingNearbyLocation
            pendingNearbyLocation = false
            pendingTerrainItem = null
            pendingTerrainWork = null
            pendingTerrainCategory = null
            readingEnrichmentRefresh?.invoke()
            readingLocationRefresh?.invoke()
            if (refreshNearby && (currentScreen == Screen.TERRAIN || currentScreen == Screen.READINGS)) renderCurrentScreen()
            else if (terrainOpenWorkId != null && currentScreen == Screen.TERRAIN && terrainBatchQueue.isEmpty()) renderCurrentScreen()
            if (isOnline() && store.pendingCount() > 0) synchronize()
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            manager.getCurrentLocation(provider, null, ContextCompat.getMainExecutor(this), saveLocation)
        } else {
            manager.requestSingleUpdate(provider, object : LocationListener {
                override fun onLocationChanged(location: Location) = saveLocation(location)
            }, mainLooper)
        }
    }

    private fun renderReadings() {
        val snapshot = store.snapshot
        if (snapshot == null) {
            content.addView(emptyState("Aucune tournée préchargée", "Connectez-vous puis touchez la barre de synchronisation."))
            return
        }
        if (campaignOuvrageId == null) renderCampaignSetup(snapshot)
        else renderCampaignReading(snapshot)
    }

    // Étape 1 — Choix de l'ouvrage et de la date de campagne
    private fun renderCampaignSetup(snapshot: JSONObject) {
        val page = vertical(padding = 18)
        page.addView(title("Nouveau relevé"))
        page.addView(subtitle("Choisissez l'ouvrage et la date pour démarrer votre campagne de relevés."))

        val ouvrages = snapshot.optJSONArray("ouvrages") ?: JSONArray()
        val ouvrageObjects = jsonItems(ouvrages) { it.optString("nom", "Ouvrage") }

        if (ouvrageObjects.isEmpty()) {
            page.addView(
                text(
                    "Aucun ouvrage avec paiement au volume ou mixte n'est autorisé pour votre compte. " +
                        "Touchez la barre de synchronisation après le déploiement du correctif.",
                    14f, false, HydriaColors.warning,
                ).apply { setPadding(0, dp(8), 0, dp(8)) }
            )
            content.addView(scroll(page))
            return
        }

        // Progression des relevés du mois en cours, par ouvrage : points actifs déjà relevés
        // côté serveur (releve_mois_courant) ou en file d'attente locale ce mois-ci, sur le
        // total de points actifs de l'ouvrage.
        val today = HydriaDates.today()
        val pendingQueueSetup = store.pending()
        fun monthProgress(ouvrage: JSONObject): Pair<Int, Int> =
            ReadingsRules.monthProgress(ouvrage, pendingQueueSetup, today.year, today.monthValue)

        // (ouvrage, libellé spinner, progression du mois)
        val ouvrageItems = ouvrageObjects.map { (ouvrage, nom) ->
            val (done, total) = monthProgress(ouvrage)
            val spinnerLabel = if (total == 0) "$nom — aucun point actif" else "$nom — $done/$total relevés ce mois"
            Triple(ouvrage, spinnerLabel, done to total)
        }

        // Date au sélecteur (JJ/MM/AAAA) : aujourd'hui à Madagascar par défaut, pas de relevé daté dans le futur.
        // Le choix est gardé dans campaignSetupDate : l'écran peut être reconstruit (fin de synchro) sans le perdre.
        val dateField = HydriaUi.dateField(this, campaignSetupDate) { campaignSetupDate = it }

        // ── Résumé du mois — en tête ──
        val totalDone = ouvrageItems.sumOf { it.third.first }
        val totalPts = ouvrageItems.sumOf { it.third.second }
        val finished = ouvrageItems.count { it.third.second > 0 && it.third.first >= it.third.second }
        val started = ouvrageItems.count { it.third.first in 1 until it.third.second }
        val notStarted = ouvrageItems.count { it.third.second > 0 && it.third.first == 0 }
        val summary = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(14))
            HydriaUi.card(this)
        }
        summary.addView(HydriaUi.overline(this, "RELEVÉS DU MOIS"))
        summary.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.BOTTOM
            addView(TextView(this@MainActivity).apply {
                text = "$totalDone/$totalPts"
                typeface = HydriaType.numeral(700)
                textSize = 34f
                letterSpacing = -0.03f
                setTextColor(HydriaColors.text)
                includeFontPadding = false
            })
            addView(TextView(this@MainActivity).apply {
                text = "points relevés"
                typeface = HydriaType.display(400)
                textSize = 12f
                setTextColor(HydriaColors.textSecondary)
                setPadding(dp(8), 0, 0, dp(6))
            })
        }, matchWrap(top = 6))
        summary.addView(
            HydriaUi.progressBar(this, if (totalPts > 0) totalDone * 100 / totalPts else 0, HydriaColors.success),
            matchWrap(8, top = 10),
        )
        summary.addView(
            text("$finished terminé(s) · $started en cours · $notStarted non commencé(s)", 12f, false, HydriaColors.textSecondary),
            matchWrap(top = 10),
        )
        page.addView(summary, matchWrap(top = 4))

        // ── Date de campagne — ligne modifiable ──
        page.addView(label("Date de la campagne"))
        page.addView(dateField, matchWrap(52, top = 2))

        // ── Un ouvrage = une carte, avec son propre bouton ──
        page.addView(label("Choisir un ouvrage"))
        val ouvrageCards = ouvrageItems.map { (ouvrage, _, progress) ->
            val (done, total) = progress
            val tone = when {
                total == 0 -> Tone.NEUTRAL
                done >= total -> Tone.SUCCESS
                else -> Tone.WARNING
            }
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(14), dp(12), dp(14), dp(12))
                HydriaUi.accentedCard(this, tone)
            }
            row.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                addView(text(ouvrage.optString("nom", "Ouvrage"), 15.5f, true, HydriaColors.text),
                    LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                addView(TextView(this@MainActivity).apply {
                    text = if (total == 0) "—" else "$done/$total"
                    typeface = HydriaType.numeral(700)
                    textSize = 20f
                    letterSpacing = -0.03f
                    setTextColor(HydriaUi.toneTextColor(tone))
                })
            })
            if (total > 0) {
                val btnLabel = when {
                    done >= total -> "Corriger une saisie"
                    done > 0 -> "Reprendre la campagne"
                    else -> "Démarrer la campagne"
                }
                val primary = done in 1 until total
                row.addView(Button(this).apply {
                    text = btnLabel
                    if (primary) HydriaUi.primaryButton(this, HydriaColors.cyan)
                    else HydriaUi.secondaryButton(this)
                    setOnClickListener {
                        campaignOuvrageId = ouvrage.optString("id")
                        campaignOuvrageNom = ouvrage.optString("nom")
                        campaignDate = dateField.iso
                        campaignShowDone = done >= total
                        campaignShowAlreadyRead = done >= total
                        campaignFocusPointId = null
                        // Campagne à saisir : l'index prend le focus et le clavier s'ouvre (pas pour une relecture).
                        readingFocusIndex = done < total
                        readingDetailsExpanded = false
                        readingPickerExpanded = false
                        readingAgentLocation = null
                        readingSocialCards.clear()
                        persistCampaign()
                        renderCurrentScreen()
                    }
                }, matchWrap(52, top = 10))
            } else {
                row.addView(text("Aucun point actif à relever", 12f, false, HydriaColors.textMuted), matchWrap(top = 8))
            }
            row as View
        }
        addInColumns(page, ouvrageCards, paneColumns())
        content.addView(scroll(page))
    }

    // Étape 2 — Saisie enchaînée des relevés pour la campagne active
    private fun renderCampaignReading(snapshot: JSONObject) {
        val page = vertical(padding = 18)

        // Retrouver l'ouvrage sélectionné
        val ouvrages = snapshot.optJSONArray("ouvrages") ?: JSONArray()
        val allOuvrageItems = jsonItems(ouvrages) { it.optString("nom", "Ouvrage") }
        val currentOuvrage = allOuvrageItems.firstOrNull { it.first.optString("id") == campaignOuvrageId }?.first

        // Demandes à usage unique posées avant la reconstruction : consommées ici, pour ne jamais rester armées.
        val focusIndexRequested = readingFocusIndex
        readingFocusIndex = false
        val searchRefocusing = campaignSearchRefocus
        campaignSearchRefocus = false

        // Tous les points actifs à relever pour cet ouvrage
        // Si la campagne porte sur le mois en cours, les points déjà relevés ce mois côté
        // serveur (releve_mois_courant) sont masqués par défaut — ils n'ont normalement pas
        // besoin d'un nouveau relevé. Le bouton toggle campaignShowAlreadyRead permet à
        // l'utilisateur de les faire réapparaître (ex. pour une correction).
        // Si la campagne rattrape un autre mois, ils restent toujours disponibles.
        val campaignIsCurrentMonth = campaignDate?.let { dateStr ->
            runCatching {
                val campaignLocalDate = java.time.LocalDate.parse(dateStr)
                val today = HydriaDates.today()
                campaignLocalDate.year == today.year && campaignLocalDate.month == today.month
            }.getOrDefault(true)
        } ?: true
        val pointsArray = currentOuvrage?.optJSONArray("points_eau") ?: JSONArray()
        // Libellé « idxls — abonné » (sans le code du point), idxls sur 2 ou 3 chiffres,
        // liste triée par idxls numérique (2 avant 10).
        val ouvragePoints = jsonObjects(pointsArray).filter { it.optBoolean("a_relever", true) }
        val idxlsWidth = ReadingPointListRules.idxlsWidth(ouvragePoints)
        val activePoints = ReadingPointListRules.sortedByIdxls(ouvragePoints, idxlsWidth).map { point ->
            val last = point.optJSONObject("dernier_releve")?.optDouble("nouvel_index") ?: 0.0
            val bpMarker = if (point.optJSONObject("alerte_bp_deguise") != null) " · ⚠ BP ?" else ""
            point to ReadingPointListRules.label(point, idxlsWidth, " · index ${formatNumber(last)}$bpMarker")
        }
        val alreadyReadCount = activePoints.count { campaignIsCurrentMonth && it.first.optBoolean("releve_mois_courant", false) }
        val allActivePoints = activePoints.filter { pt ->
            campaignShowAlreadyRead || !(campaignIsCurrentMonth && pt.first.optBoolean("releve_mois_courant", false))
        }

        // Relevés déjà saisis dans la campagne (en file locale)
        val pendingQueue = store.pending()
        // Map pointId -> (localUuid, nouvelIndex, remarque, volumeNonFacture)
        data class CampaignEntry(val uuid: String, val newIndex: Double, val remark: String, val nonBillable: Double, val socialCards: String)
        val campaignQueuedMap = mutableMapOf<String, CampaignEntry>()
        for (qi in 0 until pendingQueue.length()) {
            val queued = pendingQueue.optJSONObject(qi) ?: continue
            if (queued.optString("type") != "reading") continue
            val payload = queued.optJSONObject("payload") ?: continue
            val pointId = payload.optString("point_eau_id")
            if (payload.optString("date_releve") == campaignDate &&
                allActivePoints.any { it.first.optString("id") == pointId }
            ) {
                campaignQueuedMap[pointId] = CampaignEntry(
                    uuid = queued.optString("local_uuid"),
                    newIndex = payload.optDouble("nouvel_index", 0.0),
                    remark = payload.optString("remarque", ""),
                    nonBillable = payload.optDouble("volume_non_facture", 0.0),
                    socialCards = payload.optString("cartes_sociales", "[]"),
                )
            }
        }

        val donePointIds = campaignQueuedMap.keys.toSet()
        val remainingPoints = allActivePoints.filter { it.first.optString("id") !in donePointIds }
        val donePoints = allActivePoints.filter { it.first.optString("id") in donePointIds }
        val total = allActivePoints.size
        val completed = donePointIds.size
        val remaining = total - completed

        // Bandeau de campagne (une seule carte) : ouvrage, date, progression « 12 / 53 · 41 restants » et « Changer ».
        val progressLine = when {
            total == 0 -> "Aucun point d'eau actif à relever"
            remaining > 0 -> "$completed / $total relevés · $remaining restant(s)"
            else -> "Tous les points ont été relevés ✓"
        }
        val bannerCard = vertical(padding = 12).apply { HydriaUi.card(this) }
        val bannerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        bannerRow.addView(vertical().apply {
            addView(text("CAMPAGNE EN COURS", 11f, true, HydriaColors.cyanText))
            addView(text(campaignOuvrageNom ?: "Ouvrage", 17f, true, HydriaColors.text), matchWrap(top = 2))
            addView(text("${displayIsoDate(campaignDate ?: "")} · $progressLine", 12.5f, true, HydriaColors.successText), matchWrap(top = 3))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        bannerRow.addView(secondaryButton("Changer").apply {
            textSize = 11f
            contentDescription = "Changer d'ouvrage ou terminer la campagne"
            setOnClickListener { requestLeaveCampaign() }
        }, wrapWrap())
        bannerCard.addView(bannerRow)
        page.addView(bannerCard, matchWrap(top = 4))

        // Interrupteur « afficher les points déjà relevés ce mois » — masqués par défaut. Rangé dans le bloc
        // « Choisir un point » ; seuls les états vides (ci-dessous) l'affichent directement dans la page.
        val alreadyReadSwitch: SwitchCompat? = if (alreadyReadCount > 0) SwitchCompat(this).apply {
            text = "Afficher les points déjà relevés ce mois ($alreadyReadCount)"
            setTextColor(HydriaColors.text)
            textSize = 14f
            isChecked = campaignShowAlreadyRead
            setPadding(0, dp(6), 0, dp(6))
            setOnCheckedChangeListener { _, checked ->
                campaignShowAlreadyRead = checked
                readingPickerExpanded = true
                renderCurrentScreen()
            }
        } else null

        // État vide : aucun point visible (soit masqués par le toggle, soit ouvrage sans point actif)
        if (total == 0) {
            alreadyReadSwitch?.let { page.addView(it, matchWrap(top = 8)) }
            page.addView(card().apply {
                addView(text(if (alreadyReadCount > 0) "Points masqués" else "Aucun point à relever", 18f, true, HydriaColors.text))
                addView(
                    text(
                        if (alreadyReadCount > 0)
                            "Les $alreadyReadCount point(s) de cet ouvrage ont déjà un relevé ce mois-ci. Activez le bouton ci-dessus pour les afficher."
                        else
                            "Aucun point d'eau actif n'est configuré pour cet ouvrage.",
                        14f, false, HydriaColors.textSecondary,
                    ), matchWrap(top = 6),
                )
            }, matchWrap(top = 12))
            content.addView(scroll(page))
            return
        }

        // État vide : tous les points saisis. En mode « voir mes saisies » (campaignShowDone), le formulaire de
        // correction reste accessible : sans cette condition, « Voir mes saisies de cette campagne » rouvrait
        // la même carte « Campagne terminée » en boucle.
        if (remainingPoints.isEmpty() && donePoints.isNotEmpty() && !campaignShowDone) {
            alreadyReadSwitch?.let { page.addView(it, matchWrap(top = 8)) }
            page.addView(card().apply {
                addView(text("Campagne terminée 🎉", 18f, true, HydriaColors.text))
                addView(
                    text(
                        "Tous les points actifs ont été relevés pour cette campagne.",
                        14f, false, HydriaColors.textSecondary,
                    ), matchWrap(top = 6),
                )
            }, matchWrap(top = 12))
            page.addView(secondaryButton("Voir mes saisies de cette campagne").apply {
                setOnClickListener { campaignShowDone = true; renderCurrentScreen() }
            }, matchWrap(52, top = 10))
            page.addView(primaryButton("Nouvelle campagne").apply {
                setOnClickListener {
                    // Campagne terminée : plus rien à reprendre, les brouillons restants sont effacés.
                    store.clearReadingDrafts(ReadingDraftBook.key(campaignOuvrageId.orEmpty(), campaignDate.orEmpty()))
                    closeCampaign()
                    renderCurrentScreen()
                }
            }, matchWrap(56, top = 10))
            content.addView(scroll(page))
            return
        }

        // Interrupteur « voir mes saisies de cette campagne » : rangé dans le bloc « Choisir un point ».
        val toggleSwitch = SwitchCompat(this).apply {
            text = "Voir mes saisies de cette campagne (${donePoints.size})"
            setTextColor(HydriaColors.text)
            textSize = 14f
            isChecked = campaignShowDone
            setPadding(0, dp(6), 0, dp(6))
            setOnCheckedChangeListener { _, checked ->
                campaignShowDone = checked
                readingPickerExpanded = true
                renderCurrentScreen()
            }
        }

        // Spinner — liste filtrée selon le toggle
        val displayPoints: List<Pair<JSONObject, String>> = if (campaignShowDone) {
            if (donePoints.isEmpty()) {
                emptyList()
            } else {
                donePoints.map { pair ->
                    val pointId = pair.first.optString("id")
                    val entry = campaignQueuedMap[pointId]
                    val label = ReadingPointListRules.label(pair.first, idxlsWidth, " · saisi : ${formatNumber(entry?.newIndex ?: 0.0)}")
                    pair.first to label
                }
            }
        } else {
            remainingPoints
        }

        // Parcelle en cascade au-dessus du point d'eau : seulement pour les longues listes.
        val showParcelFilter = ReadingPointListRules.showParcelFilter(allActivePoints.map { it.first })
        val parcels = if (showParcelFilter) ReadingPointListRules.parcels(allActivePoints.map { it.first }) else emptyList()
        if (parcels.none { it.id == campaignParcelId }) campaignParcelId = ReadingPointListRules.ALL_PARCELS
        val parcelIds = displayPoints.map { it.first }
            .let { ReadingPointListRules.filterByParcel(it, campaignParcelId) }
            .map { it.optString("id") }.toSet()
        val searchedIds = ReadingPointListRules.filterBySearch(
            displayPoints.map { it.first }.filter { it.optString("id") in parcelIds }, idxlsWidth, campaignSearchQuery,
        ).map { it.optString("id") }.toSet()
        var filteredPoints = displayPoints.filter { it.first.optString("id") in searchedIds }

        // Mode « points proches » : du plus proche au plus loin selon la position du téléphone.
        val phoneLocation = nearbyLocation.takeIf { campaignNearbyMode }
        if (phoneLocation != null) {
            val order = ReadingPointListRules.sortedByDistance(
                filteredPoints.map { it.first }, idxlsWidth, phoneLocation.latitude, phoneLocation.longitude,
            ).map { it.optString("id") }
            val byId = filteredPoints.associateBy { it.first.optString("id") }
            filteredPoints = order.mapNotNull { id -> byId[id] }.map { (point, label) ->
                point to label + ReadingPointListRules.distanceSuffix(
                    ReadingPointListRules.distanceMeters(point, phoneLocation.latitude, phoneLocation.longitude))
            }
        }

        val pointItems = filteredPoints.toMutableList()
        val pointSpinner = spinner(pointItems.map { it.second })

        val nearbySwitch = SwitchCompat(this).apply {
            text = if (phoneLocation != null) "Points proches de moi (±${phoneLocation.accuracy.toInt()} m)"
                else "Points proches de moi (GPS)"
            setTextColor(HydriaColors.text)
            textSize = 14f
            isChecked = campaignNearbyMode
            setPadding(0, dp(6), 0, dp(6))
            setOnCheckedChangeListener { _, checked ->
                campaignNearbyMode = checked
                readingPickerExpanded = true
                if (checked) requestNearbyLocation() else renderCurrentScreen()
            }
        }
        val nearbyRefresh = secondaryButton("Actualiser ma position").apply {
            textSize = 12f
            visibility = if (campaignNearbyMode) View.VISIBLE else View.GONE
            setOnClickListener { requestNearbyLocation() }
        }
        val parcelSpinner = if (showParcelFilter) spinner(
            listOf("Toutes les parcelles (${allActivePoints.size})") + parcels.map { "${it.label} (${it.count})" }
        ).apply {
            setSelection(parcels.indexOfFirst { it.id == campaignParcelId } + 1, false)
            onItemSelectedListener = SimpleItemSelectedListener { position ->
                val id = parcels.getOrNull(position - 1)?.id ?: ReadingPointListRules.ALL_PARCELS
                if (id != campaignParcelId) { campaignParcelId = id; readingPickerExpanded = true; renderCurrentScreen() }
            }
        } else null

        // Recherche libre : nom d'abonné (même partiel) ou idxls. Re-rendu différé pendant la frappe,
        // le focus et le curseur sont rétablis sur le nouveau champ.
        val pointSearch = field("Rechercher un point (nom ou idxls)").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH
            setText(campaignSearchQuery)
            setSelection(text.length)
            var lastApplied = campaignSearchQuery
            addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    campaignSearchHandler.removeCallbacksAndMessages(null)
                    val typed = s?.toString().orEmpty()
                    if (typed == lastApplied) return
                    campaignSearchHandler.postDelayed({
                        lastApplied = typed
                        campaignSearchQuery = typed
                        campaignSearchRefocus = true
                        readingPickerExpanded = true
                        renderCurrentScreen()
                    }, 300)
                }
                override fun afterTextChanged(s: android.text.Editable?) {}
            })
        }
        val twoPane = windowWidth.isTwoPane && detailPane != null

        // ── Bloc repliable « Choisir un point » : interrupteurs, parcelle, recherche, liste déroulante. Fermé par
        // défaut (le formulaire commence par le point en cours) ; ouvert quand l'agent s'en sert ou qu'il n'y a
        // aucun point à saisir. En tablette 2 volets, la liste des points est à gauche : la liste déroulante est masquée.
        val pickerContent = vertical()
        alreadyReadSwitch?.let { pickerContent.addView(it, matchWrap()) }
        pickerContent.addView(toggleSwitch, matchWrap(top = 4))
        pickerContent.addView(nearbySwitch, matchWrap(top = 4))
        pickerContent.addView(nearbyRefresh, matchWrap(44, top = 4))
        if (parcelSpinner != null) {
            pickerContent.addView(label("Parcelle"))
            pickerContent.addView(parcelSpinner, matchWrap(52))
        }
        pickerContent.addView(label("Rechercher"))
        pickerContent.addView(pointSearch, matchWrap(52))
        val spinnerLabel = label("Point d'eau")
        pickerContent.addView(spinnerLabel)
        pickerContent.addView(pointSpinner, matchWrap(52))
        if (twoPane || pointItems.isEmpty()) {
            spinnerLabel.visibility = View.GONE
            pointSpinner.visibility = View.GONE
        }
        val pickerSummary = mutableListOf<String>().apply {
            if (campaignShowDone) add("Mes saisies")
            parcels.firstOrNull { it.id == campaignParcelId }?.let { add(it.label) }
            if (campaignSearchQuery.isNotBlank()) add("« ${campaignSearchQuery.trim()} »")
            if (campaignNearbyMode) add("Proches de moi")
        }.joinToString(" · ").ifBlank { "${pointItems.size} point(s)" }
        val pickerSection = HydriaUi.collapsible(
            this, "Choisir un point", pickerSummary,
            open = readingPickerExpanded || pointItems.isEmpty(), content = pickerContent,
        ).apply { onToggle = { readingPickerExpanded = it } }
        if (searchRefocusing) {
            pointSearch.post {
                pointSearch.requestFocus()
                pointSearch.setSelection(pointSearch.text.length)
                (getSystemService(INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager)
                    ?.showSoftInput(pointSearch, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
            }
        }
        if (pointItems.isEmpty()) {
            page.addView(pickerSection, matchWrap(top = 10))
            page.addView(text(
                if (campaignShowDone && donePoints.isEmpty()) "Aucun relevé saisi pour cette campagne."
                else if (campaignSearchQuery.isNotBlank()) "Aucun point ne correspond à « ${campaignSearchQuery.trim()} »."
                else if (campaignShowDone) "Aucune saisie dans cette parcelle."
                else "Aucun point restant dans cette parcelle. Choisissez une autre parcelle.",
                14f, false, HydriaColors.textSecondary,
            ).apply { setPadding(0, dp(8), 0, dp(8)) })
            content.addView(scroll(page))
            return
        }

        // ── En-tête du point : pictogramme, idxls, abonné, rang dans la liste, dernier relevé, et boutons ‹ › qui
        // changent de point sans reconstruire la page (le clavier reste ouvert pendant la saisie en série). ──
        val pointTitle = text("", 17f, true, HydriaColors.text).apply {
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        val pointMeta = text("", 12.5f, false, HydriaColors.textSecondary)
        fun stepButton(glyph: String, description: String) = secondaryButton(glyph).apply {
            textSize = 22f
            contentDescription = description
            minWidth = dp(48)
            minimumWidth = dp(48)
            minHeight = dp(48)
            minimumHeight = dp(48)
            // Après le style : le bouton garde ses 48 dp sans la marge latérale du bouton secondaire.
            setPadding(0, 0, 0, 0)
        }
        val previousPointButton = stepButton("‹", "Point précédent de la liste")
        val nextPointButton = stepButton("›", "Point suivant de la liste")
        val pointHeader = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(8), dp(8), dp(8))
            HydriaUi.card(this)
            addView(previousPointButton, LinearLayout.LayoutParams(dp(48), dp(48)))
            addView(vertical().apply {
                addView(pointTitle, matchWrap())
                addView(pointMeta, matchWrap(top = 3))
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginStart = dp(8)
                marginEnd = dp(8)
            })
            addView(nextPointButton, LinearLayout.LayoutParams(dp(48), dp(48)))
        }
        // Visible quand la saisie affichée vient du brouillon gardé (changement de point, retour, mort du processus).
        val draftBadge = text("✎ Brouillon repris", 13f, true, HydriaColors.cyanText).apply {
            setPadding(dp(10), dp(7), dp(10), dp(7))
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surface, 10f, HydriaColors.outline)
            visibility = View.GONE
        }

        // GPS de l'agent : bloc isolé, que le chantier L2-6 remplacera par la feuille de capture partagée.
        val (gpsBlock, refreshReadingLocation) =
            buildReadingGpsBlock { pointItems.getOrNull(pointSpinner.selectedItemPosition)?.first }
        readingLocationRefresh = refreshReadingLocation

        // ── Brouillon de saisie : un par point, gardé dans le store. Il survit à la reconstruction de l'écran, à un
        // changement de point, à la sortie de la campagne et à la mort du processus (voir ReadingDraftBook). ──
        val draftKey = ReadingDraftBook.key(campaignOuvrageId.orEmpty(), campaignDate.orEmpty())
        val draftNow = System.currentTimeMillis()
        val knownPointIds = ouvragePoints.map { it.optString("id") }.toSet()
        val draftBook = readingDraftBook?.takeIf { it.campaignKey == draftKey }
            ?.also { it.purge(draftNow, knownPointIds) }
            ?: ReadingDraftBook.fromJson(draftKey, store.readingDrafts(draftKey), draftNow, knownPointIds)
        readingDraftBook = draftBook
        val draftHandler = android.os.Handler(android.os.Looper.getMainLooper())
        // Corps affecté plus bas, une fois les champs construits.
        var scheduleDraftSave: () -> Unit = {}
        // Vrai pendant que le code remplit les champs (changement de point, restauration) : pas de sauvegarde.
        var applyingForm = false
        // Vrai quand le formulaire est fermé (point enregistré, écran reconstruit) : plus aucune écriture.
        var formClosed = false
        var shownPointId: String? = null
        // Sections repliables : références prises ici, construites en bas de la fonction.
        var detailsSection: HydriaCollapsible? = null
        var refreshDetailsSummary: () -> Unit = {}
        val detailsContent = vertical()
        // Défilement de la page : remonté au point quand l'agent le choisit tout en bas (liste déroulante).
        var pageScrollView: ScrollView? = null

        // Enrichissement (GPS/photo manquants)
        val enrichmentCard = vertical(padding = 12).apply { HydriaUi.card(this, emphasized = true) }
        val enrichmentStatus = text("", 13f, true, HydriaColors.warning)
        val enrichmentActions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val gpsButton = secondaryButton("Ajouter le GPS")
        val photoButton = secondaryButton("Prendre une photo")
        val phoneButton = secondaryButton("Ajouter le téléphone")
        enrichmentActions.addView(gpsButton, LinearLayout.LayoutParams(0, dp(50), 1f))
        enrichmentActions.addView(photoButton, LinearLayout.LayoutParams(0, dp(50), 1f))
        enrichmentActions.addView(phoneButton, LinearLayout.LayoutParams(0, dp(50), 1f))
        enrichmentCard.addView(enrichmentStatus, matchWrap())
        enrichmentCard.addView(enrichmentActions, matchWrap(top = 8))

        fun updatePointEnrichment(position: Int) {
            val point = pointItems.getOrNull(position)?.first
            if (point == null) { enrichmentCard.visibility = View.GONE; return }
            val pointId = point.optString("id")
            val enrichment = pointEnrichments[pointId]
            val databaseHasCoordinates = point.optBoolean("has_coordinates", false)
            val databaseHasPhoto = point.optBoolean("has_photo", false)
            val coordinatesReady = databaseHasCoordinates || (enrichment?.latitude != null && enrichment.longitude != null)
            val photoReady = databaseHasPhoto || enrichment?.photoQueued == true
            val databaseHasPhone = point.optString("telephone").isNotBlank()
            val phoneReady = databaseHasPhone || enrichment?.phoneQueued == true
            if (databaseHasCoordinates && databaseHasPhoto && databaseHasPhone) { enrichmentCard.visibility = View.GONE; return }
            enrichmentCard.visibility = View.VISIBLE
            val missing = mutableListOf<String>()
            if (!databaseHasCoordinates) missing.add(if (coordinatesReady) "GPS prêt" else "coordonnées GPS manquantes")
            if (!databaseHasPhoto) missing.add(if (photoReady) "photo prête" else "photo manquante")
            if (!databaseHasPhone) missing.add(if (phoneReady) "téléphone prêt" else "téléphone manquant")
            enrichmentStatus.text = "Fiche du point d'eau à compléter : ${missing.joinToString(" · ")}. Les éléments ajoutés seront envoyés avec le relevé."
            gpsButton.visibility = if (!databaseHasCoordinates && !coordinatesReady) View.VISIBLE else View.GONE
            photoButton.visibility = if (!databaseHasPhoto && !photoReady) View.VISIBLE else View.GONE
            phoneButton.visibility = if (!databaseHasPhone && !phoneReady) View.VISIBLE else View.GONE
        }
        gpsButton.setOnClickListener {
            pointItems.getOrNull(pointSpinner.selectedItemPosition)?.first?.optString("id")
                ?.takeIf { it.isNotBlank() }?.let(::capturePointLocation)
        }
        photoButton.setOnClickListener {
            pointItems.getOrNull(pointSpinner.selectedItemPosition)?.first?.optString("id")
                ?.takeIf { it.isNotBlank() }?.let(::capturePointPhoto)
        }
        phoneButton.setOnClickListener {
            pointItems.getOrNull(pointSpinner.selectedItemPosition)?.first?.let { point ->
                showReadingPhoneForm(point) { updatePointEnrichment(pointSpinner.selectedItemPosition) }
            }
        }
        readingEnrichmentRefresh = { updatePointEnrichment(pointSpinner.selectedItemPosition); refreshDetailsSummary() }

        // ── Alerte « BP déguisé » (calculée par le serveur) : kiosque qui consomme comme un branchement privé.
        // L'agent doit en parler à l'abonné : couper le kiosque ou le transformer en BP.
        val bpAlertCard = vertical(padding = 14).apply {
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.errorWash, 14f, HydriaColors.error)
            visibility = View.GONE
        }
        val bpAlertTitle = text("", 15f, true, HydriaColors.error)
        val bpAlertMessage = text("", 14f, false, HydriaColors.text)
        val bpAlertActions = text("", 13f, true, HydriaColors.error)
        bpAlertCard.addView(bpAlertTitle, matchWrap())
        bpAlertCard.addView(bpAlertMessage, matchWrap(top = 6))
        bpAlertCard.addView(bpAlertActions, matchWrap(top = 8))

        fun updateBpAlert(position: Int) {
            val alert = pointItems.getOrNull(position)?.first?.optJSONObject("alerte_bp_deguise")
            if (alert == null) { bpAlertCard.visibility = View.GONE; return }
            bpAlertTitle.text = "⚠ " + alert.optString("titre", "Kiosque à faible consommation : BP déguisé ?")
            bpAlertMessage.text = alert.optString("message")
            bpAlertActions.text = "À faire : parler à l'abonné → couper le kiosque OU le transformer en BP."
            bpAlertCard.visibility = View.VISIBLE
        }

        // ── Champ NOUVEL INDEX — l'objet principal de l'écran ──
        val index = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine(true)
            hint = "0"
            HydriaUi.styleNumeralInput(this)
            // Le cadre cyan est porté par indexCard : champ à plat à l'intérieur.
            background = null
            setPadding(0, 0, 0, 0)
            minHeight = dp(48)
            // La touche ✓ ferme SEULEMENT le clavier : l'enregistrement reste un geste volontaire sur le bouton
            // (décision 5 ter n°1), une faute de frappe ne part pas en un geste.
            imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_DONE
            setOnEditorActionListener { view, actionId, _ ->
                if (actionId == android.view.inputmethod.EditorInfo.IME_ACTION_DONE) {
                    (this@MainActivity.getSystemService(INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager)
                        ?.hideSoftInputFromWindow(view.windowToken, 0)
                    true
                } else false
            }
            // Tablette 2 volets : pavé numérique intégré, jamais de clavier système sur l'index.
            if (twoPane) showSoftInputOnFocus = false
        }
        val indexMinLabel = TextView(this).apply {
            typeface = HydriaType.numeral(600)
            textSize = 11f
            setTextColor(HydriaColors.textSecondary)
            gravity = Gravity.END
        }
        val consumptionLabel = TextView(this).apply {
            typeface = HydriaType.numeral(700)
            textSize = 15f
            setTextColor(HydriaColors.success)
        }
        var indexOldValue = 0.0
        // Recalcule le volume facturé (conso − cartes sociales − non facturé).
        // Corps assigné plus bas, une fois les vues cartes sociales construites.
        var recomputeVolumes: () -> Unit = {}
        // Remarque obligatoire (consommation nulle ou volume non facturé ≠ 0) : libellé recalculé à chaque
        // changement d'index ou de non facturé. Corps assigné plus bas, une fois le champ remarque construit.
        var refreshRemarkRequirement: () -> Unit = {}
        fun refreshConsumption() {
            val entered = index.text.toString().replace(',', '.').toDoubleOrNull()
            val below = entered != null && entered < indexOldValue
            consumptionLabel.text = when {
                entered == null -> "—"
                below -> "index < dernier"
                else -> "+ ${formatNumber(ReadingsRules.consumption(entered, indexOldValue))} m³"
            }
            consumptionLabel.setTextColor(if (below) HydriaColors.error else HydriaColors.success)
            refreshRemarkRequirement()
        }
        index.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                refreshConsumption(); recomputeVolumes(); scheduleDraftSave()
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        val indexCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(14))
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surfaceRaised, 18f, HydriaColors.cyan, 2f)
        }
        indexCard.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(HydriaUi.overline(this@MainActivity, "NOUVEL INDEX").apply { setTextColor(HydriaColors.cyan) },
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(indexMinLabel)
        })
        indexCard.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(index, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(TextView(this@MainActivity).apply {
                text = "m³"
                typeface = HydriaType.display(500)
                textSize = 15f
                setTextColor(HydriaColors.textSecondary)
                setPadding(dp(10), 0, 0, 0)
            })
        }, matchWrap(top = 10))
        indexCard.addView(View(this).apply { setBackgroundColor(HydriaColors.outline) }, matchWrap(1, top = 12))
        indexCard.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(10), 0, 0)
            addView(TextView(this@MainActivity).apply {
                text = "Consommation calculée"
                typeface = HydriaType.display(400)
                textSize = 12f
                setTextColor(HydriaColors.textSecondary)
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(consumptionLabel)
        })

        // Champs secondaires (rangés dans « Plus de détails »)
        val nonFacture = field("Volume non facturé (optionnel)").apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setText("0")
            addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {
                    recomputeVolumes(); refreshRemarkRequirement(); scheduleDraftSave()
                }
                override fun afterTextChanged(s: android.text.Editable?) {}
            })
        }
        // Libellés visibles : le « 0 » pré-rempli masquait le hint du volume non facturé.
        val nonFactureLabel = label("Volume non facturé (m³, optionnel)")
        val remarkLabel = label("Remarque (optionnelle)")
        val remark = field("Remarque (optionnelle)").apply {
            addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {
                    scheduleDraftSave(); refreshDetailsSummary()
                }
                override fun afterTextChanged(s: android.text.Editable?) {}
            })
        }
        var remarkRequiredNow = false
        refreshRemarkRequirement = {
            val entered = index.text.toString().replace(',', '.').toDoubleOrNull()
            val consumption = if (entered != null && entered >= indexOldValue)
                ReadingValidation.consumption(entered, indexOldValue) else null
            val nonBillable = nonFacture.text.toString().replace(',', '.').toDoubleOrNull() ?: 0.0
            val required = ReadingValidation.remarkRequired(consumption, nonBillable)
            remarkRequiredNow = required
            remarkLabel.text = if (required) "Remarque (obligatoire)" else "Remarque (optionnelle)"
            remark.hint = if (required) "Remarque (obligatoire)" else "Remarque (optionnelle)"
            if (!required) remark.error = null
            // La règle s'applique : « Plus de détails » s'ouvre tout seul, sans prendre le focus de l'index.
            if (required && remark.text.isBlank() && !applyingForm) detailsSection?.setOpen(true)
            refreshDetailsSummary()
        }

        // Badge correction (visible en mode toggle ON)
        val correctionBadge = text("", 13f, true, HydriaColors.cyan).apply {
            setPadding(dp(10), dp(7), dp(10), dp(7))
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surface, 10f, HydriaColors.outline)
            visibility = View.GONE
        }

        val invoicesButton = secondaryButton("Consulter les anciennes factures").apply {
            isEnabled = false
            setOnClickListener {
                val point = pointItems.getOrNull(pointSpinner.selectedItemPosition)?.first
                if (point == null) toast("Sélectionnez un point d'eau") else showPointInvoices(point)
            }
        }

        // « Enregistrer » enchaîne sur le point suivant : le « · point suivant » est annoncé, atténué.
        fun saveLabel(correction: Boolean): CharSequence {
            if (correction) return "Corriger le relevé"
            return android.text.SpannableStringBuilder("Enregistrer  ").apply {
                val start = length
                append("· point suivant")
                val dim = Color.argb(
                    150, Color.red(HydriaColors.onAccent), Color.green(HydriaColors.onAccent), Color.blue(HydriaColors.onAccent),
                )
                setSpan(android.text.style.ForegroundColorSpan(dim), start, length, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                setSpan(android.text.style.RelativeSizeSpan(0.82f), start, length, android.text.Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }
        val saveButton = primaryButton("Enregistrer le relevé").apply { text = saveLabel(campaignShowDone) }

        // --- Cartes sociales (kiosques uniquement) ---
        // Reprend l'étape 3 du workflow web /facturation/releves/ : 1 bidon = 20 L
        // = 0,02 m³. Le volume des cartes est déduit du volume facturé. Les cartes
        // sont préchargées avec la tournée (champ point.cartes_sociales), donc la
        // sélection fonctionne hors ligne, uniquement parmi les cartes rattachées au point.
        val socialCard = vertical(padding = 14).apply {
            HydriaUi.card(this)
            visibility = View.GONE
        }
        val socialRows = vertical()
        val socialSubtotal = text("Volume cartes sociales : 0 m³", 12f, true, HydriaColors.textSecondary)
        val addCardButton = secondaryButton("Choisir une carte sociale")
        var availableSocialCards = emptyList<JSONObject>()
        socialCard.addView(HydriaUi.overline(this@MainActivity, "CARTES SOCIALES").apply { setTextColor(HydriaColors.cyan) })
        socialCard.addView(socialRows, matchWrap(top = 8))
        socialCard.addView(addCardButton, matchWrap(44, top = 8))
        socialCard.addView(secondaryButton("Créer / gérer les cartes sociales").apply {
            setOnClickListener {
                if (!isOnline()) {
                    toast("La gestion des cartes nécessite une connexion. Les cartes déjà synchronisées restent disponibles hors connexion.")
                } else {
                    val workId = campaignOuvrageId.orEmpty()
                    val address = "https://www.hydria.mg/organisations/cartes-sociales/" +
                        if (workId.isNotBlank()) "${Uri.encode(workId)}/" else ""
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(address)))
                        toast("Après création et rattachement au point, revenez dans Hydria Terrain et synchronisez.")
                    } catch (_: android.content.ActivityNotFoundException) {
                        toast("Aucun navigateur disponible pour ouvrir la gestion des cartes.")
                    }
                }
            }
        }, matchWrap(48, top = 4))
        socialCard.addView(socialSubtotal, matchWrap(top = 8))

        val volumeFactureInfo = text("Volume facturé : —", 13f, true, HydriaColors.success).apply {
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surface, 14f, HydriaColors.outline)
        }

        fun socialCardsVolume(): Double = readingSocialCards.sumOf {
            ReadingsRules.socialCardVolume(it.optInt("quantite_bidons", 0))
        }

        fun refreshVolumeFacture() {
            val entered = index.text.toString().replace(',', '.').toDoubleOrNull()
            val nonBillable = nonFacture.text.toString().replace(',', '.').toDoubleOrNull() ?: 0.0
            val cartes = socialCardsVolume()
            socialSubtotal.text = "Volume cartes sociales : ${formatNumber(cartes)} m³"
            if (entered == null || entered < indexOldValue) {
                volumeFactureInfo.text = "Volume facturé : —"
                volumeFactureInfo.setTextColor(HydriaColors.textSecondary)
                return
            }
            val conso = ReadingsRules.consumption(entered, indexOldValue)
            val facture = ReadingsRules.billedVolume(conso, cartes, nonBillable)
            volumeFactureInfo.text = buildString {
                append("Volume facturé : ${formatNumber(facture)} m³")
                append(" · conso ${formatNumber(conso)}")
                if (cartes > 0) append(" − cartes ${formatNumber(cartes)}")
                if (nonBillable != 0.0) append(" − non facturé ${formatNumber(nonBillable)}")
            }
            volumeFactureInfo.setTextColor(if (facture < -0.001) HydriaColors.error else HydriaColors.success)
        }

        fun renderSocialRows() {
            socialRows.removeAllViews()
            refreshDetailsSummary()
            addCardButton.isEnabled = availableSocialCards.any { card -> readingSocialCards.none { it.optString("id") == card.optString("id") } }
            if (readingSocialCards.isEmpty()) {
                socialRows.addView(text(if (availableSocialCards.isEmpty())
                    "Aucune carte sociale rattachée à ce point. Créez et rattachez la carte dans la page de gestion, puis synchronisez."
                    else "Choisissez une carte rattachée à ce point, puis renseignez le nombre de bidons.",
                    12f, false, HydriaColors.textSecondary))
                return
            }
            readingSocialCards.forEachIndexed { idx, carte ->
                val row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(0, dp(4), 0, dp(4))
                }
                row.addView(vertical().apply {
                    addView(text(carte.optString("beneficiaire", "Carte ${idx + 1}"), 13f, true, HydriaColors.text))
                    if (availableSocialCards.none { it.optString("id") == carte.optString("id") }) {
                        addView(text("Carte non rattachée : retirez-la et choisissez une carte reconnue.", 11f, true, HydriaColors.warning))
                    }
                    val num = carte.optString("numero_carte", "")
                    if (num.isNotBlank()) addView(text(num, 11f, false, HydriaColors.textSecondary), matchWrap(top = 2))
                }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                val bidonInput = EditText(this).apply {
                    inputType = InputType.TYPE_CLASS_NUMBER
                    setSingleLine(true)
                    hint = "Bidons 20L"
                    HydriaUi.styleNumeralInput(this)
                    setText(carte.optInt("quantite_bidons", 0).takeIf { it > 0 }?.toString() ?: "")
                    addTextChangedListener(object : android.text.TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                        override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                        override fun afterTextChanged(s: android.text.Editable?) {
                            val raw = s?.toString()?.toIntOrNull() ?: 0
                            val qte = raw.coerceIn(0, 30)
                            if (raw != qte) {
                                s?.replace(0, s.length, qte.toString())
                                return  // relance afterTextChanged avec la valeur bornée
                            }
                            carte.put("quantite_bidons", qte)
                            carte.put("volume_total", ReadingsRules.socialCardVolume(qte))
                            refreshVolumeFacture()
                            scheduleDraftSave()
                        }
                    })
                }
                row.addView(bidonInput, LinearLayout.LayoutParams(dp(96), LinearLayout.LayoutParams.WRAP_CONTENT))
                row.addView(secondaryButton("Retirer").apply {
                    contentDescription = "Retirer la carte ${carte.optString("numero_carte")} du relevé"
                    setOnClickListener {
                        readingSocialCards.remove(carte)
                        renderSocialRows()
                        refreshVolumeFacture()
                        scheduleDraftSave()
                    }
                }, LinearLayout.LayoutParams(dp(86), dp(48)))
                socialRows.addView(row)
            }
        }

        addCardButton.setOnClickListener {
            val candidates = availableSocialCards.filter { card ->
                readingSocialCards.none { it.optString("id") == card.optString("id") }
            }
            val search = field("Rechercher un numéro ou un bénéficiaire")
            val choices = vertical()
            val body = vertical(padding = 12).apply {
                addView(search, matchWrap(54))
                addView(scroll(choices), matchWrap(300, top = 8))
            }
            val dialog = AlertDialog.Builder(this@MainActivity)
                .setTitle("Cartes rattachées à ce point")
                .setView(body).setNegativeButton("Fermer", null).create()
            fun renderChoices() {
                choices.removeAllViews()
                val query = search.text.toString().trim()
                val matches = candidates.filter {
                    it.optString("numero_carte").contains(query, ignoreCase = true) ||
                        it.optString("beneficiaire").contains(query, ignoreCase = true)
                }
                if (matches.isEmpty()) choices.addView(subtitle("Aucune carte correspondante"))
                matches.forEach { card ->
                    choices.addView(secondaryButton("${card.optString("numero_carte")} · ${card.optString("beneficiaire")}").apply {
                        setOnClickListener {
                            if (readingSocialCards.none { it.optString("id") == card.optString("id") }) {
                                readingSocialCards.add(JSONObject(card.toString()).put("quantite_bidons", 0).put("volume_total", 0.0))
                            }
                            dialog.dismiss()
                            renderSocialRows()
                            refreshVolumeFacture()
                            scheduleDraftSave()
                        }
                    }, matchWrap(top = 4))
                }
            }
            search.addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) { renderChoices() }
                override fun afterTextChanged(s: android.text.Editable?) {}
            })
            renderChoices()
            dialog.show()
        }

        fun rebuildSocialCards(point: JSONObject?) {
            readingSocialCards.clear()
            val isKiosque = point?.optString("type").orEmpty().uppercase().contains("KIOSQUE")
            socialCard.visibility = if (isKiosque) View.VISIBLE else View.GONE
            availableSocialCards = if (isKiosque && point != null) {
                val preload = point.optJSONArray("cartes_sociales") ?: JSONArray()
                (0 until preload.length()).mapNotNull { preload.optJSONObject(it) }
                    .filter { it.optString("id").isNotBlank() }.distinctBy { it.optString("id") }
            } else emptyList()
            if (campaignShowDone && point != null) {
                val savedCards = campaignQueuedMap[point.optString("id")]?.socialCards
                val queuedCards = runCatching { JSONArray(savedCards ?: "[]") }.getOrDefault(JSONArray())
                for (i in 0 until queuedCards.length()) {
                    val saved = queuedCards.optJSONObject(i) ?: continue
                    val linked = availableSocialCards.firstOrNull { it.optString("id") == saved.optString("id") }
                    val restored = JSONObject((linked ?: saved).toString())
                        .put("quantite_bidons", saved.optInt("quantite_bidons", 0))
                        .put("volume_total", saved.optDouble("volume_total", 0.0))
                    readingSocialCards.add(restored)
                }
            }
            renderSocialRows()
        }

        recomputeVolumes = { refreshVolumeFacture() }

        fun draftCards(): List<ReadingDraftCard> =
            readingSocialCards.map { ReadingDraftCard(it.optString("id"), it.optInt("quantite_bidons", 0)) }

        // Saisie non enregistrée : signature des champs (index, remarque, non facturé, cartes sociales) comparée à
        // celle de l'état initial du point (champs vides en saisie normale, valeurs de la file en mode correction).
        // La normalisation est partagée (ReadingFormSignature : Desktop et tests). La référence est reprise dans
        // updateLastReading, AVANT la restauration du brouillon.
        fun readingFormSignature(): List<String> = ReadingFormSignature.of(
            index.text.toString(), remark.text.toString(), nonFacture.text.toString(), draftCards(),
        )
        var readingFormBaseline = emptyList<String>()

        // « Plus de détails » s'ouvre tout seul quand une règle l'exige (remarque obligatoire et vide, kiosque avec
        // cartes sociales, valeur déjà saisie dans la section) ; il reste ouvert si l'agent l'a ouvert sur ce point.
        fun detailsShouldOpen(): Boolean = readingDetailsExpanded || ReadingFormLayout.shouldOpenDetails(
            remarkRequired = remarkRequiredNow,
            remarkBlank = remark.text.isBlank(),
            kioskWithCards = socialCard.visibility == View.VISIBLE && availableSocialCards.isNotEmpty(),
            hiddenValues = ReadingFormLayout.hasHiddenValues(remark.text.toString(), nonFacture.text.toString(), draftCards()),
        )

        fun persistDrafts() {
            if (draftBook.isEmpty()) store.clearReadingDrafts(draftKey) else store.saveReadingDrafts(draftKey, draftBook.toJson())
        }

        // Garde la saisie du point AFFICHÉ (shownPointId, pas la sélection du Spinner : au changement de point, les
        // champs contiennent encore le point quitté). Un brouillon identique à l'état initial n'est pas gardé.
        fun saveDraftNow() {
            val pointId = shownPointId
            if (formClosed || pointId == null) return
            draftHandler.removeCallbacksAndMessages(null)
            val typedIndex = index.text.toString()
            val typedRemark = remark.text.toString()
            val typedNonBillable = nonFacture.text.toString()
            val cards = draftCards()
            // Saisie inchangée depuis la dernière sauvegarde : on garde l'horodatage (les 3 jours ne se prolongent pas
            // à chaque simple réouverture du point).
            val saved = draftBook.get(pointId)
            if (saved != null && saved.index == typedIndex && saved.remark == typedRemark &&
                saved.nonBillable == typedNonBillable && saved.cards == cards
            ) return
            draftBook.put(pointId, typedIndex, typedRemark, typedNonBillable, cards, readingFormBaseline, System.currentTimeMillis())
            persistDrafts()
        }
        scheduleDraftSave = {
            if (!applyingForm && !formClosed) {
                draftHandler.removeCallbacksAndMessages(null)
                draftHandler.postDelayed({ saveDraftNow() }, 400L)
            }
        }

        fun updateLastReading(position: Int) {
            val point = pointItems.getOrNull(position)?.first
            val last = point?.optJSONObject("dernier_releve")
            invoicesButton.isEnabled = point != null
            indexOldValue = last?.optDouble("nouvel_index", 0.0) ?: 0.0
            pointTitle.text = point?.let { ReadingPointListRules.label(it, idxlsWidth) } ?: "—"
            val rank = "${position + 1} / ${pointItems.size}"
            if (last == null) {
                pointMeta.text = "$rank · aucun relevé précédent : saisissez l'index initial"
                indexMinLabel.text = "premier relevé"
            } else {
                pointMeta.text = "$rank · dernier ${formatNumber(indexOldValue)} · ${displayIsoDate(last.optString("date_releve"))}"
                indexMinLabel.text = "min. ${formatNumber(indexOldValue)}"
            }
            val hasPrevious = position > 0
            val hasNext = position < pointItems.size - 1
            previousPointButton.isEnabled = hasPrevious
            previousPointButton.alpha = if (hasPrevious) 1f else 0.35f
            nextPointButton.isEnabled = hasNext
            nextPointButton.alpha = if (hasNext) 1f else 0.35f
            index.error = null

            // Le code remplit les champs : pas de sauvegarde de brouillon ni d'ouverture automatique en route.
            applyingForm = true
            try {
                index.text.clear()
                remark.text.clear()
                remark.error = null
                nonFacture.setText("0")
                // En mode correction : pré-remplir avec la valeur en queue
                val entry = if (campaignShowDone && point != null) campaignQueuedMap[point.optString("id")] else null
                if (entry != null) {
                    index.setText(formatDecimal(entry.newIndex, 2).replace(',', '.'))
                    if (entry.remark.isNotBlank()) remark.setText(entry.remark)
                    nonFacture.setText(formatDecimal(entry.nonBillable, 2).replace(',', '.'))
                    correctionBadge.text = "✏ Mode correction — relevé du ${displayIsoDate(campaignDate ?: "")}"
                    correctionBadge.visibility = View.VISIBLE
                } else {
                    correctionBadge.visibility = View.GONE
                }
                saveButton.text = saveLabel(entry != null)

                refreshConsumption()
                updatePointEnrichment(position)
                updateBpAlert(position)
                refreshReadingLocation()
                // GPS non capturé automatiquement : l'agent touche le bouton s'il est au point d'eau.
                rebuildSocialCards(point)
                recomputeVolumes()
                // Référence AVANT le brouillon : une fois la saisie restaurée, le formulaire est bien « modifié ».
                // (En correction, c'est la valeur de la file : le brouillon passe devant, la référence reste la file.)
                readingFormBaseline = readingFormSignature()

                val draft = point?.let { draftBook.get(it.optString("id")) }
                if (draft != null) {
                    index.setText(draft.index)
                    remark.setText(draft.remark)
                    nonFacture.setText(draft.nonBillable)
                    // Cartes sociales du brouillon : seules celles encore rattachées au point sont reprises.
                    readingSocialCards.clear()
                    draft.cardsAmong(availableSocialCards.map { it.optString("id") }.toSet()).forEach { saved ->
                        val linked = availableSocialCards.first { it.optString("id") == saved.id }
                        readingSocialCards.add(
                            JSONObject(linked.toString())
                                .put("quantite_bidons", saved.bidons)
                                .put("volume_total", ReadingsRules.socialCardVolume(saved.bidons)),
                        )
                    }
                    renderSocialRows()
                    refreshConsumption()
                    recomputeVolumes()
                }
                draftBadge.visibility = if (draft != null) View.VISIBLE else View.GONE
            } finally {
                applyingForm = false
            }
            shownPointId = point?.optString("id")
            readingCurrentPointId = shownPointId
            detailsSection?.setOpen(detailsShouldOpen())
            refreshDetailsSummary()
        }

        // Changement de point (Spinner, ‹ ›, liste de la tablette) : un seul chemin, qui garde la saisie du point quitté.
        fun showPoint(position: Int) {
            val wantedId = pointItems.getOrNull(position)?.first?.optString("id")
            // Le Spinner notifie aussi sa sélection initiale à la mise en page : même point = rien à refaire.
            if (wantedId == shownPointId) return
            saveDraftNow()
            readingDetailsExpanded = false
            updateLastReading(position)
        }
        fun selectPointAt(position: Int) {
            if (position !in pointItems.indices) return
            pointSpinner.setSelection(position, false)
            showPoint(position)
        }
        // Focus sur l'index ; le clavier système seulement sur téléphone (la tablette a son pavé intégré).
        fun focusIndex(showKeyboard: Boolean) {
            index.requestFocus()
            index.setSelection(index.text.length)
            if (showKeyboard) {
                (getSystemService(INPUT_METHOD_SERVICE) as? android.view.inputmethod.InputMethodManager)
                    ?.showSoftInput(index, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
            }
        }

        pointSpinner.onItemSelectedListener = SimpleItemSelectedListener { position ->
            val changed = pointItems.getOrNull(position)?.first?.optString("id") != shownPointId
            showPoint(position)
            if (changed) {
                // Choix dans la liste déroulante, en bas de page : retour au point et à l'index.
                pageScrollView?.post { pageScrollView?.smoothScrollTo(0, 0) }
                index.post { focusIndex(!twoPane) }
            }
        }
        previousPointButton.setOnClickListener {
            selectPointAt(pointSpinner.selectedItemPosition - 1)
            focusIndex(!twoPane)
        }
        nextPointButton.setOnClickListener {
            selectPointAt(pointSpinner.selectedItemPosition + 1)
            focusIndex(!twoPane)
        }
        // Point à rouvrir en priorité : celui désigné (« Corriger », reconstruction de la page, point suivant) ;
        // sinon le point du brouillon le plus récent (retour dans la campagne, reprise après une mort du processus) ;
        // sinon le premier de la liste.
        val resumePointId = campaignFocusPointId
            ?: draftBook.pointIds().mapNotNull { draftBook.get(it) }.maxByOrNull { it.savedAtMillis }?.pointId
        val startPosition = resumePointId?.let { wanted -> pointItems.indexOfFirst { it.first.optString("id") == wanted } }
            ?.takeIf { it >= 0 } ?: 0
        campaignFocusPointId = null
        if (startPosition > 0) pointSpinner.setSelection(startPosition, false)
        updateLastReading(startPosition)
        readingFormDirty = { readingFormSignature() != readingFormBaseline }
        readingDraftFlush = { saveDraftNow() }
        readingDraftClose = {
            formClosed = true
            draftHandler.removeCallbacksAndMessages(null)
        }

        /** Données validées d'une saisie, prêtes à être mises en file (et éventuellement imprimées). */
        class PreparedReading(
            val point: JSONObject, val payload: JSONObject, val newIndex: Double, val oldIndex: Double,
            val cardsVolume: Double, val nonBillable: Double, val distanceMeters: Float?,
        )

        // Mêmes contrôles pour « Enregistrer » et « Calculer et imprimer » : un seul chemin de validation.
        fun prepareReading(source: View, onReady: (PreparedReading) -> Unit) {
            val point = pointItems.getOrNull(pointSpinner.selectedItemPosition)?.first
            val newIndex = index.text.toString().replace(',', '.').toDoubleOrNull()
            val oldIndex = point?.optJSONObject("dernier_releve")?.optDouble("nouvel_index", 0.0) ?: 0.0
            val nonBillable = nonFacture.text.toString().replace(',', '.').toDoubleOrNull() ?: 0.0
            val allowedIds = availableSocialCards.map { it.optString("id") }.toSet()
            val preparedCards = mg.hydria.shared.rules.readings.SocialCardGateway.prepare(readingSocialCards, allowedIds)
            if (preparedCards.error != null) {
                HydriaFeedback.error()
                HydriaFeedback.shake(source)
                detailsSection?.setOpen(true)
                toast(when (preparedCards.error) {
                    mg.hydria.shared.readings.SocialCardError.INVALID_QUANTITY -> "Saisissez entre 0 et 30 bidons par carte sociale."
                    else -> "Choisissez uniquement des cartes rattachées à ce point."
                })
                return
            }
            val cartesVolume = preparedCards.totalVolume
            // Remarque obligatoire (règle du serveur, qui refuserait sinon le relevé en HTTP 400 à la synchro).
            val validationError = ReadingValidation.validate(point != null, newIndex, oldIndex, nonBillable, cartesVolume, campaignDate)
                ?: newIndex?.let {
                    ReadingValidation.validateRemark(ReadingValidation.consumption(it, oldIndex), nonBillable, remark.text.toString())
                }
            if (validationError != null) {
                HydriaFeedback.error()
                HydriaFeedback.shake(source)
            }
            when (validationError) {
                ReadingError.POINT_REQUIRED -> toast("Sélectionnez un point d'eau")
                ReadingError.INVALID_INDEX -> index.error = "Index invalide"
                ReadingError.INDEX_DECREASED -> index.error = "L'index doit être supérieur ou égal à $oldIndex"
                ReadingError.NEGATIVE_NON_BILLABLE -> {
                    detailsSection?.setOpen(true)
                    nonFacture.error = "Valeur négative interdite"
                }
                ReadingError.NEGATIVE_BILLED_VOLUME -> {
                    detailsSection?.setOpen(true)
                    toast("Volume facturé négatif : réduisez les bidons des cartes sociales ou le volume non facturé.")
                }
                ReadingError.INVALID_CAMPAIGN_DATE -> toast("Date de campagne invalide")
                ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION -> {
                    // La remarque est dans « Plus de détails » : on l'ouvre AVANT de lui donner le focus.
                    detailsSection?.setOpen(true)
                    remark.error = "Remarque obligatoire : consommation nulle"
                    remark.requestFocus()
                }
                ReadingError.REMARK_REQUIRED_NON_BILLABLE -> {
                    detailsSection?.setOpen(true)
                    remark.error = "Remarque obligatoire : volume non facturé renseigné"
                    remark.requestFocus()
                }
                null -> {
                    requireNotNull(point)
                    val pointId = point.getString("id")
                    val enrichment = pointEnrichments[pointId]
                    val payload = JSONObject()
                        .put("point_eau_id", pointId)
                        .put("date_releve", campaignDate)
                        .put("nouvel_index", newIndex)
                        .put("volume_non_facture", nonBillable)
                        .put("remarque", remark.text.toString())
                    val cartesArray = mg.hydria.shared.rules.readings.SocialCardGateway.payload(preparedCards)
                    if (cartesArray.length() > 0) payload.put("cartes_sociales", cartesArray.toString())
                    if (!point.optBoolean("has_coordinates", false) &&
                        enrichment?.gpsQueued != true &&
                        enrichment?.latitude != null &&
                        enrichment.longitude != null
                    ) {
                        payload.put("point_latitude", enrichment.latitude)
                        payload.put("point_longitude", enrichment.longitude)
                    }
                    val agentLocation = readingAgentLocation
                    var distanceMeters: Float? = null
                    if (agentLocation != null) {
                        payload.put("terrain_latitude", agentLocation.latitude)
                            .put("terrain_longitude", agentLocation.longitude)
                            .put("terrain_gps_accuracy_m", agentLocation.accuracy.toDouble())
                            .put("terrain_captured_at", java.time.Instant.now().toString())
                        if (point.optBoolean("has_coordinates")) {
                            val result = FloatArray(1)
                            Location.distanceBetween(agentLocation.latitude, agentLocation.longitude, point.optDouble("latitude"), point.optDouble("longitude"), result)
                            distanceMeters = result[0]
                            payload.put("terrain_distance_point_m", distanceMeters.toDouble())
                        }
                    }
                    onReady(PreparedReading(point, payload, newIndex!!, oldIndex, cartesVolume, nonBillable, distanceMeters))
                }
            }
        }

        // Mise en file locale : la synchronisation (immédiate si en ligne) envoie ensuite au serveur.
        // [reopenKeyboard] faux pour le chemin d'impression 80 mm : le clavier ne doit pas se superposer à l'impression.
        fun commitReading(payload: JSONObject, reopenKeyboard: Boolean = true) {
            val pointId = payload.getString("point_eau_id")
            HydriaFeedback.success()
            HydriaFeedback.pulse(saveButton)
            // En mode correction : supprimer l'ancienne entrée avant de re-enqueuer
            val oldUuid = campaignQueuedMap[pointId]?.uuid
            if (oldUuid != null) store.remove(oldUuid)
            val isCorrection = oldUuid != null

            store.enqueue("reading", payload)
            pointEnrichments.remove(pointId)
            readingAgentLocation = null
            readingSocialCards.clear()
            // Point enregistré : son brouillon est supprimé et plus rien ne doit en recréer un (écriture désarmée).
            formClosed = true
            draftHandler.removeCallbacksAndMessages(null)
            draftBook.remove(pointId)
            persistDrafts()
            readingDraftFlush = null
            readingDraftClose = null
            readingCurrentPointId = null
            // Point suivant : celui qui suit dans l'ordre affiché (parcelle, recherche, « proches de moi »), en
            // sautant les points déjà faits. En correction, retour à la saisie normale sur le premier point restant.
            campaignFocusPointId = if (campaignShowDone) null
            else ReadingNextPoint.after(pointItems.map { it.first.optString("id") }, pointId, donePointIds + pointId)
            readingFocusIndex = reopenKeyboard
            readingDetailsExpanded = false
            readingPickerExpanded = false
            // Une recherche ne sert qu'à trouver ce point : le suivant se prend dans la liste complète.
            campaignSearchQuery = ""
            updateStatus()
            if (isOnline()) synchronize()
            toast(
                if (isCorrection) "Relevé corrigé dans la file d'attente"
                else "Relevé enregistré · ${remaining - 1} point(s) restant(s)"
            )
            // Retourner en mode saisie normale après correction
            if (campaignShowDone) campaignShowDone = false
            renderCurrentScreen()
        }

        fun confirmDistance(distanceMeters: Float?, proceed: () -> Unit) {
            if (distanceMeters != null && distanceMeters > 250) {
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Distance importante")
                    .setMessage("Vous êtes à ${distanceMeters.toInt()} m du point enregistré. Vérifiez que vous avez sélectionné le bon point.")
                    .setNegativeButton("Vérifier", null)
                    .setPositiveButton("Continuer quand même") { _, _ -> proceed() }
                    .show()
            } else proceed()
        }

        saveButton.setOnClickListener {
            prepareReading(saveButton) { reading -> confirmDistance(reading.distanceMeters) { commitReading(reading.payload) } }
        }

        // Calcul de la facture et ticket 80 mm : tout vient de la tournée préchargée, donc sans réseau.
        // Le serveur recalcule le montant à la synchronisation et attribue le numéro officiel.
        val printButton = secondaryButton("Calculer et imprimer (80 mm)").apply {
            contentDescription = "Calculer la facture et l'imprimer sur un ticket 80 millimètres"
        }
        printButton.setOnClickListener {
            prepareReading(printButton) { reading ->
                val pointId = reading.point.getString("id")
                if (campaignQueuedMap[pointId] != null) {
                    // Une facture déjà imprimée ne se réimprime pas par correction : risque de double facturation.
                    toast("Relevé déjà enregistré pour ce point : la facture ne peut plus être imprimée ici.")
                    return@prepareReading
                }
                val localUuid = java.util.UUID.randomUUID().toString()
                val isDirector = store.snapshot?.optJSONObject("utilisateur")?.optBoolean("est_directeur", false) == true
                val outcome = mg.hydria.shared.rules.readings.ReadingTicketGateway.prepare(
                    reading.point, currentOuvrage ?: JSONObject(), isDirector, reading.newIndex, reading.oldIndex,
                    reading.cardsVolume, reading.nonBillable, campaignDate.orEmpty(), localUuid,
                )
                val saveWithoutPrinting = { dialogTitle: String, message: String ->
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle(dialogTitle).setMessage(message)
                        .setNegativeButton("Annuler", null)
                        .setPositiveButton("Enregistrer sans imprimer") { _, _ -> confirmDistance(reading.distanceMeters) { commitReading(reading.payload) } }
                        .show()
                    Unit
                }
                when (outcome) {
                    is mg.hydria.shared.rules.readings.TicketOutcome.Unavailable ->
                        saveWithoutPrinting("Impression impossible", outcome.message)
                    is mg.hydria.shared.rules.readings.TicketOutcome.Blocked -> {
                        val reasons = outcome.reasons.joinToString("\n") {
                            when (it) {
                                mg.hydria.shared.readings.PrintBlock.CONSUMPTION_DEVIATION ->
                                    "• Consommation en écart de ${formatNumber(outcome.deviationPercent ?: 0.0)} % par rapport à la moyenne " +
                                        "(${formatNumber(outcome.mean)} m³) : limite de ±50 %."
                                mg.hydria.shared.readings.PrintBlock.NON_BILLABLE ->
                                    "• Volume non facturé différent de 0 (hors cartes sociales)."
                            }
                        }
                        saveWithoutPrinting("Impression refusée", "$reasons\n\nEnregistrez le relevé sans imprimer : la facture sera imprimée après validation du Directeur.")
                    }
                    is mg.hydria.shared.rules.readings.TicketOutcome.Ready -> {
                        val ticket = outcome.ticket
                        val unpaid = if (ticket.unpaidTotal > 0) {
                            "\nRappel de factures impayées (non incluses) : ${mg.hydria.shared.readings.ReadingTicketFormat.amount(ticket.unpaidTotal)} Ar"
                        } else ""
                        AlertDialog.Builder(this@MainActivity)
                            .setTitle("Facture à imprimer")
                            .setMessage(
                                "${ticket.pointName}\nVolume facturé : ${mg.hydria.shared.readings.ReadingTicketFormat.quantity(ticket.billedVolume)} m³\n" +
                                    "TOTAL À PAYER : ${mg.hydria.shared.readings.ReadingTicketFormat.amount(outcome.total)} Ar$unpaid\n\n" +
                                    "Le relevé sera enregistré (ticket n° ${ticket.invoiceNumber}, provisoire jusqu'à la synchronisation)."
                            )
                            .setNegativeButton("Annuler", null)
                            .setPositiveButton("Enregistrer et imprimer") { _, _ ->
                                confirmDistance(reading.distanceMeters) {
                                    reading.payload.put("local_uuid", localUuid)
                                        .put("montant", outcome.total)
                                        .put("ticket_local", 1)
                                    lastReadingTicket = ticket
                                    commitReading(reading.payload, reopenKeyboard = false)
                                    printLastTicket()
                                }
                            }
                            .show()
                    }
                }
            }
        }
        val reprintButton = secondaryButton("Réimprimer le dernier ticket").apply {
            visibility = if (lastReadingTicket != null) View.VISIBLE else View.GONE
            setOnClickListener { printLastTicket() }
        }

        // ── Page : point, saisie, détails, choix du point. Les deux boutons d'enregistrement vivent dans la barre
        // fixe du bas (HydriaUi.actionBar), toujours visibles, sans défiler. ──
        page.addView(pointHeader, matchWrap(top = 10))
        page.addView(bpAlertCard, matchWrap(top = 8))
        page.addView(correctionBadge, matchWrap(top = 6))
        page.addView(draftBadge, matchWrap(top = 6))
        page.addView(indexCard, matchWrap(top = 10))
        page.addView(volumeFactureInfo, matchWrap(top = 8))
        if (twoPane) {
            // Pavé numérique 3×4 intégré : pas de clavier système en tablette.
            fun insertIndex(s: String) {
                if (s == "," && (index.text.contains(',') || index.text.contains('.'))) return
                val a = index.selectionStart.coerceAtLeast(0)
                val b = index.selectionEnd.coerceAtLeast(a)
                index.text.replace(a, b, s)
                index.setSelection((a + s.length).coerceAtMost(index.text.length))
            }
            fun deleteIndex() {
                val a = index.selectionStart
                val b = index.selectionEnd
                when {
                    a != b -> { val lo = minOf(a, b); index.text.replace(lo, maxOf(a, b), ""); index.setSelection(lo) }
                    a > 0 -> { index.text.replace(a - 1, a, ""); index.setSelection(a - 1) }
                }
            }
            page.addView(numericKeypad({ insertIndex(it) }, { deleteIndex() }), matchWrap(top = 10))
        }

        // « Plus de détails » : remarque, volume non facturé, cartes sociales, GPS, fiche du point, anciennes factures.
        detailsContent.addView(remarkLabel, matchWrap())
        detailsContent.addView(remark, matchWrap(56))
        detailsContent.addView(nonFactureLabel, matchWrap())
        detailsContent.addView(nonFacture, matchWrap(56))
        detailsContent.addView(socialCard, matchWrap(top = 12))
        detailsContent.addView(gpsBlock, matchWrap(top = 12))
        detailsContent.addView(enrichmentCard, matchWrap(top = 10))
        detailsContent.addView(invoicesButton, matchWrap(52, top = 10))
        detailsContent.addView(reprintButton, matchWrap(48, top = 6))
        val detailsPanel = HydriaUi.collapsible(this, "Plus de détails", "", detailsShouldOpen(), detailsContent)
            .apply { onToggle = { readingDetailsExpanded = it } }
        detailsSection = detailsPanel
        refreshDetailsSummary = {
            val parts = mutableListOf<String>()
            if (remarkRequiredNow && remark.text.isBlank()) parts.add("Remarque obligatoire")
            else if (remark.text.isNotBlank()) parts.add("Remarque saisie")
            val nonBillableValue = nonFacture.text.toString().replace(',', '.').toDoubleOrNull() ?: 0.0
            if (nonBillableValue != 0.0) parts.add("Non facturé ${formatNumber(nonBillableValue)} m³")
            if (socialCard.visibility == View.VISIBLE) {
                parts.add(when (readingSocialCards.size) {
                    0 -> "Cartes sociales"
                    1 -> "1 carte"
                    else -> "${readingSocialCards.size} cartes"
                })
            }
            if (enrichmentCard.visibility == View.VISIBLE) parts.add("Fiche à compléter")
            detailsPanel.setSummary(parts.joinToString(" · "))
        }
        refreshDetailsSummary()
        page.addView(detailsPanel, matchWrap(top = 12))
        page.addView(pickerSection, matchWrap(top = 10))

        // ── Barre fixe : « Enregistrer · point suivant » en principal, impression 80 mm en secondaire. L'emplacement
        // libre de la barre (bannerSlot) est réservé à la bannière « Annuler » du chantier L2-2. ──
        saveButton.minHeight = dp(56)
        saveButton.minimumHeight = dp(56)
        printButton.minHeight = dp(48)
        printButton.minimumHeight = dp(48)
        val actionBar = HydriaUi.actionBar(this)
        actionBar.addButton(saveButton)
        actionBar.addButton(printButton)
        val pageScroll = scroll(page)
        pageScrollView = pageScroll
        val formColumn = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(pageScroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(actionBar, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }

        if (twoPane) {
            // Volet gauche : la liste des points de la campagne remplace le déroulant.
            pointSpinner.visibility = View.GONE
            val listRoot = vertical(padding = 14).apply { setBackgroundColor(HydriaColors.background) }
            listRoot.addView(HydriaUi.overline(this, "POINTS DE LA CAMPAGNE · $completed / $total"))
            // Même parcelle que le filtre ; en mode « points proches », les points de la liste d'abord.
            val parcelPoints = ReadingPointListRules.filterBySearch(
                ReadingPointListRules.filterByParcel(allActivePoints.map { it.first }, campaignParcelId),
                idxlsWidth, campaignSearchQuery,
            ).map { it.optString("id") }.toSet()
            val listedIds = pointItems.map { it.first.optString("id") }
            allActivePoints.filter { it.first.optString("id") in parcelPoints }
                .sortedBy { entry -> listedIds.indexOf(entry.first.optString("id")).let { if (it < 0) Int.MAX_VALUE else it } }
                .forEachIndexed { _, entryPair ->
                val pt = entryPair.first
                val pid = pt.optString("id")
                val savedValue = campaignQueuedMap[pid]?.newIndex
                val rowView = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    setPadding(dp(12), dp(12), dp(12), dp(12))
                    HydriaUi.card(this)
                    isClickable = true
                    isFocusable = true
                    if (savedValue != null) alpha = 0.55f
                    setOnClickListener {
                        val pos = pointItems.indexOfFirst { it.first.optString("id") == pid }
                        if (pos >= 0) {
                            selectPointAt(pos)
                            focusIndex(showKeyboard = false)
                        } else if (!campaignShowDone) { campaignShowDone = true; renderCurrentScreen() }
                    }
                }
                rowView.addView(text(ReadingPointListRules.label(pt, idxlsWidth), 13.5f, true, HydriaColors.text),
                    LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                rowView.addView(TextView(this).apply {
                    text = savedValue?.let { formatNumber(it) } ?: "—"
                    typeface = HydriaType.numeral(700)
                    textSize = 13f
                    setTextColor(if (savedValue != null) HydriaColors.success else HydriaColors.textMuted)
                })
                listRoot.addView(rowView, matchWrap(top = 8))
            }
            content.addView(scroll(listRoot))
            detailPane!!.removeAllViews()
            detailPane!!.addView(formColumn, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        } else {
            content.addView(formColumn, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        }
        // Focus sur le nouvel index : ouverture de la campagne, après un enregistrement, depuis « Corriger ».
        // Jamais lors d'une reconstruction causée par la recherche (elle garde le focus), ni après une impression.
        if (focusIndexRequested && !searchRefocusing) index.post { focusIndex(!twoPane) }
    }

    /**
     * Bloc GPS du relevé : position de l'agent (précision, distance au point) et bouton de capture, optionnels.
     * Isolé dans cette fonction pour que le chantier L2-6 le remplace par la feuille de capture partagée sans
     * toucher au formulaire. [currentPoint] donne le point affiché ; retourne la vue et la fonction qui
     * rafraîchit son texte (appelée au changement de point et à la fin d'une capture).
     */
    private fun buildReadingGpsBlock(currentPoint: () -> JSONObject?): Pair<View, () -> Unit> {
        // GPS — capture optionnelle : l'agent peut saisir des relevés loin du point d'eau, auquel cas la position
        // n'apporte rien. Rien n'est capturé automatiquement ; l'agent touche le bouton s'il est au point.
        val info = text("Position GPS non capturée (optionnel). Touchez le bouton si vous êtes au point d'eau.", 13f, true, HydriaColors.textSecondary).apply {
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.surface, 14f, HydriaColors.outline)
        }
        val capture = secondaryButton("Capturer ma position GPS (optionnel)")
        capture.setOnClickListener {
            currentPoint()?.optString("id")?.takeIf { it.isNotBlank() }?.let { captureReadingAgentLocation(it) }
        }
        val refresh: () -> Unit = {
            val location = readingAgentLocation
            val point = currentPoint()
            if (location == null) {
                info.text = "Position GPS non capturée (optionnel). Touchez le bouton si vous êtes au point d'eau."
            } else {
                var distance: Float? = null
                if (point != null && point.optBoolean("has_coordinates")) {
                    val result = FloatArray(1)
                    Location.distanceBetween(location.latitude, location.longitude, point.optDouble("latitude"), point.optDouble("longitude"), result)
                    distance = result[0]
                }
                info.text = buildString {
                    append("GPS agent ±${location.accuracy.toInt()} m")
                    if (distance != null) append(" · distance du point ${distance.toInt()} m")
                    if (distance != null && distance > 250) append("\nAttention : vérifiez le point sélectionné.")
                }
            }
        }
        val block = vertical().apply {
            addView(info, matchWrap())
            addView(capture, matchWrap(48, top = 6))
        }
        return block to refresh
    }

    /** Position du téléphone pour le mode « points proches » du relevé (réutilise la position Terrain). */
    private fun requestNearbyLocation() {
        pendingNearbyLocation = true
        pendingLocationPointId = "nearby"
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) acquirePointLocation("nearby")
        else locationPermissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
    }

    /** Téléphone de l'abonné manquant : saisi pendant le relevé, envoyé comme mise à jour du point d'eau. */
    private fun showReadingPhoneForm(point: JSONObject, onSaved: () -> Unit) {
        val pointId = point.optString("id").takeIf { it.isNotBlank() } ?: return
        val phone = field("Ex. 034 12 345 67").apply {
            inputType = InputType.TYPE_CLASS_PHONE
            setText(point.optString("telephone"))
        }
        val dialog = AlertDialog.Builder(this)
            .setTitle("Téléphone de l'abonné")
            .setMessage(point.optString("nom").takeUnless { it.isBlank() || it == "N/A" } ?: "Point d'eau")
            .setView(vertical(padding = 18).apply { addView(phone, matchWrap(56)) })
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Enregistrer", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val value = phone.text.toString().trim()
                val digits = value.count { it.isDigit() }
                if (digits < 9 || digits > 13 || value.length > 20) {
                    phone.error = "Numéro invalide (9 à 13 chiffres)"
                    return@setOnClickListener
                }
                store.enqueue("terrain_data", JSONObject()
                    .put("operation_type", "update_point")
                    .put("point_id", pointId)
                    .put("telephone", value)
                    .put("base_updated_at", mg.hydria.shared.rules.terrain.TerrainEditRules.baseVersion(
                        store.pending(), "point_eau", pointId, point.optString("updated_at"))))
                pointEnrichments.getOrPut(pointId) { PointEnrichment() }.phoneQueued = true
                TerrainRepository.applyLocalReadingPointEnrichment(store, pointId, telephone = value)
                point.put("telephone", value)
                updateStatus()
                dialog.dismiss()
                toast("Téléphone enregistré · ${store.pendingCount()} action(s) en attente.")
                onSaved()
                if (isOnline()) synchronize()
            }
        }
        dialog.show()
    }

    private fun showPointInvoices(point: JSONObject) {
        if (!isOnline()) {
            val cached = point.optJSONArray("historique_recent") ?: JSONArray()
            showInvoicesDialog(
                point = point,
                invoices = cached,
                total = cached.length(),
                truncated = false,
                offline = true,
            )
            return
        }

        val token = store.token ?: return
        val progress = AlertDialog.Builder(this)
            .setTitle("Anciennes factures")
            .setMessage("Chargement en cours…")
            .setCancelable(false)
            .create()
        progress.show()
        executor.execute {
            val result = runCatching { HydriaNetwork.pointInvoices(token, point.getString("id")) }
            runOnUiThread {
                progress.dismiss()
                result.onSuccess { response ->
                    if (response.successful) {
                        showInvoicesDialog(
                            point = response.body.optJSONObject("point_eau") ?: point,
                            invoices = response.body.optJSONArray("factures") ?: JSONArray(),
                            total = response.body.optInt("total", 0),
                            truncated = response.body.optBoolean("tronque", false),
                            offline = false,
                        )
                    } else {
                        toast("Factures indisponibles : ${response.error}")
                    }
                }.onFailure { toast("Factures indisponibles : ${it.message ?: "erreur réseau"}") }
            }
        }
    }

    private fun showInvoicesDialog(
        point: JSONObject,
        invoices: JSONArray,
        total: Int,
        truncated: Boolean,
        offline: Boolean,
    ) {
        val page = vertical(padding = 14)
        val pointLabel = listOf(point.optString("code"), point.optString("nom"))
            .filter { it.isNotBlank() }.joinToString(" · ")
        page.addView(text(pointLabel.ifBlank { "Point d’eau" }, 17f, true, HydriaColors.text))
        page.addView(subtitle(when {
            offline -> "Mode hors ligne : ${invoices.length()} facture(s) récemment préchargée(s)."
            truncated -> "${invoices.length()} facture(s) affichée(s) sur $total."
            else -> "$total facture(s)."
        }))

        if (invoices.length() == 0) {
            page.addView(emptyState("Aucune facture", "Aucune ancienne facture n’est disponible pour ce point d’eau."))
        } else {
            for (position in 0 until invoices.length()) {
                val invoice = invoices.optJSONObject(position) ?: continue
                val pointed = invoice.optBoolean("pointee", false)
                val amount = if (invoice.isNull("montant")) "Montant non calculé"
                    else "${formatNumber(invoice.optDouble("montant", 0.0))} Ar"
                val number = invoice.optString("numero_facture").ifBlank { "Facture sans numéro" }
                val invoiceCard = card()
                invoiceCard.addView(text(number, 16f, true, HydriaColors.text))
                invoiceCard.addView(text(
                    "${displayIsoDate(invoice.optString("date_releve"))} · $amount",
                    13f, false, HydriaColors.textSecondary,
                ))
                invoiceCard.addView(text(
                    "Index ${formatNumber(invoice.optDouble("ancien_index", 0.0))} → ${formatNumber(invoice.optDouble("nouvel_index", 0.0))} · Volume ${formatNumber(invoice.optDouble("consommation", 0.0))} m³",
                    12f, false, HydriaColors.textSecondary,
                ))
                val diamex = invoice.optString("numero_diamex")
                invoiceCard.addView(text(
                    if (pointed) "POINTÉE${if (diamex.isNotBlank()) " · DiameX $diamex" else ""}" else "NON POINTÉE",
                    13f,
                    true,
                    if (pointed) HydriaColors.success else HydriaColors.warning,
                ))
                page.addView(invoiceCard, matchWrap(top = 10))
            }
        }
        AlertDialog.Builder(this)
            .setTitle("Anciennes factures")
            .setView(scroll(page))
            .setPositiveButton("Fermer", null)
            .show()
    }

    private fun renderRepairs() {
        val repairs = RepairsRepository.list(store)
        if (repairs == null) {
            content.addView(emptyState("Réparations indisponibles", "Préchargez une tournée pour les consulter hors ligne."))
            return
        }
        val allRepairItems = jsonObjects(repairs)
        val pendingCompletionIds = RepairRules.pendingCompletionIds(store.pending())
        val repairItems = mg.hydria.shared.rules.repairs.RepairOverviewGateway.visible(
            allRepairItems, pendingCompletionIds, showCompletedRepairs, showRepairsOutsidePerimeter)
        val page = vertical(padding = 18)
        page.addView(title(if (showCompletedRepairs) "Réparations" else "Réparations à faire"))
        page.addView(subtitle("Les ouvrages les plus critiques apparaissent en premier."))
        page.addView(primaryButton("Nouvelle réparation").apply {
            setOnClickListener { showPlanningEditor(isRepair = true, existing = null) }
        }, matchWrap(54, top = 4))
        page.addView(card().apply {
            addView(text("OPTIONS D’AFFICHAGE", 11f, true, HydriaColors.cyan))
            addView(SwitchCompat(this@MainActivity).apply {
                text = "Afficher les ouvrages hors de mon périmètre"
                setTextColor(HydriaColors.text)
                textSize = 14f
                isChecked = showRepairsOutsidePerimeter
                setPadding(0, dp(8), 0, dp(4))
                setOnCheckedChangeListener { _, checked ->
                    showRepairsOutsidePerimeter = checked
                    renderCurrentScreen()
                }
            }, matchWrap())
            addView(SwitchCompat(this@MainActivity).apply {
                text = "Afficher les réparations terminées"
                setTextColor(HydriaColors.text)
                textSize = 14f
                isChecked = showCompletedRepairs
                setPadding(0, dp(4), 0, 0)
                setOnCheckedChangeListener { _, checked ->
                    showCompletedRepairs = checked
                    renderCurrentScreen()
                }
            }, matchWrap())
        }, matchWrap(top = 12))
        repairModel.filters.replaceItems(repairItems, HydriaDates.today().toString())
        addSharedFilters(page, repairModel.filters, collapsedByDefault = true) { target, filtered ->
            val overview = mg.hydria.shared.rules.repairs.RepairOverviewGateway.prepare(filtered, pendingCompletionIds)
            val repairGroups = overview.groups
            val completedCount = overview.completedCount
            val countLabel = if (showCompletedRepairs) {
                "${filtered.size} réparation(s), dont $completedCount terminée(s) · ${repairGroups.size} ouvrage(s)."
            } else {
                "${filtered.size} réparation(s) à faire · ${repairGroups.size} ouvrage(s)."
            }
            target.addView(subtitle(countLabel))
            if (filtered.isEmpty()) {
                val message = if (repairItems.isEmpty() && !showCompletedRepairs) {
                    "Toutes les interventions synchronisées sont terminées."
                } else {
                    "Aucune intervention ne correspond aux options et filtres sélectionnés."
                }
                target.addView(emptyState(if (repairItems.isEmpty()) "Tout est à jour" else "Aucune réparation", message))
            }
            val sections = mutableListOf<View>()
            repairGroups.forEach { group ->
                val orderedRepairs = group.items
                val criticalRepair = orderedRepairs.first()
                val workSection = card(emphasized = true)
                workSection.contentDescription = "Ouvrage ${criticalRepair.optString("ouvrage_nom", "Sans ouvrage")}, ${orderedRepairs.size} réparation(s)"
                workSection.addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(vertical().apply {
                        addView(text("OUVRAGE", 11f, true, HydriaColors.cyan))
                        addView(text(criticalRepair.optString("ouvrage_nom", "Sans ouvrage"), 21f, true, HydriaColors.text), matchWrap(top = 4))
                    }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                    addView(HydriaUi.badge(this@MainActivity, "${orderedRepairs.size} INTERVENTION${if (orderedRepairs.size > 1) "S" else ""}", Tone.INFO), wrapWrap())
                })
                val location = listOf(
                    criticalRepair.optString("commune"),
                    criticalRepair.optString("district"),
                    criticalRepair.optString("region"),
                ).filter { it.isNotBlank() }.joinToString(" · ")
                if (location.isNotBlank()) {
                    workSection.addView(text(location, 13f, false, HydriaColors.textSecondary), matchWrap(top = 6))
                }
                if (criticalRepair.optBoolean("hors_perimetre")) {
                    workSection.addView(
                        HydriaUi.badge(this@MainActivity, "HORS PÉRIMÈTRE · CONSULTATION", Tone.WARNING),
                        wrapWrap(top = 8),
                    )
                }
                workSection.addView(text(
                    "À traiter en premier · ${RepairRules.activityLabel(criticalRepair)}",
                    13f,
                    true,
                    RepairRules.priorityColor(criticalRepair),
                ), matchWrap(top = 9))
                orderedRepairs.forEach { repair ->
                    val completed = RepairRules.isCompleted(repair) || repair.optString("id") in pendingCompletionIds
                    workSection.addView(repairActivityCard(repair, completed), matchWrap(top = 12))
                }
                sections.add(workSection)
            }
            addInColumns(target, sections, paneColumns(), gap = 12)
        }
        content.addView(scroll(page))
    }

    private fun repairActivityCard(repair: JSONObject, completed: Boolean): View {
        val outsidePerimeter = repair.optBoolean("hors_perimetre")
        val tone = when {
            completed -> Tone.SUCCESS
            outsidePerimeter -> Tone.NEUTRAL
            else -> RepairRules.priorityTone(repair)
        }
        // « 224 j » + RETARD, « AUJ. » ou « dans 5 j » : calculé dans shared, plus de signe négatif.
        val overdueLabel = RepairRules.overdueLabel(repair)

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            HydriaUi.accentedCard(this, tone)
            if (completed) alpha = 0.75f
        }

        val topRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        // Colonne du chiffre principal : retard en jours. Largeur libre (au moins 46 dp) pour que
        // « 224 j » reste sur une ligne ; l'autosize ne rétrécit que si la place manque (REP_PLAN-11).
        topRow.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            minimumWidth = dp(46)
            addView(TextView(this@MainActivity).apply {
                val late = !completed && overdueLabel?.late == true
                text = when {
                    completed -> "✓"
                    overdueLabel == null -> "—"
                    else -> overdueLabel.value
                }
                typeface = if (completed) HydriaType.display(700) else HydriaType.numeral(700)
                // « dans 5 j » et « AUJ. » sont secondaires : plus petits que le retard, qui doit sauter aux yeux.
                textSize = when {
                    completed -> 18f
                    late -> 22f
                    else -> 15f
                }
                letterSpacing = -0.03f
                gravity = Gravity.CENTER
                maxLines = 1
                minWidth = dp(46)
                setTextColor(when {
                    completed -> HydriaColors.successText
                    late -> HydriaColors.errorText
                    else -> HydriaColors.textSecondary
                })
                // Après textSize : l'autosize l'ignore une fois activé.
                if (!completed) TextViewCompat.setAutoSizeTextTypeUniformWithConfiguration(
                    this, 14, if (late) 22 else 15, 1, TypedValue.COMPLEX_UNIT_SP)
            })
            if (!completed && overdueLabel != null && overdueLabel.caption.isNotBlank()) addView(TextView(this@MainActivity).apply {
                text = overdueLabel.caption
                typeface = HydriaType.display(600)
                textSize = 9.5f
                letterSpacing = 0.06f
                maxLines = 1
                setTextColor(if (overdueLabel.late) HydriaColors.errorText else HydriaColors.textSecondary)
            })
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        val body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        body.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(text(RepairRules.activityLabel(repair), 16f, true, HydriaColors.text),
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(HydriaUi.badge(this@MainActivity, RepairRules.priorityLabel(repair), RepairRules.priorityTone(repair)))
        })
        addDuplicateBadges(body, repair)
        body.addView(text(
            "${repair.optString("statut", "En cours")} · ${repair.optString("date_prevue_display").ifBlank { displayIsoDate(repair.optString("date_prevue")) }}",
            12.5f, false, HydriaColors.textSecondary,
        ), matchWrap(top = 5))
        repair.optJSONArray("composants")?.let { array ->
            (0 until array.length()).mapNotNull { array.optJSONObject(it)?.optString("nom")?.takeIf { name -> name.isNotBlank() } }
        }?.takeIf { it.isNotEmpty() }?.let { names ->
            body.addView(text("Composants : ${names.joinToString(", ")}", 12.5f, true, HydriaColors.textSecondary), matchWrap(top = 5))
        }
        val assignment = listOf(repair.optString("assigne_a"), repair.optString("participants"))
            .filter { it.isNotBlank() }.joinToString(" · ")
        if (assignment.isNotBlank()) body.addView(text("Équipe : $assignment", 12f, false, HydriaColors.textSecondary), matchWrap(top = 5))
        repair.optString("remarque").takeIf { it.isNotBlank() }?.let {
            body.addView(text("Remarque : $it", 12f, false, HydriaColors.textSecondary), matchWrap(top = 5))
        }
        repair.optString("suite_a_donner").takeIf { it.isNotBlank() }?.let {
            body.addView(text("Suite : $it", 12f, false, HydriaColors.textSecondary), matchWrap(top = 5))
        }
        val photoCount = repair.optInt("nb_photos") + (repairPhotoQueuedCounts[repair.optString("id")] ?: 0)
        val resources = listOf(
            repair.optInt("nb_details").takeIf { it > 0 }?.let { "$it détail(s)" },
            repair.optInt("nb_livraisons").takeIf { it > 0 }?.let { "$it livraison(s)" },
            photoCount.takeIf { it > 0 }?.let { "$it photo(s)" },
        ).filterNotNull().joinToString(" · ")
        if (resources.isNotBlank()) body.addView(text(resources, 12f, false, HydriaColors.textSecondary), matchWrap(top = 6))
        topRow.addView(body, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
            marginStart = dp(12)
        })
        container.addView(topRow)

        when {
            outsidePerimeter -> container.addView(
                text("Consultation uniquement : cet ouvrage est hors de votre périmètre.", 12f, true, HydriaColors.warning),
                matchWrap(top = 10),
            )
            completed -> {
                container.addView(
                    text("Terminée · part à la prochaine synchronisation", 12f, true, HydriaColors.success),
                    matchWrap(top = 10),
                )
                // Une réparation terminée reste complétable : photos preuve, date, employé, remarque.
                addRepairExtraButtons(container, repair)
            }
            else -> {
                container.addView(Button(this).apply {
                    text = "✓ Marquer terminée"
                    HydriaUi.primaryButton(this, HydriaColors.cyan)
                    setOnClickListener {
                        AlertDialog.Builder(this@MainActivity)
                            .setTitle("Confirmer la réparation")
                            .setMessage("Marquer cette intervention comme terminée ?")
                            .setNegativeButton("Annuler", null)
                            .setPositiveButton("Terminer") { _, _ ->
                                HydriaFeedback.success()
                                RepairsRepository.enqueueFinish(store, repair.getString("id"))
                                toast("Action enregistrée${if (isOnline()) " et en cours d’envoi" else " hors connexion"}")
                                updateStatus()
                                renderCurrentScreen()
                                if (isOnline()) synchronize()
                            }.show()
                    }
                }, matchWrap(52, top = 12))
                addRepairExtraButtons(container, repair)
            }
        }
        return container
    }

    private fun addRepairExtraButtons(container: LinearLayout, repair: JSONObject) {
        container.addView(Button(this).apply {
            text = "📷 Ajouter des photos"
            HydriaUi.secondaryButton(this)
            setOnClickListener { chooseRepairPhotoSource(repair.getString("id")) }
        }, matchWrap(48, top = 8))
        container.addView(Button(this).apply {
            text = "Modifier"
            HydriaUi.secondaryButton(this)
            setOnClickListener { showPlanningEditor(isRepair = true, existing = repair) }
        }, matchWrap(48, top = 8))
    }

    private fun renderPlannings() {
        val plannings = PlanningsRepository.list(store)
        if (plannings == null) {
            content.addView(emptyState("Plannings indisponibles", "Préchargez une tournée pour les consulter hors ligne."))
            return
        }
        val planningItems = jsonObjects(plannings).sortedBy(PlanningRules::dateKey)
        planningModel.replaceItems(planningItems, HydriaDates.today().toString())
        val screen = vertical().apply { setBackgroundColor(HydriaColors.background) }
        screen.addView(vertical(padding = 18).apply {
            addView(title("Agenda terrain"))
            addView(subtitle("Vos rendez-vous regroupés par date, disponibles même hors connexion."))
            // Pointage GPS du jour, directement depuis l'agenda.
            addView(planningPointageCard(), matchWrap(top = 2))
            addView(primaryButton("Nouveau planning").apply {
                setOnClickListener { showPlanningEditor(isRepair = false, existing = null) }
            }, matchWrap(54, top = 10))
        }, matchWrap())

        val dateRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(14), dp(9), dp(14), dp(9))
        }
        val dateScroller = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            setBackgroundColor(HydriaColors.backgroundDeep)
            addView(dateRow)
            contentDescription = "Navigation par date"
        }
        screen.addView(dateScroller, matchWrap())

        val body = vertical(padding = 18)
        val planningScroll = scroll(body)
        screen.addView(planningScroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))

        val sectionViews = linkedMapOf<String, View>()
        val dateButtons = linkedMapOf<String, Pair<LinearLayout, (Boolean) -> Unit>>()
        val dateStates = linkedMapOf<String, PlanningDayState>()
        var selectedDate = ""
        var ignoreScrollSelectionUntil = 0L

        fun topInsideScroll(view: View): Int {
            var y = view.top
            var parent = view.parent
            while (parent is View && parent !== planningScroll) {
                y += parent.top
                parent = parent.parent
            }
            return y
        }

        fun selectDate(dateKey: String, centerChip: Boolean = true) {
            if (dateKey.isBlank() || selectedDate == dateKey) return
            selectedDate = dateKey
            planningModel.selectDate(dateKey)
            dateButtons.forEach { (key, cell) -> cell.second(key == dateKey) }
            if (centerChip) {
                dateButtons[dateKey]?.first?.let { chip ->
                    dateScroller.post {
                        val targetX = (chip.left - (dateScroller.width - chip.width) / 2).coerceAtLeast(0)
                        dateScroller.smoothScrollTo(targetX, 0)
                    }
                }
            }
        }

        planningScroll.setOnScrollChangeListener { _, _, scrollY, _, _ ->
            if (System.currentTimeMillis() < ignoreScrollSelectionUntil || sectionViews.isEmpty()) return@setOnScrollChangeListener
            val anchor = scrollY + dp(36)
            val visibleDate = sectionViews.entries.lastOrNull { topInsideScroll(it.value) <= anchor }?.key
                ?: sectionViews.keys.first()
            selectDate(visibleDate)
        }

        addSharedFilters(body, planningModel, collapsedByDefault = true) { target, filtered ->
            sectionViews.clear()
            dateButtons.clear()
            dateStates.clear()
            dateRow.removeAllViews()
            target.addView(subtitle("${filtered.size} planning(s) affiché(s) sur ${planningItems.size}."))
            if (filtered.isEmpty()) {
                selectedDate = ""
                target.addView(emptyState("Aucun planning", "Aucune activité ne correspond aux filtres sélectionnés."))
                return@addSharedFilters
            }

            val agenda = planningModel.state.agenda
            agenda.days.forEach { day ->
                val dateKey = day.dateKey
                val dayPlannings = day.items
                val dayState = day.state
                dateStates[dateKey] = dayState
                val indicators = PlanningRules.dayIndicatorText(dayState)
                val cell = planningDayCell(dateKey, dayPlannings.size, dayState) {
                    sectionViews[dateKey]?.let { section ->
                        selectDate(dateKey)
                        ignoreScrollSelectionUntil = System.currentTimeMillis() + 700L
                        planningScroll.smoothScrollTo(0, (topInsideScroll(section) - dp(10)).coerceAtLeast(0))
                    }
                }
                cell.first.contentDescription = buildString {
                    append("${PlanningRules.fullDateLabel(dateKey)}, ${dayPlannings.size} planning(s)")
                    if (indicators.isNotBlank()) append(", $indicators")
                }
                dateButtons[dateKey] = cell
                dateRow.addView(cell.first, LinearLayout.LayoutParams(dp(52), dp(64)).apply { marginEnd = dp(8) })

                val section = card(emphasized = true)
                section.contentDescription = "Planning du ${PlanningRules.fullDateLabel(dateKey)}"
                section.addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    addView(vertical().apply {
                        addView(text(PlanningRules.weekdayLabel(dateKey), 11f, true, HydriaColors.cyan))
                        addView(text(PlanningRules.fullDateLabel(dateKey), 20f, true, HydriaColors.text), matchWrap(top = 4))
                    }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                    addView(vertical().apply {
                        gravity = Gravity.END
                        addView(HydriaUi.badge(this@MainActivity, "${dayPlannings.size} RDV", Tone.INFO), wrapWrap())
                        if (dayState.isHoliday) {
                            addView(HydriaUi.badge(this@MainActivity, "Jour férié", Tone.WARNING), wrapWrap(top = 5))
                        }
                        if (dayState.isWeekend) {
                            addView(HydriaUi.badge(this@MainActivity, "Week-end", Tone.INFO), wrapWrap(top = 5))
                        }
                    }, wrapWrap())
                })
                dayPlannings.forEach { planning -> section.addView(planningAgendaCard(planning), matchWrap(top = 12)) }
                sectionViews[dateKey] = section
                target.addView(section, matchWrap(top = 12))
            }

            val nextSelected = agenda.selectedDate
            selectedDate = ""
            selectDate(nextSelected)
        }
        content.addView(screen)
    }

    /** Case de jour du bandeau (52 × 64 dp) : abrév. + numéro monospace + puce de charge. */
    private fun planningDayCell(
        dateKey: String,
        count: Int,
        state: PlanningDayState,
        onClick: () -> Unit,
    ): Pair<LinearLayout, (Boolean) -> Unit> {
        val weekday = TextView(this).apply {
            text = PlanningRules.shortWeekdayLabel(dateKey)
            textSize = 10f
            typeface = HydriaType.display(600)
            gravity = Gravity.CENTER
            includeFontPadding = false
        }
        val day = TextView(this).apply {
            text = PlanningRules.dayNumberLabel(dateKey)
            textSize = 20f
            typeface = HydriaType.numeral(700)
            letterSpacing = -0.03f
            gravity = Gravity.CENTER
            includeFontPadding = false
        }
        val loadColor = when {
            count >= 3 -> HydriaColors.warning
            count >= 1 -> HydriaColors.cyan
            else -> HydriaColors.outline
        }
        val pip = View(this).apply { background = HydriaUi.rounded(this@MainActivity, loadColor, 3f) }
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            isClickable = true
            isFocusable = true
            setPadding(0, dp(6), 0, dp(6))
            addView(weekday, LinearLayout.LayoutParams(-1, -2))
            addView(day, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(1) })
            addView(pip, LinearLayout.LayoutParams(dp(5), dp(5)).apply { topMargin = dp(3) })
            setOnClickListener { onClick() }
        }
        val restyle: (Boolean) -> Unit = { selected ->
            container.background = HydriaUi.rounded(
                this,
                if (selected) HydriaColors.cyan else HydriaColors.surface,
                14f,
                if (selected) HydriaColors.cyan else HydriaColors.outline,
            )
            container.isSelected = selected
            weekday.setTextColor(if (selected) HydriaColors.onAccent else HydriaColors.textMuted)
            day.setTextColor(when {
                selected -> HydriaColors.onAccent
                state.isHoliday -> HydriaColors.warning
                state.isWeekend -> HydriaColors.textMuted
                else -> HydriaColors.text
            })
        }
        restyle(false)
        return container to restyle
    }

    /** Filet de couleur d'une carte d'activité selon son type. */
    private fun planningActivityTone(planning: JSONObject): Tone = when (PlanningRules.activityKind(planning)) {
        mg.hydria.shared.planning.PlanningActivityKind.VALIDATED -> Tone.SUCCESS
        mg.hydria.shared.planning.PlanningActivityKind.REPAIR -> Tone.ERROR
        mg.hydria.shared.planning.PlanningActivityKind.REST -> Tone.NEUTRAL
        mg.hydria.shared.planning.PlanningActivityKind.OTHER -> Tone.INFO
    }

    /**
     * Compteur de doublons (réparation / réhabilitation / maçonnerie) : interventions déjà réalisées
     * sur la même cible avec la même activité, calculé par le serveur au moment de la synchronisation.
     * Absent du JSON pour les autres types d'activité : rien n'est alors affiché.
     */
    private fun addDuplicateBadges(parent: LinearLayout, item: JSONObject, top: Int = 6) {
        val duplicates = item.optJSONObject("doublons") ?: return
        val count = duplicates.optInt("nb")
        val row = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        row.addView(
            HydriaUi.badge(this, "$count déjà réalisée${if (count > 1) "s" else ""}", if (count > 0) Tone.INFO else Tone.NEUTRAL),
            wrapWrap(),
        )
        if (duplicates.optBoolean("recent")) {
            row.addView(
                HydriaUi.badge(this, "Doublon récent · ${duplicates.optString("dernier_display")}", Tone.WARNING),
                wrapWrap(top = 4),
            )
        }
        parent.addView(row, matchWrap(top = top))
    }

    /**
     * Pointage intégré à la page Planning : créneau en cours, état du pointage des plannings
     * du jour (réponse /pointage/aujourdhui en cache) et accès à l'écran de pointage GPS.
     */
    private fun planningPointageCard(): View {
        val today = mg.hydria.app.pointage.PointageStore.cachedToday(store.accountKey)
        val card = vertical(padding = 14).apply { HydriaUi.accentedCard(this, Tone.INFO) }
        val now = java.time.ZonedDateTime.now(mg.hydria.app.pointage.PointageRules.ZONE)
        val current = mg.hydria.app.pointage.PointageRules.creneauActuel(now)
        val next = mg.hydria.app.pointage.PointageRules.prochainCreneau(now)
        card.addView(text("POINTAGE DU JOUR", 11f, true, HydriaColors.cyan))
        val plannings = today?.optJSONArray("plannings")
        val lines = mutableListOf<Pair<String, Tone>>()
        if (plannings != null) for (i in 0 until plannings.length()) {
            val planning = plannings.getJSONObject(i)
            val name = listOf(planning.optString("activite"), planning.optString("ouvrage")).filter { it.isNotBlank() }.joinToString(" · ")
            if (!mg.hydria.app.pointage.PointageRules.pointageRequis(planning)) {
                lines += "$name — pas de pointage" to Tone.NEUTRAL
                continue
            }
            val slots = planning.optJSONArray("creneaux") ?: JSONArray()
            val states = (0 until slots.length()).map { slots.getJSONObject(it) }
                .filter { it.optBoolean("prevu") || it.optString("statut") == "ok" }
                .joinToString("  ") { slot ->
                    val mark = when (slot.optString("statut")) {
                        "ok" -> "✓ ${slot.optString("heure")}".trim()
                        "manque" -> "✗"
                        "en_cours" -> "à pointer"
                        else -> "○"
                    }
                    "${slot.optString("label")} $mark"
                }
            lines += "$name — ${states.ifBlank { "aucun créneau prévu" }}" to
                (if (states.contains("à pointer") || states.contains("✗")) Tone.WARNING else Tone.SUCCESS)
        }
        when {
            today == null -> card.addView(text("Ouvrez le pointage une fois en ligne pour charger vos créneaux du jour.",
                13f, false, HydriaColors.textSecondary), matchWrap(top = 6))
            lines.isEmpty() -> card.addView(text("Aucun planning aujourd'hui : ajoutez-le pour pouvoir pointer.",
                13f, false, HydriaColors.textSecondary), matchWrap(top = 6))
            else -> lines.forEach { (line, tone) ->
                card.addView(text(line, 13f, true, HydriaUi.toneTextColor(tone)), matchWrap(top = 6))
            }
        }
        val pending = mg.hydria.app.pointage.PointageStore.pendingCount(store.accountKey)
        val timing = when {
            current != null -> "Créneau en cours : ${current.label} ${current.fenetre}"
            next != null -> "Prochain créneau : ${next.label} ${next.fenetre}"
            else -> "Plus de créneau de pointage aujourd'hui"
        } + if (pending > 0) " · $pending pointage(s) en attente d'envoi" else ""
        card.addView(text(timing, 12.5f, false, HydriaColors.textSecondary), matchWrap(top = 8))
        val canPoint = current != null && (today == null || mg.hydria.app.pointage.PointageRules.pointageAttendu(today))
        card.addView((if (canPoint) primaryButton("Pointer ma position") else secondaryButton("Ouvrir le pointage")).apply {
            setOnClickListener { HydriaFeedback.tap(); openPointage() }
        }, matchWrap(50, top = 10))
        return card
    }

    private fun planningAgendaCard(planning: JSONObject): View {
        val planningDone = planning.optBoolean("valide")
        val event = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            HydriaUi.accentedCard(this, planningActivityTone(planning))
        }
        event.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(text(planning.optString("fiche_poste", "Activité"), 16f, true, HydriaColors.text),
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(HydriaUi.badge(this@MainActivity, if (planningDone) "Validé" else "À réaliser",
                if (planningDone) Tone.SUCCESS else Tone.WARNING))
        })
        addDuplicateBadges(event, planning)
        val context = listOf(
            planning.optString("type_activite"), planning.optString("ouvrage_nom"),
            planning.optString("commune"), planning.optString("district"), planning.optString("region"),
        ).filter { it.isNotBlank() }.joinToString(" · ")
        if (context.isNotBlank()) event.addView(text(context, 13f, false, HydriaColors.textSecondary), matchWrap(top = 7))
        val people = listOf(planning.optString("employe"), planning.optString("participants"))
            .filter { it.isNotBlank() }.joinToString(" · ")
        if (people.isNotBlank()) event.addView(text("Équipe : $people", 13f, false, HydriaColors.textSecondary), matchWrap(top = 6))
        planning.optString("remarque").takeIf { it.isNotBlank() }?.let {
            event.addView(text(it, 13f, false, HydriaColors.textSecondary), matchWrap(top = 7))
        }
        val counters = listOf(
            planning.optInt("nb_avances").takeIf { it > 0 }?.let { "$it avance(s)" },
            planning.optInt("nb_deplacements").takeIf { it > 0 }?.let { "$it déplacement(s)" },
            planning.optInt("nb_livraisons").takeIf { it > 0 }?.let { "$it livraison(s)" },
            planning.optInt("nb_paiements").takeIf { it > 0 }?.let { "$it paiement(s)" },
        ).filterNotNull().joinToString(" · ")
        if (counters.isNotBlank()) event.addView(text(counters, 12f, false, HydriaColors.textSecondary), matchWrap(top = 7))
        val specialDay = when {
            planning.optBoolean("jour_ferie") -> " · Jour férié"
            planning.optBoolean("weekend") -> " · Week-end"
            else -> ""
        }
        val proof = if (planning.optBoolean("preuve_obligatoire")) {
            " · Preuve ${planning.optString("preuve_type").ifBlank { "requise" }}"
        } else ""
        event.addView(text(
            "${planning.optString("statut", if (planningDone) "Validé" else "À réaliser")}$specialDay$proof",
            13f, true, if (planningDone) HydriaColors.success else HydriaColors.warning,
        ), matchWrap(top = 8))
        event.addView(Button(this).apply {
            text = "Modifier"
            HydriaUi.secondaryButton(this)
            setOnClickListener { showPlanningEditor(isRepair = false, existing = planning) }
        }, matchWrap(48, top = 10))
        return event
    }

    private fun showPlanningEditor(isRepair: Boolean, existing: JSONObject?) {
        if (!isRepair) planningModel.clearFormError()
        val references = store.snapshot?.optJSONObject("references")
        if (references == null) {
            toast("Synchronisez d’abord l’application pour charger les listes de saisie.")
            if (isOnline()) synchronize()
            return
        }
        val employees = jsonObjects(references.optJSONArray("employes") ?: JSONArray())
        val works = jsonObjects(references.optJSONArray("ouvrages") ?: JSONArray())
        val activities = jsonObjects(
            references.optJSONArray(if (isRepair) "repair_fiches" else "planning_fiches") ?: JSONArray()
        )
        // Planning validé : il ne peut pas être annulé (le serveur le refuse aussi).
        val lockedValidated = existing?.let { it.optBoolean("valide") || (isRepair && it.optBoolean("terminee")) } == true
        val statuses = jsonObjects(references.optJSONArray("statuts") ?: JSONArray())
            .filter { !lockedValidated || it.optString("id") != "annule" }
        val priorities = jsonObjects(references.optJSONArray("priorites") ?: JSONArray())
        if (employees.isEmpty() || activities.isEmpty() || (isRepair && works.isEmpty())) {
            toast("Les références autorisées sont vides. Synchronisez puis vérifiez vos droits Hydria.")
            return
        }

        val form = vertical(padding = 18)
        val employeeSpinner = spinner(employees.map { it.optString("nom", "Employé") })
        val workOptions = if (isRepair) works else listOf(JSONObject().put("id", "").put("nom", "Aucun ouvrage")) + works
        // Autocomplétion au lieu d'une liste déroulante (des centaines d'ouvrages).
        // Planning : champ vide = « Aucun ouvrage » (workOptions[0]).
        val pickerWorks = if (isRepair) workOptions else workOptions.drop(1)
        val workPicker = HydriaAutocomplete(this, pickerWorks.map { it.optString("nom", "Ouvrage") },
            if (isRepair) "Rechercher un ouvrage…" else "Rechercher un ouvrage (facultatif)…")
        fun currentWork(): JSONObject? = pickerWorks.getOrNull(workPicker.selectedIndex) ?: if (isRepair) null else workOptions.first()
        // Cascade Groupe > Type d'activité > Activité au lieu d'une seule longue liste.
        // Réparation : uniquement le groupe « Opérations sur les ouvrages », donc pas de liste Groupe.
        val activityCascade = if (isRepair) HydriaActivityCascade(this, ActivityCascadeTree.repairActivities(activities), showGroup = false)
            else HydriaActivityCascade(this, activities)
        // Date au sélecteur (JJ/MM/AAAA) : une date réelle par construction, future autorisée (date prévue).
        val dateField = HydriaUi.dateField(this,
            existing?.optString(if (isRepair) "date_prevue" else "date")?.takeIf { it.isNotBlank() }, maxToday = false)
        val statusSpinner = spinner(statuses.map { it.optString("nom", "En cours") })
        val prioritySpinner = spinner(priorities.map { it.optString("nom", "Normale") })
        val remarkField = EditText(this).apply {
            hint = "Remarque"
            setText(existing?.optString("remarque").orEmpty())
            minLines = 2
            maxLines = 4
            gravity = Gravity.TOP
        }

        fun selectById(spinner: Spinner, items: List<JSONObject>, id: String, fallback: Int = 0) {
            val position = items.indexOfFirst { it.optString("id") == id }
            spinner.setSelection(if (position >= 0) position else fallback, false)
        }
        // Nouvelle saisie : l'employé connecté est présélectionné (drapeau « moi » des références).
        selectById(employeeSpinner, employees,
            existing?.optString("employe_id") ?: employees.firstOrNull { it.optBoolean("moi") }?.optString("id").orEmpty())
        existing?.optString("ouvrage_id")?.takeIf { it.isNotBlank() }?.let { wanted ->
            workPicker.select(pickerWorks.indexOfFirst { it.optString("id") == wanted })
        }
        existing?.optString("fiche_poste_id")?.takeIf { it.isNotBlank() }?.let { activityCascade.select(it) }
        selectById(statusSpinner, statuses, existing?.optString("statut_code").orEmpty())
        if (isRepair) selectById(prioritySpinner, priorities, existing?.optString("priorite_code").orEmpty(),
            priorities.indexOfFirst { it.optString("id") == "normale" }.coerceAtLeast(0))

        // --- Cible de la réparation (équipement OU point d'eau) et composants concernés ---
        val componentCatalog = references.optJSONObject("composants")
        val targetSpinner = spinner(listOf("Aucune cible précisée"))
        val targetLabel = label("Cible (point d'eau ou équipement)")
        val componentsLabel = label("Composants concernés")
        // Règles de l'activité choisie : cible / composants obligatoires, types admis,
        // composants restreints (ex. anti-rouille -> parties métalliques uniquement).
        var activityRules = ActivityTargetRules.of(activityCascade.selectedActivity)
        val componentsBox = vertical()
        val componentChecks = mutableListOf<Pair<CheckBox, String>>()
        var targetOptions: List<RepairTargetOption> = emptyList()
        var lastWorkId: String? = null
        var lastTargetKey = ""
        var pendingTargetKey: String? = existing?.let { repair ->
            repair.optString("equipement_id").takeIf { it.isNotBlank() }?.let { "eq:$it" }
                ?: repair.optString("point_eau_id").takeIf { it.isNotBlank() }?.let { "pe:$it" }
        }
        val existingTargetKey = pendingTargetKey
        var pendingComponentIds: Set<String> = existing?.optJSONArray("composants_ids")
            ?.let { ids -> (0 until ids.length()).map { ids.getString(it) }.toSet() } ?: emptySet()

        fun selectedTarget(): RepairTargetOption? = targetOptions.getOrNull(targetSpinner.selectedItemPosition - 1)
        fun rebuildComponents() {
            componentsBox.removeAllViews()
            componentChecks.clear()
            val option = selectedTarget()
            val catalogItems = if (option == null) emptyList() else jsonObjects(
                componentCatalog?.optJSONObject(if (option.kind == "eq") "equipement" else "point_eau")
                    ?.optJSONArray(option.typeId) ?: JSONArray())
            val items = activityRules.filterComponents(catalogItems)
            if (items.isEmpty()) componentsBox.addView(text(
                when {
                    option == null -> "Choisissez d'abord une cible (point d'eau ou équipement) ci-dessus."
                    catalogItems.isNotEmpty() -> "Cette activité ne s'applique à aucun composant de ce type " +
                        "(admis : ${activityRules.allowedComponents.joinToString(", ")})."
                    else -> "Aucun composant défini pour ce type de ${if (option.kind == "eq") "équipement" else "point d'eau"}."
                },
                12.5f, false, HydriaColors.textSecondary), matchWrap(top = 2))
            items.forEach { item ->
                val id = item.optString("id")
                val check = CheckBox(this).apply {
                    text = item.optString("nom")
                    setTextColor(HydriaColors.text)
                    buttonTintList = android.content.res.ColorStateList.valueOf(HydriaColors.cyan)
                    isChecked = id in pendingComponentIds
                    // Un seul composant : cocher l'un décoche les autres.
                    setOnCheckedChangeListener { box, checked ->
                        if (checked && !activityRules.multipleComponents)
                            componentChecks.forEach { (other, _) -> if (other !== box) other.isChecked = false }
                    }
                }
                componentChecks.add(check to id)
                componentsBox.addView(check, matchWrap())
            }
            pendingComponentIds = emptySet()
        }
        fun rebuildTargets() {
            val workId = currentWork()?.optString("id").orEmpty()
            val work = jsonObjects(store.snapshot?.optJSONObject("terrain")?.optJSONArray("ouvrages") ?: JSONArray())
                .firstOrNull { it.optString("id") == workId }
            val options = mutableListOf<RepairTargetOption>()
            if (activityRules.allowsTarget("pe")) jsonObjects(work?.optJSONArray("points_eau") ?: JSONArray()).forEach { point ->
                val name = listOf(point.optString("code"), point.optString("nom")).filter { it.isNotBlank() }.joinToString(" — ")
                options.add(RepairTargetOption("pe", point.optString("id"), "Point d'eau · $name", point.optString("type_id")))
            }
            if (activityRules.allowsTarget("eq")) jsonObjects(work?.optJSONArray("equipements") ?: JSONArray()).forEach { equipment ->
                val name = equipment.optString("nom").ifBlank { equipment.optString("code") }
                val type = equipment.optString("type").takeIf { it.isNotBlank() }?.let { " ($it)" }.orEmpty()
                options.add(RepairTargetOption("eq", equipment.optString("id"), "Équipement · $name$type", equipment.optString("type_id")))
            }
            targetOptions = options
            targetSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
                listOf("Aucune cible précisée") + options.map { it.label })
            val wanted = pendingTargetKey
            val position = wanted?.let { key -> options.indexOfFirst { "${it.kind}:${it.id}" == key } }
                ?.takeIf { it >= 0 }?.plus(1) ?: 0
            targetSpinner.setSelection(position, false)
            pendingTargetKey = null
            lastTargetKey = selectedTarget()?.let { "${it.kind}:${it.id}" }.orEmpty()
            rebuildComponents()
        }
        run {
            workPicker.onSelected = {
                val workId = currentWork()?.optString("id").orEmpty()
                if (workId != lastWorkId) { lastWorkId = workId; rebuildTargets() }
            }
            targetSpinner.onItemSelectedListener = SimpleItemSelectedListener {
                val key = selectedTarget()?.let { option -> "${option.kind}:${option.id}" }.orEmpty()
                if (key != lastTargetKey) { lastTargetKey = key; rebuildComponents() }
            }
            lastWorkId = currentWork()?.optString("id").orEmpty()
            rebuildTargets()
        }
        fun applyActivityRules() {
            val what = when (activityRules.targetTypes) {
                "point_eau" -> "Point d'eau"
                "equipement" -> "Équipement"
                else -> "Cible (point d'eau ou équipement)"
            }
            targetLabel.text = if (activityRules.targetRequired) "$what — obligatoire" else what
            componentsLabel.text = buildString {
                append("Composants concernés")
                if (activityRules.componentsRequired) append(" — obligatoire")
                if (!activityRules.multipleComponents) append(" (un seul)")
            }
            val targetVisibility = if (activityRules.targetHidden) View.GONE else View.VISIBLE
            targetLabel.visibility = targetVisibility
            targetSpinner.visibility = targetVisibility
            val componentsVisibility = if (activityRules.componentsHidden) View.GONE else View.VISIBLE
            componentsLabel.visibility = componentsVisibility
            componentsBox.visibility = componentsVisibility
        }
        applyActivityRules()
        activityCascade.onActivityChanged = { activity ->
            // Garder la cible et les composants déjà cochés s'ils restent admis.
            pendingTargetKey = selectedTarget()?.let { "${it.kind}:${it.id}" }
            pendingComponentIds = componentChecks.filter { it.first.isChecked }.map { it.second }.toSet()
            activityRules = ActivityTargetRules.of(activity)
            applyActivityRules()
            rebuildTargets()
        }
        // Contrôle des règles de l'activité à l'enregistrement (null = conforme). Sans cibles
        // chargées, rien n'est envoyé ni exigé : le serveur ne vérifie pas non plus.
        fun activityRulesError(activity: JSONObject?): String? {
            if (targetOptions.isEmpty() && selectedTarget() == null) return null
            val target = selectedTarget()?.let { WorkTarget(it.kind, it.id, it.label, it.typeId) }
            return activityRules.error(
                ActivityCascadeTree.activityName(activity ?: JSONObject()), target,
                componentChecks.filter { it.first.isChecked }.map { it.second }, componentChecks.size)
        }

        // Erreurs en ligne, sous le champ concerné : le toast (éphémère, souvent masqué par le clavier) n'est
        // qu'un dernier recours, quand le champ n'est pas affiché.
        fun inlineError() = text("", 12.5f, true, HydriaColors.error).apply {
            visibility = View.GONE
            setPadding(0, dp(4), 0, 0)
        }
        val employeeError = inlineError()
        val activityError = inlineError()
        val targetError = inlineError()
        val componentsError = inlineError()
        val dateError = inlineError()
        fun clearFormErrors() {
            listOf(employeeError, activityError, targetError, componentsError, dateError).forEach {
                it.visibility = View.GONE
                it.text = ""
            }
            workPicker.error = null
        }
        /** Affiche [message] sous [anchor], l'amène à l'écran et secoue le champ ; sans champ visible, toast. */
        fun showFieldError(errorView: TextView, anchor: View, message: String) {
            HydriaFeedback.error()
            if (anchor.visibility != View.VISIBLE) { toast(message); return }
            errorView.text = message
            errorView.visibility = View.VISIBLE
            HydriaFeedback.shake(anchor)
            errorView.post {
                errorView.requestRectangleOnScreen(android.graphics.Rect(0, 0, errorView.width, errorView.height), false)
            }
        }
        fun showEditTextError(field: EditText, message: String) {
            HydriaFeedback.error()
            field.error = message
            field.requestFocus()
            HydriaFeedback.shake(field)
        }

        if (lockedValidated) {
            workPicker.isEnabled = false
            workPicker.alpha = 0.55f
            activityCascade.setLocked(true)
            form.addView(text("Planning validé : l'activité et l'ouvrage ne peuvent plus changer, ni le planning être annulé. "
                + "Vous pouvez changer la date ou l'employé.", 13f, true, HydriaColors.cyan), matchWrap(top = 2))
        }
        form.addView(label("Employé responsable")); form.addView(employeeSpinner, matchWrap(52))
        form.addView(employeeError, matchWrap())
        form.addView(label(if (isRepair) "Ouvrage (obligatoire)" else "Ouvrage")); form.addView(workPicker, matchWrap(56))
        form.addView(activityCascade, matchWrap(top = 4))
        form.addView(activityError, matchWrap())
        form.addView(targetLabel); form.addView(targetSpinner, matchWrap(52))
        form.addView(targetError, matchWrap())
        form.addView(componentsLabel); form.addView(componentsBox, matchWrap())
        form.addView(componentsError, matchWrap())
        form.addView(label("Date")); form.addView(dateField, matchWrap(54))
        form.addView(dateError, matchWrap())
        form.addView(label("Statut")); form.addView(statusSpinner, matchWrap(52))
        if (isRepair) {
            form.addView(label("Priorité")); form.addView(prioritySpinner, matchWrap(52))
        }
        form.addView(label("Remarque")); form.addView(remarkField, matchWrap(92))

        // Indicateur « formulaire modifié » : signature des champs comparée à celle de l'ouverture. Plus fiable
        // que des écouteurs, que les Spinner déclenchent aussi sur leur sélection initiale (fausse « modification »).
        fun formSignature(): String = listOf(
            employeeSpinner.selectedItemPosition.toString(),
            workPicker.selectedIndex.toString(), workPicker.text.toString(),
            activityCascade.selectedActivity?.optString("id").orEmpty(),
            selectedTarget()?.let { "${it.kind}:${it.id}" }.orEmpty(),
            componentChecks.filter { it.first.isChecked }.joinToString(",") { it.second },
            dateField.iso,
            statusSpinner.selectedItemPosition.toString(), prioritySpinner.selectedItemPosition.toString(),
            remarkField.text.toString(),
        ).joinToString("|")
        val openedSignature = formSignature()
        fun isFormDirty() = formSignature() != openedSignature

        val dialog = AlertDialog.Builder(this)
            .setTitle(if (existing == null) {
                if (isRepair) "Nouvelle réparation" else "Nouveau planning"
            } else {
                if (isRepair) "Modifier la réparation" else "Modifier le planning"
            })
            .setView(scroll(form))
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Enregistrer", null)
            .create()
        // Un toucher à côté ne ferme plus le formulaire. « Annuler » et Retour demandent confirmation si la
        // saisie a été modifiée ; « Continuer la saisie » est le bouton principal (positif).
        dialog.setCanceledOnTouchOutside(false)
        fun requestClose() {
            if (!isFormDirty()) { dialog.dismiss(); return }
            confirmAbandon("Ce que vous avez saisi dans ce formulaire sera perdu.") { dialog.dismiss() }
        }
        dialog.onBackPressedDispatcher.addCallback(dialog) { requestClose() }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener { requestClose() }
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                clearFormErrors()
                val selectedEmployee = employees.getOrNull(employeeSpinner.selectedItemPosition)
                if (workPicker.selectedIndex < 0 && workPicker.text.toString().isNotBlank()) {
                    showEditTextError(workPicker, "Choisissez un ouvrage dans la liste")
                    return@setOnClickListener
                }
                val selectedWork = currentWork()
                val selectedActivity = activityCascade.selectedActivity
                val selectedStatus = statuses.getOrNull(statusSpinner.selectedItemPosition)
                val selectedPriority = priorities.getOrNull(prioritySpinner.selectedItemPosition)
                val dateValue = dateField.iso
                activityRulesError(selectedActivity)?.let { message ->
                    // Règles de l'activité : sous les composants si elles les concernent, sinon sous la cible.
                    if (message.contains("composant")) showFieldError(componentsError, componentsBox, message)
                    else showFieldError(targetError, targetSpinner, message)
                    return@setOnClickListener
                }
                if (!isRepair) {
                    val result = planningModel.validateForm(mg.hydria.shared.planning.PlanningDraft(
                        employeeId = selectedEmployee?.getString("id"),
                        activityId = selectedActivity?.getString("id"),
                        date = dateValue,
                        workId = selectedWork?.optString("id").orEmpty(),
                        status = selectedStatus?.optString("id", "en_cours") ?: "en_cours",
                        remark = remarkField.text.toString(),
                        existingId = existing?.optString("id")))
                    val error = result.error
                    if (error != null) {
                        when (error) {
                            mg.hydria.shared.planning.PlanningFormError.EMPLOYEE -> showFieldError(employeeError, employeeSpinner, error.message)
                            mg.hydria.shared.planning.PlanningFormError.ACTIVITY -> showFieldError(activityError, activityCascade, error.message)
                            mg.hydria.shared.planning.PlanningFormError.DATE_FORMAT -> showFieldError(dateError, dateField, error.message)
                        }
                    } else {
                        val payload = JSONObject(requireNotNull(result.fields))
                        // Cible + composants : mêmes règles que la réparation. Rien n'est envoyé si les
                        // options ne sont pas chargées, pour ne pas effacer une cible côté serveur.
                        val targetKnown = targetOptions.isNotEmpty() && (existingTargetKey == null ||
                            existingTargetKey in targetOptions.map { "${it.kind}:${it.id}" })
                        if (targetKnown) {
                            payload.put("equipement_id", selectedTarget()?.takeIf { it.kind == "eq" }?.id.orEmpty())
                                .put("point_eau_id", selectedTarget()?.takeIf { it.kind == "pe" }?.id.orEmpty())
                                .put("composants_ids", componentChecks.filter { it.first.isChecked }.joinToString(",") { it.second })
                        }
                        PlanningsRepository.enqueueSave(store, payload)
                        dialog.dismiss()
                        toast("Planning enregistré${if (isOnline()) " et en cours d’envoi" else " hors connexion"}.")
                        updateStatus()
                        if (isOnline()) synchronize()
                    }
                    return@setOnClickListener
                }
                val result = mg.hydria.shared.repairs.RepairFormRules.validate(
                    mg.hydria.shared.repairs.RepairDraft(
                        employeeId = selectedEmployee?.getString("id"),
                        activityId = selectedActivity?.getString("id"),
                        workId = selectedWork?.optString("id").orEmpty(),
                        date = dateValue,
                        status = selectedStatus?.optString("id", "en_cours") ?: "en_cours",
                        priority = selectedPriority?.optString("id", "normale") ?: "normale",
                        remark = remarkField.text.toString(), existingId = existing?.optString("id"),
                        // Sans options (terrain non préchargé) ou cible existante introuvable : ne rien envoyer,
                        // pour ne pas effacer côté serveur une cible que l'écran ne sait pas afficher.
                        target = if (targetOptions.isEmpty() || (existingTargetKey != null &&
                            existingTargetKey !in targetOptions.map { "${it.kind}:${it.id}" })) null
                        else mg.hydria.shared.repairs.RepairTarget(
                            equipmentId = selectedTarget()?.takeIf { it.kind == "eq" }?.id.orEmpty(),
                            pointEauId = selectedTarget()?.takeIf { it.kind == "pe" }?.id.orEmpty(),
                            componentIds = componentChecks.filter { it.first.isChecked }.map { it.second })))
                val error = result.error
                if (error != null) {
                    when (error) {
                        mg.hydria.shared.repairs.RepairFormError.EMPLOYEE -> showFieldError(employeeError, employeeSpinner, error.message)
                        mg.hydria.shared.repairs.RepairFormError.ACTIVITY -> showFieldError(activityError, activityCascade, error.message)
                        mg.hydria.shared.repairs.RepairFormError.WORK -> showEditTextError(workPicker, error.message)
                        mg.hydria.shared.repairs.RepairFormError.DATE_FORMAT -> showFieldError(dateError, dateField, error.message)
                        mg.hydria.shared.repairs.RepairFormError.TARGET_CONFLICT,
                        mg.hydria.shared.repairs.RepairFormError.COMPONENTS_WITHOUT_TARGET -> showFieldError(targetError, targetSpinner, error.message)
                    }
                } else {
                    RepairsRepository.enqueueSave(store, JSONObject(requireNotNull(result.fields)))
                    dialog.dismiss()
                    toast("Réparation enregistré${if (isOnline()) " et en cours d’envoi" else " hors connexion"}.")
                    updateStatus()
                    if (isOnline()) synchronize()
                }
            }
        }
        dialog.show()
    }

    private fun addSharedFilters(
        page: LinearLayout,
        model: mg.hydria.shared.rules.planning.PlanningViewModelGateway,
        collapsedByDefault: Boolean = false,
        renderResults: (LinearLayout, List<JSONObject>) -> Unit,
    ) {
        val employeeSpinner = spinner(emptyList())
        val regionSpinner = spinner(emptyList())
        val districtSpinner = spinner(emptyList())
        val communeSpinner = spinner(emptyList())
        val results = vertical()
        val filterPanel = card(emphasized = true)
        val filterToggle = secondaryButton("")
        val perimeterSummary = subtitle("")
        var filtersExpanded = !collapsedByDefault
        var binding = false

        fun setOptions(target: Spinner, options: List<mg.hydria.shared.planning.PlanningOption>, selectedId: String) {
            target.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, options.map { it.label })
            target.setSelection(options.indexOfFirst { it.id == selectedId }.coerceAtLeast(0), false)
            target.isEnabled = options.size > 1
        }
        fun updateToggle() {
            val count = model.state.activeFilterCount
            val suffix = if (count > 0) " · $count actif${if (count > 1) "s" else ""}" else ""
            filterToggle.text = if (filtersExpanded) "Masquer les filtres$suffix" else "Afficher les filtres$suffix"
            filterToggle.contentDescription = if (filtersExpanded) "Masquer les filtres, $count filtre(s) actif(s)"
                else "Afficher les filtres, $count filtre(s) actif(s)"
            filterPanel.visibility = if (filtersExpanded) View.VISIBLE else View.GONE
        }
        fun renderState() {
            binding = true
            val state = model.state
            setOptions(employeeSpinner, state.employeeOptions, state.filters.employeeId)
            setOptions(regionSpinner, state.regionOptions, state.filters.regionId)
            setOptions(districtSpinner, state.districtOptions, state.filters.districtId)
            setOptions(communeSpinner, state.communeOptions, state.filters.communeId)
            binding = false
            perimeterSummary.text = state.perimeterSummary
            updateToggle()
            results.removeAllViews()
            renderResults(results, state.items)
        }
        fun select(field: mg.hydria.shared.planning.PlanningFilter, id: String, currentId: String) {
            // Les callbacks de Spinner peuvent arriver apres setAdapter : ne pas
            // rejouer une selection identique, ce qui viderait les sous-filtres.
            if (binding || id == currentId) return
            model.selectFilter(field, id)
            renderState()
        }
        employeeSpinner.onItemSelectedListener = SimpleItemSelectedListener { position ->
            val state = model.state
            select(mg.hydria.shared.planning.PlanningFilter.EMPLOYEE,
                state.employeeOptions.getOrNull(position)?.id.orEmpty(), state.filters.employeeId)
        }
        regionSpinner.onItemSelectedListener = SimpleItemSelectedListener { position ->
            val state = model.state
            select(mg.hydria.shared.planning.PlanningFilter.REGION,
                state.regionOptions.getOrNull(position)?.id.orEmpty(), state.filters.regionId)
        }
        districtSpinner.onItemSelectedListener = SimpleItemSelectedListener { position ->
            val state = model.state
            select(mg.hydria.shared.planning.PlanningFilter.DISTRICT,
                state.districtOptions.getOrNull(position)?.id.orEmpty(), state.filters.districtId)
        }
        communeSpinner.onItemSelectedListener = SimpleItemSelectedListener { position ->
            val state = model.state
            select(mg.hydria.shared.planning.PlanningFilter.COMMUNE,
                state.communeOptions.getOrNull(position)?.id.orEmpty(), state.filters.communeId)
        }
        filterPanel.addView(label("Employé")); filterPanel.addView(employeeSpinner, matchWrap(52))
        filterPanel.addView(label("Région")); filterPanel.addView(regionSpinner, matchWrap(52))
        filterPanel.addView(label("District")); filterPanel.addView(districtSpinner, matchWrap(52))
        filterPanel.addView(label("Commune")); filterPanel.addView(communeSpinner, matchWrap(52))
        filterToggle.setOnClickListener { filtersExpanded = !filtersExpanded; updateToggle() }
        // Recherche libre par ouvrage, hors du panneau de filtres (toujours visible).
        val workSearch = field("Rechercher un ouvrage…").apply {
            setText(model.state.filters.query)
            contentDescription = "Rechercher un ouvrage"
            imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH
        }
        val applyWorkSearch = Runnable {
            model.setQuery(workSearch.text.toString())
            renderState()
        }
        workSearch.addTextChangedListener(object : android.text.TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                // Petit delai : evite de reconstruire la liste a chaque lettre tapee.
                workSearch.removeCallbacks(applyWorkSearch)
                workSearch.postDelayed(applyWorkSearch, 250)
            }
            override fun afterTextChanged(s: android.text.Editable?) {}
        })
        page.addView(perimeterSummary, matchWrap(top = 4))
        page.addView(workSearch, matchWrap(52))
        page.addView(filterToggle, matchWrap(50, top = 8))
        page.addView(filterPanel, matchWrap(top = 8))
        page.addView(results, matchWrap(top = 12))
        renderState()
    }

    private fun jsonObjects(array: JSONArray): List<JSONObject> =
        (0 until array.length()).map { array.getJSONObject(it) }

    private fun formatNumber(value: Double): String =
        if (value % 1.0 == 0.0) String.format(Locale.FRANCE, "%,.0f", value)
        else String.format(Locale.FRANCE, "%,.2f", value)

    private fun displayIsoDate(value: String): String = try {
        val parsed = SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(value)
        if (parsed == null) value else SimpleDateFormat("dd/MM/yyyy", Locale.FRANCE).format(parsed)
    } catch (_: Exception) {
        value
    }

    /** Dernière version publiée (null tant que la vérification n'a pas abouti). */
    private var latestVersion: JSONObject? = null

    @Suppress("DEPRECATION")
    private fun appVersionCode(): Long = runCatching {
        val info = packageManager.getPackageInfo(packageName, 0)
        if (android.os.Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
    }.getOrDefault(0L)

    private fun isUpdateAvailable(): Boolean =
        (latestVersion?.optLong("versionCode", 0L) ?: 0L) > appVersionCode()

    /** Texte « à jour / nouvelle version » affiché sous le numéro de version. */
    private fun updateStatusText(): String {
        val latest = latestVersion ?: return "Vérification de la dernière version…"
        return if (isUpdateAvailable()) "Nouvelle version disponible : ${latest.optString("versionName")}"
        else "✓ Vous avez la dernière version"
    }

    private fun checkForUpdate(onDone: () -> Unit) {
        executor.execute {
            val latest = HydriaApi.latestAppVersion()
            runOnUiThread {
                if (latest != null) latestVersion = latest
                onDone()
            }
        }
    }

    private fun showSessionMenu() {
        val statusView = TextView(this).apply {
            textSize = 12.5f
            typeface = HydriaType.display(500)
        }
        fun refreshStatus() {
            statusView.text = updateStatusText()
            statusView.setTextColor(if (isUpdateAvailable()) HydriaColors.error else HydriaColors.textSecondary)
        }
        refreshStatus()
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(20), dp(24), dp(8))
            addView(TextView(this@MainActivity).apply {
                text = getString(R.string.tools_and_session)
                textSize = 20f
                typeface = HydriaType.display(700)
                setTextColor(HydriaColors.text)
            })
            addView(TextView(this@MainActivity).apply {
                text = "Version ${appVersionName()}"
                textSize = 12.5f
                typeface = HydriaType.display(500)
                setTextColor(HydriaColors.textSecondary)
            }, matchWrap(top = 4))
            addView(statusView)
        }
        val entries = mutableListOf<Pair<String, () -> Unit>>(
            "Carte terrain" to { startActivity(Intent(this, NavigationTerrainActivity::class.java)) },
            "Commencer ma tournée" to {
                val rawTerrain = store.snapshot?.optJSONObject("terrain")
                if (rawTerrain == null) toast("Synchronisez pour charger votre périmètre terrain.")
                else startTerrainBatch(TerrainRules.buildTourTasks(terrainForPerimetre(rawTerrain)))
            },
            getString(R.string.calculator_title) to { startActivity(Intent(this, AdvancedCalculatorActivity::class.java)) },
            "Synchroniser maintenant" to { synchronize() },
            "Centre de synchronisation" to { showSyncCenter() },
            "Workflow volumétrique" to { startActivity(Intent(this, mg.hydria.app.volume.VolumeActivity::class.java)) },
            "Se déconnecter" to {
                if (store.pendingCount() > 0) toast("Synchronisez les actions en attente avant de vous déconnecter.")
                else confirmLogout()
            },
        )
        if (isUpdateAvailable()) {
            entries.add("⬇ Télécharger la mise à jour (${latestVersion?.optString("versionName")})" to {
                val url = latestVersion?.optString("url").orEmpty()
                    .ifBlank { "https://www.hydria.mg/static/downloads/android/hydria-app.apk" }
                startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)))
            })
        }
        val dialog = AlertDialog.Builder(this)
            .setCustomTitle(header)
            .setItems(entries.map { it.first }.toTypedArray()) { _, which -> entries[which].second() }
            .show()
        // Vérification en ligne à chaque ouverture : le bouton de mise à jour apparaît à la réouverture.
        val hadUpdate = isUpdateAvailable()
        checkForUpdate {
            if (!dialog.isShowing) return@checkForUpdate
            if (isUpdateAvailable() != hadUpdate) { dialog.dismiss(); showSessionMenu() } else refreshStatus()
        }
    }

    /**
     * Se déconnecter efface la tournée préchargée et exige du réseau pour se reconnecter : on confirme.
     * « Annuler » est le bouton principal (positif, à droite) ; « Se déconnecter » demande un geste volontaire.
     */
    private fun confirmLogout() {
        AlertDialog.Builder(this)
            .setTitle("Se déconnecter ?")
            .setMessage("Vous aurez besoin d'internet pour vous reconnecter et recharger votre tournée.")
            .setPositiveButton("Annuler", null)
            .setNegativeButton("Se déconnecter") { _, _ ->
                closeCampaign()
                store.clearSession()
                showLogin()
            }
            .show()
    }

    /** Un élément de la file est-il en conflit serveur (index refusé, version divergente) ? */
    private fun isSyncConflict(item: JSONObject): Boolean =
        mg.hydria.shared.sync.QueueOverviewGateway.isConflict(item)

    /**
     * Centre de synchronisation — feuille modale ouverte par la pastille d'en-tête.
     * Les conflits remontent en tête avec leur action « Corriger » directe.
     */
    private fun showSyncCenter() {
        val overview = mg.hydria.shared.sync.QueueOverviewGateway.summarize(store.pending())
        val items = overview.items
        val conflicts = overview.conflicts
        val ordinary = overview.ordinary
        val readingCount = overview.readingCount
        val photoCount = overview.photoCount

        val dialog = com.google.android.material.bottomsheet.BottomSheetDialog(this)

        val sheet = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(10), dp(18), dp(16))
            background = sheetBackground()
        }
        sheet.addView(View(this).apply {
            background = HydriaUi.rounded(this@MainActivity, HydriaColors.outline, 3f)
        }, LinearLayout.LayoutParams(dp(42), dp(5)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(14)
        })
        sheet.addView(TextView(this).apply {
            text = "Travail en attente"
            typeface = HydriaType.display(700)
            textSize = 19f
            letterSpacing = -0.02f
            setTextColor(HydriaColors.text)
        })
        sheet.addView(TextView(this).apply {
            text = "Rien n'est perdu : tout est gardé sur le téléphone."
            typeface = HydriaType.display(400)
            textSize = 12.5f
            setTextColor(HydriaColors.textSecondary)
        }, matchWrap(top = 3))

        sheet.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(syncCounter(readingCount.toString(), "relevés"))
            addView(syncCounter(photoCount.toString(), "photos"))
            addView(syncCounter(conflicts.size.toString(), "conflits",
                if (conflicts.isNotEmpty()) HydriaColors.error else HydriaColors.text))
        }, matchWrap(top = 16))

        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (items.isEmpty()) {
            list.addView(TextView(this).apply {
                text = "File vide — tout est synchronisé."
                typeface = HydriaType.display(500)
                textSize = 13f
                setTextColor(HydriaColors.textSecondary)
                setPadding(0, dp(16), 0, dp(8))
            })
        }
        (conflicts + ordinary).forEach { item ->
            list.addView(syncCenterItemCard(item) { dialog.dismiss() }, matchWrap(top = 8))
        }
        val listScroll = ScrollView(this).apply {
            isFillViewport = true
            addView(list)
        }
        sheet.addView(listScroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, dp(360),
        ).apply { topMargin = dp(10) })

        sheet.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(Button(this@MainActivity).apply {
                text = "Synchroniser"
                HydriaUi.primaryButton(this, HydriaColors.cyan)
                isEnabled = items.isNotEmpty() || store.snapshot != null
                setOnClickListener { dialog.dismiss(); synchronize() }
            }, LinearLayout.LayoutParams(0, dp(60), 1.4f).apply { marginEnd = dp(10) })
            addView(Button(this@MainActivity).apply {
                text = "Journal"
                HydriaUi.secondaryButton(this)
                setOnClickListener { showSyncJournal(items) }
            }, LinearLayout.LayoutParams(0, dp(60), 1f))
        }, matchWrap(top = 14))

        sheet.addView(TextView(this).apply {
            val online = isOnline()
            text = mg.hydria.shared.sync.QueueOverviewRules.status(items.size, online)
            typeface = HydriaType.display(500)
            textSize = 11.5f
            setTextColor(if (online) HydriaColors.textSecondary else HydriaColors.warning)
        }, matchWrap(top = 12))

        dialog.setContentView(sheet)
        dialog.show()
    }

    private fun syncCounter(value: String, label: String, color: Int = HydriaColors.text): View =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = value
                typeface = HydriaType.numeral(700)
                textSize = 26f
                letterSpacing = -0.03f
                setTextColor(color)
            })
            addView(TextView(this@MainActivity).apply {
                text = label
                typeface = HydriaType.display(500)
                textSize = 11f
                setTextColor(HydriaColors.textSecondary)
            })
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

    private fun syncCenterItemCard(item: JSONObject, dismiss: () -> Unit): View {
        val conflict = isSyncConflict(item)
        val error = item.optString("last_error")
        val tone = when {
            conflict -> Tone.ERROR
            error.isNotBlank() -> Tone.WARNING
            else -> Tone.NEUTRAL
        }
        val type = item.optString("type")
        val label = mg.hydria.shared.sync.QueueOverviewRules.typeLabel(type)
        val cardView = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            HydriaUi.accentedCard(this, tone)
        }
        cardView.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(text(label, 14.5f, true, HydriaColors.text),
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(HydriaUi.badge(this@MainActivity,
                if (conflict) "Conflit" else if (error.isNotBlank()) "Erreur" else "En attente", tone))
        })
        cardView.addView(text(syncPayloadDetails(item), 12f, false, HydriaColors.textSecondary), matchWrap(top = 6))
        if (error.isNotBlank() && !conflict) {
            cardView.addView(text(error, 11.5f, false, HydriaColors.error), matchWrap(top = 5))
            // Relevé refusé par le serveur (HTTP 400) : il se corrige dans l'écran de saisie, comme un conflit.
            val refused = mg.hydria.shared.sync.QueueOverviewGateway.isServerRefusal(item)
            val deleteButton = Button(this@MainActivity).apply {
                text = "Supprimer de la file"
                HydriaUi.secondaryButton(this)
                setOnClickListener {
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle("Supprimer cette action ?")
                        .setMessage("Cette action en attente sera retirée définitivement, sans être envoyée au serveur. À utiliser seulement si vous savez qu'elle ne pourra jamais aboutir (ex. fonctionnalité pas encore activée côté serveur).")
                        .setNegativeButton("Annuler", null)
                        .setPositiveButton("Supprimer") { _, _ ->
                            store.remove(item.getString("local_uuid"))
                            dismiss()
                            updateStatus()
                            toast("Action supprimée de la file d'attente.")
                        }
                        .show()
                }
            }
            if (refused) {
                cardView.addView(text(
                    "Le serveur a refusé ce relevé. Corrigez la saisie puis enregistrez à nouveau.",
                    11.5f, false, HydriaColors.error,
                ), matchWrap(top = 5))
                cardView.addView(LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    addView(Button(this@MainActivity).apply {
                        text = "Corriger"
                        HydriaUi.primaryButton(this, HydriaColors.cyan)
                        setOnClickListener { dismiss(); openReadingCorrection(item) }
                    }, LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginEnd = dp(8) })
                    addView(deleteButton, LinearLayout.LayoutParams(0, dp(52), 1f))
                }, matchWrap(top = 8))
            } else cardView.addView(deleteButton, matchWrap(44, top = 8))
        }
        if (conflict) {
            cardView.addView(text(
                "Le serveur a refusé cette version. Corrigez la saisie ou comparez les deux versions.",
                11.5f, false, HydriaColors.error,
            ), matchWrap(top = 5))
            cardView.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                if (type == "reading") {
                    addView(Button(this@MainActivity).apply {
                        text = "Corriger"
                        HydriaUi.primaryButton(this, HydriaColors.cyan)
                        setOnClickListener { dismiss(); openReadingCorrection(item) }
                    }, LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginEnd = dp(8) })
                }
                addView(Button(this@MainActivity).apply {
                    text = "Comparer"
                    HydriaUi.secondaryButton(this)
                    setOnClickListener { dismiss(); showSyncConflict(item) }
                }, LinearLayout.LayoutParams(0, dp(52), if (type == "reading") 1f else 2f))
            }, matchWrap(top = 8))
        }
        return cardView
    }

    /** Rouvre la saisie du point d'eau concerné par un relevé en conflit, en mode correction. */
    private fun openReadingCorrection(item: JSONObject) {
        val payload = item.optJSONObject("payload")
        val pointId = payload?.optString("point_eau_id").orEmpty()
        val date = payload?.optString("date_releve").orEmpty()
        val ouvrages = store.snapshot?.optJSONArray("ouvrages") ?: JSONArray()
        var ouvrage: JSONObject? = null
        outer@ for (i in 0 until ouvrages.length()) {
            val candidate = ouvrages.optJSONObject(i) ?: continue
            val points = candidate.optJSONArray("points_eau") ?: continue
            for (j in 0 until points.length()) {
                if (points.optJSONObject(j)?.optString("id") == pointId) { ouvrage = candidate; break@outer }
            }
        }
        if (ouvrage == null || pointId.isBlank() || date.isBlank()) {
            toast("Point introuvable dans la tournée locale. Ouvrez l'onglet Relevés pour corriger.")
            currentScreen = Screen.READINGS
            renderCurrentScreen()
            return
        }
        campaignOuvrageId = ouvrage.optString("id")
        campaignOuvrageNom = ouvrage.optString("nom", "Ouvrage")
        campaignDate = date
        campaignShowDone = true
        campaignShowAlreadyRead = true
        // Rouvrir précisément le point refusé : sans filtre de parcelle, de recherche ni de tri « proches ».
        campaignFocusPointId = pointId
        readingFocusIndex = true
        readingDetailsExpanded = false
        readingPickerExpanded = false
        campaignParcelId = ReadingPointListRules.ALL_PARCELS
        campaignSearchQuery = ""
        campaignNearbyMode = false
        readingAgentLocation = null
        readingSocialCards.clear()
        persistCampaign()
        currentScreen = Screen.READINGS
        renderCurrentScreen()
        toast("Corrigez le relevé refusé, puis enregistrez à nouveau.")
    }

    private fun showSyncJournal(items: List<JSONObject>) {
        val body = mg.hydria.shared.sync.QueueJournalGateway.journal(items)
        AlertDialog.Builder(this)
            .setTitle("Journal de la file")
            .setMessage(body)
            .setNeutralButton("Données locales") { _, _ -> showLocalDataSummary() }
            .setPositiveButton("Fermer", null)
            .show()
    }

    private fun showLocalDataSummary() {
        val snapshot = store.snapshot
        if (snapshot == null) {
            toast("Aucune donnée n'est encore enregistrée sur ce téléphone.")
            return
        }
        val terrainStats = snapshot.optJSONObject("terrain")?.optJSONObject("stats")
        val generated = snapshot.optString("generated_at", "date inconnue")
        val message = buildString {
            append("Dernière actualisation : $generated\n\n")
            if (terrainStats != null) {
                append("${terrainStats.optInt("total_ouvrages")} ouvrages\n")
                append("${terrainStats.optInt("total_points_eau")} points d'eau\n")
                append("${terrainStats.optInt("total_equipements")} équipements\n\n")
                append("À compléter :\n")
                append("• ${terrainStats.optInt("points_sans_coordonnees")} GPS\n")
                append("• ${terrainStats.optInt("points_sans_photo")} photos de points\n")
                append("• ${terrainStats.optInt("equipements_sans_photo")} photos d'équipements\n")
                append("• ${terrainStats.optInt("points_sans_nom_abonne")} noms d'abonnés")
            } else append("Les données classiques sont disponibles, mais le module Terrain serveur n'est pas encore chargé.")
        }
        AlertDialog.Builder(this).setTitle("Données locales disponibles")
            .setMessage(message)
            .setNegativeButton("Fermer", null)
            .setPositiveButton("Actualiser") { _, _ -> synchronize() }
            .show()
    }

    private fun syncPayloadDetails(item: JSONObject): String =
        mg.hydria.shared.sync.QueueJournalGateway.payloadDetails(item)

    private fun syncServerConflictDetails(conflict: JSONObject): String =
        mg.hydria.shared.sync.QueueJournalGateway.serverConflictDetails(conflict)

    private fun showSyncConflict(item: JSONObject) {
        val payload = item.optJSONObject("payload") ?: JSONObject()
        val conflict = payload.optJSONObject("_sync_conflict") ?: JSONObject()
        val comparison = buildString {
            append("VERSION DU TÉLÉPHONE\n")
            append(syncPayloadDetails(item))
            payload.optString("base_updated_at").takeIf { it.isNotBlank() }?.let {
                append("\nBasée sur la version du : $it")
            }
            append("\n\n")
            append(syncServerConflictDetails(conflict))
            append("\n\nForcer remplacera les champs concernés sur le serveur par ceux du téléphone.")
        }
        AlertDialog.Builder(this)
            .setTitle("Conflit de synchronisation")
            .setMessage(comparison)
            .setNegativeButton("Garder en attente", null)
            .setNeutralButton("Supprimer") { _, _ ->
                AlertDialog.Builder(this)
                    .setTitle("Annuler cette saisie locale ?")
                    .setMessage("La donnée enregistrée sur ce téléphone sera supprimée. La version du serveur sera conservée.")
                    .setNegativeButton("Retour", null)
                    .setPositiveButton("Supprimer la saisie") { _, _ ->
                        store.remove(item.optString("local_uuid"))
                        updateStatus()
                        renderCurrentScreen()
                        toast("Saisie locale supprimée. La version serveur est conservée.")
                    }
                    .show()
            }
            .setPositiveButton("Forcer l’envoi") { _, _ ->
                AlertDialog.Builder(this)
                    .setTitle("Remplacer la version serveur ?")
                    .setMessage("Cette action enverra la version du téléphone malgré le conflit.")
                    .setNegativeButton("Annuler", null)
                    .setPositiveButton("Confirmer et synchroniser") { _, _ ->
                        payload.remove("_sync_conflict")
                        payload.put("force_sync", "true")
                        store.updatePayload(item.optString("local_uuid"), payload)
                        synchronize()
                    }
                    .show()
            }
            .show()
    }

    /** Fond de la feuille modale : coins supérieurs arrondis (rayon 26 dp). */
    private fun sheetBackground(): android.graphics.drawable.GradientDrawable =
        android.graphics.drawable.GradientDrawable().apply {
            shape = android.graphics.drawable.GradientDrawable.RECTANGLE
            setColor(HydriaColors.surface)
            val r = dp(26).toFloat()
            cornerRadii = floatArrayOf(r, r, r, r, 0f, 0f, 0f, 0f)
        }

    /**
     * Pastille de synchronisation de l'en-tête (remplace la barre pleine largeur
     * de la v2.3). Un [override] non nul est un message d'échec transitoire :
     * il part en toast, la pastille garde son état.
     */
    private fun updateStatus(override: String? = null) {
        if (!::syncStatus.isInitialized) return
        override?.takeIf { !syncing }?.let { toast(it) }
        val pending = store.pendingCount()
        val online = isOnline()
        val tone = when {
            !online -> Tone.ERROR
            syncing || pending > 0 -> Tone.WARNING
            else -> Tone.SUCCESS
        }
        val accent = HydriaUi.toneColor(tone)
        // Hors ligne ET en attente : afficher le nombre (pas juste "hors ligne"), sinon
        // une saisie faite hors connexion semble ne jamais avoir rejoint la file — alors
        // qu'elle y est bien (voir contentDescription ci-dessous, déjà correct lui).
        val showsCount = !syncing && pending > 0
        syncStatus.text = when {
            syncing -> "…"
            pending > 0 -> pending.toString()
            !online -> "hors ligne"
            else -> "à jour"
        }
        syncStatus.typeface = if (showsCount) HydriaType.numeral(700) else HydriaType.display(600)
        syncStatus.textSize = if (showsCount) 13f else 12.5f
        syncStatus.setTextColor(HydriaUi.toneTextColor(tone))
        // Pastille visible de 38 dp dans une zone tactile de 48 dp ; setPadding() après le fond,
        // car l'InsetDrawable impose son propre padding à la vue.
        syncStatus.background = HydriaUi.withTouchInset(
            this,
            HydriaUi.rounded(
                this,
                Color.argb(36, Color.red(accent), Color.green(accent), Color.blue(accent)),
                19f,
                Color.argb(115, Color.red(accent), Color.green(accent), Color.blue(accent)),
            ),
            insetVerticalDp = 5f,
        )
        syncStatus.setPadding(dp(13), 0, dp(13), 0)
        syncStatus.contentDescription = when {
            !online -> "Hors ligne, $pending action(s) conservée(s) sur ce téléphone"
            pending > 0 -> "$pending action(s) à synchroniser, toucher pour ouvrir le centre de synchronisation"
            else -> "Synchronisation à jour"
        }
        updateNavigationBadges()
    }

    private fun updateNavigationBadges() {
        val item = navItems[Screen.REPAIRS] ?: return
        val count = repairsBadgeCount()
        item.badge.visibility = if (count > 0) View.VISIBLE else View.GONE
        item.badge.text = if (count > 99) "99+" else count.toString()
    }

    private fun isOnline(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        // Certains téléphones et réseaux d'entreprise ne positionnent jamais
        // VALIDATED malgré un accès HTTPS fonctionnel. En cas d'échec réel,
        // la tentative de synchronisation conserve simplement la file locale.
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    @Suppress("DEPRECATION")
    private fun appVersionName(): String = runCatching {
        packageManager.getPackageInfo(packageName, 0).versionName
    }.getOrNull().orEmpty().ifBlank { "2.1.4" }

    private fun jsonItems(array: JSONArray, label: (JSONObject) -> String): List<Pair<JSONObject, String>> =
        (0 until array.length()).map { array.getJSONObject(it).let { item -> item to label(item) } }
    private fun vertical(padding: Int = 0) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        if (padding > 0) setPadding(dp(padding), dp(padding), dp(padding), dp(padding))
    }
    private fun scroll(child: View) = ScrollView(this).apply {
        isFillViewport = true
        setBackgroundColor(HydriaColors.background)
        addView(child)
    }
    private fun text(value: String, size: Float, bold: Boolean, color: Int) = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(color)
        includeFontPadding = false
        setLineSpacing(0f, 1.12f)
        typeface = android.graphics.Typeface.create("sans-serif", if (bold) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
    }
    private fun title(value: String) = text(value, 25f, true, HydriaColors.text)
    private fun subtitle(value: String) = text(value, 13f, false, HydriaColors.textSecondary).apply { setPadding(0, dp(4), 0, dp(12)) }
    private fun label(value: String) = text(value, 13f, true, HydriaColors.textSecondary).apply { setPadding(0, dp(12), 0, dp(5)) }
    private fun field(hintValue: String) = EditText(this).apply {
        hint = hintValue
        setSingleLine(true)
        HydriaUi.styleInput(this)
    }
    private fun spinner(items: List<String>) = Spinner(this).apply {
        adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, items)
        HydriaUi.styleSpinner(this)
    }
    private fun card(emphasized: Boolean = false) = vertical(padding = if (emphasized) 17 else 14).apply {
        HydriaUi.card(this, emphasized)
    }
    private fun emptyState(title: String, message: String) = vertical(padding = 28).apply {
        gravity = Gravity.CENTER
        HydriaUi.card(this)
        addView(text(title, 18f, true, HydriaColors.text).apply { gravity = Gravity.CENTER })
        addView(text(message, 14f, false, HydriaColors.textSecondary).apply { gravity = Gravity.CENTER; setPadding(0, dp(8), 0, 0) })
    }
    private fun primaryButton(value: String) = Button(this).apply {
        text = value
        HydriaUi.stylePrimary(this)
    }
    private fun secondaryButton(value: String) = Button(this).apply {
        text = value
        HydriaUi.styleSecondary(this)
    }
    private fun matchWrap(height: Int = LinearLayout.LayoutParams.WRAP_CONTENT, top: Int = 0) =
        LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, if (height > 0) dp(height) else height).apply { topMargin = dp(top) }
    private fun wrapWrap(top: Int = 0) = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(top) }
    private fun weighted() = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f)
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    override fun onDestroy() {
        networkCallback?.let { callback ->
            val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            runCatching { manager.unregisterNetworkCallback(callback) }
        }
        executor.shutdownNow()
        super.onDestroy()
    }
}

/** Cible possible d'une réparation : point d'eau ("pe") ou équipement ("eq") de l'ouvrage choisi. */
private data class RepairTargetOption(val kind: String, val id: String, val label: String, val typeId: String)

private class SimpleItemSelectedListener(private val selected: (Int) -> Unit) : android.widget.AdapterView.OnItemSelectedListener {
    override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) = selected(position)
    override fun onNothingSelected(parent: android.widget.AdapterView<*>?) = Unit
}
