package mg.hydria.app.navigation

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.RectF
import android.location.Location
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.graphics.ColorUtils
import com.google.android.material.bottomsheet.BottomSheetDialog
import mg.hydria.app.HydriaNetwork
import mg.hydria.app.HydriaColors
import mg.hydria.app.HydriaType
import mg.hydria.app.HydriaUi
import mg.hydria.app.search.SearchDetailActivity
import mg.hydria.app.HydriaWindow
import mg.hydria.app.OfflineStore
import mg.hydria.app.navigation.data.GeoRepository
import mg.hydria.app.navigation.geo.GeoMath
import mg.hydria.app.navigation.geo.IndicatorCandidate
import mg.hydria.app.navigation.location.HeadingController
import mg.hydria.app.navigation.location.TerrainLocationController
import mg.hydria.app.navigation.map.MarkerLayerManager
import mg.hydria.app.navigation.model.CapturedPosition
import mg.hydria.app.navigation.model.GeoCategory
import mg.hydria.app.navigation.model.GeoEntity
import mg.hydria.app.navigation.model.NavigationMode
import mg.hydria.app.navigation.model.NavigationConfig
import mg.hydria.app.navigation.model.NavigationTarget
import mg.hydria.app.navigation.model.NavigationRoute
import mg.hydria.app.navigation.model.PlacementCandidate
import mg.hydria.app.navigation.model.RouteProfile
import mg.hydria.app.navigation.sync.NavigationSyncManager
import mg.hydria.app.navigation.ui.EdgeIndicatorsView
import mg.hydria.shared.navigation.IndicatorSelection
import mg.hydria.shared.navigation.ScreenPoint
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.Style
import org.maplibre.geojson.Point
import java.io.ByteArrayOutputStream
import java.io.File
import java.time.Instant
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors

class NavigationTerrainActivity : AppCompatActivity() {
    companion object {
        /** Rayon autour de l'utilisateur dans lequel toutes les entités sont toujours chargées. */
        private const val NEAR_USER_RADIUS_M = 3_000.0
        private const val ONLINE_STYLE_URL ="https://tiles.openfreemap.org/styles/liberty"
        private const val ROUTE_PREFS = "hydria_navigation_route"
        /** Au-delà de ce déplacement depuis le point de calcul, l'itinéraire est recalculé. */
        private const val ROUTE_REFRESH_DISTANCE_M = 300.0
        private const val ROUTE_REFRESH_MIN_AGE_MS = 20_000L
        private const val ROUTE_RETRY_AGE_MS = 30_000L
    }
    private lateinit var mapView: MapView
    private var map: MapLibreMap? = null
    private var layers: MarkerLayerManager? = null
    private lateinit var store: OfflineStore
    private lateinit var repository: GeoRepository
    private lateinit var syncManager: NavigationSyncManager
    private val syncExecutor = Executors.newSingleThreadExecutor()
    private val routeExecutor = Executors.newSingleThreadExecutor()
    private var navigationConfig = NavigationConfig()
    private var navigationSyncing = false
    private lateinit var status: TextView
    private lateinit var modeLabel: TextView
    private lateinit var hud: LinearLayout
    private lateinit var hudArrow: TextView
    private lateinit var hudName: TextView
    private lateinit var hudDistance: TextView
    private lateinit var hudMeta: TextView
    private lateinit var edgeIndicators: EdgeIndicatorsView
    private var wideNav = false
    private var nearbyList: LinearLayout? = null
    private lateinit var locationController: TerrainLocationController
    private lateinit var headingController: HeadingController
    private var entities = emptyList<GeoEntity>()
    private var visibleCategories = GeoCategory.entries.toMutableSet()
    private var currentLocation: Location? = null
    private var centeredOnUser = false
    private var headingDegrees = 0.0
    private var mode = NavigationMode.FOLLOW_GPS
    private var target: NavigationTarget? = null
    private var directionUp = false
    private var arrivalShownFor: String? = null
    // Itinéraire routier (calculé par le serveur ; sans réseau on garde le cap direct).
    private var routeProfile = RouteProfile.MOTO
    private var activeRoute: NavigationRoute? = null
    private var routeRequestId = 0
    private var routeInFlight = false
    private var routeFetchedAtMs = 0L
    private lateinit var hudRoute: TextView
    private lateinit var hudProfileButton: Button
    private var usingOnlineStyle = false
    private var offlineFallbackStarted = false
    private var pendingPhotoCandidate: PlacementCandidate? = null
    private var pendingPhotoFile: File? = null

    private val locationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) locationController.start() else updateStatus("Localisation refusée")
    }

    private val entityPhotoLauncher = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val candidate = pendingPhotoCandidate
        val photoFile = pendingPhotoFile
        if (success && candidate != null && photoFile != null) {
            runCatching { compressEntityPhoto(photoFile) }
                .onSuccess { encoded -> queueEntityPhoto(candidate, encoded) }
                .onFailure { toast("Impossible de préparer la photo : ${it.message ?: "erreur inconnue"}") }
        }
        photoFile?.delete()
        pendingPhotoCandidate = null
        pendingPhotoFile = null
    }

    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val candidate = pendingPhotoCandidate
        if (granted && candidate != null) launchEntityPhoto(candidate)
        else {
            pendingPhotoCandidate = null
            pendingPhotoFile = null
            toast("Autorisez l'appareil photo pour photographier l'entité.")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        HydriaType.bind(this)
        MapLibre.getInstance(applicationContext)
        routeProfile = RouteProfile.fromKey(getSharedPreferences(ROUTE_PREFS, MODE_PRIVATE).getString("profile", null))
        store = OfflineStore(this)
        repository = GeoRepository(store)
        syncManager = NavigationSyncManager(this, repository)
        repository.importSnapshot(store.snapshot)
        entities = repository.allEntities(limit = 600)
        buildUi(savedInstanceState)
        locationController = TerrainLocationController(this, ::onLocation, ::updateStatus)
        headingController = HeadingController(this, ::onHeading)
        synchronizeNavigation()
    }

    private fun buildUi(savedInstanceState: Bundle?) {
        wideNav = HydriaWindow.of(this).isTablet
        val panelW = if (wideNav) dp(392) else 0
        val root = FrameLayout(this).apply { setBackgroundColor(HydriaColors.backgroundDeep) }
        mapView = MapView(this)
        mapView.onCreate(savedInstanceState)
        root.addView(mapView, FrameLayout.LayoutParams(-1, -1))

        edgeIndicators = EdgeIndicatorsView(this)
        root.addView(edgeIndicators, FrameLayout.LayoutParams(-1, -1))

        val top = vertical(10).apply {
            background = HydriaUi.rounded(this@NavigationTerrainActivity, overlayColor(238), 14f, HydriaColors.outline)
            addView(horizontal().apply {
                addView(button("←") { finish() }, LinearLayout.LayoutParams(dp(48), dp(44)))
                addView(vertical(0).apply {
                    addView(label("NAVIGATION TERRAIN", 16f, true))
                    modeLabel = label("Suivi GPS", 12f, false, HydriaColors.cyanText)
                    addView(modeLabel)
                }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(8) })
                addView(button("Sync") { synchronizeNavigation() }, LinearLayout.LayoutParams(dp(66), dp(44)))
                addView(button("Couches") { showLayerFilters() }, LinearLayout.LayoutParams(dp(88), dp(44)).apply { marginStart = dp(6) })
            })
            status = label("Initialisation de la carte locale…", 12f, false, HydriaColors.textSecondary)
            addView(status, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(5) })
        }
        // Filtres de couches actionnables (remplacent la légende non cliquable).
        top.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(horizontal().apply {
                GeoCategory.entries.forEach { category ->
                    addView(layerChip(category), LinearLayout.LayoutParams(-2, dp(32)).apply { marginEnd = dp(6) })
                }
            })
        }, LinearLayout.LayoutParams(-1, dp(32)).apply { topMargin = dp(6) })
        root.addView(top, FrameLayout.LayoutParams(-1, -2, Gravity.TOP).apply {
            setMargins(dp(10), dp(10), dp(10) + panelW, 0)
        })

        val tools = vertical(6).apply {
            addView(button("◎") { recenter() }, LinearLayout.LayoutParams(dp(54), dp(50)))
            addView(button("N") { toggleOrientation() }, LinearLayout.LayoutParams(dp(54), dp(50)).apply { topMargin = dp(6) })
            addView(button("+") { zoomBy(1.0) }, LinearLayout.LayoutParams(dp(54), dp(50)).apply { topMargin = dp(6) })
            addView(button("−") { zoomBy(-1.0) }, LinearLayout.LayoutParams(dp(54), dp(50)).apply { topMargin = dp(6) })
        }
        root.addView(tools, FrameLayout.LayoutParams(-2, -2, Gravity.END or Gravity.CENTER_VERTICAL).apply { marginEnd = dp(12) + panelW })

        hud = vertical(12).apply {
            visibility = View.GONE
            background = HydriaUi.rounded(this@NavigationTerrainActivity, overlayColor(245), 20f, HydriaColors.vase)
            addView(horizontal().apply {
                // Cercle de cap (62 dp) : fond vase translucide, filet 2 dp vase.
                val circle = FrameLayout(this@NavigationTerrainActivity).apply {
                    background = HydriaUi.rounded(
                        this@NavigationTerrainActivity, Color.argb(38, 242, 154, 56), 31f, HydriaColors.vase, 2f,
                    )
                }
                hudArrow = TextView(this@NavigationTerrainActivity).apply {
                    text = "↑"
                    textSize = 28f
                    setTextColor(HydriaColors.vaseText)
                    gravity = Gravity.CENTER
                    typeface = HydriaType.display(700)
                }
                circle.addView(hudArrow, FrameLayout.LayoutParams(-1, -1))
                addView(circle, LinearLayout.LayoutParams(dp(62), dp(62)))
                addView(vertical(0).apply {
                    addView(TextView(this@NavigationTerrainActivity).apply {
                        text = "EN ROUTE"
                        textSize = 10f
                        typeface = HydriaType.display(600)
                        setTextColor(HydriaColors.textSecondary)
                        letterSpacing = 0.09f
                    })
                    hudName = label("", 15f, true)
                    addView(hudName, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(2) })
                    hudDistance = TextView(this@NavigationTerrainActivity).apply {
                        textSize = 22f
                        typeface = HydriaType.numeral(700)
                        letterSpacing = -0.03f
                        setTextColor(HydriaColors.text)
                    }
                    addView(hudDistance, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(2) })
                    hudMeta = label("", 12f, false, HydriaColors.textSecondary)
                    addView(hudMeta)
                }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(12) })
                addView(button("Annuler") { cancelNavigation() }, LinearLayout.LayoutParams(dp(88), dp(48)))
            })
            addView(horizontal().apply {
                hudProfileButton = button("") { cycleRouteProfile() }
                addView(hudProfileButton, LinearLayout.LayoutParams(dp(112), dp(40)))
                hudRoute = label("", 12f, false, HydriaColors.textSecondary)
                addView(hudRoute, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(10) })
                addView(button("Tracé") { showRouteOverview() }, LinearLayout.LayoutParams(dp(72), dp(40)))
            }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
            updateProfileButton()
        }
        val actions = horizontal().apply {
            addView(button("Marquer ma position") { markCurrentPosition() }, LinearLayout.LayoutParams(0, dp(58), 1f))
            addView(button("Placer sur la carte") { markMapCenter() }, LinearLayout.LayoutParams(0, dp(58), 1f).apply { marginStart = dp(8) })
        }

        if (wideNav) {
            // 4c : le guidage devient une colonne fixe à droite ; la carte garde toute sa surface.
            val panel = vertical(10).apply {
                setBackgroundColor(HydriaColors.background)
                addView(hud, LinearLayout.LayoutParams(-1, -2))
                addView(TextView(this@NavigationTerrainActivity).apply {
                    text = "AUTOUR DE MOI · 500 M"
                    textSize = 10.5f
                    typeface = HydriaType.display(600)
                    letterSpacing = 0.09f
                    setTextColor(HydriaColors.textMuted)
                    setPadding(0, dp(12), 0, dp(6))
                })
                val nl = LinearLayout(this@NavigationTerrainActivity).apply { orientation = LinearLayout.VERTICAL }
                nearbyList = nl
                addView(android.widget.ScrollView(this@NavigationTerrainActivity).apply { addView(nl) },
                    LinearLayout.LayoutParams(-1, 0, 1f))
                addView(actions, LinearLayout.LayoutParams(-1, dp(64)).apply { topMargin = dp(8) })
            }
            root.addView(panel, FrameLayout.LayoutParams(panelW, -1, Gravity.END))
        } else {
            root.addView(hud, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM).apply {
                setMargins(dp(10), 0, dp(10), dp(84))
            })
            root.addView(actions, FrameLayout.LayoutParams(-1, dp(70), Gravity.BOTTOM).apply { setMargins(dp(10), 0, dp(10), dp(8)) })
        }
        setContentView(root)

        mapView.getMapAsync { mapLibreMap ->
            map = mapLibreMap
            mapLibreMap.uiSettings.apply {
                isCompassEnabled = false; isZoomGesturesEnabled = true; isRotateGesturesEnabled = true
                isTiltGesturesEnabled = false; isLogoEnabled = false
            }
            mapView.addOnDidFailLoadingMapListener { _ ->
                if (usingOnlineStyle && !offlineFallbackStarted) {
                    offlineFallbackStarted = true
                    runOnUiThread {
                        updateStatus("Fond en ligne indisponible : fond local active")
                        loadNavigationStyle(mapLibreMap, forceOffline = true)
                    }
                }
            }
            loadNavigationStyle(mapLibreMap)
            mapLibreMap.addOnMapClickListener { point -> selectAt(point) }
            mapLibreMap.addOnMapLongClickListener { point -> chooseMarkerCategoryAt(point.latitude, point.longitude, "carte", null) ; true }
            mapLibreMap.addOnCameraMoveStartedListener { reason ->
                if (reason == MapLibreMap.OnCameraMoveStartedListener.REASON_API_GESTURE && mode != NavigationMode.NAVIGATE) {
                    mode = NavigationMode.EXPLORE; updateMode()
                }
            }
            mapLibreMap.addOnCameraIdleListener { refreshMarkers() }
            if (entities.isNotEmpty()) {
                val first = entities.first()
                mapLibreMap.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(first.latitude, first.longitude), 13.0))
            }
        }
    }

    private fun loadNavigationStyle(mapLibreMap: MapLibreMap, forceOffline: Boolean = false) {
        usingOnlineStyle = !forceOffline && isOnline()
        mapLibreMap.uiSettings.isAttributionEnabled = usingOnlineStyle
        val styleUri = if (usingOnlineStyle) ONLINE_STYLE_URL else "asset://navigation_neutral_style.json"
        mapLibreMap.setStyle(Style.Builder().fromUri(styleUri)) { style ->
            layers = MarkerLayerManager(style)
            activeRoute?.let { layers?.showRoute(it.coordinates) }
            refreshMarkers()
            updateStatus(if (usingOnlineStyle) "Fond de carte en ligne" else "Fond de carte local")
        }
    }

    private fun refreshMarkers() {
        val center = map?.cameraPosition?.target
        entities = if (center != null) {
            val bounds = map?.projection?.visibleRegion?.latLngBounds
            if (bounds != null && !bounds.isEmptySpan) {
                val latitudePadding = (bounds.latitudeSpan * 0.12).coerceAtLeast(0.001)
                val longitudePadding = (bounds.longitudeSpan * 0.12).coerceAtLeast(0.001)
                repository.withinBounds(
                    north = (bounds.latitudeNorth + latitudePadding).coerceAtMost(90.0),
                    south = (bounds.latitudeSouth - latitudePadding).coerceAtLeast(-90.0),
                    east = (bounds.longitudeEast + longitudePadding).coerceAtMost(180.0),
                    west = (bounds.longitudeWest - longitudePadding).coerceAtLeast(-180.0),
                    centerLatitude = center.latitude,
                    centerLongitude = center.longitude,
                    limit = 600,
                )
            } else repository.allEntities(limit = 600)
        } else {
            repository.allEntities(limit = 600)
        }
        // Priorité aux environs de l'utilisateur : toutes les entités à moins de NEAR_USER_RADIUS_M
        // sont toujours affichées, même si la zone visible est dense (sinon elles sont évincées
        // par la limite de 600, triée autour du centre de la carte).
        val user = currentLocation
        if (user != null) {
            val near = repository.nearby(user.latitude, user.longitude, NEAR_USER_RADIUS_M, limit = 800)
            if (near.isNotEmpty()) {
                val seen = HashSet<String>(entities.size + near.size)
                entities = (near + entities).filter { seen.add(it.id) }
            }
        }
        val filtered = entities.filter { it.category in visibleCategories }
        layers?.submit(filtered)
        updateIndicators()
        updateNearbyPanel()
    }

    /** Liste « Autour de moi » de la colonne latérale (tablette) — rayon 500 m, triée par distance. */
    private fun updateNearbyPanel() {
        val list = nearbyList ?: return
        list.removeAllViews()
        val originLat = currentLocation?.latitude ?: map?.cameraPosition?.target?.latitude
        val originLon = currentLocation?.longitude ?: map?.cameraPosition?.target?.longitude
        if (originLat == null || originLon == null) {
            list.addView(label("Position en attente…", 12f, false, HydriaColors.textSecondary))
            return
        }
        val rows = entities.asSequence()
            .filter { it.category in visibleCategories }
            .map { it to GeoMath.distanceMeters(originLat, originLon, it.latitude, it.longitude) }
            .filter { it.second <= 500.0 }
            .sortedBy { it.second }
            .take(40)
            .toList()
        if (rows.isEmpty()) {
            list.addView(label("Rien dans un rayon de 500 m.", 12f, false, HydriaColors.textSecondary))
            return
        }
        rows.forEach { (entity, distance) ->
            list.addView(nearbyRow(entity, distance), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })
        }
    }

    private fun nearbyRow(entity: GeoEntity, distance: Double): View = horizontal().apply {
        setPadding(dp(10), dp(8), dp(10), dp(8))
        isClickable = true
        background = HydriaUi.rounded(this@NavigationTerrainActivity, HydriaColors.surface, 10f, HydriaColors.outlineSoft)
        addView(View(this@NavigationTerrainActivity).apply {
            background = HydriaUi.rounded(this@NavigationTerrainActivity, catColor(entity.category), 4f)
        }, LinearLayout.LayoutParams(dp(8), dp(8)).apply { marginEnd = dp(8) })
        addView(vertical(0).apply {
            addView(label(entity.name.ifBlank { entity.category.label }, 13f, true).apply { maxLines = 1 })
            addView(label(entity.category.label, 10.5f, false, HydriaColors.textMuted))
        }, LinearLayout.LayoutParams(0, -2, 1f))
        addView(TextView(this@NavigationTerrainActivity).apply {
            text = GeoMath.formatDistance(distance)
            typeface = HydriaType.numeral(700)
            textSize = 13f
            setTextColor(HydriaColors.textSecondary)
        }, LinearLayout.LayoutParams(-2, -2))
        setOnClickListener { startNavigation(entity) }
    }

    private fun selectAt(point: LatLng): Boolean {
        val mapLibreMap = map ?: return false
        val screenPoint = mapLibreMap.projection.toScreenLocation(point)
        // RECH_NAV-01 : zone de ±24 dp autour du doigt (un picto fait ~20 dp) sur les entités, les
        // villages et les grappes ; on garde l'élément dont le centre est le plus proche du doigt.
        val reach = dp(24).toFloat()
        val area = RectF(screenPoint.x - reach, screenPoint.y - reach, screenPoint.x + reach, screenPoint.y + reach)
        val feature = IndicatorSelection.nearestHit(
            mapLibreMap.queryRenderedFeatures(
                area, MarkerLayerManager.ENTITY_LAYER, MarkerLayerManager.VILLAGE_MARKER_LAYER, MarkerLayerManager.CLUSTER_LAYER,
            ),
            screenPoint.x, screenPoint.y, reach * 2f,
        ) { candidate ->
            val position = candidate.geometry() as? Point
            if (position == null) ScreenPoint(Float.MAX_VALUE, Float.MAX_VALUE)
            else mapLibreMap.projection.toScreenLocation(LatLng(position.latitude(), position.longitude())).let { ScreenPoint(it.x, it.y) }
        } ?: return false
        if (feature.hasProperty("point_count")) {
            // Grappe : zoom de +2 niveaux centré sur elle, TOUJOURS en exploration libre, même pendant une navigation :
            // en NAVIGATE (comme en suivi GPS), le prochain fix GPS recentrerait la carte sur l'agent et annulerait le
            // geste. Comme showRouteOverview(), la cible et le HUD restent actifs ; « ◎ » ramène au suivi.
            val center = (feature.geometry() as? Point)?.let { LatLng(it.latitude(), it.longitude()) } ?: point
            mode = NavigationMode.EXPLORE; updateMode()
            val zoom = (mapLibreMap.cameraPosition.zoom + 2.0).coerceAtMost(mapLibreMap.maxZoomLevel)
            mapLibreMap.animateCamera(CameraUpdateFactory.newLatLngZoom(center, zoom))
            return true
        }
        val id = feature.getStringProperty("entity_id") ?: return false
        val category = feature.getStringProperty("category") ?: return false
        entities.firstOrNull { it.id == id && it.category.storageKey == category }?.let(::showEntitySheet)
        return true
    }

    private fun showEntitySheet(entity: GeoEntity) {
        val origin = currentLocation
        val distance = origin?.let { GeoMath.distanceMeters(it.latitude, it.longitude, entity.latitude, entity.longitude) }
        val dialog = BottomSheetDialog(this)
        val body = vertical(18).apply {
            setBackgroundColor(HydriaColors.surface)
            addView(label(entity.name, 22f, true))
            addView(label("${entity.category.label} · ${entity.typeLabel.ifBlank { "Type non renseigné" }}", 13f, false, HydriaColors.cyan))
            distance?.let { addView(label(GeoMath.formatDistance(it), 16f, true, HydriaColors.vase)) }
            addView(label(String.format(Locale.FRANCE, "%.7f, %.7f", entity.latitude, entity.longitude), 13f, false, HydriaColors.textSecondary))
            addView(label("Synchronisation : ${entity.syncState}", 12f, false, HydriaColors.textSecondary))
            if (entity.code.isNotBlank()) addView(label("Code : ${entity.code}", 12f, false, HydriaColors.textSecondary))
            addView(button("Y aller") { dialog.dismiss(); startNavigation(entity) }, LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(12) })
            addView(button("Centrer") { dialog.dismiss(); centerOn(entity, 17.0) }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(7) })
            val detailType = detailTypeOf(entity.category)
            if (detailType != null) {
                addView(button("Voir la fiche") {
                    dialog.dismiss(); openEntityDetail(detailType, entity.id, entity.name, entity)
                }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(7) })
            } else {
                addView(label("Repère de terrain : pas de fiche.", 12f, false, HydriaColors.textMuted),
                    LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })
            }
            if (entity.ouvrageId.isNotBlank() && (entity.category == GeoCategory.WATER_POINT || entity.category == GeoCategory.EQUIPMENT)) {
                addView(button("Voir l'ouvrage") {
                    dialog.dismiss(); openEntityDetail("ouvrage", entity.ouvrageId, "Ouvrage", null)
                }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(7) })
            }
            if (navigationConfig.canModifyPositions) addView(button("Modifier la position GPS") {
                dialog.dismiss(); captureEntityPosition(entity)
            }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(7) })
            val photoCandidate = if (entity.category == GeoCategory.WATER_POINT || entity.category == GeoCategory.EQUIPMENT) {
                repository.placementCandidate(entity.category, entity.id)
            } else null
            if (photoCandidate != null && !photoCandidate.hasPhoto) addView(button("Prendre une photo") {
                dialog.dismiss(); captureEntityPhoto(photoCandidate)
            }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(7) })
            if (entity.isFieldMarker && navigationConfig.canCreateLandmarks) addView(button("Archiver le marquage") {
                dialog.dismiss(); confirmArchiveLandmark(entity)
            }, LinearLayout.LayoutParams(-1, dp(50)).apply { topMargin = dp(7) })
        }
        dialog.setContentView(body)
        dialog.show()
    }

    /** Type de fiche de la Recherche correspondant à une catégorie de la carte (les repères n'ont pas de fiche). */
    private fun detailTypeOf(category: GeoCategory): String? = when (category) {
        GeoCategory.VILLAGE -> "village"
        GeoCategory.WATER_POINT -> "point_eau"
        GeoCategory.EQUIPMENT -> "equipement"
        else -> null
    }

    /**
     * Ouvre la fiche complète d'une entité ; la fiche propose « Retour à la carte ». Hors ligne et sans fiche en
     * cache, l'aperçu est construit avec ce que la carte connaît déjà de l'entité.
     */
    private fun openEntityDetail(type: String, id: String, title: String, entity: GeoEntity?) {
        startActivity(Intent(this, SearchDetailActivity::class.java).apply {
            putExtra("entity_type", type)
            putExtra("entity_id", id)
            putExtra("title", title)
            putExtra("from_navigation", true)
            if (entity != null) {
                putExtra("cached_item", org.json.JSONObject()
                    .put("id", entity.id)
                    .put("title", entity.name)
                    .put("type_display", entity.category.label)
                    .put("details", org.json.JSONObject()
                        .put("type", entity.typeLabel)
                        .put("code", entity.code)
                        .put("latitude", entity.latitude)
                        .put("longitude", entity.longitude))
                    .toString())
            }
        })
    }

    private fun startNavigation(entity: GeoEntity) {
        target = NavigationTarget(entity, navigationConfig.arrivalRadiusMeters)
        mode = NavigationMode.NAVIGATE
        arrivalShownFor = null
        hud.visibility = View.VISIBLE
        activeRoute = null; layers?.clearRoute()
        updateMode(); updateNavigationHud(); updateIndicators()
        requestRoute()
    }

    private fun cancelNavigation() {
        target = null; mode = NavigationMode.FOLLOW_GPS; hud.visibility = View.GONE
        routeRequestId++; routeInFlight = false; activeRoute = null; layers?.clearRoute()
        updateMode(); updateIndicators()
    }

    private fun onLocation(location: Location) {
        if (!mg.hydria.shared.navigation.NavigationProgressRules.acceptsLocation(System.currentTimeMillis(), location.time)) return
        currentLocation = location
        layers?.updateLocation(location.latitude, location.longitude)
        if (!centeredOnUser && map != null) {
            // Premier fix : on cadre l'utilisateur de près (au lieu du zoom 13 centré sur une
            // entité quelconque) et on recharge les marqueurs autour de lui.
            centeredOnUser = true
            map?.moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(location.latitude, location.longitude), 15.0))
            refreshMarkers()
        } else if (mode == NavigationMode.FOLLOW_GPS || mode == NavigationMode.NAVIGATE) {
            map?.animateCamera(CameraUpdateFactory.newLatLng(LatLng(location.latitude, location.longitude)), 350)
        }
        updateNavigationHud(); updateIndicators(); updateStatus(); updateNearbyPanel()
        maybeRefreshRoute(location)
    }

    private fun onHeading(value: Double) {
        headingDegrees = value
        if (directionUp && mode != NavigationMode.EXPLORE) {
            map?.moveCamera(CameraUpdateFactory.newCameraPosition(
                CameraPosition.Builder(map?.cameraPosition).bearing(value).build()
            ))
        }
        updateNavigationHud(); updateIndicators()
    }

    private fun updateNavigationHud() {
        val destination = target?.entity ?: return
        hudName.text = destination.name
        val location = currentLocation ?: run {
            hudDistance.text = "—"
            hudMeta.text = "Position GPS en attente…"
            return
        }
        val reference = if (directionUp) headingDegrees else (map?.cameraPosition?.bearing ?: 0.0)
        val progress = mg.hydria.shared.navigation.NavigationProgressRules.calculate(
            location.latitude, location.longitude, destination.latitude, destination.longitude,
            reference, location.speed.takeIf { location.hasSpeed() }, target?.arrivalRadiusMeters ?: 25.0,
        )
        val distance = progress.distanceMeters
        val bearing = progress.bearingDegrees
        hudArrow.rotation = progress.relativeDirectionDegrees.toFloat()
        val eta = progress.estimatedMinutes?.let { " · ~$it min" }.orEmpty()
        hudDistance.text = GeoMath.formatDistance(distance)
        hudMeta.text = "à vol d'oiseau · cap ${bearing.toInt()}°$eta · GPS ±${location.accuracy.toInt()} m"
        if (progress.hasArrived && arrivalShownFor != destination.id) {
            arrivalShownFor = destination.id
            AlertDialog.Builder(this).setTitle("Destination atteinte")
                .setMessage("Vous êtes à moins de ${(target?.arrivalRadiusMeters ?: 25.0).toInt()} m de ${destination.name}.")
                .setPositiveButton("Terminer") { _, _ -> cancelNavigation() }
                .setNegativeButton("Continuer", null).show()
        }
    }

    private fun cycleRouteProfile() {
        routeProfile = routeProfile.next()
        getSharedPreferences(ROUTE_PREFS, MODE_PRIVATE).edit().putString("profile", routeProfile.key).apply()
        updateProfileButton()
        if (target != null) requestRoute()
    }

    private fun updateProfileButton() {
        if (::hudProfileButton.isInitialized) hudProfileButton.text = "${routeProfile.icon} ${routeProfile.label}"
    }

    /** Demande au serveur l'itinéraire routier position actuelle -> cible ; hors ligne, on garde le cap direct. */
    private fun requestRoute() {
        val destination = target?.entity ?: return
        val location = currentLocation ?: run { hudRoute.text = "Itinéraire : position GPS en attente…"; return }
        val token = store.token
        if (token == null || !isOnline()) { setRouteUnavailable("hors connexion"); return }
        val requestId = ++routeRequestId
        val profile = routeProfile
        val fromLat = location.latitude
        val fromLon = location.longitude
        routeInFlight = true
        routeFetchedAtMs = System.currentTimeMillis()
        hudRoute.text = "Calcul de l'itinéraire…"
        routeExecutor.execute {
            val response = runCatching {
                HydriaNetwork.navigationRoute(token, fromLat, fromLon, destination.latitude, destination.longitude, profile.key)
            }.getOrNull()
            runOnUiThread {
                // Réponse périmée (cible changée, annulation, autre profil demandé entre-temps) : on l'ignore.
                if (requestId != routeRequestId || target?.entity?.id != destination.id) return@runOnUiThread
                routeInFlight = false
                val route = response?.takeIf { it.successful }?.let { NavigationRoute.fromJson(it.body, fromLat, fromLon) }
                if (route != null) {
                    activeRoute = route
                    layers?.showRoute(route.coordinates)
                    updateRouteLabel()
                } else {
                    activeRoute = null
                    layers?.clearRoute()
                    setRouteUnavailable(response?.error?.takeIf { it.isNotBlank() } ?: "serveur injoignable")
                }
            }
        }
    }

    /** Recalcule si l'agent s'est éloigné du point de calcul, ou retente si aucun itinéraire n'a pu être obtenu. */
    private fun maybeRefreshRoute(location: Location) {
        if (target == null || routeInFlight) return
        val age = System.currentTimeMillis() - routeFetchedAtMs
        val route = activeRoute
        val stale = if (route == null) age > ROUTE_RETRY_AGE_MS else {
            age > ROUTE_REFRESH_MIN_AGE_MS && GeoMath.distanceMeters(
                route.originLatitude, route.originLongitude, location.latitude, location.longitude,
            ) > ROUTE_REFRESH_DISTANCE_M
        }
        if (stale) requestRoute()
    }

    private fun updateRouteLabel() {
        val route = activeRoute ?: return
        val walk = if (route.walkMeters >= 150) " · dont ${GeoMath.formatDistance(route.walkMeters.toDouble())} à pied" else ""
        hudRoute.text = "Par la route : ${GeoMath.formatDistance(route.distanceKm * 1000)} · " +
            "~${NavigationRoute.formatDuration(route.durationMinutes)} (${route.profile.label.lowercase(Locale.FRANCE)})$walk"
    }

    private fun setRouteUnavailable(reason: String) {
        hudRoute.text = "Itinéraire routier indisponible ($reason) — cap direct"
    }

    /** Cadre toute la route à l'écran (passe en exploration libre pour que le suivi GPS ne recentre pas). */
    private fun showRouteOverview() {
        val route = activeRoute ?: run { toast("Aucun itinéraire à afficher"); return }
        mode = NavigationMode.EXPLORE; updateMode()
        val bounds = LatLngBounds.Builder().apply { route.coordinates.forEach { include(LatLng(it[1], it[0])) } }.build()
        map?.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds, dp(60)), 600)
    }

    private fun updateIndicators() {
        if (!::edgeIndicators.isInitialized || edgeIndicators.width == 0) return
        val mapLibreMap = map ?: return
        val cameraTarget = mapLibreMap.cameraPosition.target ?: return
        val originLat = currentLocation?.latitude ?: cameraTarget.latitude
        val originLon = currentLocation?.longitude ?: cameraTarget.longitude
        val cameraBearing = mapLibreMap.cameraPosition.bearing
        val destinationId = target?.entity?.id
        val candidates = mg.hydria.shared.navigation.IndicatorSelection.select(
            entities, visibleCategories, originLat, originLon, cameraBearing, destinationId,
            edgeIndicators.width.toFloat(), edgeIndicators.height.toFloat(), navigationConfig.maxEdgeIndicators,
        ) { entity ->
            val screen = mapLibreMap.projection.toScreenLocation(LatLng(entity.latitude, entity.longitude))
            mg.hydria.shared.navigation.ScreenPoint(screen.x, screen.y)
        }.map { IndicatorCandidate(it.entity, it.distanceMeters, it.relativeBearingDegrees, it.isDestination) }
        edgeIndicators.submit(candidates) { candidate ->
            showEntitySheet(candidate.entity)
        }
    }

    private fun captureEntityPosition(entity: GeoEntity) {
        val location = currentLocation ?: run { toast("Position GPS indisponible") ; return }
        val warning = if (location.accuracy > 30f) "\nAttention : précision faible (±${location.accuracy.toInt()} m)." else ""
        AlertDialog.Builder(this).setTitle("Remplacer les coordonnées ?")
            .setMessage("La position actuelle sera conservée dans l’historique.$warning")
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Enregistrer") { _, _ ->
                val captured = location.toCaptured("gps")
                val localUuid = repository.updatePosition(entity, captured)
                store.enqueue("geo_position_upsert",
                    mg.hydria.shared.navigation.GeoOperationPayloads.updatePosition(entity, localUuid, captured))
                entities = repository.allEntities(limit = 600); refreshMarkers(); updateStatus("Position enregistrée hors ligne")
            }.show()
    }

    private fun markCurrentPosition() {
        val location = currentLocation ?: run { toast("Position GPS indisponible") ; return }
        chooseMarkerCategoryAt(location.latitude, location.longitude, "gps", location)
    }

    private fun confirmArchiveLandmark(entity: GeoEntity) {
        AlertDialog.Builder(this).setTitle("Archiver ce repère ?")
            .setMessage(entity.name)
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Archiver") { _, _ ->
                val localUuid = repository.archiveLandmark(entity)
                store.enqueue("landmark_archive",
                    mg.hydria.shared.navigation.GeoOperationPayloads.archiveLandmark(entity, localUuid))
                entities = repository.allEntities(limit = 600)
                refreshMarkers()
                updateStatus("Repère archivé hors ligne")
            }.show()
    }

    private fun markMapCenter() {
        val center = map?.cameraPosition?.target ?: run { toast("Carte indisponible") ; return }
        chooseMarkerCategoryAt(center.latitude, center.longitude, "carte", null)
    }

    private fun chooseMarkerCategoryAt(latitude: Double, longitude: Double, method: String, location: Location?) {
        if (!navigationConfig.canCreateLandmarks) { toast("Creation de marquages non autorisee") ; return }
        val categories = listOf(GeoCategory.WATER_POINT, GeoCategory.EQUIPMENT, GeoCategory.LANDMARK)
        AlertDialog.Builder(this)
            .setTitle("Que voulez-vous marquer ?")
            .setItems(categories.map { it.label }.toTypedArray()) { _, which ->
                val category = categories[which]
                if (category == GeoCategory.LANDMARK) {
                    createLandmarkAt(latitude, longitude, method, location)
                } else {
                    showCoordinateStatePicker(category, latitude, longitude, method, location)
                }
            }
            .setNegativeButton("Annuler", null)
            .show()
    }

    private fun showCoordinateStatePicker(
        category: GeoCategory,
        latitude: Double,
        longitude: Double,
        method: String,
        location: Location?,
    ) {
        val all = repository.placementCandidates(category)
        val nearbyCandidateIds = repository.candidateIdsServingNearbyVillages(category, latitude, longitude)
        val availability = mg.hydria.shared.navigation.NavigationFormRules.coordinates(all, nearbyCandidateIds)
        val withoutCoordinates = availability.nearbyWithoutCoordinates
        val withCoordinates = availability.withCoordinates
        val options = buildList {
            if (withoutCoordinates > 0) add(
                false to "Sans coordonnées GPS ($withoutCoordinates)\nLiés aux villages proches (25 km)"
            )
            if (withCoordinates > 0) add(
                true to "Avec coordonnées GPS ($withCoordinates)\nÀ utiliser seulement pour corriger une position"
            )
        }
        if (options.isEmpty()) {
            val message = if (availability.withoutCoordinates > 0) {
                "Aucun ${category.label.lowercase(Locale.FRANCE)} sans GPS lié aux villages dans un rayon de 25 km"
            } else {
                "Aucun ${category.label.lowercase(Locale.FRANCE)} disponible dans le référentiel"
            }
            toast(message)
            return
        }
        AlertDialog.Builder(this)
            .setTitle(category.label)
            .setItems(options.map { it.second }.toTypedArray()) { _, which ->
                showExistingEntityPicker(category, latitude, longitude, method, location, options[which].first)
            }
            .setNegativeButton("Annuler", null)
            .show()
    }

    private fun createLandmarkAt(
        latitude: Double,
        longitude: Double,
        method: String,
        location: Location?,
        markerCategory: GeoCategory = GeoCategory.LANDMARK,
    ) {
        if (!navigationConfig.canCreateLandmarks) { toast("Création de repères non autorisée") ; return }
        val types = repository.landmarkTypes()
        if (types.isEmpty()) return
        AlertDialog.Builder(this).setTitle("Type de repère")
            .setItems(types.map { it.second }.toTypedArray()) { _, which ->
                val input = EditText(this).apply { hint = "Nom du repère"; setText(types[which].second) }
                AlertDialog.Builder(this).setTitle("Nouveau repère").setView(input)
                    .setNegativeButton("Annuler", null)
                    .setPositiveButton("Enregistrer") { _, _ ->
                        val captured = CapturedPosition(
                            latitude, longitude, location?.altitude?.takeIf { location.hasAltitude() },
                            location?.accuracy?.toDouble(), Instant.now().toString(), method,
                        )
                        val entity = repository.createLandmark(
                            mg.hydria.shared.navigation.NavigationFormRules.landmarkName(input.text.toString(), types[which].second),
                            types[which].first,
                            captured,
                            markerCategory,
                        )
                        store.enqueue("landmark_upsert",
                            mg.hydria.shared.navigation.GeoOperationPayloads.createLandmark(
                                entity, markerCategory, types[which].first, captured))
                        entities = repository.allEntities(limit = 600); refreshMarkers(); centerOn(entity, 17.0)
                        updateStatus("Repère créé hors ligne")
                    }.show()
            }.show()
    }

    private fun showExistingEntityPicker(
        category: GeoCategory,
        latitude: Double,
        longitude: Double,
        method: String,
        location: Location?,
        hasCoordinates: Boolean,
    ) {
        val nearbyCandidateIds = if (hasCoordinates) emptySet() else {
            repository.candidateIdsServingNearbyVillages(category, latitude, longitude)
        }
        val selection = mg.hydria.shared.navigation.PlacementSelection.select(
            repository.placementCandidates(category), latitude, longitude, hasCoordinates, nearbyCandidateIds,
            sortKey = { it.lowercase(Locale.FRANCE) },
        )
        val candidates = selection.candidates
        if (candidates.isEmpty()) {
            toast(if (hasCoordinates) {
                "Aucun ${category.label.lowercase(Locale.FRANCE)} déjà géolocalisé disponible"
            } else {
                "Aucun ${category.label.lowercase(Locale.FRANCE)} sans GPS lié aux villages proches"
            })
            return
        }
        val labels = candidates.map { (candidate, distance) ->
            val identity = listOf(candidate.code, candidate.name).filter { it.isNotBlank() }.distinct().joinToString(" - ")
            val village = candidate.villageName.takeIf { it.isNotBlank() }?.let { " - $it" }.orEmpty()
            val distanceLabel = distance?.let { GeoMath.formatDistance(it) } ?: "sans coordonnées"
            val photoLabel = if (candidate.hasPhoto) "photo présente" else "photo manquante"
            "$identity$village  ($distanceLabel · $photoLabel)"
        }.toTypedArray()
        var selected = 0
        val proximityTitle = if (!hasCoordinates) {
            "À géolocaliser près des villages : ${category.label}"
        } else if (selection.usesNearbyCoordinates) {
            "Choisir : ${category.label} - moins de 25 km"
        } else {
            "Choisir : ${category.label} - les plus proches"
        }
        AlertDialog.Builder(this)
            .setTitle(proximityTitle)
            .setSingleChoiceItems(labels, selected) { _, which -> selected = which }
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Marquer") { _, _ ->
                val candidate = candidates.getOrNull(selected)?.first
                if (candidate == null) toast("Selectionnez un element dans la liste")
                else confirmExistingEntityPlacement(candidate, latitude, longitude, method, location)
            }
            .show()
    }

    private fun confirmExistingEntityPlacement(
        candidate: PlacementCandidate,
        latitude: Double,
        longitude: Double,
        method: String,
        location: Location?,
    ) {
        val oldDistance = mg.hydria.shared.navigation.PlacementSelection.distance(candidate, latitude, longitude)
        AlertDialog.Builder(this)
            .setTitle("Marquer ${candidate.name} ici ?")
            .setMessage(oldDistance?.let { "La position enregistree sera deplacee de ${GeoMath.formatDistance(it)}. L'ancienne position restera dans l'historique." }
                ?: "Cette fiche n'a pas encore de coordonnees. La position choisie sera enregistree.")
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Confirmer") { _, _ ->
                val captured = CapturedPosition(
                    latitude,
                    longitude,
                    location?.altitude?.takeIf { location.hasAltitude() },
                    location?.accuracy?.toDouble(),
                    location?.let { Instant.ofEpochMilli(it.time).toString() } ?: Instant.now().toString(),
                    method,
                )
                val (entity, localUuid) = repository.placeCandidate(candidate, captured)
                store.enqueue("geo_position_upsert",
                    mg.hydria.shared.navigation.GeoOperationPayloads.placeCandidate(
                        candidate, entity.id, localUuid, captured, oldDistance != null))
                entities = repository.allEntities(limit = 600)
                refreshMarkers()
                entities.firstOrNull { it.id == entity.id && it.category == entity.category }?.let { centerOn(it, 17.0) }
                updateStatus("${entity.category.label} marque hors ligne")
                if (!candidate.hasPhoto) promptMissingEntityPhoto(candidate)
            }
            .show()
    }

    private fun promptMissingEntityPhoto(candidate: PlacementCandidate) {
        AlertDialog.Builder(this)
            .setTitle("Photo manquante")
            .setMessage("${candidate.name} n'a pas de photo dans la base. Voulez-vous la photographier maintenant ?")
            .setNegativeButton("Plus tard", null)
            .setPositiveButton("Prendre une photo") { _, _ -> captureEntityPhoto(candidate) }
            .show()
    }

    private fun captureEntityPhoto(candidate: PlacementCandidate) {
        pendingPhotoCandidate = candidate
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            launchEntityPhoto(candidate)
        } else {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun launchEntityPhoto(candidate: PlacementCandidate) {
        val photoFile = File.createTempFile("hydria_navigation_", ".jpg", cacheDir)
        pendingPhotoCandidate = candidate
        pendingPhotoFile = photoFile
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", photoFile)
        entityPhotoLauncher.launch(uri)
    }

    private fun compressEntityPhoto(photoFile: File): String {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(photoFile.absolutePath, bounds)
        val sampleSize = mg.hydria.shared.navigation.NavigationPhotoRules.sampleSize(bounds.outWidth, bounds.outHeight)
        val bitmap = BitmapFactory.decodeFile(
            photoFile.absolutePath,
            BitmapFactory.Options().apply { inSampleSize = sampleSize },
        ) ?: error("Photo illisible")
        val dimensions = mg.hydria.shared.navigation.NavigationPhotoRules.dimensions(bitmap.width, bitmap.height)
        val resized = if (dimensions.needsResize) Bitmap.createScaledBitmap(
            bitmap, dimensions.width, dimensions.height, true,
        ) else bitmap
        val output = ByteArrayOutputStream()
        resized.compress(Bitmap.CompressFormat.JPEG, mg.hydria.shared.navigation.NavigationPhotoRules.JPEG_QUALITY, output)
        if (resized !== bitmap) resized.recycle()
        bitmap.recycle()
        val bytes = output.toByteArray()
        mg.hydria.shared.navigation.NavigationPhotoRules.checkSize(bytes.size)
        return Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun queueEntityPhoto(candidate: PlacementCandidate, encoded: String) {
        val localUuid = UUID.randomUUID().toString()
        val payload = mg.hydria.shared.navigation.NavigationPhotoPayloads.create(candidate, encoded, localUuid)
        store.enqueue("terrain_photo", payload)
        repository.markCandidatePhotoQueued(candidate.category, candidate.id)
        updateStatus("Photo enregistrée hors ligne")
        toast("Photo enregistrée · ${store.pendingCount()} action(s) en attente")
        uploadEntityPhotoIfOnline(localUuid, payload)
    }

    private fun uploadEntityPhotoIfOnline(localUuid: String, payload: JSONObject) {
        val token = store.token ?: return
        if (!isOnline()) return
        syncExecutor.execute {
            val result = mg.hydria.shared.navigation.ImmediatePhotoUpload.run(
                markSynchronizing = { store.markSynchronizing(localUuid) },
                send = {
                    val response = HydriaNetwork.saveTerrainItem(token, payload)
                    mg.hydria.shared.navigation.PhotoUploadResponse(response.successful, response.error)
                },
                remove = { store.remove(localUuid) },
                markFailed = { store.markFailed(localUuid, it) },
            )
            runOnUiThread { updateStatus(result.statusMessage) }
        }
    }

    private fun showLayerFilters() {
        val categories = GeoCategory.entries
        val checked = categories.map { it in visibleCategories }.toBooleanArray()
        AlertDialog.Builder(this).setTitle("Couches visibles")
            .setMultiChoiceItems(categories.map { it.label }.toTypedArray(), checked) { _, which, enabled ->
                if (enabled) visibleCategories += categories[which] else visibleCategories -= categories[which]
            }
            .setPositiveButton("Appliquer") { _, _ -> refreshMarkers() }.show()
    }

    private fun recenter() {
        mode = NavigationMode.FOLLOW_GPS; updateMode()
        currentLocation?.let { map?.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(it.latitude, it.longitude), 16.0)) }
    }

    private fun toggleOrientation() {
        directionUp = !directionUp
        if (!directionUp) map?.animateCamera(CameraUpdateFactory.bearingTo(0.0))
        updateStatus(if (directionUp) "Orientation selon la direction" else "Orientation nord en haut")
    }

    private fun zoomBy(delta: Double) { map?.animateCamera(CameraUpdateFactory.zoomBy(delta)) }
    private fun centerOn(entity: GeoEntity, zoom: Double) = map?.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(entity.latitude, entity.longitude), zoom)) ?: Unit

    private fun updateMode() {
        modeLabel.text = when (mode) {
            NavigationMode.FOLLOW_GPS -> "Suivi GPS"
            NavigationMode.EXPLORE -> "Exploration libre"
            NavigationMode.NAVIGATE -> "Navigation vers une cible"
        }
    }

    private fun updateStatus(message: String? = null) {
        if (!::status.isInitialized) return
        val network = if (isOnline()) "réseau disponible" else "hors connexion"
        val gps = currentLocation?.let { "GPS ±${it.accuracy.toInt()} m" } ?: "GPS en attente"
        val mapBackground = if (usingOnlineStyle) "fond en ligne" else "fond local"
        status.text = listOfNotNull(message, gps, network, mapBackground, "${store.pendingCount()} en attente").joinToString(" · ")
    }

    private fun isOnline(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        val caps = manager.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun synchronizeNavigation() {
        val token = store.token ?: return
        if (navigationSyncing || !isOnline()) { updateStatus(); return }
        navigationSyncing = true
        updateStatus("Synchronisation cartographique")
        syncExecutor.execute {
            val result = runCatching { syncManager.synchronize(token) }
            runOnUiThread {
                navigationSyncing = false
                result.onSuccess {
                    navigationConfig = it.config
                    entities = repository.allEntities(limit = 600)
                    refreshMarkers()
                    updateStatus(it.message)
                }.onFailure { updateStatus(it.message ?: "Synchronisation cartographique indisponible") }
            }
        }
    }

    private fun Location.toCaptured(method: String) = CapturedPosition(
        latitude, longitude, altitude.takeIf { hasAltitude() }, accuracy.toDouble(), Instant.ofEpochMilli(time).toString(), method,
    )

    private fun vertical(padding: Int = 0) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(padding), dp(padding), dp(padding), dp(padding))
    }
    private fun horizontal() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
    private fun catColor(category: GeoCategory): Int = when (category) {
        GeoCategory.VILLAGE -> Color.rgb(155, 138, 251)
        GeoCategory.WATER_POINT -> Color.rgb(85, 217, 231)
        GeoCategory.EQUIPMENT -> Color.rgb(242, 154, 56)
        GeoCategory.LANDMARK -> Color.rgb(88, 213, 148)
    }

    /** Filtre de couche 32 dp : puce de couleur + libellé, bascule la visibilité de la catégorie. */
    private fun layerChip(category: GeoCategory): View {
        val color = catColor(category)
        val pip = View(this)
        val text = label("${category.shortLabel}  ${category.label}", 11f, true)
        val chip = horizontal().apply {
            setPadding(dp(10), 0, dp(12), 0)
            isClickable = true
            isFocusable = true
            addView(pip, LinearLayout.LayoutParams(dp(8), dp(8)).apply { marginEnd = dp(6) })
            addView(text)
        }
        fun applyStyle() {
            val on = category in visibleCategories
            pip.background = HydriaUi.rounded(this@NavigationTerrainActivity, if (on) color else HydriaColors.textMuted, 4f)
            text.setTextColor(if (on) HydriaColors.text else HydriaColors.textMuted)
            chip.background = HydriaUi.rounded(
                this@NavigationTerrainActivity,
                if (on) HydriaColors.surfaceRaised else overlayColor(210),
                16f,
                if (on) color else HydriaColors.outline,
            )
            chip.contentDescription =
                if (on) "${category.label}, couche visible" else "${category.label}, couche masquée"
        }
        chip.setOnClickListener {
            if (category in visibleCategories) visibleCategories -= category else visibleCategories += category
            applyStyle()
            refreshMarkers()
        }
        applyStyle()
        return chip
    }
    private fun label(value: String, size: Float, bold: Boolean, color: Int = HydriaColors.text) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }
    private fun button(value: String, action: () -> Unit) = Button(this).apply {
        text = value; setTextColor(HydriaColors.text); textSize = 12f; isAllCaps = false
        background = HydriaUi.rounded(this@NavigationTerrainActivity, HydriaColors.surfaceRaised, 12f, HydriaColors.outline)
        setOnClickListener { action() }
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    /** Fond des panneaux posés sur la carte : surface du thème, lisible en clair comme en sombre (RECH_NAV-02). */
    private fun overlayColor(alpha: Int) = ColorUtils.setAlphaComponent(HydriaColors.surface, alpha)
    private fun toast(value: String) = Toast.makeText(this, value, Toast.LENGTH_SHORT).show()

    override fun onStart() { super.onStart(); mapView.onStart() }
    override fun onResume() {
        super.onResume(); mapView.onResume(); headingController.start()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) locationController.start()
        else locationPermission.launch(Manifest.permission.ACCESS_FINE_LOCATION)
    }
    override fun onPause() { locationController.stop(); headingController.stop(); mapView.onPause(); super.onPause() }
    override fun onStop() { mapView.onStop(); super.onStop() }
    override fun onLowMemory() { super.onLowMemory(); mapView.onLowMemory() }
    override fun onDestroy() { syncExecutor.shutdownNow(); routeExecutor.shutdownNow(); mapView.onDestroy(); super.onDestroy() }
    override fun onSaveInstanceState(outState: Bundle) { super.onSaveInstanceState(outState); mapView.onSaveInstanceState(outState) }
}
