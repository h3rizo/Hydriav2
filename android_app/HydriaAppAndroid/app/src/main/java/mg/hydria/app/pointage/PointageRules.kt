package mg.hydria.app.pointage

import org.json.JSONObject
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Règles de pointage GPS, miroir de backend/apps/planning/services_pointage.py.
 * Le serveur reste l'autorité : ces règles ne servent qu'à répondre tout de suite,
 * sans réseau, quand le résultat est sans ambiguïté.
 */
object PointageRules {
    const val DISTANCE_MAX_M = 3000.0
    const val PRECISION_MAX_M = 100.0
    val ZONE: ZoneId = ZoneId.of("Indian/Antananarivo")

    data class Creneau(val type: String, val label: String, val debut: LocalTime, val fin: LocalTime, val prevuKey: String) {
        val fenetre: String get() = "%02dh-%02dh".format(debut.hour, fin.hour)
    }

    /**
     * Bandeau affiché quand /pointage/aujourdhui échoue. Seule une vraie absence de
     * réseau (exception de transport, ou pas de connexion) est « hors ligne » ; un refus
     * ou une panne du serveur est affiché avec sa cause pour pouvoir être corrigé.
     */
    fun refreshFailureNote(status: Int?, error: String?, exception: String?, online: Boolean): String {
        val suffix = " Données du planning en mémoire sur le téléphone."
        return when {
            status == null && !online -> "Hors ligne :$suffix"
            status == null -> "Serveur injoignable (${exception ?: "connexion interrompue"}).$suffix"
            status == 401 -> "Session expirée ou révoquée : déconnectez-vous puis reconnectez-vous." +
                (error?.let { " ($it)" } ?: "")
            status == 403 -> (error ?: "Accès refusé") + " (HTTP 403)."
            else -> "Erreur serveur HTTP $status : ${error ?: "réponse invalide"}.$suffix"
        }
    }

    val CRENEAUX = listOf(
        Creneau("matin", "Matinée", LocalTime.of(10, 0), LocalTime.of(12, 0), "prevu_matinee"),
        Creneau("aprem", "Après-midi", LocalTime.of(15, 0), LocalTime.of(18, 0), "prevu_apres_midi"),
        Creneau("nuit", "Nuitée", LocalTime.of(19, 0), LocalTime.of(21, 0), "prevu_nuitee"),
    )

    data class Village(val nom: String, val lat: Double, val lng: Double)

    sealed class Verdict {
        data class Ok(val creneau: Creneau, val distanceM: Double, val village: Village) : Verdict()
        data class Refuse(val message: String) : Verdict()
        /** Pas assez d'information locale (pas de planning en cache, village sans GPS) : le serveur tranchera. */
        data class Indetermine(val creneau: Creneau?) : Verdict()
    }

    /** Créneau en cours à [maintenant] (heure de Madagascar), sinon null. */
    fun creneauActuel(maintenant: ZonedDateTime): Creneau? =
        creneauPour(maintenant.withZoneSameInstant(ZONE).toLocalTime())

    /** Prochain créneau de la journée après [maintenant], sinon null (journée terminée). */
    fun prochainCreneau(maintenant: ZonedDateTime): Creneau? {
        val heure = maintenant.withZoneSameInstant(ZONE).toLocalTime()
        return CRENEAUX.firstOrNull { it.debut > heure }
    }

    /**
     * Planning retenu pour un pointage, même règle que le serveur
     * (services_pointage.enregistrer_pointage) : parmi les plannings dont un village est à
     * moins de 3 km, celui où le créneau est déclaré prévu, puis le plus proche.
     * null si aucun planning géolocalisé n'est assez proche (le serveur tranchera).
     */
    fun planningPourPointage(today: JSONObject?, lat: Double, lng: Double, type: String): String? {
        val plannings = today?.optJSONArray("plannings") ?: return null
        val champ = CRENEAUX.firstOrNull { it.type == type } ?: return null
        data class Candidat(val id: String, val prevu: Boolean, val distance: Double)
        val candidats = (0 until plannings.length()).mapNotNull { i ->
            val pl = plannings.getJSONObject(i)
            if (!pointageRequis(pl)) return@mapNotNull null
            val villages = pl.optJSONArray("villages") ?: return@mapNotNull null
            val distance = (0 until villages.length()).map { villages.getJSONObject(it) }
                .filter { !it.isNull("lat") && !it.isNull("lng") }
                .minOfOrNull { haversineM(lat, lng, it.getDouble("lat"), it.getDouble("lng")) }
                ?: return@mapNotNull null
            val creneaux = pl.optJSONArray("creneaux")
            val prevu = creneaux != null && (0 until creneaux.length()).any {
                creneaux.getJSONObject(it).let { c -> c.optString("type") == champ.type && c.optBoolean("prevu") }
            }
            Candidat(pl.optString("planning_id"), prevu, distance)
        }.filter { it.distance <= DISTANCE_MAX_M }
        return candidats.minWithOrNull(compareBy<Candidat>({ !it.prevu }, { it.distance }))?.id
    }

    /**
     * Pas de pointage sur un ouvrage dont le type « n'existe pas » (bureau, terrain,
     * suspendu…) : le serveur envoie `pointage_requis=false`. Absent (ancien serveur) = requis.
     */
    fun pointageRequis(planning: JSONObject): Boolean = planning.optBoolean("pointage_requis", true)

    /** Au moins un planning du jour demande un pointage. */
    fun pointageAttendu(today: JSONObject?): Boolean {
        val plannings = today?.optJSONArray("plannings") ?: return false
        return (0 until plannings.length()).any { pointageRequis(plannings.getJSONObject(it)) }
    }

    fun creneauPour(heure: LocalTime): Creneau? = CRENEAUX.firstOrNull { heure >= it.debut && heure <= it.fin }

    fun haversineM(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val r = 6371008.8
        val p1 = Math.toRadians(lat1)
        val p2 = Math.toRadians(lat2)
        val dPhi = p2 - p1
        val dLambda = Math.toRadians(lng2 - lng1)
        val a = sin(dPhi / 2).pow(2) + cos(p1) * cos(p2) * sin(dLambda / 2).pow(2)
        return 2 * r * asin(sqrt(a))
    }

    fun formatDistance(metres: Double): String =
        if (metres >= 1000) "%.1f km".format(java.util.Locale.FRANCE, metres / 1000) else "${metres.roundToInt()} m"

    fun libelleFenetres(): String =
        "Créneaux : " + CRENEAUX.joinToString(", ") { "${it.label.lowercase()} ${it.fenetre}" }

    /** Villages (avec GPS) de tous les plannings du jour, depuis la réponse de /pointage/aujourdhui. */
    fun villagesDuJour(today: JSONObject?): List<Village> {
        val plannings = today?.optJSONArray("plannings") ?: return emptyList()
        val result = LinkedHashMap<String, Village>()
        for (i in 0 until plannings.length()) {
            if (!pointageRequis(plannings.getJSONObject(i))) continue
            val villages = plannings.getJSONObject(i).optJSONArray("villages") ?: continue
            for (j in 0 until villages.length()) {
                val v = villages.getJSONObject(j)
                if (v.isNull("lat") || v.isNull("lng")) continue
                result[v.optString("id")] = Village(v.optString("nom"), v.getDouble("lat"), v.getDouble("lng"))
            }
        }
        return result.values.toList()
    }

    /**
     * Village le plus proche SI l'employé est au-delà de [DISTANCE_MAX_M] de tous les villages
     * du jour (le bouton « Pointer » est alors grisé). null = pointage possible ou indéterminé :
     * pas de village géolocalisé, ou signal trop imprécis pour conclure.
     */
    fun tropLoin(lat: Double, lng: Double, precisionM: Double?, villages: List<Village>): Pair<Village, Double>? {
        if (precisionM == null || precisionM > PRECISION_MAX_M) return null
        val nearest = villages.map { it to haversineM(lat, lng, it.lat, it.lng) }.minByOrNull { it.second } ?: return null
        return nearest.takeIf { it.second > DISTANCE_MAX_M }
    }

    fun verdict(lat: Double, lng: Double, villages: List<Village>, maintenant: ZonedDateTime): Verdict {
        val creneau = creneauPour(maintenant.withZoneSameInstant(ZONE).toLocalTime())
            ?: return Verdict.Refuse("Pointage impossible à cette heure. ${libelleFenetres()}.")
        if (villages.isEmpty()) return Verdict.Indetermine(creneau)
        val (village, distance) = villages
            .map { it to haversineM(lat, lng, it.lat, it.lng) }
            .minByOrNull { it.second }!!
        if (distance > DISTANCE_MAX_M) {
            return Verdict.Refuse(
                "Vous êtes à ${formatDistance(distance)} du site (${village.nom}). Rapprochez-vous à moins de 3 km pour pointer."
            )
        }
        return Verdict.Ok(creneau, distance, village)
    }
}
