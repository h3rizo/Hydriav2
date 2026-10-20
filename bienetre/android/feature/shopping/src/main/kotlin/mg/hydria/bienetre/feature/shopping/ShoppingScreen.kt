package mg.hydria.bienetre.feature.shopping

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.ShoppingCartCheckout
import androidx.compose.material.icons.outlined.Storefront
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
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
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
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
import mg.hydria.bienetre.core.model.ShoppingItem
import mg.hydria.bienetre.core.model.IngredientOption
import mg.hydria.bienetre.core.model.WellbeingArticle
import java.text.NumberFormat
import java.time.LocalDate
import java.util.Locale

@Composable
fun ShoppingRoute(onSessionExpired: () -> Unit, viewModel: ShoppingViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) { if (state == ShoppingUiState.SessionExpired) onSessionExpired() }
    ShoppingScreen(state, viewModel::load, viewModel::generate, viewModel::check, viewModel::purchaseDate, viewModel::price, viewModel::addManual,
        viewModel::saveIngredientPreference, viewModel::saveWellbeingPreference)
}

@Composable
fun ShoppingScreen(
    state: ShoppingUiState,
    onRetry: () -> Unit,
    onGenerate: (String, String) -> Unit,
    onCheck: (ShoppingItem, Boolean) -> Unit,
    onPurchaseDate: (ShoppingItem, String?) -> Unit,
    onPrice: (ShoppingItem, String, String) -> Unit,
    onAddManual: (Long, String, String) -> Unit,
    onSaveIngredientPreference: (Long, Long?, Boolean, Boolean, String) -> Unit,
    onSaveWellbeingPreference: (Long, Long?, Boolean, String) -> Unit,
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            ShoppingUiState.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            ShoppingUiState.SessionExpired -> Unit
            is ShoppingUiState.Error -> ShoppingError(state.message, onRetry)
            is ShoppingUiState.Content -> ShoppingContentScreen(state.data, onGenerate, onCheck, onPurchaseDate, onPrice, onAddManual, onSaveIngredientPreference, onSaveWellbeingPreference)
        }
    }
}

@Composable
private fun ShoppingContentScreen(
    data: ShoppingContent,
    generate: (String, String) -> Unit,
    check: (ShoppingItem, Boolean) -> Unit,
    purchaseDate: (ShoppingItem, String?) -> Unit,
    price: (ShoppingItem, String, String) -> Unit,
    addManual: (Long, String, String) -> Unit,
    saveIngredientPreference: (Long, Long?, Boolean, Boolean, String) -> Unit,
    saveWellbeingPreference: (Long, Long?, Boolean, String) -> Unit,
) {
    var generateDialog by remember { mutableStateOf(false) }
    var manualDialog by remember { mutableStateOf(false) }
    var priceItem by remember { mutableStateOf<ShoppingItem?>(null) }
    var dateItem by remember { mutableStateOf<ShoppingItem?>(null) }
    var preferencesDialog by remember { mutableStateOf(false) }
    var ingredientPreference by remember { mutableStateOf<IngredientOption?>(null) }
    var wellbeingPreference by remember { mutableStateOf<WellbeingArticle?>(null) }
    val groups = data.items.groupBy { Pair(it.vendorId, it.vendorName ?: "Sans vendeur attribué") }
        .toList().sortedBy { it.first.second }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(20.dp, 28.dp, 20.dp, 32.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item {
            Text("PLACARD ET COURSES", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
            Text("Vos achats", style = MaterialTheme.typography.displaySmall)
        }
        if (data.offline) item {
            WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.CloudOff, null, tint = WellnessGold)
                    Column(Modifier.padding(start = 12.dp)) {
                        Text("Mode hors connexion", fontWeight = FontWeight.Bold)
                        Text("La dernière liste enregistrée reste disponible.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                    }
                }
            }
        }
        item {
            OutlinedButton(onClick = { preferencesDialog = true }, modifier = Modifier.fillMaxWidth(), enabled = !data.savingPreferences) {
                Icon(Icons.Outlined.Settings, null)
                Text(if (data.savingPreferences) "Enregistrement…" else "Préférences d’approvisionnement", Modifier.padding(start = 8.dp))
            }
        }
        item { ShoppingHero(data) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = { generateDialog = true }, enabled = !data.generating, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Outlined.Refresh, null); Text("Générer", Modifier.padding(start = 7.dp))
                }
                OutlinedButton(onClick = { manualDialog = true }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Outlined.Add, null); Text("Article", Modifier.padding(start = 7.dp))
                }
            }
        }
        data.message?.let { item { WellnessCard(Modifier.fillMaxWidth(), emphasized = true) { Text(it) } } }
        if (groups.isEmpty()) item { EmptyShopping() }
        groups.forEach { (vendor, vendorItems) ->
            item {
                VendorGroup(
                    vendorName = vendor.second,
                    city = vendorItems.firstOrNull()?.vendorCity,
                    items = vendorItems.sortedWith(compareBy({ it.checked }, { it.name })),
                    busyIds = data.busyItemIds,
                    onCheck = check,
                    onPrice = { priceItem = it },
                    onDate = { dateItem = it },
                )
            }
        }
    }
    if (generateDialog) GenerateDialog(data.generating, { generateDialog = false }) { start, end -> generate(start, end); generateDialog = false }
    if (manualDialog) ManualItemDialog(data, { manualDialog = false }) { id, quantity, unit -> addManual(id, quantity, unit); manualDialog = false }
    priceItem?.let { item -> PriceDialog(item, { priceItem = null }) { value, unit -> price(item, value, unit); priceItem = null } }
    dateItem?.let { item -> DateDialog(item, { dateItem = null }) { date -> purchaseDate(item, date); dateItem = null } }
    if (preferencesDialog) SupplyPreferencesDialog(data, { preferencesDialog = false },
        { preferencesDialog = false; ingredientPreference = it }, { preferencesDialog = false; wellbeingPreference = it })
    ingredientPreference?.let { ingredient -> IngredientPreferenceDialog(data, ingredient, { ingredientPreference = null }) { vendor, disliked, unavailable, note ->
        saveIngredientPreference(ingredient.id, vendor, disliked, unavailable, note); ingredientPreference = null
    } }
    wellbeingPreference?.let { article -> WellbeingPreferenceDialog(data, article, { wellbeingPreference = null }) { vendor, unavailable, note ->
        saveWellbeingPreference(article.id, vendor, unavailable, note); wellbeingPreference = null
    } }
}

@Composable
private fun SupplyPreferencesDialog(data: ShoppingContent, dismiss: () -> Unit, ingredient: (IngredientOption) -> Unit, article: (WellbeingArticle) -> Unit) {
    var tab by remember { mutableStateOf("ingredients") }
    var search by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Préférences d’approvisionnement") }, confirmButton = { TextButton(dismiss) { Text("Fermer") } }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                item { FilterChip(tab == "ingredients", { tab = "ingredients" }, { Text("Ingrédients") }) }
                item { FilterChip(tab == "articles", { tab = "articles" }, { Text("Bien-être") }) }
            }
            OutlinedTextField(search, { search = it }, Modifier.fillMaxWidth(), label = { Text("Rechercher") }, singleLine = true)
            LazyColumn(Modifier.height(420.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (tab == "ingredients") {
                    val values = data.ingredients.filter { search.isBlank() || it.name.contains(search, true) }
                    items(values, key = { it.id }) { value ->
                        val preference = data.ingredientPreferences.firstOrNull { it.ingredientId == value.id }
                        PreferenceRow(value.icon, value.name, listOfNotNull(
                            preference?.preferredVendorName,
                            "Non apprécié".takeIf { preference?.disliked == true },
                            "Indisponible".takeIf { preference?.unavailable == true },
                        ).joinToString(" • ").ifBlank { "Aucune préférence" }) { ingredient(value) }
                    }
                } else {
                    val values = data.articles.filter { search.isBlank() || it.name.contains(search, true) }
                    items(values, key = { it.id }) { value ->
                        val preference = data.wellbeingPreferences.firstOrNull { it.articleId == value.id }
                        PreferenceRow(value.icon, value.name, listOfNotNull(preference?.preferredVendorName, "Indisponible".takeIf { preference?.unavailable == true }).joinToString(" • ").ifBlank { "Aucune préférence" }) { article(value) }
                    }
                }
            }
        }
    }, shape = RoundedCornerShape(28.dp))
}

@Composable private fun PreferenceRow(icon: String, name: String, summary: String, click: () -> Unit) {
    WellnessCard(Modifier.fillMaxWidth().clickable(onClick = click)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(icon.ifBlank { "•" }, fontSize = 21.sp)
            Column(Modifier.padding(start = 10.dp)) { Text(name, fontWeight = FontWeight.SemiBold); Text(summary, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp) }
        }
    }
}

@Composable
private fun IngredientPreferenceDialog(data: ShoppingContent, ingredient: IngredientOption, dismiss: () -> Unit, save: (Long?, Boolean, Boolean, String) -> Unit) {
    val current = data.ingredientPreferences.firstOrNull { it.ingredientId == ingredient.id }
    var vendor by remember { mutableStateOf(current?.preferredVendorId) }; var disliked by remember { mutableStateOf(current?.disliked ?: false) }
    var unavailable by remember { mutableStateOf(current?.unavailable ?: false) }; var note by remember { mutableStateOf(current?.note.orEmpty()) }
    PreferenceEditorDialog(ingredient.icon, ingredient.name, data.vendors, vendor, { vendor = it }, disliked, { disliked = it }, unavailable, { unavailable = it }, note, { if (it.length <= 255) note = it }, dismiss) {
        save(vendor, disliked, unavailable, note)
    }
}

@Composable
private fun WellbeingPreferenceDialog(data: ShoppingContent, article: WellbeingArticle, dismiss: () -> Unit, save: (Long?, Boolean, String) -> Unit) {
    val current = data.wellbeingPreferences.firstOrNull { it.articleId == article.id }
    var vendor by remember { mutableStateOf(current?.preferredVendorId) }; var unavailable by remember { mutableStateOf(current?.unavailable ?: false) }; var note by remember { mutableStateOf(current?.note.orEmpty()) }
    val allowedVendors = data.vendors.filter { it.id in article.vendorIds }
    PreferenceEditorDialog(article.icon, article.name, allowedVendors, vendor, { vendor = it }, false, null, unavailable, { unavailable = it }, note, { if (it.length <= 255) note = it }, dismiss) {
        save(vendor, unavailable, note)
    }
}

@Composable
private fun PreferenceEditorDialog(
    icon: String, name: String, vendors: List<mg.hydria.bienetre.core.model.VendorOption>, vendorId: Long?, setVendor: (Long?) -> Unit,
    disliked: Boolean, setDisliked: ((Boolean) -> Unit)?, unavailable: Boolean, setUnavailable: (Boolean) -> Unit,
    note: String, setNote: (String) -> Unit, dismiss: () -> Unit, save: () -> Unit,
) {
    AlertDialog(onDismissRequest = dismiss, title = { Text("${icon.ifBlank { "•" }} $name") }, confirmButton = { Button(save) { Text("Enregistrer") } }, dismissButton = { TextButton(dismiss) { Text("Annuler") } }, text = {
        LazyColumn(Modifier.height(430.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Text("Disponibilité", fontWeight = FontWeight.Bold)
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    setDisliked?.let { setter -> FilterChip(disliked, { setter(!disliked) }, { Text("Non apprécié") }) }
                    FilterChip(unavailable, { setUnavailable(!unavailable) }, { Text("Indisponible") })
                }
            }
            item { Text("Vendeur préféré", fontWeight = FontWeight.Bold); FilterChip(vendorId == null, { setVendor(null) }, { Text("Aucun") }) }
            items(vendors, key = { it.id }) { vendor -> FilterChip(vendorId == vendor.id, { setVendor(vendor.id) }, { Text("${vendor.name} • ${vendor.cityName}") }) }
            if (vendors.isEmpty()) item { Text("Aucun vendeur compatible n’est référencé.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
            item { OutlinedTextField(note, setNote, Modifier.fillMaxWidth(), label = { Text("Note facultative") }, supportingText = { Text("${note.length}/255") }, minLines = 2) }
            item { Text("Enregistrer sans option efface la préférence existante.", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp) }
        }
    }, shape = RoundedCornerShape(28.dp))
}

@Composable
private fun ShoppingHero(data: ShoppingContent) {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(72.dp).background(WellnessEmerald.copy(alpha = .14f), CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Outlined.ShoppingCartCheckout, null, tint = WellnessEmerald, modifier = Modifier.size(34.dp))
            }
            Column(Modifier.weight(1f).padding(start = 16.dp)) {
                Text("${data.checkedCount} sur ${data.items.size} achetés", style = MaterialTheme.typography.titleLarge)
                LinearProgressIndicator(
                    progress = { if (data.items.isEmpty()) 0f else data.checkedCount.toFloat() / data.items.size },
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp).height(7.dp),
                    color = WellnessEmerald,
                )
                Text("Budget estimé ${money(data.estimatedTotal)}", Modifier.padding(top = 10.dp), color = WellnessGold, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun VendorGroup(vendorName: String, city: String?, items: List<ShoppingItem>, busyIds: Set<Long>, onCheck: (ShoppingItem, Boolean) -> Unit, onPrice: (ShoppingItem) -> Unit, onDate: (ShoppingItem) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle(city ?: "Vendeur", vendorName)
        WellnessCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Outlined.Storefront, null, tint = WellnessOrange)
                Text("${items.size} article${if (items.size > 1) "s" else ""} • ${money(items.sumOf { it.estimatedTotal })}", Modifier.padding(start = 10.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            items.forEach { item -> ShoppingItemRow(item, item.id in busyIds, onCheck, onPrice, onDate) }
        }
    }
}

@Composable
private fun ShoppingItemRow(item: ShoppingItem, busy: Boolean, onCheck: (ShoppingItem, Boolean) -> Unit, onPrice: (ShoppingItem) -> Unit, onDate: (ShoppingItem) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(top = 15.dp), verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = item.checked, onCheckedChange = { onCheck(item, it) }, enabled = !busy)
        Text(item.icon.ifBlank { "•" }, fontSize = 22.sp)
        Column(Modifier.weight(1f).padding(start = 10.dp)) {
            Text(item.name, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis, textDecoration = if (item.checked) TextDecoration.LineThrough else null)
            Text("${number(item.quantity)} ${item.unit}${item.earliestMealDate?.let { " • repas dès $it" }.orEmpty()}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            Text(item.latestPrice?.let { "${money(it)} ${priceUnit(item.latestPriceUnit)} • estimé ${money(item.estimatedTotal)}" } ?: "Prix non renseigné", color = if (item.latestPrice != null) WellnessGold else MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            item.purchaseDate?.let { Text("Acheté le $it", color = WellnessEmerald, fontSize = 11.sp) }
            if (item.pendingSync) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.CloudUpload, null, Modifier.size(13.dp), tint = WellnessGold)
                    Text(" Synchronisation en attente", color = WellnessGold, fontSize = 11.sp)
                }
            }
        }
        Column {
            TextButton(onClick = { onPrice(item) }, enabled = !busy) { Icon(Icons.Outlined.Edit, "Modifier le prix") }
            TextButton(onClick = { onDate(item) }, enabled = !busy) { Icon(Icons.Outlined.CalendarMonth, "Date d’achat") }
        }
    }
}

@Composable
private fun GenerateDialog(generating: Boolean, dismiss: () -> Unit, generate: (String, String) -> Unit) {
    val today = LocalDate.now()
    var start by remember { mutableStateOf(today.toString()) }
    var end by remember { mutableStateOf(today.plusDays(6).toString()) }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Générer les courses") }, confirmButton = { Button(onClick = { generate(start, end) }, enabled = !generating) { Text("Générer") } }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Les ingrédients proviennent des repas planifiés.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item { FilterChip(false, { start = today.toString(); end = today.toString() }, { Text("Aujourd’hui") }) }
                item { FilterChip(false, { start = today.toString(); end = today.plusDays(6).toString() }, { Text("7 jours") }) }
            }
            OutlinedTextField(start, { start = it }, label = { Text("Début AAAA-MM-JJ") }, singleLine = true)
            OutlinedTextField(end, { end = it }, label = { Text("Fin AAAA-MM-JJ") }, singleLine = true)
        }
    })
}

@Composable
private fun PriceDialog(item: ShoppingItem, dismiss: () -> Unit, save: (String, String) -> Unit) {
    var value by remember { mutableStateOf(item.latestPrice?.toString().orEmpty()) }
    var unit by remember { mutableStateOf(item.latestPriceUnit ?: "total") }
    val units = if (item.type == "wellbeing_article") listOf("total", "piece", "box", "bottle", "pack") else listOf("total", "100g", "kg", "piece")
    AlertDialog(onDismissRequest = dismiss, title = { Text("Prix • ${item.name}") }, confirmButton = { Button(onClick = { save(value, unit) }) { Text("Enregistrer") } }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(item.vendorName ?: "Définissez d’abord un vendeur préféré.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedTextField(value, { value = it }, label = { Text("Prix en ariary") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(7.dp)) { items(units) { choice -> FilterChip(unit == choice, { unit = choice }, { Text(priceUnit(choice)) }) } }
        }
    })
}

@Composable
private fun DateDialog(item: ShoppingItem, dismiss: () -> Unit, save: (String?) -> Unit) {
    var value by remember { mutableStateOf(item.purchaseDate.orEmpty()) }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Date d’achat") }, confirmButton = { Button(onClick = { save(value.ifBlank { null }) }) { Text("Enregistrer") } }, dismissButton = { TextButton(onClick = { save(null) }) { Text("Effacer") } }, text = { OutlinedTextField(value, { value = it }, label = { Text("AAAA-MM-JJ") }, singleLine = true) })
}

@Composable
private fun ManualItemDialog(data: ShoppingContent, dismiss: () -> Unit, add: (Long, String, String) -> Unit) {
    var articleId by remember { mutableStateOf(data.articles.firstOrNull()?.id) }
    var quantity by remember { mutableStateOf("1") }
    var unit by remember { mutableStateOf(data.articles.firstOrNull()?.unit ?: "piece") }
    AlertDialog(onDismissRequest = dismiss, title = { Text("Article bien-être") }, confirmButton = { Button(onClick = { articleId?.let { add(it, quantity, unit) } }, enabled = articleId != null) { Text("Ajouter") } }, dismissButton = { TextButton(onClick = dismiss) { Text("Annuler") } }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Choisissez un article", fontWeight = FontWeight.Bold)
            LazyColumn(Modifier.height(180.dp)) { items(data.articles) { article -> Row(Modifier.fillMaxWidth().clickable { articleId = article.id; unit = article.unit }.padding(vertical = 8.dp)) { Text(article.icon.ifBlank { "•" }); Text(article.name, Modifier.padding(start = 10.dp), fontWeight = if (articleId == article.id) FontWeight.Bold else FontWeight.Normal) } } }
            OutlinedTextField(quantity, { quantity = it }, label = { Text("Quantité") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true)
            OutlinedTextField(unit, { unit = it }, label = { Text("Unité") }, singleLine = true)
        }
    })
}

@Composable private fun EmptyShopping() { WellnessCard(Modifier.fillMaxWidth()) { Icon(Icons.Outlined.ShoppingCartCheckout, null, tint = WellnessGold); Text("Aucune liste active", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.titleLarge); Text("Générez une liste depuis vos repas de la journée ou de la semaine.", Modifier.padding(top = 7.dp), color = MaterialTheme.colorScheme.onSurfaceVariant) } }
@Composable private fun ShoppingError(message: String, retry: () -> Unit) { Box(Modifier.fillMaxSize().padding(28.dp), contentAlignment = Alignment.Center) { WellnessCard(Modifier.fillMaxWidth()) { Text("Impossible de charger les courses", style = MaterialTheme.typography.titleLarge); Text(message, Modifier.padding(top = 9.dp)); Button(retry, Modifier.padding(top = 16.dp)) { Text("Réessayer") } } } }
private fun number(value: Double) = if (value % 1 == 0.0) value.toInt().toString() else "%.1f".format(Locale.FRENCH, value)
private fun money(value: Double) = "${NumberFormat.getIntegerInstance(Locale.FRENCH).format(value)} Ar"
private fun priceUnit(value: String?) = when (value) { "100g" -> "/100 g"; "kg" -> "/kg"; "piece" -> "/pièce"; "box" -> "/boîte"; "bottle" -> "/bouteille"; "pack" -> "/paquet"; else -> "total" }
