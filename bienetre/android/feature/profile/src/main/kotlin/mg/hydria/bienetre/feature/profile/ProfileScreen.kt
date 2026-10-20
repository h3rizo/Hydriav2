package mg.hydria.bienetre.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.Calculate
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import mg.hydria.bienetre.core.designsystem.AuroraBackground
import mg.hydria.bienetre.core.designsystem.SectionTitle
import mg.hydria.bienetre.core.designsystem.WellnessCard
import mg.hydria.bienetre.core.designsystem.WellnessEmerald
import mg.hydria.bienetre.core.designsystem.WellnessGold
import mg.hydria.bienetre.core.designsystem.WellnessOrange
import mg.hydria.bienetre.core.designsystem.WellnessSky
import mg.hydria.bienetre.core.model.ProfileMetrics
import mg.hydria.bienetre.core.preferences.ThemeMode
import java.text.NumberFormat
import java.util.Locale

@Composable
fun ProfileRoute(
    themeMode: ThemeMode,
    onThemeModeChange: (ThemeMode) -> Unit,
    onSessionExpired: () -> Unit,
    onOpenProgress: () -> Unit,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) {
        if (state == ProfileUiState.SessionExpired) onSessionExpired()
    }
    ProfileScreen(state, themeMode, onThemeModeChange, viewModel::load, viewModel::edit, viewModel::save, onOpenProgress)
}

@Composable
fun ProfileScreen(
    state: ProfileUiState,
    themeMode: ThemeMode,
    onThemeModeChange: (ThemeMode) -> Unit,
    onRetry: () -> Unit,
    onEdit: ((ProfileForm) -> ProfileForm) -> Unit,
    onSave: () -> Unit,
    onOpenProgress: () -> Unit = {},
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            ProfileUiState.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            ProfileUiState.SessionExpired -> Unit
            is ProfileUiState.Error -> ErrorCard(state.message, onRetry)
            is ProfileUiState.Content -> ProfileContent(state, themeMode, onThemeModeChange, onEdit, onSave, onOpenProgress)
        }
    }
}

@Composable
private fun ProfileContent(
    state: ProfileUiState.Content,
    themeMode: ThemeMode,
    onThemeModeChange: (ThemeMode) -> Unit,
    onEdit: ((ProfileForm) -> ProfileForm) -> Unit,
    onSave: () -> Unit,
    onOpenProgress: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp, 30.dp, 20.dp, 36.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        item {
            Text("VOTRE PROFIL", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
            Text(state.overview.profile.username, modifier = Modifier.padding(top = 5.dp), style = MaterialTheme.typography.displaySmall)
            state.overview.profile.residenceCityName?.let {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        item { AppearanceSection(themeMode, onThemeModeChange) }
        item { MetricsSection(state.overview.metrics) }
        item {
            WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.AutoMirrored.Outlined.TrendingUp, null, tint = WellnessEmerald)
                    Column(Modifier.weight(1f).padding(horizontal = 14.dp)) {
                        Text("Progression corporelle", fontWeight = FontWeight.Bold)
                        Text("Poids, composition et évolution", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    }
                    Button(onClick = onOpenProgress) { Text("Ouvrir") }
                }
            }
        }
        item { PersonalForm(state.form, onEdit) }
        item { GoalForm(state.form, onEdit) }
        item { CoachForm(state.form, onEdit) }
        state.validationError?.let { error -> item { FeedbackCard(error, false) } }
        state.message?.let { message -> item { FeedbackCard(message, true) } }
        item {
            Button(
                onClick = onSave,
                enabled = !state.saving,
                modifier = Modifier.fillMaxWidth().height(54.dp),
            ) {
                Icon(Icons.Outlined.Edit, null)
                Text(if (state.saving) "Enregistrement…" else "Enregistrer le profil", Modifier.padding(start = 9.dp))
            }
        }
    }
}

@Composable
private fun AppearanceSection(themeMode: ThemeMode, onThemeModeChange: (ThemeMode) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Apparence", "Un thème adapté à votre usage")
        WellnessCard(Modifier.fillMaxWidth()) {
            ChoiceRow(
                options = listOf(
                    ThemeMode.System.name to "Système",
                    ThemeMode.Dark.name to "Sombre",
                    ThemeMode.Light.name to "Clair",
                ),
                selected = themeMode.name,
                onSelected = { value -> onThemeModeChange(ThemeMode.valueOf(value)) },
            )
        }
    }
}

@Composable
private fun MetricsSection(metrics: ProfileMetrics) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Métriques calculées", "Vos repères personnalisés")
        LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val values = listOf(
                Triple("Métabolisme", metrics.basalMetabolism, "kcal"),
                Triple("Dépense/jour", metrics.dailyEnergyExpenditure, "kcal"),
                Triple("Cible", metrics.calorieTarget, "kcal"),
                Triple("Protéines", metrics.proteinTarget, "g"),
                Triple("Glucides", metrics.carbohydrateTarget, "g"),
                Triple("Lipides", metrics.fatTarget, "g"),
            )
            items(values) { (label, value, unit) ->
                WellnessCard(Modifier.fillParentMaxWidth(0.44f)) {
                    Icon(Icons.Outlined.Calculate, null, tint = metricColor(label))
                    Text(label, Modifier.padding(top = 12.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    Text(
                        value?.let { "${formatNumber(it)} $unit" } ?: "—",
                        Modifier.padding(top = 5.dp),
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
        if (!metrics.complete) {
            FeedbackCard(metrics.message.ifBlank { "Complétez votre profil pour calculer vos objectifs." }, false)
        }
    }
}

@Composable
private fun PersonalForm(form: ProfileForm, onEdit: ((ProfileForm) -> ProfileForm) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Informations", "Votre point de départ")
        WellnessCard(Modifier.fillMaxWidth()) {
            FormField("Date de naissance", form.birthDate, { value -> onEdit { it.copy(birthDate = value) } }, KeyboardType.Number)
            Text("Sexe", Modifier.padding(top = 14.dp, bottom = 6.dp), fontWeight = FontWeight.SemiBold)
            ChoiceRow(
                options = listOf("homme" to "Homme", "femme" to "Femme", "autre" to "Autre"),
                selected = form.gender,
                onSelected = { value -> onEdit { it.copy(gender = value) } },
            )
            FormField("Taille (cm)", form.heightCm, { value -> onEdit { it.copy(heightCm = value) } }, KeyboardType.Decimal)
            FormField("Poids de référence (kg)", form.weightKg, { value -> onEdit { it.copy(weightKg = value) } }, KeyboardType.Decimal)
            FormField("Activités par semaine", form.activitiesPerWeek, { value -> onEdit { it.copy(activitiesPerWeek = value) } }, KeyboardType.Number)
            FormField("Durée moyenne (minutes)", form.averageDurationMinutes, { value -> onEdit { it.copy(averageDurationMinutes = value) } }, KeyboardType.Number)
        }
    }
}

@Composable
private fun GoalForm(form: ProfileForm, onEdit: ((ProfileForm) -> ProfileForm) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Objectif", "La direction que vous choisissez")
        WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
            ChoiceRow(
                options = listOf(
                    "perte_poids" to "Perdre du poids",
                    "prise_masse" to "Prendre du muscle",
                    "sechage" to "Séchage",
                    "alimentation_saine" to "Manger sainement",
                    "recomposition_corporelle" to "Recomposition",
                ),
                selected = form.objective,
                onSelected = { value -> onEdit { it.copy(objective = value) } },
            )
            Text("Mode de jeûne", Modifier.padding(top = 18.dp, bottom = 6.dp), fontWeight = FontWeight.SemiBold)
            ChoiceRow(
                options = listOf(
                    "aucun" to "Aucun",
                    "sans_collation" to "Sans collation",
                    "jeune_16_8" to "Jeûne 16/8",
                    "omad" to "OMAD",
                ),
                selected = form.fastingMode,
                onSelected = { value -> onEdit { it.copy(fastingMode = value) } },
            )
        }
    }
}

@Composable
private fun CoachForm(form: ProfileForm, onEdit: ((ProfileForm) -> ProfileForm) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Coaching", "Votre visibilité auprès des membres")
        WellnessCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Apparaître comme coach", fontWeight = FontWeight.SemiBold)
                    Text("Active votre fiche dans l’annuaire.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                Switch(checked = form.listedAsCoach, onCheckedChange = { checked -> onEdit { it.copy(listedAsCoach = checked) } })
            }
            if (form.listedAsCoach) {
                FormField("Biographie", form.coachBio, { value -> onEdit { it.copy(coachBio = value) } })
                FormField("Spécialités", form.coachSpecialties, { value -> onEdit { it.copy(coachSpecialties = value) } })
                FormField("Disponibilités", form.coachAvailability, { value -> onEdit { it.copy(coachAvailability = value) } })
            }
        }
    }
}

@Composable
private fun FormField(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        label = { Text(label) },
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        singleLine = keyboardType != KeyboardType.Text,
    )
}

@Composable
private fun ChoiceRow(options: List<Pair<String, String>>, selected: String, onSelected: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        options.forEach { (value, label) ->
            FilterChip(selected = selected == value, onClick = { onSelected(value) }, label = { Text(label) })
        }
    }
}

@Composable
private fun FeedbackCard(message: String, success: Boolean) {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = success) {
        Text(message, color = if (success) WellnessEmerald else MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun ErrorCard(message: String, onRetry: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(28.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        WellnessCard(Modifier.fillMaxWidth()) {
            Text("Impossible de charger le profil", style = MaterialTheme.typography.titleLarge)
            Text(message, Modifier.padding(top = 10.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            Button(onClick = onRetry, modifier = Modifier.padding(top = 16.dp)) {
                Icon(Icons.Outlined.Refresh, null)
                Text("Réessayer", Modifier.padding(start = 8.dp))
            }
        }
    }
}

private fun formatNumber(value: Double): String = NumberFormat.getNumberInstance(Locale.FRENCH).apply {
    maximumFractionDigits = 0
}.format(value)

private fun metricColor(label: String) = when (label) {
    "Métabolisme", "Cible" -> WellnessOrange
    "Protéines" -> WellnessEmerald
    "Glucides" -> WellnessGold
    "Lipides" -> mg.hydria.bienetre.core.designsystem.WellnessViolet
    else -> WellnessSky
}
