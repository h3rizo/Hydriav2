package mg.hydria.shared.rules.readings

import mg.hydria.shared.navigation.GeoMath
import mg.hydria.shared.rules.forms.AutocompleteMatch
import org.json.JSONObject

/**
 * Liste déroulante des points d'eau du formulaire de relevé (Android + Desktop).
 *
 * Libellé « 💧 07 — RAKOTO Jean » : idxls du point (numéro dans le fichier de
 * l'ouvrage) + nom de l'abonné, sans le code technique du point. Le tri est
 * alphabétique sur ce libellé ; comme l'idxls est complété de zéros sur une
 * largeur fixe, l'ordre alphabétique suit aussi l'ordre numérique (02 < 10).
 *
 * Champs lus sur `snapshot.ouvrages[].points_eau[]` : `idxls`, `nom`,
 * `type_pictogram`, `parcelle_id`, `parcelle`, `has_coordinates`, `latitude`,
 * `longitude`.
 */
object ReadingPointListRules {
    /** Au-delà de ce nombre de points, un filtre Parcelle est proposé au-dessus du point d'eau. */
    const val PARCEL_FILTER_THRESHOLD = 20

    const val ALL_PARCELS = ""
    const val NO_PARCEL = "__sans_parcelle__"

    data class Parcel(val id: String, val label: String, val count: Int)

    /** Largeur de l'idxls : 2 chiffres si le plus grand idxls de l'ouvrage est < 100, sinon 3. */
    fun idxlsWidth(points: List<JSONObject>): Int {
        val max = points.mapNotNull { it.optString("idxls").trim().toIntOrNull() }.maxOrNull() ?: 0
        return if (max < 100) 2 else 3
    }

    /**
     * idxls complété de zéros à gauche sur [width] chiffres (« 7 » -> « 07 »).
     */
    fun formatIdxls(idxls: String, width: Int): String {
        val trimmed = idxls.trim()
        return if (isValidIdxls(trimmed)) trimmed.toInt().toString().padStart(width, '0')
        else "⚠${trimmed.ifBlank { "?" }}"
    }

    /** Un idxls valide est entièrement numérique ; sinon c'est une anomalie à signaler et corriger (« ⚠ » dans le libellé). */
    fun isValidIdxls(idxls: String): Boolean = idxls.trim().let { it.isNotEmpty() && it.all(Char::isDigit) && it.toIntOrNull() != null }

    /** « 💧 07 — RAKOTO Jean » (+ [suffix] éventuel : distance, index saisi…). */
    fun label(point: JSONObject, width: Int, suffix: String = ""): String {
        val pictogram = point.optString("type_pictogram", "💧").ifBlank { "💧" }
        val name = point.optString("nom").trim().takeUnless { it.isBlank() || it == "N/A" } ?: "Abonné non renseigné"
        return "$pictogram ${formatIdxls(point.optString("idxls"), width)} — $name$suffix"
    }

    /** Tri alphabétique sur le libellé sans pictogramme (accents et casse ignorés). */
    fun sortedAlphabetically(points: List<JSONObject>, width: Int): List<JSONObject> =
        points.sortedBy { point -> AutocompleteMatch.normalize(label(point, width).substringAfter(' ')) }

    /**
     * Tri numérique sur l'idxls (2 avant 10) ; à égalité ou sans idxls numérique
     * (placés en dernier), ordre alphabétique du libellé.
     */
    fun sortedByIdxls(points: List<JSONObject>, width: Int): List<JSONObject> =
        sortedAlphabetically(points, width).sortedBy { it.optString("idxls").trim().toIntOrNull() ?: Int.MAX_VALUE }

    fun showParcelFilter(points: List<JSONObject>): Boolean =
        points.size > PARCEL_FILTER_THRESHOLD && parcels(points).size > 1

    /** Parcelles présentes (triées par référence), « Sans parcelle » en dernier. */
    fun parcels(points: List<JSONObject>): List<Parcel> =
        points.groupBy { it.optString("parcelle_id").ifBlank { NO_PARCEL } }
            .map { (id, items) ->
                val reference = items.first().optString("parcelle").trim()
                Parcel(id, if (id == NO_PARCEL) "Sans parcelle" else reference.ifBlank { "Parcelle sans référence" }, items.size)
            }
            .sortedWith(compareBy<Parcel>({ it.id == NO_PARCEL }, { AutocompleteMatch.normalize(it.label) }))

    fun filterByParcel(points: List<JSONObject>, parcelId: String): List<JSONObject> =
        if (parcelId == ALL_PARCELS) points
        else points.filter { it.optString("parcelle_id").ifBlank { NO_PARCEL } == parcelId }

    /**
     * Recherche libre par nom d'abonné ou par idxls : tous les mots saisis doivent apparaître
     * (accents et casse ignorés), « 7 » et « 07 » trouvent tous deux l'idxls 7. Requête vide = aucun filtre.
     */
    fun filterBySearch(points: List<JSONObject>, width: Int, query: String): List<JSONObject> {
        if (query.isBlank()) return points
        return points.filter { point ->
            AutocompleteMatch.matches("${point.optString("idxls").trim()} ${label(point, width)}", query)
        }
    }

    /** Distance au téléphone en mètres, ou null si le point n'a pas de position. */
    fun distanceMeters(point: JSONObject, latitude: Double, longitude: Double): Double? {
        if (!point.optBoolean("has_coordinates")) return null
        val lat = point.optDouble("latitude")
        val lon = point.optDouble("longitude")
        if (lat.isNaN() || lon.isNaN() || !GeoMath.isValid(lat, lon)) return null
        return GeoMath.distanceMeters(latitude, longitude, lat, lon)
    }

    /** Mode « points proches » : du plus proche au plus loin, points sans GPS à la fin (ordre alphabétique). */
    fun sortedByDistance(points: List<JSONObject>, width: Int, latitude: Double, longitude: Double): List<JSONObject> {
        val alphabetical = sortedByIdxls(points, width)
        return alphabetical.sortedBy { distanceMeters(it, latitude, longitude) ?: Double.MAX_VALUE }
    }

    /** « · 35 m » / « · 1,2 km » / « · sans GPS ». */
    fun distanceSuffix(meters: Double?): String = when {
        meters == null -> " · sans GPS"
        meters < 1000 -> " · ${meters.toInt()} m"
        else -> " · ${String.format(java.util.Locale.FRANCE, "%.1f", meters / 1000)} km"
    }
}
