package mg.hydria.bienetre.feature.meals

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.automirrored.outlined.MenuBook
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.Groups
import androidx.compose.material.icons.outlined.LocalDining
import androidx.compose.material.icons.outlined.Refresh
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import mg.hydria.bienetre.core.designsystem.AuroraBackground
import mg.hydria.bienetre.core.designsystem.SectionTitle
import mg.hydria.bienetre.core.designsystem.WellnessCard
import mg.hydria.bienetre.core.designsystem.WellnessEmerald
import mg.hydria.bienetre.core.designsystem.WellnessGold
import mg.hydria.bienetre.core.designsystem.WellnessOrange
import mg.hydria.bienetre.core.model.MealPlanEntry
import mg.hydria.bienetre.core.model.Recipe
import mg.hydria.bienetre.core.model.IngredientOption
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun MealsRoute(onSessionExpired: () -> Unit, onOpenHousehold: () -> Unit, viewModel: MealsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) { if (state == MealsUiState.SessionExpired) onSessionExpired() }
    MealsScreen(state, viewModel::load, viewModel::previousWeek, viewModel::nextWeek, viewModel::currentWeek, onOpenHousehold,
        viewModel::generate, viewModel::setStatus, viewModel::setPortions, viewModel::delete, viewModel::add, viewModel::createPersonalRecipe)
}

@Composable
fun MealsScreen(
    state: MealsUiState,
    onRetry: () -> Unit,
    onPreviousWeek: () -> Unit,
    onNextWeek: () -> Unit,
    onCurrentWeek: () -> Unit,
    onOpenHousehold: () -> Unit,
    onGenerate: () -> Unit,
    onStatus: (MealPlanEntry, String) -> Unit,
    onPortions: (MealPlanEntry, Double) -> Unit,
    onDelete: (MealPlanEntry) -> Unit,
    onAdd: (LocalDate, String, Long) -> Unit,
    onCreateRecipe: (String, String, String, List<RecipeIngredientDraft>) -> Unit,
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            MealsUiState.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            MealsUiState.SessionExpired -> Unit
            is MealsUiState.Error -> ErrorState(state.message, onRetry)
            is MealsUiState.Content -> MealsContentScreen(state.data, onPreviousWeek, onNextWeek, onCurrentWeek, onOpenHousehold, onGenerate, onStatus, onPortions, onDelete, onAdd, onCreateRecipe)
        }
    }
}

@Composable
private fun MealsContentScreen(
    data: MealsContent,
    previous: () -> Unit,
    next: () -> Unit,
    current: () -> Unit,
    openHousehold: () -> Unit,
    generate: () -> Unit,
    status: (MealPlanEntry, String) -> Unit,
    portions: (MealPlanEntry, Double) -> Unit,
    delete: (MealPlanEntry) -> Unit,
    add: (LocalDate, String, Long) -> Unit,
    createRecipe: (String, String, String, List<RecipeIngredientDraft>) -> Unit,
) {
    var detail by remember { mutableStateOf<Recipe?>(null) }
    var adding by remember { mutableStateOf(false) }
    var creatingRecipe by remember { mutableStateOf(false) }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp, 28.dp, 20.dp, 32.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item {
            Text("PLAN NUTRITION", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
            Text("Vos repas", style = MaterialTheme.typography.displaySmall)
        }
        item { WeekSelector(data.weekStart, previous, next, current) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = generate, enabled = !data.generating, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Outlined.Refresh, null); Text(if (data.generating) "Génération…" else "Générer", Modifier.padding(start = 7.dp))
                }
                OutlinedButton(onClick = { adding = true }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Outlined.Add, null); Text("Ajouter", Modifier.padding(start = 7.dp))
                }
            }
        }
        item {
            OutlinedButton(onClick = { creatingRecipe = true }, modifier = Modifier.fillMaxWidth(), enabled = !data.creatingRecipe) {
                Icon(Icons.AutoMirrored.Outlined.MenuBook, null)
                Text(if (data.creatingRecipe) "Création…" else "Créer une recette personnelle", Modifier.padding(start = 8.dp))
            }
        }
        item {
            OutlinedButton(onClick = openHousehold, modifier = Modifier.fillMaxWidth()) {
                Icon(Icons.Outlined.Groups, null)
                Text("Foyer & repas partagés", Modifier.padding(start = 8.dp))
            }
        }
        data.message?.let { item { WellnessCard(Modifier.fillMaxWidth(), emphasized = true) { Text(it) } } }
        (0L..6L).forEach { offset ->
            val date = data.weekStart.plusDays(offset)
            val dayMeals = data.meals.filter { it.date == date.toString() }
            item { DaySection(date, dayMeals, data.busyMealIds, data.recipes, status, portions, delete) { detail = it } }
        }
    }
    detail?.let { RecipeDialog(it) { detail = null } }
    if (adding) AddMealDialog(data, { adding = false }, add)
    if (creatingRecipe) PersonalRecipeDialog(data, { creatingRecipe = false }, createRecipe)
}

@Composable
private fun WeekSelector(start: LocalDate, previous: () -> Unit, next: () -> Unit, current: () -> Unit) {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = previous) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Semaine précédente") }
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
                Text("SEMAINE", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, letterSpacing = 1.5.sp)
                Text("${shortDate(start)} — ${shortDate(start.plusDays(6))}", fontWeight = FontWeight.Bold)
            }
            IconButton(onClick = next) { Icon(Icons.AutoMirrored.Outlined.ArrowForward, "Semaine suivante") }
        }
        TextButton(onClick = current, modifier = Modifier.align(Alignment.CenterHorizontally)) { Text("Revenir à cette semaine") }
    }
}

@Composable
private fun DaySection(
    date: LocalDate,
    meals: List<MealPlanEntry>,
    busyIds: Set<Long>,
    recipes: List<Recipe>,
    status: (MealPlanEntry, String) -> Unit,
    portions: (MealPlanEntry, Double) -> Unit,
    delete: (MealPlanEntry) -> Unit,
    detail: (Recipe) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle(date.format(DateTimeFormatter.ofPattern("EEEE", Locale.FRENCH)), date.format(DateTimeFormatter.ofPattern("d MMMM", Locale.FRENCH)))
        if (meals.isEmpty()) WellnessCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Outlined.LocalDining, null, tint = WellnessGold); Text("Aucun repas planifié.", Modifier.padding(start = 12.dp), color = MaterialTheme.colorScheme.onSurfaceVariant) }
        } else meals.forEach { meal -> MealCard(meal, meal.id in busyIds, status, portions, delete) { recipes.firstOrNull { it.id == meal.recipeId }?.let(detail) } }
    }
}

@Composable
private fun MealCard(meal: MealPlanEntry, busy: Boolean, status: (MealPlanEntry, String) -> Unit, portions: (MealPlanEntry, Double) -> Unit, delete: (MealPlanEntry) -> Unit, detail: () -> Unit) {
    WellnessCard(Modifier.fillMaxWidth().clickable(onClick = detail)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (meal.imageUrl != null) AsyncImage(meal.imageUrl, meal.recipeName, Modifier.size(70.dp).clip(RoundedCornerShape(18.dp)), contentScale = ContentScale.Crop)
            else Box(Modifier.size(70.dp).background(WellnessOrange.copy(alpha = .14f), RoundedCornerShape(18.dp)), contentAlignment = Alignment.Center) { Text(meal.recipeIcon.ifBlank { "🍽" }, fontSize = 28.sp) }
            Column(Modifier.weight(1f).padding(start = 14.dp)) {
                Text(typeLabel(meal.type).uppercase(), color = WellnessOrange, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
                Text(meal.recipeName, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text("${number(meal.calories * meal.portions)} kcal • ${number(meal.proteins * meal.portions)} g protéines", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
            IconButton(onClick = { delete(meal) }, enabled = !busy) { Icon(Icons.Outlined.DeleteOutline, "Supprimer") }
        }
        LazyRow(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            items(listOf("prevu" to "Prévu", "mange" to "Mangé", "saute" to "Sauté")) { (value, label) ->
                FilterChip(selected = meal.status == value, onClick = { status(meal, value) }, enabled = !busy, label = { Text(label) })
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.End) {
            Text("Portions", color = MaterialTheme.colorScheme.onSurfaceVariant)
            TextButton(onClick = { portions(meal, meal.portions - .25) }, enabled = !busy) { Text("−") }
            Text(number(meal.portions), fontWeight = FontWeight.Bold)
            TextButton(onClick = { portions(meal, meal.portions + .25) }, enabled = !busy) { Text("+") }
        }
    }
}

@Composable
private fun RecipeDialog(recipe: Recipe, dismiss: () -> Unit) {
    AlertDialog(onDismissRequest = dismiss, confirmButton = { TextButton(onClick = dismiss) { Text("Fermer") } }, title = { Text(recipe.name) }, text = {
        LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            recipe.imageUrl?.let { item { AsyncImage(it, recipe.name, Modifier.fillMaxWidth().height(180.dp).clip(RoundedCornerShape(20.dp)), contentScale = ContentScale.Crop) } }
            item { Text("${number(recipe.calories)} kcal • P ${number(recipe.proteins)} g • G ${number(recipe.carbohydrates)} g • L ${number(recipe.fats)} g", color = WellnessEmerald) }
            if (recipe.ingredients.isNotEmpty()) { item { Text("Ingrédients", fontWeight = FontWeight.Bold) }; items(recipe.ingredients) { Text("• ${it.name} — ${number(it.quantity)} ${it.unit}") } }
            if (recipe.preparation.isNotBlank()) { item { Text("Préparation", fontWeight = FontWeight.Bold) }; item { Text(recipe.preparation) } }
        }
    })
}

@Composable
private fun AddMealDialog(data: MealsContent, dismiss: () -> Unit, add: (LocalDate, String, Long) -> Unit) {
    var day by remember { mutableStateOf(data.weekStart) }
    var type by remember { mutableStateOf("midi") }
    var recipeId by remember { mutableStateOf(data.recipes.firstOrNull()?.id) }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Ajouter un repas") }, confirmButton = {
        Button(onClick = { recipeId?.let { add(day, type, it) }; dismiss() }, enabled = recipeId != null) { Text("Ajouter") }
    }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Jour", fontWeight = FontWeight.Bold)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items((0L..6L).map(data.weekStart::plusDays)) { value -> FilterChip(day == value, { day = value }, { Text(value.format(DateTimeFormatter.ofPattern("EEE d", Locale.FRENCH))) }) } }
            Text("Moment", fontWeight = FontWeight.Bold)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { items(listOf("matin", "midi", "soir", "collation")) { value -> FilterChip(type == value, { type = value }, { Text(typeLabel(value)) }) } }
            Text("Recette", fontWeight = FontWeight.Bold)
            LazyColumn(Modifier.height(190.dp)) { items(data.recipes.filter { categoryMatches(it.mealCategory, type) }) { recipe -> Row(Modifier.fillMaxWidth().clickable { recipeId = recipe.id }.padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) { Box(Modifier.size(10.dp).background(if (recipeId == recipe.id) WellnessOrange else MaterialTheme.colorScheme.outlineVariant, CircleShape)); Text(recipe.name, Modifier.padding(start = 10.dp)) } } }
        }
    })
}

@Composable
private fun PersonalRecipeDialog(
    data: MealsContent,
    dismiss: () -> Unit,
    create: (String, String, String, List<RecipeIngredientDraft>) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("dejeuner") }
    var preparation by remember { mutableStateOf("") }
    var search by remember { mutableStateOf("") }
    var validationMessage by remember { mutableStateOf<String?>(null) }
    val quantities = remember { mutableStateMapOf<Long, String>() }
    val filtered = remember(data.ingredients, search) {
        data.ingredients.filter { search.isBlank() || it.name.contains(search.trim(), ignoreCase = true) }.take(40)
    }
    AlertDialog(
        onDismissRequest = dismiss,
        title = { Text("Recette personnelle") },
        confirmButton = {
            Button(
                onClick = {
                    val ingredients = quantities.mapNotNull { (id, raw) ->
                        val option = data.ingredients.firstOrNull { it.id == id } ?: return@mapNotNull null
                        raw.replace(',', '.').toDoubleOrNull()?.let { RecipeIngredientDraft(id, it, option.baseUnit) }
                    }
                    val quantitiesAreValid = ingredients.size == quantities.size &&
                        ingredients.all { it.quantity > 0.0 && it.quantity <= 100_000.0 }
                    when {
                        name.trim().length < 3 -> validationMessage = "Le nom doit contenir au moins 3 caractères."
                        !quantitiesAreValid -> validationMessage = "Chaque quantité doit être un nombre supérieur à zéro."
                        else -> {
                            validationMessage = null
                            create(name, category, preparation, ingredients)
                            dismiss()
                        }
                    }
                },
                enabled = !data.creatingRecipe && quantities.isNotEmpty(),
            ) { Text("Créer") }
        },
        dismissButton = { TextButton(onClick = dismiss, enabled = !data.creatingRecipe) { Text("Annuler") } },
        text = {
            LazyColumn(Modifier.height(520.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                item {
                    OutlinedTextField(name, { if (it.length <= 255) name = it }, Modifier.fillMaxWidth(), label = { Text("Nom de la recette") }, singleLine = true)
                }
                item {
                    Text("Catégorie", fontWeight = FontWeight.Bold)
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        items(listOf("petit_dejeuner", "dejeuner", "diner", "collation")) { value ->
                            FilterChip(category == value, { category = value }, { Text(typeLabel(value)) })
                        }
                    }
                }
                item {
                    OutlinedTextField(
                        preparation,
                        { if (it.length <= 10_000) preparation = it },
                        Modifier.fillMaxWidth(),
                        label = { Text("Préparation") },
                        minLines = 3,
                    )
                }
                item {
                    Text("Ingrédients", fontWeight = FontWeight.Bold)
                    Text("Les macros seront calculées par Django à partir des quantités.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                    OutlinedTextField(search, { search = it }, Modifier.fillMaxWidth().padding(top = 8.dp), label = { Text("Rechercher dans le catalogue") }, singleLine = true)
                }
                validationMessage?.let { message ->
                    item { Text(message, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
                }
                if (data.ingredients.isEmpty()) {
                    item { Text("Le catalogue d’ingrédients est vide.", color = WellnessOrange) }
                } else {
                    items(filtered, key = { it.id }) { ingredient ->
                        IngredientChoice(
                            ingredient = ingredient,
                            quantity = quantities[ingredient.id],
                            onToggle = {
                                if (quantities.containsKey(ingredient.id)) quantities.remove(ingredient.id)
                                else quantities[ingredient.id] = "100"
                            },
                            onQuantity = { quantities[ingredient.id] = it },
                        )
                    }
                }
            }
        },
        shape = RoundedCornerShape(28.dp),
    )
}

@Composable
private fun IngredientChoice(
    ingredient: IngredientOption,
    quantity: String?,
    onToggle: () -> Unit,
    onQuantity: (String) -> Unit,
) {
    WellnessCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(ingredient.icon.ifBlank { "•" }, fontSize = 20.sp)
            Column(Modifier.weight(1f).padding(horizontal = 10.dp)) {
                Text(ingredient.name, fontWeight = FontWeight.SemiBold)
                if (ingredient.category.isNotBlank()) Text(ingredient.category, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            FilterChip(selected = quantity != null, onClick = onToggle, label = { Text(if (quantity == null) "Ajouter" else "Retirer") })
        }
        if (quantity != null) {
            OutlinedTextField(
                value = quantity,
                onValueChange = onQuantity,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                label = { Text("Quantité (${ingredient.baseUnit})") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                singleLine = true,
            )
        }
    }
}

@Composable private fun ErrorState(message: String, retry: () -> Unit) { Box(Modifier.fillMaxSize().padding(28.dp), contentAlignment = Alignment.Center) { WellnessCard(Modifier.fillMaxWidth()) { Text("Impossible de charger les repas", style = MaterialTheme.typography.titleLarge); Text(message, Modifier.padding(top = 8.dp)); Button(retry, Modifier.padding(top = 16.dp)) { Text("Réessayer") } } } }
private fun shortDate(date: LocalDate) = date.format(DateTimeFormatter.ofPattern("d MMM", Locale.FRENCH))
private fun number(value: Double) = if (value % 1.0 == 0.0) value.toInt().toString() else "%.1f".format(Locale.FRENCH, value)
private fun typeLabel(value: String) = when (value) { "petit_dejeuner", "matin" -> "Petit-déjeuner"; "dejeuner", "midi" -> "Déjeuner"; "diner", "soir" -> "Dîner"; "collation" -> "Collation"; else -> value.replace('_', ' ') }
private fun categoryMatches(category: String, type: String) = category == type || (category == "petit_dejeuner" && type == "matin") || (category == "dejeuner" && type == "midi") || (category == "diner" && type == "soir")
