package mg.hydria.app

import org.junit.Assert.*
import org.junit.Test
import java.time.Clock
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset

/** Composant date (lot 1-D) : affichage JJ/MM/AAAA, normalisation et borne « aujourd'hui » du sélecteur. */
class HydriaDatesTest {
    private val today = LocalDate.of(2026, 10, 19)

    @Test fun zoneIsMadagascar() {
        assertEquals("Indian/Antananarivo", HydriaDates.ZONE.id)
    }

    @Test fun todayFollowsTheMadagascarDayWhateverTheDeviceTimezone() {
        // 19/10 à 22:00 UTC = 20/10 à 01:00 à Madagascar (UTC+3) : entre 21 h et 3 h, le jour de Madagascar a déjà changé.
        val instant = Instant.parse("2026-10-19T22:00:00Z")
        assertEquals(LocalDate.of(2026, 10, 20), HydriaDates.today(Clock.fixed(instant, ZoneOffset.UTC)))
        assertEquals(LocalDate.of(2026, 10, 20), HydriaDates.today(Clock.fixed(instant, ZoneId.of("America/Los_Angeles"))))
        // Une seconde avant minuit à Madagascar : toujours le 19.
        assertEquals(LocalDate.of(2026, 10, 19), HydriaDates.today(Clock.fixed(Instant.parse("2026-10-19T20:59:59Z"), ZoneOffset.UTC)))
    }

    @Test fun displayShowsDayMonthYear() {
        assertEquals("12/10/2026", HydriaDates.display("2026-10-12"))
        assertEquals("05/01/2026", HydriaDates.display(" 2026-01-05 "))
        assertEquals("29/02/2024", HydriaDates.display("2024-02-29"))
    }

    @Test fun displayIsEmptyForMissingOrImpossibleDates() {
        assertEquals("", HydriaDates.display(null))
        assertEquals("", HydriaDates.display(""))
        assertEquals("", HydriaDates.display("2026-02-30"))
        assertEquals("", HydriaDates.display("2026-13-01"))
        assertEquals("", HydriaDates.display("12/10/2026"))
        assertEquals("", HydriaDates.display("2026-1-5"))
    }

    @Test fun parseOnlyAcceptsRealIsoDates() {
        assertEquals(LocalDate.of(2026, 2, 28), HydriaDates.parse("2026-02-28"))
        assertNull(HydriaDates.parse("2026-02-29"))
        assertNull(HydriaDates.parse("2026-02-30"))
        assertNull(HydriaDates.parse(null))
    }

    @Test fun normalizeKeepsAPastDateAndFallsBackToToday() {
        assertEquals("2026-10-01", HydriaDates.normalize("2026-10-01", maxToday = true, today = today))
        assertEquals("2026-10-19", HydriaDates.normalize(null, maxToday = true, today = today))
        assertEquals("2026-10-19", HydriaDates.normalize("", maxToday = false, today = today))
        assertEquals("2026-10-19", HydriaDates.normalize("2026-02-30", maxToday = true, today = today))
    }

    @Test fun normalizeCapsFutureDatesOnlyWhenMaxTodayIsSet() {
        assertEquals("2026-10-19", HydriaDates.normalize("2026-12-25", maxToday = true, today = today))
        assertEquals("2026-12-25", HydriaDates.normalize("2026-12-25", maxToday = false, today = today))
        assertEquals("2026-10-19", HydriaDates.normalize("2026-10-19", maxToday = true, today = today))
    }

    @Test fun pickerMaxIsTheSameCalendarDayWhateverTheDeviceTimezone() {
        // Madagascar est à UTC+3 ; un téléphone réglé très à l'est ou à l'ouest ne doit pas décaler la borne.
        for (id in listOf("Indian/Antananarivo", "UTC", "Pacific/Kiritimati", "Pacific/Pago_Pago", "America/Los_Angeles", "Asia/Tokyo")) {
            val zone = ZoneId.of(id)
            val millis = HydriaDates.pickerMaxMillis(today, zone)
            assertEquals(id, today, Instant.ofEpochMilli(millis).atZone(zone).toLocalDate())
        }
    }
}
