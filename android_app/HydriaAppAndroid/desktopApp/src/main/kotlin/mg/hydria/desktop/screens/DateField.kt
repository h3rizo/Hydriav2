package mg.hydria.desktop.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDefaults
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.input.pointer.PointerIcon
import androidx.compose.ui.input.pointer.pointerHoverIcon
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/** « Aujourd'hui » se calcule toujours à l'heure de Madagascar, quel que soit le fuseau du poste. */
internal val MADAGASCAR_ZONE: ZoneId = ZoneId.of("Indian/Antananarivo")

internal fun todayMadagascar(): LocalDate = LocalDate.now(MADAGASCAR_ZONE)

private val DISPLAY_FORMAT = DateTimeFormatter.ofPattern("dd/MM/yyyy")

/** "2026-09-28" (ou "2026-09-28T..") -> date ; null si absent, mal formé ou inexistant (« 2026-02-30 »). */
internal fun parseIsoDate(iso: String?): LocalDate? =
    iso?.trim()?.take(10)?.let { runCatching { LocalDate.parse(it) }.getOrNull() }

/** ISO -> « JJ/MM/AAAA » ; vide si la date est absente ou invalide. */
internal fun displayDate(iso: String?): String = parseIsoDate(iso)?.format(DISPLAY_FORMAT).orEmpty()

/** Le sélecteur Material 3 compte en millisecondes UTC à minuit du jour choisi. */
internal fun isoToPickerMillis(iso: String?): Long? =
    parseIsoDate(iso)?.atStartOfDay(ZoneOffset.UTC)?.toInstant()?.toEpochMilli()

internal fun pickerMillisToIso(millis: Long): String =
    Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate().toString()

/** Jour proposé par le calendrier : tous, ou seulement jusqu'à [today] inclus quand [maxToday] est vrai. */
internal fun isSelectableDay(utcMillis: Long, maxToday: Boolean, today: LocalDate): Boolean =
    !maxToday || !Instant.ofEpochMilli(utcMillis).atZone(ZoneOffset.UTC).toLocalDate().isAfter(today)

/**
 * Champ date non saisissable au clavier (équivalent Desktop de `HydriaUi.dateField` d'Android) :
 * affiche JJ/MM/AAAA, ouvre un calendrier Material 3 au clic, garde l'ISO (AAAA-MM-JJ) en interne.
 * [maxToday] : pas de date après aujourd'hui (Madagascar) ; à désactiver pour un planning ou une réparation.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateField(
    label: String,
    iso: String,
    onChange: (String) -> Unit,
    maxToday: Boolean = true,
    modifier: Modifier = Modifier,
) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedTextField(
            value = displayDate(iso),
            onValueChange = {},
            readOnly = true,
            singleLine = true,
            label = { Text(label) },
            trailingIcon = { Icon(Icons.Filled.CalendarMonth, contentDescription = "Choisir une date") },
            // Un seul arrêt de tabulation : le voile ci-dessous (Entrée / Espace ouvre le calendrier).
            modifier = Modifier.fillMaxWidth().focusProperties { canFocus = false },
        )
        Box(Modifier.matchParentSize().pointerHoverIcon(PointerIcon.Hand).clickable { open = true })
    }
    if (open) {
        val today = remember { todayMadagascar() }
        val selectable = remember(maxToday, today) {
            object : SelectableDates {
                override fun isSelectableDate(utcTimeMillis: Long) = isSelectableDay(utcTimeMillis, maxToday, today)
                override fun isSelectableYear(year: Int) = !maxToday || year <= today.year
            }
        }
        // Hors plage du calendrier (1900-2100), le sélecteur refuserait la date initiale : on l'ignore.
        val initial = parseIsoDate(iso)?.takeIf { it.year in DatePickerDefaults.YearRange }
            ?.let { isoToPickerMillis(it.toString()) }
        val state = rememberDatePickerState(initialSelectedDateMillis = initial, selectableDates = selectable)
        DatePickerDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton(
                    enabled = state.selectedDateMillis != null,
                    onClick = {
                        state.selectedDateMillis?.let { onChange(pickerMillisToIso(it)) }
                        open = false
                    },
                ) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { open = false }) { Text("Annuler") } },
        ) { DatePicker(state) }
    }
}
