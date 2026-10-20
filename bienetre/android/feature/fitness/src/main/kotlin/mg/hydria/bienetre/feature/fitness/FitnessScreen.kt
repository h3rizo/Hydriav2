package mg.hydria.bienetre.feature.fitness

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.compose.AsyncImage
import kotlinx.coroutines.delay
import mg.hydria.bienetre.core.designsystem.*
import mg.hydria.bienetre.core.model.*
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun FitnessRoute(onSessionExpired: () -> Unit, viewModel: FitnessViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) { if (state == FitnessUiState.SessionExpired) onSessionExpired() }
    FitnessScreen(state, viewModel::load, viewModel::generate, viewModel::start, viewModel::end, viewModel::complete, viewModel::postpone)
}

@Composable
fun FitnessScreen(
    state: FitnessUiState,
    onRetry: () -> Unit,
    onGenerate: (String, Int, Int) -> Unit,
    onStart: () -> Unit,
    onEnd: () -> Unit,
    onComplete: (WorkoutPlanItem, String, String, String, Int, String, String) -> Unit,
    onPostpone: (WorkoutPlanItem, String) -> Unit,
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            FitnessUiState.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            FitnessUiState.SessionExpired -> Unit
            is FitnessUiState.Error -> FitnessError(state.message, onRetry)
            is FitnessUiState.Content -> FitnessContentScreen(state.data, onGenerate, onStart, onEnd, onComplete, onPostpone)
        }
    }
}

@Composable
private fun FitnessContentScreen(data: FitnessContent, generate: (String, Int, Int) -> Unit, start: () -> Unit, end: () -> Unit, complete: (WorkoutPlanItem, String, String, String, Int, String, String) -> Unit, postpone: (WorkoutPlanItem, String) -> Unit) {
    var tab by remember { mutableIntStateOf(0) }
    var generateDialog by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(start = 20.dp, top = 28.dp, end = 20.dp)) {
            Text("MOUVEMENT ET RÉCUPÉRATION", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
            Text("Votre entraînement", style = MaterialTheme.typography.displaySmall)
            PrimaryTabRow(selectedTabIndex = tab, modifier = Modifier.padding(top = 16.dp)) {
                Tab(tab == 0, { tab = 0 }, text = { Text("Programme") }, icon = { Icon(Icons.Outlined.CalendarViewWeek, null) })
                Tab(tab == 1, { tab = 1 }, text = { Text("Séance du jour") }, icon = { Icon(Icons.Outlined.Timer, null) })
            }
        }
        data.message?.let { WellnessCard(Modifier.fillMaxWidth().padding(20.dp), emphasized = true) { Text(it) } }
        if (tab == 0) ProgramTab(data, { generateDialog = true }) else TodayTab(data, start, end, complete, postpone)
    }
    if (generateDialog) GenerateProgramDialog(data.busy, { generateDialog = false }) { date, frequency, weeks -> generate(date, frequency, weeks); generateDialog = false }
}

@Composable
private fun ProgramTab(data: FitnessContent, openGenerate: () -> Unit) {
    val cycle = data.overview.cycle
    val plan = cycle.plan
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(20.dp, 18.dp, 20.dp, 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            if (plan == null) WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
                Icon(Icons.Outlined.FitnessCenter, null, tint = WellnessEmerald, modifier = Modifier.size(34.dp)); Text("Aucun programme actif", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.titleLarge); Text("Générez un cycle adapté à votre objectif et à votre profil.", Modifier.padding(top = 7.dp), color = MaterialTheme.colorScheme.onSurfaceVariant); Button(openGenerate, Modifier.padding(top = 16.dp), enabled = !data.busy) { Text("Créer mon programme") }
            } else PlanHero(plan, openGenerate, data.busy)
        }
        cycle.weeks.forEach { week -> item { WeekCard(week) } }
    }
}

@Composable
private fun PlanHero(plan: WorkoutPlan, regenerate: () -> Unit, busy: Boolean) {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
        Text(objectiveLabel(plan.objective), style = MaterialTheme.typography.headlineSmall)
        Text("${plan.frequencyPerWeek} séances par semaine • ${plan.durationWeeks} semaines", Modifier.padding(top = 7.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Cycle commencé le ${plan.startDate}", Modifier.padding(top = 4.dp), color = WellnessEmerald)
        TextButton(onClick = regenerate, enabled = !busy, modifier = Modifier.padding(top = 7.dp)) { Icon(Icons.Outlined.Refresh, null); Text("Régénérer", Modifier.padding(start = 7.dp)) }
    }
}

@Composable
private fun WeekCard(week: WorkoutWeek) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle("Semaine ${week.index}", "${shortDate(week.startDate)} — ${shortDate(week.endDate)}")
        if (week.items.isEmpty()) WellnessCard(Modifier.fillMaxWidth()) { Text("Aucun exercice programmé.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        else week.items.groupBy { it.plannedDate ?: it.weekday }.forEach { (day, items) ->
            WellnessCard(Modifier.fillMaxWidth()) {
                Text(dayLabel(day), color = WellnessOrange, fontWeight = FontWeight.Bold)
                items.sortedBy { it.order }.forEach { item ->
                    Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        ExerciseVisual(item, 50)
                        Column(Modifier.weight(1f).padding(start = 12.dp)) { Text(item.exerciseName, fontWeight = FontWeight.SemiBold); Text(exercisePrescription(item), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) }
                        StatusIcon(item.status)
                    }
                }
            }
        }
    }
}

@Composable
private fun TodayTab(data: FitnessContent, start: () -> Unit, end: () -> Unit, complete: (WorkoutPlanItem, String, String, String, Int, String, String) -> Unit, postpone: (WorkoutPlanItem, String) -> Unit) {
    val today = data.overview.today
    val session = data.overview.daySession
    var completionItem by remember { mutableStateOf<WorkoutPlanItem?>(null) }
    var postponeItem by remember { mutableStateOf<WorkoutPlanItem?>(null) }
    var restDeadline by remember { mutableStateOf<Long?>(null) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(20.dp, 18.dp, 20.dp, 32.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item { SessionHero(session, today.items.size, data.busy, start, end) }
        if (today.items.isEmpty()) item { WellnessCard(Modifier.fillMaxWidth()) { Text("Aucun exercice disponible aujourd’hui", style = MaterialTheme.typography.titleLarge); Text("Les séances manquées peuvent être reportées par Django au prochain bloc disponible.", Modifier.padding(top = 7.dp), color = MaterialTheme.colorScheme.onSurfaceVariant) } }
        items(today.items, key = { it.id }) { item ->
            TodayExerciseCard(item, item.id in data.busyItemIds, { restDeadline = System.currentTimeMillis() + item.restSeconds * 1000L }, { completionItem = item }, { postponeItem = item })
        }
        if (data.overview.history.isNotEmpty()) { item { SectionTitle("Historique", "Vos dernières validations") }; items(data.overview.history.take(6)) { HistoryCard(it) } }
        session?.analysis?.takeIf(String::isNotBlank)?.let { item { WellnessCard(Modifier.fillMaxWidth(), emphasized = true) { Text("Analyse de séance", color = WellnessOrange, fontWeight = FontWeight.Bold); Text(it, Modifier.padding(top = 8.dp)) } } }
    }
    restDeadline?.let { RestTimerDialog(it) { restDeadline = null } }
    completionItem?.let { item -> CompletionDialog(item, { completionItem = null }) { sets, reps, weight, duration, comment -> complete(item, sets, reps, weight, item.restSeconds, duration, comment); completionItem = null } }
    postponeItem?.let { item -> PostponeDialog(item, { postponeItem = null }) { date -> postpone(item, date); postponeItem = null } }
}

@Composable
private fun SessionHero(session: WorkoutDaySession?, itemCount: Int, busy: Boolean, start: () -> Unit, end: () -> Unit) {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(74.dp).background(WellnessOrange.copy(alpha = .14f), CircleShape), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Timer, null, tint = WellnessOrange, modifier = Modifier.size(34.dp)) }
            Column(Modifier.weight(1f).padding(start = 16.dp)) {
                Text(if (session?.active == true) "SÉANCE EN COURS" else "PRÊT À BOUGER", color = if (session?.active == true) WellnessEmerald else MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.4.sp)
                Text(if (session != null) sessionClock(session) else "00:00", fontSize = 30.sp, fontWeight = FontWeight.Bold)
                Text("${session?.completedItemsCount ?: 0} / $itemCount exercices", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Button(onClick = if (session?.active == true) end else start, enabled = !busy && itemCount > 0, modifier = Modifier.fillMaxWidth().padding(top = 16.dp)) { Icon(if (session?.active == true) Icons.Outlined.Stop else Icons.Outlined.PlayArrow, null); Text(if (session?.active == true) "Terminer la séance" else "Démarrer la séance", Modifier.padding(start = 8.dp)) }
    }
}

@Composable
private fun sessionClock(session: WorkoutDaySession): String {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(session.id, session.active) { while (session.active) { now = System.currentTimeMillis(); delay(1_000) } }
    val elapsed = if (session.active) ((now - parseInstant(session.startedAt).toEpochMilli()) / 1000).coerceAtLeast(0).toInt() else session.totalDurationSeconds
    return durationLabel(elapsed)
}

@Composable
private fun TodayExerciseCard(item: WorkoutPlanItem, busy: Boolean, rest: () -> Unit, complete: () -> Unit, postpone: () -> Unit) {
    WellnessCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) { ExerciseVisual(item, 68); Column(Modifier.weight(1f).padding(start = 14.dp)) { Text(item.exerciseName, style = MaterialTheme.typography.titleLarge, maxLines = 2, overflow = TextOverflow.Ellipsis); Text(exercisePrescription(item), color = WellnessEmerald, fontWeight = FontWeight.SemiBold); if (item.progressionHint.isNotBlank()) Text(item.progressionHint, Modifier.padding(top = 5.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp) } }
        if (item.coachNote.isNotBlank()) Text("Coach : ${item.coachNote}", Modifier.padding(top = 12.dp), color = WellnessGold)
        Row(Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            OutlinedButton(rest, Modifier.weight(1f), enabled = !busy && item.restSeconds > 0) { Icon(Icons.Outlined.HourglassBottom, null); Text("Repos", Modifier.padding(start = 5.dp)) }
            Button(complete, Modifier.weight(1f), enabled = !busy) { Icon(Icons.Outlined.Check, null); Text("Valider", Modifier.padding(start = 5.dp)) }
        }
        TextButton(onClick = postpone, enabled = !busy, modifier = Modifier.align(Alignment.End)) { Icon(Icons.Outlined.EventRepeat, null); Text("Reporter", Modifier.padding(start = 6.dp)) }
    }
}

@Composable private fun ExerciseVisual(item: WorkoutPlanItem, size: Int) { if (item.imageUrl != null) AsyncImage(item.imageUrl, item.exerciseName, Modifier.size(size.dp).clip(RoundedCornerShape(16.dp)), contentScale = ContentScale.Crop) else Box(Modifier.size(size.dp).background(WellnessEmerald.copy(alpha = .12f), RoundedCornerShape(16.dp)), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.FitnessCenter, null, tint = WellnessEmerald) } }
@Composable private fun StatusIcon(status: String) { Icon(if (status == "termine") Icons.Outlined.CheckCircle else if (status == "reporte") Icons.Outlined.EventRepeat else Icons.Outlined.RadioButtonUnchecked, status, tint = if (status == "termine") WellnessEmerald else if (status == "reporte") WellnessGold else MaterialTheme.colorScheme.outline) }

@Composable
private fun RestTimerDialog(deadline: Long, dismiss: () -> Unit) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(deadline) { while (now < deadline) { now = System.currentTimeMillis(); delay(250) } }
    val seconds = ((deadline - now + 999) / 1000).coerceAtLeast(0)
    AlertDialog(onDismissRequest = dismiss, confirmButton = { Button(onClick = dismiss) { Text(if (seconds == 0L) "Reprendre" else "Arrêter") } }, icon = { Icon(Icons.Outlined.HourglassBottom, null, tint = WellnessGold) }, title = { Text(if (seconds == 0L) "Repos terminé" else "Récupération") }, text = { Text(durationLabel(seconds.toInt()), fontSize = 46.sp, fontWeight = FontWeight.Bold) })
}

@Composable
private fun CompletionDialog(item: WorkoutPlanItem, dismiss: () -> Unit, save: (String, String, String, String, String) -> Unit) {
    var sets by remember { mutableStateOf(item.sets.toString()) }; var reps by remember { mutableStateOf(item.repetitions.toString()) }; var weight by remember { mutableStateOf((item.suggestedWeightKg ?: item.targetWeightKg)?.toString().orEmpty()) }; var duration by remember { mutableStateOf(item.durationSeconds.toString()) }; var comment by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Valider • ${item.exerciseName}") }, confirmButton = { Button(onClick = { save(sets, reps, weight, duration, comment) }) { Text("Valider") } }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = { LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) { item { NumberField("Séries réalisées", sets) { sets = it } }; item { NumberField("Répétitions réalisées", reps) { reps = it } }; item { NumberField("Poids utilisé (kg)", weight, true) { weight = it } }; item { NumberField("Durée effective (secondes)", duration) { duration = it } }; item { OutlinedTextField(comment, { comment = it }, label = { Text("Commentaire") }, modifier = Modifier.fillMaxWidth()) } } })
}
@Composable private fun NumberField(label: String, value: String, decimal: Boolean = false, change: (String) -> Unit) { OutlinedTextField(value, change, label = { Text(label) }, keyboardOptions = KeyboardOptions(keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number), singleLine = true, modifier = Modifier.fillMaxWidth()) }

@Composable
private fun PostponeDialog(item: WorkoutPlanItem, dismiss: () -> Unit, save: (String) -> Unit) { var date by remember { mutableStateOf(LocalDate.now().plusDays(1).toString()) }; AlertDialog(onDismissRequest = dismiss, title = { Text("Reporter ${item.exerciseName}") }, confirmButton = { Button(onClick = { save(date) }) { Text("Reporter") } }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = { OutlinedTextField(date, { date = it }, label = { Text("Nouvelle date AAAA-MM-JJ") }, singleLine = true) }) }

@Composable private fun GenerateProgramDialog(busy: Boolean, dismiss: () -> Unit, save: (String, Int, Int) -> Unit) { var date by remember { mutableStateOf(LocalDate.now().toString()) }; var frequency by remember { mutableIntStateOf(3) }; var weeks by remember { mutableIntStateOf(4) }; AlertDialog(onDismissRequest = dismiss, title = { Text("Générer un programme") }, confirmButton = { Button(onClick = { save(date, frequency, weeks) }, enabled = !busy) { Text("Générer") } }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = { Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { OutlinedTextField(date, { date = it }, label = { Text("Début AAAA-MM-JJ") }, singleLine = true); Text("Séances par semaine"); LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items((2..5).toList()) { FilterChip(frequency == it, { frequency = it }, { Text("$it") }) } }; Text("Durée du cycle"); LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items(listOf(2, 4, 6, 8, 12)) { FilterChip(weeks == it, { weeks = it }, { Text("$it sem.") }) } } } }) }

@Composable private fun HistoryCard(entry: WorkoutHistoryEntry) { WellnessCard(Modifier.fillMaxWidth()) { Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Outlined.History, null, tint = WellnessSky); Column(Modifier.weight(1f).padding(start = 12.dp)) { Text(entry.exerciseName, fontWeight = FontWeight.SemiBold); Text("${entry.sets} × ${entry.repetitions}${entry.weightKg?.let { " à ${number(it)} kg" }.orEmpty()} • ${entry.date}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp); if (entry.comment.isNotBlank()) Text(entry.comment, fontSize = 12.sp) } } } }
@Composable private fun FitnessError(message: String, retry: () -> Unit) { Box(Modifier.fillMaxSize().padding(28.dp), contentAlignment = Alignment.Center) { WellnessCard(Modifier.fillMaxWidth()) { Text("Impossible de charger le programme", style = MaterialTheme.typography.titleLarge); Text(message, Modifier.padding(top = 9.dp)); Button(retry, Modifier.padding(top = 16.dp)) { Text("Réessayer") } } } }

private fun exercisePrescription(item: WorkoutPlanItem) = buildList { if (item.sets > 0) add("${item.sets} séries"); if (item.repetitions > 0) add("${item.repetitions} répétitions"); if (item.durationSeconds > 0) add(durationLabel(item.durationSeconds)); if (item.restSeconds > 0) add("repos ${item.restSeconds}s"); (item.suggestedWeightKg ?: item.targetWeightKg)?.let { add("${number(it)} kg") } }.joinToString(" • ")
private fun durationLabel(seconds: Int) = "%02d:%02d".format(seconds / 60, seconds % 60)
private fun parseInstant(value: String): Instant = runCatching { Instant.parse(value) }.recoverCatching { OffsetDateTime.parse(value).toInstant() }.getOrDefault(Instant.now())
private fun shortDate(value: String) = runCatching { LocalDate.parse(value).format(DateTimeFormatter.ofPattern("d MMM", Locale.FRENCH)) }.getOrDefault(value)
private fun dayLabel(value: String) = runCatching { LocalDate.parse(value).format(DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.FRENCH)) }.getOrDefault(value.replaceFirstChar(Char::uppercase))
private fun objectiveLabel(value: String) = when (value) { "perte_poids" -> "Perte de poids"; "prise_masse" -> "Prise de masse"; "sechage" -> "Séchage"; "alimentation_saine" -> "Équilibre et santé"; else -> value.replace('_', ' ') }
private fun number(value: Double) = if (value % 1 == 0.0) value.toInt().toString() else "%.1f".format(Locale.FRENCH, value)
