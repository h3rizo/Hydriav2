package mg.hydria.compta.sync

import java.time.Instant

/** État agrégé de synchronisation, affiché en permanence dans l'UI (chip). */
data class SyncStatus(
    val online: Boolean,
    val running: Boolean,
    val enAttente: Int,
    val aProbleme: Int,
    val dernierPullOk: Instant?,
) {
    enum class Niveau { A_JOUR, EN_ATTENTE, HORS_LIGNE, A_REVOIR, EN_COURS }

    val niveau: Niveau
        get() = when {
            running -> Niveau.EN_COURS
            aProbleme > 0 -> Niveau.A_REVOIR
            !online -> Niveau.HORS_LIGNE
            enAttente > 0 -> Niveau.EN_ATTENTE
            else -> Niveau.A_JOUR
        }

    val libelle: String
        get() = when (niveau) {
            Niveau.EN_COURS -> "Synchronisation…"
            Niveau.A_REVOIR -> "$aProbleme à revoir"
            Niveau.HORS_LIGNE -> "Hors ligne"
            Niveau.EN_ATTENTE -> "$enAttente en attente"
            Niveau.A_JOUR -> "À jour"
        }
}
