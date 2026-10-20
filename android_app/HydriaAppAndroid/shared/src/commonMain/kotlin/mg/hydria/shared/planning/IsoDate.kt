package mg.hydria.shared.planning

import kotlinx.datetime.LocalDate

/**
 * Date ISO (AAAA-MM-JJ) saisie dans un formulaire. Elle doit exister au calendrier : « 2026-02-30 » et
 * « 2026-13-01 » ont la bonne forme mais sont refusées ici, avant la mise en file, au lieu de l'être
 * par le serveur à la synchronisation (des heures plus tard, loin du contexte de saisie).
 */
object IsoDate {
    private val pattern = Regex("\\d{4}-\\d{2}-\\d{2}")

    fun isReal(value: String): Boolean {
        val date = value.trim()
        return date.matches(pattern) && runCatching { LocalDate.parse(date) }.isSuccess
    }
}
