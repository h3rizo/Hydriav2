package mg.hydria.app

import java.time.Clock
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Dates des champs de saisie (HydriaUi.dateField). Pur Kotlin, sans Android : testable en JVM.
 * « Aujourd'hui » est toujours celui de Madagascar, jamais celui du fuseau (parfois mal réglé) du téléphone.
 */
object HydriaDates {
    val ZONE: ZoneId = ZoneId.of("Indian/Antananarivo")
    private val DISPLAY: DateTimeFormatter = DateTimeFormatter.ofPattern("dd/MM/uuuu")

    /** Jour de Madagascar. [clock] ne sert qu'aux tests : son fuseau est ignoré, seul l'instant compte. */
    fun today(clock: Clock = Clock.systemUTC()): LocalDate = LocalDate.now(clock.withZone(ZONE))

    /** Date réelle (« 2026-02-30 » refusée), ou null. */
    fun parse(iso: String?): LocalDate? = iso?.trim()?.takeIf { it.length == 10 }
        ?.let { runCatching { LocalDate.parse(it) }.getOrNull() }

    /** « 2026-10-12 » -> « 12/10/2026 » ; vide si la date est absente ou invalide. */
    fun display(iso: String?): String = parse(iso)?.format(DISPLAY).orEmpty()

    /**
     * Valeur ISO retenue pour un champ : la date donnée si elle est réelle, sinon aujourd'hui ;
     * ramenée à aujourd'hui quand [maxToday] interdit une date future.
     */
    fun normalize(iso: String?, maxToday: Boolean, today: LocalDate = today()): String {
        val date = parse(iso) ?: today
        return (if (maxToday && date.isAfter(today)) today else date).toString()
    }

    /**
     * Valeur de DatePicker.maxDate pour [today]. Le sélecteur compare des jours dans le fuseau du
     * téléphone : midi ce jour-là dans CE fuseau désigne le bon jour quel que soit son décalage.
     */
    fun pickerMaxMillis(today: LocalDate, deviceZone: ZoneId = ZoneId.systemDefault()): Long =
        today.atTime(12, 0).atZone(deviceZone).toInstant().toEpochMilli()
}
