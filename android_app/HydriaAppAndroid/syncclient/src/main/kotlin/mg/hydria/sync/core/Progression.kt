package mg.hydria.sync.core

/** Etape en cours d'une synchronisation. */
enum class Phase { PREPARATION, RECEPTION, ENVOI }

/**
 * Avancement d'une synchronisation, publie par le moteur a chaque fichier. Valeur immuable : l'interface
 * (fenetre, info-bulle de la zone de notification) ne fait que la lire.
 *
 * Le total de la reception est connu des le debut (le moteur lit d'abord toute la liste des changements) ;
 * celui de l'envoi ne l'est pas (`total` = 0 : progression indeterminee).
 */
data class Progression(
    val phase: Phase,
    val fait: Int = 0,
    val total: Int = 0,
    val octetsFaits: Long = 0,
    val octetsTotal: Long = 0,
    /** Fichier en cours (chemin ou nom), pour information. */
    val courant: String? = null,
    val debutMs: Long = 0,
    val maintenantMs: Long = 0,
    /** Fichiers envoyes au serveur depuis le debut de la synchronisation. */
    val envoyes: Int = 0,
) {
    /** 0..1 pendant la reception, `null` quand il n'y a pas de total (indetermine). */
    val fraction: Float?
        get() = if (phase == Phase.RECEPTION && octetsTotal > 0) (octetsFaits.toDouble() / octetsTotal).coerceIn(0.0, 1.0).toFloat() else null

    val pourcentage: Int? get() = fraction?.let { (it * 100).toInt() }

    /** Temps restant estime d'apres la vitesse moyenne depuis le debut ; `null` tant qu'on manque de recul. */
    val restantSecondes: Long?
        get() {
            val ecoule = (maintenantMs - debutMs) / 1000.0
            if (phase != Phase.RECEPTION || octetsFaits <= 0 || ecoule < 3.0) return null
            val vitesse = octetsFaits / ecoule
            return ((octetsTotal - octetsFaits).coerceAtLeast(0) / vitesse).toLong()
        }
}

/** « 657 Mo », « 1,4 Go », « 12 Ko » : unites 1024, virgule decimale. */
fun formaterOctets(octets: Long): String {
    val unite = listOf("octets", "Ko", "Mo", "Go")
    var valeur = octets.toDouble()
    var i = 0
    while (valeur >= 1024 && i < unite.lastIndex) { valeur /= 1024; i++ }
    return if (i == 0) "$octets octets" else "%.${if (valeur < 10) 1 else 0}f %s".format(valeur, unite[i]).replace('.', ',')
}

/** « 12 min », « 1 h 05 », « moins d'une minute ». */
fun formaterDuree(secondes: Long): String = when {
    secondes < 60 -> "moins d'une minute"
    secondes < 3600 -> "${(secondes + 30) / 60} min"
    else -> "${secondes / 3600} h ${"%02d".format((secondes % 3600) / 60)}"
}

/** Texte court (info-bulle, ligne de la fenetre) ; `null` si rien d'utile a dire. */
fun Progression.libelle(): String = when (phase) {
    Phase.PREPARATION -> "Recherche des changements…"
    Phase.RECEPTION ->
        if (total == 0) "Réception…"
        else "Réception : $fait sur $total fichiers (${pourcentage ?: 0} %)"
    Phase.ENVOI -> "Envoi : $envoyes fichier${if (envoyes > 1) "s" else ""}"
}
