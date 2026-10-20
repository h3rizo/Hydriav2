package mg.hydria.app.navigation.map

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import mg.hydria.app.navigation.model.GeoCategory
import mg.hydria.app.navigation.model.GeoEntity
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.iconAllowOverlap
import org.maplibre.android.style.layers.PropertyFactory.iconImage
import org.maplibre.android.style.layers.PropertyFactory.iconSize
import org.maplibre.android.style.layers.PropertyFactory.textAllowOverlap
import org.maplibre.android.style.layers.PropertyFactory.textAnchor
import org.maplibre.android.style.layers.PropertyFactory.textColor
import org.maplibre.android.style.layers.PropertyFactory.textField
import org.maplibre.android.style.layers.PropertyFactory.textHaloColor
import org.maplibre.android.style.layers.PropertyFactory.textHaloWidth
import org.maplibre.android.style.layers.PropertyFactory.textIgnorePlacement
import org.maplibre.android.style.layers.PropertyFactory.textMaxWidth
import org.maplibre.android.style.layers.PropertyFactory.textOffset
import org.maplibre.android.style.layers.PropertyFactory.textOptional
import org.maplibre.android.style.layers.PropertyFactory.textSize
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.layers.Property
import org.maplibre.android.style.sources.GeoJsonOptions
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.android.style.expressions.Expression.get
import org.maplibre.android.style.expressions.Expression.all
import org.maplibre.android.style.expressions.Expression.eq
import org.maplibre.android.style.expressions.Expression.has
import org.maplibre.android.style.expressions.Expression.literal
import org.maplibre.android.style.expressions.Expression.not
import org.maplibre.geojson.Feature
import org.maplibre.geojson.LineString
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.Point

class MarkerLayerManager(private val style: Style) {
    companion object {
        const val SOURCE_ID = "hydria-navigation-entities"
        const val VILLAGE_SOURCE_ID = "hydria-navigation-villages"
        const val CLUSTER_LAYER = "hydria-navigation-clusters"
        const val CLUSTER_COUNT_LAYER = "hydria-navigation-cluster-counts"
        const val ENTITY_LAYER = "hydria-navigation-markers"
        const val VILLAGE_MARKER_LAYER = "hydria-navigation-village-markers"
        const val VILLAGE_LABEL_LAYER = "hydria-navigation-village-labels"
        const val ENTITY_LABEL_LAYER = "hydria-navigation-entity-labels"
        const val ROUTE_SOURCE = "hydria-navigation-route"
        private const val ROUTE_CASING_LAYER = "hydria-navigation-route-casing"
        private const val ROUTE_LAYER = "hydria-navigation-route-line"
        private const val LOCATION_SOURCE = "hydria-current-location"
        private const val LOCATION_LAYER = "hydria-current-location-layer"
    }

    private val source = GeoJsonSource(
        SOURCE_ID,
        FeatureCollection.fromFeatures(emptyArray()),
        GeoJsonOptions().withCluster(true).withClusterRadius(46),
    )
    private val villageSource = GeoJsonSource(
        VILLAGE_SOURCE_ID,
        FeatureCollection.fromFeatures(emptyArray()),
    )
    private val locationSource = GeoJsonSource(LOCATION_SOURCE, FeatureCollection.fromFeatures(emptyArray()))
    private val routeSource = GeoJsonSource(ROUTE_SOURCE, FeatureCollection.fromFeatures(emptyArray()))

    init {
        GeoCategory.entries.forEach { category -> style.addImage(iconName(category), markerBitmap(category)) }
        style.addSource(source)
        style.addSource(villageSource)
        // Itinéraire routier : ajouté avant les marqueurs pour passer SOUS les repères et les libellés.
        style.addSource(routeSource)
        style.addLayer(
            LineLayer(ROUTE_CASING_LAYER, ROUTE_SOURCE).withProperties(
                lineColor(Color.rgb(7, 21, 29)), lineWidth(9f), lineCap(Property.LINE_CAP_ROUND), lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addLayer(
            LineLayer(ROUTE_LAYER, ROUTE_SOURCE).withProperties(
                lineColor(Color.rgb(242, 154, 56)), lineWidth(5.5f), lineCap(Property.LINE_CAP_ROUND), lineJoin(Property.LINE_JOIN_ROUND),
            )
        )
        style.addLayer(
            CircleLayer(CLUSTER_LAYER, SOURCE_ID).withFilter(has("point_count")).withProperties(
                circleColor(Color.rgb(26, 169, 190)), circleRadius(20f),
            )
        )
        // Nombre d'éléments de la grappe (RECH_NAV-01) : encre foncée sur le disque cyan (≈ 6,5:1).
        style.addLayer(
            SymbolLayer(CLUSTER_COUNT_LAYER, SOURCE_ID).withFilter(has("point_count")).withProperties(
                textField(get("point_count_abbreviated")), textSize(13f), textColor(Color.rgb(7, 21, 29)),
                textAllowOverlap(true), textIgnorePlacement(true),
            )
        )
        style.addLayer(
            SymbolLayer(ENTITY_LAYER, SOURCE_ID).withFilter(not(has("point_count"))).withProperties(
                iconImage(get("icon")), iconSize(0.72f), iconAllowOverlap(true),
            )
        )
        style.addLayer(
            SymbolLayer(VILLAGE_MARKER_LAYER, VILLAGE_SOURCE_ID).withProperties(
                iconImage(get("icon")), iconSize(0.72f), iconAllowOverlap(true),
            )
        )
        style.addLayer(
            SymbolLayer(VILLAGE_LABEL_LAYER, VILLAGE_SOURCE_ID)
                .withProperties(*labelProperties(12f))
                .apply { minZoom = 7f }
        )
        style.addLayer(
            SymbolLayer(ENTITY_LABEL_LAYER, SOURCE_ID)
                .withFilter(all(not(has("point_count")), not(eq(get("category"), literal(GeoCategory.VILLAGE.storageKey)))))
                .withProperties(*labelProperties(11f))
                .apply { minZoom = 13f }
        )
        style.addSource(locationSource)
        style.addLayer(
            CircleLayer(LOCATION_LAYER, LOCATION_SOURCE).withProperties(
                circleColor(Color.rgb(85, 217, 231)), circleRadius(9f),
            )
        )
    }

    fun submit(entities: List<GeoEntity>) {
        fun feature(entity: GeoEntity) =
            Feature.fromGeometry(Point.fromLngLat(entity.longitude, entity.latitude)).apply {
                addStringProperty("entity_id", entity.id)
                addStringProperty("category", entity.category.storageKey)
                addStringProperty("icon", iconName(entity.category))
                addStringProperty("name", entity.name.ifBlank { entity.code.ifBlank { entity.category.label } })
            }

        val villages = entities.filter { it.category == GeoCategory.VILLAGE }.map(::feature)
        val otherEntities = entities.filter { it.category != GeoCategory.VILLAGE }.map(::feature)
        villageSource.setGeoJson(FeatureCollection.fromFeatures(villages))
        source.setGeoJson(FeatureCollection.fromFeatures(otherEntities))
    }

    /** Trace l'itinéraire (liste de [longitude, latitude]). */
    fun showRoute(coordinates: List<DoubleArray>) {
        val line = LineString.fromLngLats(coordinates.map { Point.fromLngLat(it[0], it[1]) })
        routeSource.setGeoJson(FeatureCollection.fromFeature(Feature.fromGeometry(line)))
    }

    fun clearRoute() {
        routeSource.setGeoJson(FeatureCollection.fromFeatures(emptyArray()))
    }

    fun updateLocation(latitude: Double, longitude: Double) {
        locationSource.setGeoJson(FeatureCollection.fromFeature(Feature.fromGeometry(Point.fromLngLat(longitude, latitude))))
    }

    private fun iconName(category: GeoCategory) = "hydria-marker-${category.storageKey}"

    private fun labelProperties(size: Float) = arrayOf(
        textField(get("name")),
        textSize(size),
        textColor(Color.rgb(245, 249, 250)),
        textHaloColor(Color.rgb(7, 21, 29)),
        textHaloWidth(1.6f),
        textOffset(arrayOf(0f, 2.15f)),
        textAnchor(Property.TEXT_ANCHOR_TOP),
        textMaxWidth(13f),
        textAllowOverlap(false),
        textIgnorePlacement(false),
        textOptional(true),
    )

    private fun markerBitmap(category: GeoCategory): Bitmap {
        val bitmap = Bitmap.createBitmap(72, 72, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val color = when (category) {
            GeoCategory.VILLAGE -> Color.rgb(155, 138, 251)
            GeoCategory.WATER_POINT -> Color.rgb(85, 217, 231)
            GeoCategory.EQUIPMENT -> Color.rgb(242, 154, 56)
            GeoCategory.LANDMARK -> Color.rgb(88, 213, 148)
        }
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { this.color = color }
        canvas.drawCircle(36f, 31f, 25f, paint)
        paint.color = Color.rgb(7, 21, 29)
        paint.textAlign = Paint.Align.CENTER
        paint.textSize = 29f
        paint.isFakeBoldText = true
        canvas.drawText(category.shortLabel, 36f, 41f, paint)
        paint.color = color
        val path = android.graphics.Path().apply { moveTo(27f, 51f); lineTo(36f, 68f); lineTo(45f, 51f); close() }
        canvas.drawPath(path, paint)
        return bitmap
    }
}
