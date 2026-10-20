package mg.hydria.bienetre.feature.household

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.Restaurant
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import mg.hydria.bienetre.core.designsystem.WellnessOrange
import mg.hydria.bienetre.core.model.HouseholdMember
import mg.hydria.bienetre.core.model.IngredientOption
import mg.hydria.bienetre.core.model.SharedMeal
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun HouseholdRoute(
    currentUserId: Long,
    currentUserName: String,
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
    viewModel: HouseholdViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) { if (state == HouseholdUiState.SessionExpired) onSessionExpired() }
    HouseholdScreen(state, currentUserId, currentUserName, onBack, viewModel::load, viewModel::searchProfiles, viewModel::createMember, viewModel::createMeal)
}

@Composable
fun HouseholdScreen(
    state: HouseholdUiState,
    currentUserId: Long,
    currentUserName: String,
    onBack: () -> Unit,
    retry: () -> Unit,
    searchProfiles: (String) -> Unit,
    createMember: (String, String, Int?, String, Long?) -> Unit,
    createMeal: (String, String, String, String, Long?, Long?, List<SharedIngredientDraft>, List<SharedParticipantDraft>) -> Unit,
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            HouseholdUiState.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            HouseholdUiState.SessionExpired -> Unit
            is HouseholdUiState.Error -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Button(retry) { Text(state.message) } }
            is HouseholdUiState.Content -> HouseholdContentScreen(state.data, currentUserId, currentUserName, onBack, searchProfiles, createMember, createMeal)
        }
    }
}

@Composable
private fun HouseholdContentScreen(
    data: HouseholdContent,
    currentUserId: Long,
    currentUserName: String,
    onBack: () -> Unit,
    searchProfiles: (String) -> Unit,
    createMember: (String, String, Int?, String, Long?) -> Unit,
    createMeal: (String, String, String, String, Long?, Long?, List<SharedIngredientDraft>, List<SharedParticipantDraft>) -> Unit,
) {
    var memberDialog by remember { mutableStateOf(false) }
    var mealDialog by remember { mutableStateOf(false) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(20.dp, 18.dp, 20.dp, 36.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Retour") }
                Column(Modifier.padding(start = 4.dp)) {
                    Text("VIE ENSEMBLE", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.6.sp)
                    Text("Foyer & repas partagés", style = MaterialTheme.typography.headlineMedium)
                }
            }
        }
        data.message?.let { item { WellnessCard(Modifier.fillMaxWidth(), emphasized = true) { Text(it) } } }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton({ memberDialog = true }, Modifier.weight(1f), enabled = !data.busy) { Icon(Icons.Outlined.Groups, null); Text("Membre", Modifier.padding(start = 6.dp)) }
                Button({ mealDialog = true }, Modifier.weight(1f), enabled = !data.busy) { Icon(Icons.Outlined.Restaurant, null); Text("Repas", Modifier.padding(start = 6.dp)) }
            }
        }
        item { SectionTitle("Votre foyer", "${data.overview.members.size} membre(s)") }
        if (data.overview.members.isEmpty()) item { EmptyCard("Ajoutez les personnes qui partagent régulièrement vos repas.") }
        items(data.overview.members, key = { it.id }) { MemberCard(it) }
        item { SectionTitle("Repas visibles", "Créés par vous ou partagés avec vous") }
        if (data.overview.meals.isEmpty()) item { EmptyCard("Aucun repas collectif pour le moment.") }
        items(data.overview.meals, key = { it.id }) { SharedMealCard(it) }
    }
    if (memberDialog) MemberDialog(data, { memberDialog = false }, searchProfiles, createMember)
    if (mealDialog) MealDialog(data, currentUserId, currentUserName, { mealDialog = false }, createMeal)
}

@Composable private fun EmptyCard(text: String) = WellnessCard(Modifier.fillMaxWidth()) { Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant) }

@Composable
private fun MemberCard(member: HouseholdMember) = WellnessCard(Modifier.fillMaxWidth()) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(44.dp).background(WellnessOrange.copy(alpha = .14f), CircleShape), contentAlignment = Alignment.Center) { Text(member.name.take(1).uppercase()) }
        Column(Modifier.padding(start = 12.dp)) {
            Text(member.name, fontWeight = FontWeight.Bold)
            Text(listOfNotNull(member.relationship.takeIf(String::isNotBlank), member.age?.let { "$it ans" }).joinToString(" • ").ifBlank { "Membre du foyer" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            if (member.linkedProfileName.isNotBlank()) Text("Profil lié : ${member.linkedProfileName}", color = WellnessEmerald, fontSize = 11.sp)
        }
    }
}

@Composable
private fun SharedMealCard(meal: SharedMeal) = WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
    Text(meal.sourceLabel.uppercase(), color = WellnessOrange, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
    Text(meal.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
    Text(formatDate(meal.eatenAt) + " • ${number(meal.totalServings)} portions • par ${meal.creatorUsername}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
    Text("${number(meal.calories)} kcal  P ${number(meal.proteins)} g  G ${number(meal.carbohydrates)} g  L ${number(meal.fats)} g", Modifier.padding(top = 9.dp), color = WellnessEmerald, fontWeight = FontWeight.SemiBold)
    Text("${meal.ingredients.size} ingrédient(s) • ${meal.participants.joinToString { it.name }}", Modifier.padding(top = 6.dp), fontSize = 12.sp)
    if (meal.notes.isNotBlank()) Text(meal.notes, Modifier.padding(top = 8.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun MemberDialog(data: HouseholdContent, dismiss: () -> Unit, search: (String) -> Unit, create: (String, String, Int?, String, Long?) -> Unit) {
    var name by remember { mutableStateOf("") }; var relationship by remember { mutableStateOf("") }; var age by remember { mutableStateOf("") }
    var sex by remember { mutableStateOf("") }; var profileQuery by remember { mutableStateOf("") }; var profileId by remember { mutableStateOf<Long?>(null) }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Ajouter un membre") }, confirmButton = {
        Button({ create(name, relationship, age.toIntOrNull(), sex, profileId); dismiss() }, enabled = !data.busy && name.trim().length >= 2) { Text("Ajouter") }
    }, dismissButton = { TextButton(dismiss) { Text("Annuler") } }, text = {
        LazyColumn(Modifier.height(470.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { OutlinedTextField(name, { if (it.length <= 120) name = it }, Modifier.fillMaxWidth(), label = { Text("Nom") }, singleLine = true) }
            item { OutlinedTextField(relationship, { if (it.length <= 50) relationship = it }, Modifier.fillMaxWidth(), label = { Text("Lien (conjoint, enfant…)") }, singleLine = true) }
            item { OutlinedTextField(age, { age = it.filter(Char::isDigit).take(3) }, Modifier.fillMaxWidth(), label = { Text("Âge facultatif") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true) }
            item { LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items(listOf("" to "Non précisé", "female" to "Femme", "male" to "Homme", "other" to "Autre")) { (value, label) -> FilterChip(sex == value, { sex = value }, { Text(label) }) } } }
            item {
                Text("Profil Hydria facultatif", fontWeight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(profileQuery, { profileQuery = it; profileId = null }, Modifier.weight(1f), label = { Text("Nom ou identifiant") }, singleLine = true)
                    IconButton({ search(profileQuery) }, enabled = profileQuery.trim().length >= 2 && !data.searching) { Icon(Icons.Outlined.Add, "Rechercher") }
                }
            }
            items(data.profiles, key = { it.id }) { profile -> FilterChip(profileId == profile.id, { profileId = if (profileId == profile.id) null else profile.id }, { Text(profile.displayName) }) }
        }
    }, shape = RoundedCornerShape(28.dp))
}

@Composable
private fun MealDialog(
    data: HouseholdContent, currentUserId: Long, currentUserName: String, dismiss: () -> Unit,
    create: (String, String, String, String, Long?, Long?, List<SharedIngredientDraft>, List<SharedParticipantDraft>) -> Unit,
) {
    val now = remember { LocalDateTime.now().withSecond(0).withNano(0) }
    var title by remember { mutableStateOf("") }; var date by remember { mutableStateOf(now.toLocalDate().toString()) }; var time by remember { mutableStateOf(now.toLocalTime().toString()) }
    var source by remember { mutableStateOf("home_cooked") }; var notes by remember { mutableStateOf("") }; var ingredientSearch by remember { mutableStateOf("") }
    var shoppingSelf by remember { mutableStateOf(false) }; var cookedSelf by remember { mutableStateOf(false) }
    val quantities = remember { mutableStateMapOf<Long, String>() }; val servings = remember { mutableStateMapOf<String, String>("profile:$currentUserId" to "1") }
    val ingredients = remember(data.overview.ingredients, ingredientSearch) { data.overview.ingredients.filter { ingredientSearch.isBlank() || it.name.contains(ingredientSearch, true) }.take(30) }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Nouveau repas partagé") }, confirmButton = {
        Button(onClick = {
            val ingredientDrafts = quantities.mapNotNull { (id, raw) -> data.overview.ingredients.firstOrNull { it.id == id }?.let { option -> raw.replace(',', '.').toDoubleOrNull()?.let { SharedIngredientDraft(id, it, option.baseUnit) } } }
            val participantDrafts = servings.mapNotNull { (key, raw) -> raw.replace(',', '.').toDoubleOrNull()?.let { amount -> if (key.startsWith("profile:")) SharedParticipantDraft(currentUserId, null, amount) else SharedParticipantDraft(null, key.substringAfter(':').toLong(), amount) } }
            create(title, "${date}T${time}:00", source, notes, if (shoppingSelf && source == "home_cooked") currentUserId else null, if (cookedSelf && source == "home_cooked") currentUserId else null, ingredientDrafts, participantDrafts)
            dismiss()
        }, enabled = !data.busy && title.trim().length >= 2 && quantities.isNotEmpty() && servings.isNotEmpty()) { Text("Créer") }
    }, dismissButton = { TextButton(dismiss) { Text("Annuler") } }, text = {
        LazyColumn(Modifier.height(560.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            item { OutlinedTextField(title, { if (it.length <= 150) title = it }, Modifier.fillMaxWidth(), label = { Text("Titre") }, singleLine = true) }
            item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { OutlinedTextField(date, { date = it }, Modifier.weight(1f), label = { Text("Date AAAA-MM-JJ") }, singleLine = true); OutlinedTextField(time, { time = it }, Modifier.weight(.7f), label = { Text("Heure HH:mm") }, singleLine = true) } }
            item { LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items(listOf("home_cooked" to "Maison", "bought" to "Acheté", "restaurant" to "Restaurant")) { (value, label) -> FilterChip(source == value, { source = value }, { Text(label) }) } } }
            if (source == "home_cooked") item { Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) { FilterChip(shoppingSelf, { shoppingSelf = !shoppingSelf }, { Text("J’ai fait les courses") }); FilterChip(cookedSelf, { cookedSelf = !cookedSelf }, { Text("J’ai cuisiné") }) } }
            item { Text("Participants & portions", fontWeight = FontWeight.Bold); ParticipantChoice("profile:$currentUserId", currentUserName, servings) }
            items(data.overview.members, key = { "member:${it.id}" }) { member -> ParticipantChoice("member:${member.id}", member.name, servings) }
            item { Text("Ingrédients", fontWeight = FontWeight.Bold); OutlinedTextField(ingredientSearch, { ingredientSearch = it }, Modifier.fillMaxWidth(), label = { Text("Rechercher") }, singleLine = true) }
            items(ingredients, key = { it.id }) { ingredient -> IngredientInput(ingredient, quantities) }
            item { OutlinedTextField(notes, { notes = it }, Modifier.fillMaxWidth(), label = { Text("Notes") }, minLines = 2) }
        }
    }, shape = RoundedCornerShape(28.dp))
}

@Composable private fun ParticipantChoice(key: String, name: String, values: MutableMap<String, String>) {
    val value = values[key]
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        FilterChip(value != null, { if (value == null) values[key] = "1" else values.remove(key) }, { Text(name) }, Modifier.weight(1f))
        if (value != null) OutlinedTextField(value, { values[key] = it }, Modifier.weight(.45f).padding(start = 8.dp), label = { Text("Portions") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true)
    }
}

@Composable private fun IngredientInput(ingredient: IngredientOption, values: MutableMap<Long, String>) {
    val value = values[ingredient.id]
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        FilterChip(value != null, { if (value == null) values[ingredient.id] = "100" else values.remove(ingredient.id) }, { Text("${ingredient.icon} ${ingredient.name}") }, Modifier.weight(1f))
        if (value != null) OutlinedTextField(value, { values[ingredient.id] = it }, Modifier.weight(.45f).padding(start = 8.dp), label = { Text(ingredient.baseUnit) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true)
    }
}

private fun formatDate(raw: String) = runCatching { LocalDateTime.parse(raw.replace("Z", "")).format(DateTimeFormatter.ofPattern("d MMM yyyy • HH:mm", Locale.FRENCH)) }.getOrElse { raw.take(16).replace('T', ' ') }
private fun number(value: Double) = if (value % 1.0 == 0.0) value.toInt().toString() else "%.1f".format(Locale.FRENCH, value)
