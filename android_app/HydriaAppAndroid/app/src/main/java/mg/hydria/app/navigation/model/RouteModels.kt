package mg.hydria.app.navigation.model

import org.json.JSONObject

/** Moyen de déplacement pour le calcul d'itinéraire (même clés que les profils du serveur). */
enum class RouteProfile(val key: String, val label: String, val icon: String) {
    MOTO("moto", "Moto", "🏍"),
    VOITURE("voiture", "Voiture", "🚗"),
    PIED("pied", "À pied", "🚶");

    fun next(): RouteProfile = entries[(ordinal + 1) % entries.size]

    companion object {
        fun fromKey(key: String?): RouteProfile = entries.firstOrNull { it.key == key } ?: MOTO
    }
}

/** Itinéraire routier calculé par le serveur entre la position de l'agent et une entité. */
data class NavigationRoute(
    val profile: RouteProfile,
    val distanceKm: Double,
    val durationMinutes: Int,
    val walkMeters: Int,
    val accessStartMeters: Int,
    val accessEndMeters: Int,
    val detour: Double?,
    /** Points du tracé (longitude, latitude). */
    val coordinates: List<DoubleArray>,
    val originLatitude: Double,
    val originLongitude: Double,
) {
    companion object {
        fun fromJson(body: JSONObject, originLatitude: Double, originLongitude: Double): NavigationRoute? {
            if (!body.optBoolean("success", false)) return null
            val line = body.optJSONObject("geometrie")?.optJSONArray("coordinates") ?: return null
            val points = (0 until line.length()).mapNotNull { index ->
                val pair = line.optJSONArray(index) ?: return@mapNotNull null
                if (pair.length() < 2) null else doubleArrayOf(pair.getDouble(0), pair.getDouble(1))
            }
            if (points.size < 2) return null
            return NavigationRoute(
                profile = RouteProfile.fromKey(body.optString("profil")),
                distanceKm = body.optDouble("distance_km"),
                durationMinutes = body.optInt("duree_minutes"),
                walkMeters = body.optInt("marche_m"),
                accessStartMeters = body.optInt("acces_depart_m"),
                accessEndMeters = body.optInt("acces_arrivee_m"),
                detour = body.optDouble("detour").takeUnless { it.isNaN() },
                coordinates = points,
                originLatitude = originLatitude,
                originLongitude = originLongitude,
            )
        }

        fun formatDuration(minutes: Int): String {
            val h = minutes / 60
            val m = minutes % 60
            return if (h > 0) "$h h ${"%02d".format(m)}" else "$m min"
        }
    }
}
