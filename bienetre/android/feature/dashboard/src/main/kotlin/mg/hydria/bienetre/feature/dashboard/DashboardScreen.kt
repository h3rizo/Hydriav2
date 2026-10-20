package mg.hydria.bienetre.feature.dashboard

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.FitnessCenter
import androidx.compose.material.icons.outlined.LocalDining
import androidx.compose.material.icons.outlined.MonitorWeight
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.ShoppingBag
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import mg.hydria.bienetre.core.designsystem.AuroraBackground
import mg.hydria.bienetre.core.designsystem.BienetreBrandLogo
import mg.hydria.bienetre.core.designsystem.SectionTitle
import mg.hydria.bienetre.core.designsystem.WellnessCard
import mg.hydria.bienetre.core.designsystem.WellnessEmerald
import mg.hydria.bienetre.core.designsystem.WellnessGold
import mg.hydria.bienetre.core.designsystem.WellnessOrange
import mg.hydria.bienetre.core.designsystem.WellnessRose
import mg.hydria.bienetre.core.designsystem.WellnessSky
import mg.hydria.bienetre.core.designsystem.WellnessViolet
import mg.hydria.bienetre.core.model.Dashboard
import mg.hydria.bienetre.core.model.DashboardMeal
import mg.hydria.bienetre.core.model.DashboardShoppingItem
import mg.hydria.bienetre.core.model.DashboardWorkout
import mg.hydria.bienetre.core.model.NutrientProgress
import java.text.NumberFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun DashboardRoute(
    displayName: String,
    onLogout: () -> Unit,
    onSessionExpired: () -> Unit,
    viewModel: DashboardViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) {
        if (state == DashboardUiState.SessionExpired) onSessionExpired()
    }
    DashboardScreen(
        displayName = displayName,
        state = state,
        onRetry = viewModel::refresh,
        onLogout = onLogout,
    )
}

@Composable
fun DashboardScreen(
    displayName: String,
    state: DashboardUiState,
    onRetry: () -> Unit,
    onLogout: () -> Unit,
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            DashboardUiState.Loading -> DashboardSkeleton()
            DashboardUiState.SessionExpired -> Unit
            is DashboardUiState.Error -> DashboardError(state.message, onRetry)
            is DashboardUiState.Content -> DashboardContent(displayName, state.dashboard, onLogout)
        }
    }
}

@Composable
private fun DashboardContent(displayName: String, dashboard: Dashboard, onLogout: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(
            start = 20.dp,
            top = 28.dp,
            end = 20.dp,
            bottom = 28.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        item { DashboardHeader(displayName, dashboard.date, onLogout) }
        item { BalanceHero(dashboard) }
        item { NutritionSection(dashboard) }
        item { MealsSection(dashboard.meals) }
        item { WorkoutSection(dashboard.workouts) }
        item { ShoppingSection(dashboard.shoppingItems) }
        item { ProgressSection(dashboard) }
        if (dashboard.suggestions.isNotEmpty()) {
            item { SuggestionSection(dashboard.suggestions.first()) }
        }
    }
}

@Composable
private fun DashboardHeader(displayName: String, date: String, onLogout: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        BienetreBrandLogo(
            modifier = Modifier.size(48.dp).padding(end = 10.dp),
            contentDescription = null,
        )
        Column(Modifier.weight(1f)) {
            Text(
                text = formatDate(date).uppercase(),
                color = MaterialTheme.colorScheme.primary,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 1.7.sp,
            )
            Text(
                text = "Bonjour, $displayName",
                modifier = Modifier.padding(top = 4.dp),
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.onBackground,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        IconButton(onClick = onLogout) {
            Icon(Icons.AutoMirrored.Outlined.Logout, contentDescription = "Se déconnecter")
        }
    }
}

@Composable
private fun BalanceHero(dashboard: Dashboard) {
    WellnessCard(modifier = Modifier.fillMaxWidth(), emphasized = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    "VOTRE ÉQUILIBRE",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.8.sp,
                )
                Text(
                    dashboard.objective?.let(::objectiveLabel) ?: "Définissez votre objectif",
                    modifier = Modifier.padding(top = 8.dp),
                    style = MaterialTheme.typography.headlineMedium,
                )
                Text(
                    dashboard.metricsMessage ?: "Suivez vos apports au fil de la journée.",
                    modifier = Modifier.padding(top = 9.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyLarge,
                )
            }
            Spacer(Modifier.width(16.dp))
            ProgressRing(dashboard.nutrition.overallPercent)
        }
    }
}

@Composable
private fun ProgressRing(percent: Int) {
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(92.dp)) {
        val track = MaterialTheme.colorScheme.outlineVariant
        Canvas(Modifier.fillMaxSize()) {
            drawArc(
                color = track,
                startAngle = -90f,
                sweepAngle = 360f,
                useCenter = false,
                style = Stroke(8.dp.toPx(), cap = StrokeCap.Round),
            )
            drawArc(
                brush = Brush.sweepGradient(listOf(WellnessOrange, WellnessGold, WellnessOrange)),
                startAngle = -90f,
                sweepAngle = 360f * percent.coerceIn(0, 100) / 100f,
                useCenter = false,
                style = Stroke(8.dp.toPx(), cap = StrokeCap.Round),
            )
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("$percent%", fontWeight = FontWeight.Bold, fontSize = 22.sp)
            Text("du jour", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        }
    }
}

@Composable
private fun NutritionSection(dashboard: Dashboard) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Nutrition", "Vos apports aujourd’hui")
        LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            item { NutrientCard("Calories", dashboard.nutrition.calories, "kcal", WellnessOrange) }
            item { NutrientCard("Protéines", dashboard.nutrition.proteins, "g", WellnessEmerald) }
            item { NutrientCard("Glucides", dashboard.nutrition.carbohydrates, "g", WellnessGold) }
            item { NutrientCard("Lipides", dashboard.nutrition.fats, "g", WellnessViolet) }
        }
    }
}

@Composable
private fun NutrientCard(label: String, progress: NutrientProgress, unit: String, color: Color) {
    WellnessCard(modifier = Modifier.width(154.dp)) {
        Box(Modifier.size(10.dp).background(color, CircleShape))
        Text(label, modifier = Modifier.padding(top = 12.dp), fontWeight = FontWeight.SemiBold)
        Text(
            "${formatNumber(progress.consumed)} $unit",
            modifier = Modifier.padding(top = 10.dp),
            fontSize = 23.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            progress.target?.let { "/ ${formatNumber(it)} $unit" } ?: "Objectif à calculer",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 12.sp,
        )
        LinearProgressIndicator(
            progress = { progress.percent / 100f },
            modifier = Modifier.fillMaxWidth().padding(top = 14.dp).height(6.dp),
            color = color,
            trackColor = MaterialTheme.colorScheme.outlineVariant,
            strokeCap = StrokeCap.Round,
        )
        Text("${progress.percent}%", modifier = Modifier.padding(top = 7.dp), color = color, fontSize = 12.sp)
    }
}

@Composable
private fun MealsSection(meals: List<DashboardMeal>) {
    DashboardListSection(
        kicker = "Repas",
        title = "Votre journée alimentaire",
        emptyText = "Aucun repas n’est planifié aujourd’hui.",
        icon = { Icon(Icons.Outlined.LocalDining, null, tint = WellnessOrange) },
        entries = meals.take(4),
    ) { meal ->
        Column(Modifier.weight(1f)) {
            Text(meal.recipeName, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                "${mealTypeLabel(meal.type)} • ${formatNumber(meal.portions)} portion • ${formatNumber(meal.calories)} kcal",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
        StatusDot(done = meal.status == "mange")
    }
}

@Composable
private fun WorkoutSection(workouts: List<DashboardWorkout>) {
    DashboardListSection(
        kicker = "Sport",
        title = "Entraînement du jour",
        emptyText = "Aucun entraînement n’est programmé aujourd’hui.",
        icon = { Icon(Icons.Outlined.FitnessCenter, null, tint = WellnessEmerald) },
        entries = workouts.take(4),
    ) { workout ->
        Column(Modifier.weight(1f)) {
            Text(workout.exercise, fontWeight = FontWeight.SemiBold)
            Text(
                workoutDescription(workout),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
        StatusDot(workout.completed)
    }
}

@Composable
private fun ShoppingSection(items: List<DashboardShoppingItem>) {
    DashboardListSection(
        kicker = "Courses",
        title = "À prévoir",
        emptyText = "Aucune liste de courses active aujourd’hui.",
        icon = { Icon(Icons.Outlined.ShoppingBag, null, tint = WellnessGold) },
        entries = items.take(5),
    ) { item ->
        Text(item.icon ?: "•", fontSize = 18.sp)
        Column(Modifier.weight(1f).padding(start = 10.dp)) {
            Text(item.name, fontWeight = FontWeight.SemiBold)
            Text(
                "${formatNumber(item.quantity)} ${item.unit}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
        StatusDot(item.checked)
    }
}

@Composable
private fun ProgressSection(dashboard: Dashboard) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Progression", "Votre dernière mesure")
        WellnessCard(Modifier.fillMaxWidth()) {
            val measurement = dashboard.latestMeasurement
            if (measurement == null) {
                EmptyLine(Icons.Outlined.MonitorWeight, "Aucune mesure corporelle enregistrée.")
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.MonitorWeight, null, tint = WellnessSky)
                    Column(Modifier.weight(1f).padding(start = 14.dp)) {
                        Text(
                            measurement.weight?.let { "${formatNumber(it)} kg" } ?: "Poids non renseigné",
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            formatDate(measurement.date),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    dashboard.weightDelta?.let {
                        Text(
                            text = "${if (it > 0) "+" else ""}${formatNumber(it)} kg",
                            color = if (it <= 0) WellnessEmerald else WellnessRose,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun SuggestionSection(suggestion: String) {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
        Text("CONSEIL DU JOUR", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.7.sp)
        Text(suggestion, modifier = Modifier.padding(top = 9.dp), style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun <T> DashboardListSection(
    kicker: String,
    title: String,
    emptyText: String,
    icon: @Composable () -> Unit,
    entries: List<T>,
    rowContent: @Composable RowScope.(T) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle(kicker, title)
        WellnessCard(Modifier.fillMaxWidth()) {
            if (entries.isEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    icon()
                    Text(
                        emptyText,
                        modifier = Modifier.padding(start = 12.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                entries.forEachIndexed { index, entry ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) { rowContent(entry) }
                    if (index < entries.lastIndex) HorizontalDivider(Modifier.padding(vertical = 5.dp))
                }
            }
        }
    }
}

@Composable
private fun StatusDot(done: Boolean) {
    Icon(
        Icons.Outlined.CheckCircle,
        contentDescription = if (done) "Terminé" else "À faire",
        tint = if (done) WellnessEmerald else MaterialTheme.colorScheme.outlineVariant,
    )
}

@Composable
private fun EmptyLine(icon: androidx.compose.ui.graphics.vector.ImageVector, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(text, Modifier.padding(start = 12.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun DashboardSkeleton() {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
        repeat(4) { index ->
            Box(
                Modifier
                    .fillMaxWidth(if (index == 0) 0.65f else 1f)
                    .height(if (index == 1) 176.dp else 96.dp)
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f), RoundedCornerShape(26.dp)),
            )
        }
    }
}

@Composable
private fun DashboardError(message: String, onRetry: () -> Unit) {
    Box(Modifier.fillMaxSize().padding(28.dp), contentAlignment = Alignment.Center) {
        WellnessCard(Modifier.fillMaxWidth()) {
            Text("Impossible d’afficher votre journée", style = MaterialTheme.typography.titleLarge)
            Text(message, Modifier.padding(top = 10.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Button(onClick = onRetry, modifier = Modifier.padding(top = 18.dp)) {
                Icon(Icons.Outlined.Refresh, null)
                Text("Réessayer", Modifier.padding(start = 8.dp))
            }
        }
    }
}

private fun formatDate(value: String): String = runCatching {
    LocalDate.parse(value).format(DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.FRENCH))
}.getOrDefault(value)

private fun formatNumber(value: Double): String = NumberFormat.getNumberInstance(Locale.FRENCH).apply {
    maximumFractionDigits = if (value % 1.0 == 0.0) 0 else 1
}.format(value)

private fun objectiveLabel(value: String): String = when (value) {
    "perte_poids" -> "Perdre du poids durablement"
    "prise_masse" -> "Développer votre masse musculaire"
    "maintien" -> "Maintenir votre équilibre"
    else -> value.replace('_', ' ').replaceFirstChar(Char::uppercase)
}

private fun mealTypeLabel(value: String): String = when (value) {
    "petit_dejeuner" -> "Petit-déjeuner"
    "dejeuner" -> "Déjeuner"
    "diner" -> "Dîner"
    "collation" -> "Collation"
    else -> value.replace('_', ' ').replaceFirstChar(Char::uppercase)
}

private fun workoutDescription(workout: DashboardWorkout): String = buildList {
    add("${workout.sets} séries")
    workout.repetitions?.let { add("$it répétitions") }
    workout.durationSeconds?.let { add("${it / 60} min") }
}.joinToString(" • ")
