package mg.hydria.desktop.screens

import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class DateFieldTest {
    @Test
    fun displayIsDayMonthYear() {
        assertEquals("28/09/2026", displayDate("2026-09-28"))
        assertEquals("28/09/2026", displayDate("2026-09-28T10:00:00Z"))
        assertEquals("29/02/2024", displayDate(" 2024-02-29 "))
    }

    @Test
    fun missingOrImpossibleDatesDisplayNothing() {
        for (bad in listOf(null, "", "  ", "2026-02-30", "2026-13-01", "7/9/2026", "2026-9-8", "abc")) {
            assertEquals("", displayDate(bad), "« $bad »")
            assertNull(parseIsoDate(bad), "« $bad »")
        }
    }

    @Test
    fun pickerMillisAreUtcMidnightOfTheChosenDay() {
        assertEquals(0L, isoToPickerMillis("1970-01-01"))
        assertEquals(86_400_000L, isoToPickerMillis("1970-01-02"))
        assertNull(isoToPickerMillis("2026-02-30"))
    }

    @Test
    fun isoSurvivesAPickerRoundTrip() {
        for (iso in listOf("2026-10-20", "2024-02-29", "2026-12-31", "2000-01-01", "2026-01-01")) {
            assertEquals(iso, pickerMillisToIso(isoToPickerMillis(iso)!!), iso)
        }
    }

    @Test
    fun maxTodayRefusesOnlyTheFutureAndTodayStaysSelectable() {
        val today = LocalDate.of(2026, 10, 20)
        fun selectable(iso: String, maxToday: Boolean) = isSelectableDay(isoToPickerMillis(iso)!!, maxToday, today)
        assertTrue(selectable("2026-10-19", true))
        assertTrue(selectable("2026-10-20", true))
        assertFalse(selectable("2026-10-21", true))
        assertFalse(selectable("2027-01-01", true))
        // Planning et réparation : une date à venir reste permise.
        assertTrue(selectable("2026-10-21", false))
        assertTrue(selectable("2027-01-01", false))
    }

    @Test
    fun todayIsComputedInTheMadagascarZone() {
        assertEquals("Indian/Antananarivo", MADAGASCAR_ZONE.id)
        // Même instant, deux fuseaux : à 22 h UTC il est déjà le lendemain à Madagascar (UTC+3).
        val instant = java.time.Instant.parse("2026-10-20T22:30:00Z")
        assertEquals(LocalDate.of(2026, 10, 21), LocalDate.ofInstant(instant, MADAGASCAR_ZONE))
        assertEquals(LocalDate.of(2026, 10, 20), LocalDate.ofInstant(instant, java.time.ZoneOffset.UTC))
    }
}
