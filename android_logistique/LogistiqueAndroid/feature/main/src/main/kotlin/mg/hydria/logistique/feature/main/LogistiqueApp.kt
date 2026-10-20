package mg.hydria.logistique.feature.main

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import mg.hydria.logistique.database.StockDisplayRow
import mg.hydria.logistique.database.MovementDisplayRow
import mg.hydria.logistique.database.PurchaseDisplayRow
import mg.hydria.logistique.database.PurchaseItemDisplayRow

private enum class Destination(val route: String, val label: String, val mark: String) {
    HOME("home", "Accueil", "A"),
    STOCKS("stocks", "Stocks", "S"),
    OPERATIONS("operations", "Opérations", "+"),
    HISTORY("history", "Historique", "H"),
    SYNC("sync", "Synchro", "↻"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogistiqueApp(viewModel: MainViewModel = hiltViewModel()) {
    val session by viewModel.session.collectAsStateWithLifecycle()
    if (session.checking) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        return
    }
    if (!session.authenticated) {
        LoginScreen(session, viewModel::login)
        return
    }

    val navController = rememberNavController()
    val current by navController.currentBackStackEntryAsState()
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Logistique", fontWeight = FontWeight.Bold)
                        Text("Tous les magasins autorisés", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                },
                actions = {
                    ConnectionBadge(online = state.online, pending = state.pendingCount)
                    Spacer(Modifier.size(12.dp))
                },
            )
        },
        bottomBar = {
            NavigationBar {
                Destination.entries.forEach { destination ->
                    NavigationBarItem(
                        selected = current?.destination?.route == destination.route,
                        onClick = {
                            navController.navigate(destination.route) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Text(destination.mark, fontWeight = FontWeight.Black) },
                        label = { Text(destination.label, maxLines = 1) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(navController, startDestination = Destination.HOME.route, modifier = Modifier.padding(padding)) {
            composable(Destination.HOME.route) { HomeScreen(viewModel) }
            composable(Destination.STOCKS.route) { StocksScreen(viewModel) }
            composable(Destination.OPERATIONS.route) { OperationsScreen(viewModel) }
            composable(Destination.HISTORY.route) { HistoryScreen(viewModel) }
            composable(Destination.SYNC.route) { SyncScreen(viewModel, session) }
        }
    }
}

@Composable
private fun LoginScreen(session: SessionUiState, onLogin: (String, String) -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text("LOGISTIQUE", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
            Text("Hydria terrain", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Black)
            Text("Application indépendante · accès selon votre périmètre serveur", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(10.dp))
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Identifiant") },
                singleLine = true,
                enabled = !session.loading,
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Mot de passe") },
                singleLine = true,
                enabled = !session.loading,
                visualTransformation = PasswordVisualTransformation(),
            )
            session.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(
                onClick = { onLogin(username, password) },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                enabled = username.isNotBlank() && password.isNotBlank() && !session.loading,
            ) {
                if (session.loading) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                else Text("Se connecter", fontWeight = FontWeight.Bold)
            }
            Text("Le mot de passe n’est jamais conservé sur l’appareil.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ConnectionBadge(online: Boolean, pending: Int) {
    val bg = if (online) Color(0xFFDCEFE4) else Color(0xFFFFE8C2)
    val fg = if (online) Color(0xFF155A35) else Color(0xFF6D4300)
    Text(
        text = if (online) "En ligne" else "Hors ligne · $pending",
        modifier = Modifier.background(bg, RoundedCornerShape(8.dp)).padding(horizontal = 10.dp, vertical = 6.dp),
        color = fg,
        style = MaterialTheme.typography.labelMedium,
        fontWeight = FontWeight.Bold,
    )
}

@Composable
private fun HomeScreen(viewModel: MainViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val dashboardStats by viewModel.dashboardStats.collectAsStateWithLifecycle()
    val repairOverdue = dashboardStats.firstOrNull { it.code == "repair_overdue_works" }
    val maintenanceOnly = dashboardStats.firstOrNull { it.code == "maintenance_only_works" }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text("Vue terrain", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Black)
            Text("Dernier état synchronisé, complété par les opérations locales estimées.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric("Positions", state.stockCount.toString(), Modifier.weight(1f))
                Metric("Stock bas", state.lowCount.toString(), Modifier.weight(1f), warning = state.lowCount > 0)
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric("À synchroniser", state.pendingCount.toString(), Modifier.weight(1f))
                Metric("Conflits", state.conflictCount.toString(), Modifier.weight(1f), warning = state.conflictCount > 0)
            }
        }
        item { SectionTitle("Activités échues par ouvrage") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric("Réparations échues", repairOverdue?.count?.toString() ?: "—", Modifier.weight(1f), warning = (repairOverdue?.count ?: 0) > 0)
                Metric("Entretiens seulement", maintenanceOnly?.count?.toString() ?: "—", Modifier.weight(1f))
            }
        }
        item {
            Text(
                "Comptage distinct des ouvrages au ${repairOverdue?.asOfDate ?: maintenanceOnly?.asOfDate ?: "dernier état synchronisé"}. “Entretiens seulement” exclut tout ouvrage ayant aussi une réparation, réhabilitation ou panne échue.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        item { SectionTitle("À traiter") }
        item { ActionRow("Réceptions à effectuer", "Les achats réceptionnables apparaîtront après synchronisation") }
        item { ActionRow("Livraisons en attente", "Contrôle de stock obligatoire avant validation") }
        item { ActionRow("Transferts en transit", "Réception ligne par ligne, écart conservé") }
        if (state.unallocatedCount > 0) item {
            ActionRow("Stock non ventilé", "${state.unallocatedCount} position(s) distincte(s) des magasins", warning = true)
        }
    }
}

@Composable
private fun Metric(label: String, value: String, modifier: Modifier, warning: Boolean = false) {
    Surface(modifier, shape = RoundedCornerShape(14.dp), color = if (warning) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceContainer) {
        Column(Modifier.padding(16.dp)) {
            Text(value, style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Black)
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun SectionTitle(value: String) = Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp))

@Composable
private fun ActionRow(title: String, subtitle: String, warning: Boolean = false, onClick: (() -> Unit)? = null) {
    val actionModifier = if (onClick == null) Modifier else Modifier.clickable(onClick = onClick)
    Surface(
        modifier = actionModifier,
        shape = RoundedCornerShape(12.dp),
        color = if (warning) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun StocksScreen(viewModel: MainViewModel) {
    val stocks by viewModel.stocks.collectAsStateWithLifecycle()
    val query by viewModel.stockQuery.collectAsStateWithLifecycle()
    val status by viewModel.stockStatus.collectAsStateWithLifecycle()
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { SectionTitle("Stocks") }
        item {
            OutlinedTextField(
                value = query,
                onValueChange = viewModel::setStockQuery,
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Code ou désignation") },
                singleLine = true,
            )
        }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("" to "Tous", "OK" to "OK", "LOW" to "Stock bas", "OUT" to "Rupture").forEach { (value, label) ->
                    FilterChip(selected = status == value, onClick = { viewModel.setStockStatus(value) }, label = { Text(label) })
                }
            }
        }
        if (stocks.isEmpty()) item { EmptyState("Aucun stock synchronisé", "Connectez-vous puis lancez la première synchronisation.") }
        items(stocks, key = { it.stock.id }) { StockRow(it) }
    }
}

@Composable
private fun StockRow(row: StockDisplayRow) {
    val stock = row.stock
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text("${row.articleCode} · ${row.articleName}", fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(
                if (stock.magasinId == null) "${row.baseName} · Non ventilé (base)" else "${row.baseName} · ${row.magasinName}",
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Actuel ${stock.currentQuantity} ${row.unit}")
                Text("Réservé ${stock.reservedQuantity}")
                Text("Disponible ${stock.availableQuantity}", fontWeight = FontWeight.Bold)
            }
            if (stock.estimated) {
                Text("ESTIMÉ · NON CONFIRMÉ PAR LE SERVEUR", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.tertiary)
                stock.estimateReason?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
        }
    }
}

@Composable
private fun OperationsScreen(viewModel: MainViewModel) {
    val purchases by viewModel.receivablePurchases.collectAsStateWithLifecycle()
    val purchaseItems by viewModel.purchaseItems.collectAsStateWithLifecycle()
    val receptionState by viewModel.purchaseReception.collectAsStateWithLifecycle()
    val operationState by viewModel.operation.collectAsStateWithLifecycle()
    val stocks by viewModel.stocks.collectAsStateWithLifecycle()
    val bases by viewModel.bases.collectAsStateWithLifecycle()
    val magasins by viewModel.magasins.collectAsStateWithLifecycle()
    val employees by viewModel.employees.collectAsStateWithLifecycle()
    val ouvrages by viewModel.ouvrages.collectAsStateWithLifecycle()
    val plannings by viewModel.plannings.collectAsStateWithLifecycle()
    val transfers by viewModel.transfers.collectAsStateWithLifecycle()
    val transferItems by viewModel.transferItems.collectAsStateWithLifecycle()
    val actions = listOf(
        "Réceptionner un achat" to "Confirmation de la réception complète",
        "Effectuer une livraison" to "Ouvrage, planning, quantité et magasin",
        "Créer ou recevoir un transfert" to "Origine et destination distinctes",
        "Réaliser un inventaire" to "Quantité physique constatée",
        "Ajuster un stock" to "Formulaire séparé et mouvement audité",
        "Enregistrer un retour terrain" to "Entrée idempotente, magasin facultatif",
    )
    var selectedAction by remember { mutableStateOf<Pair<String, String>?>(null) }
    var purchaseToReceive by remember { mutableStateOf<PurchaseDisplayRow?>(null) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { SectionTitle("Opérations") }
        item { Text("Choisissez une opération et renseignez le formulaire. Les stocks et référentiels sont synchronisés depuis le serveur.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        items(actions) { action ->
            ActionRow(action.first, action.second, onClick = { selectedAction = action })
        }
    }
    selectedAction?.takeIf { it.first == "Réceptionner un achat" }?.let {
        AlertDialog(
            onDismissRequest = { selectedAction = null },
            title = { Text("Achats à réceptionner") },
            text = {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (purchases.isEmpty()) {
                        item { Text("Aucun achat réceptionnable dans votre périmètre.") }
                    } else {
                        items(purchases, key = { it.purchase.id }) { row ->
                            Surface(
                                modifier = Modifier.fillMaxWidth().clickable {
                                    selectedAction = null
                                    purchaseToReceive = row
                                },
                                shape = RoundedCornerShape(10.dp),
                                color = MaterialTheme.colorScheme.surfaceContainerHigh,
                            ) {
                                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                                    Text(row.purchase.number.orEmpty(), fontWeight = FontWeight.Bold)
                                    Text(row.purchase.supplierName.orEmpty().ifBlank { "Fournisseur non renseigné" })
                                    Text("${row.baseName} · ${row.magasinName}", color = MaterialTheme.colorScheme.primary)
                                    Text("${row.itemCount} article(s) · ${row.purchase.totalAriary} Ar · ${row.purchase.status}", style = MaterialTheme.typography.bodySmall)
                                    PurchaseLines(
                                        lines = purchaseItems.filter { it.item.purchaseId == row.purchase.id },
                                        limit = 3,
                                    )
                                }
                            }
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { selectedAction = null }) { Text("Fermer") } },
        )
    }
    when (selectedAction?.first) {
        "Effectuer une livraison" -> DeliveryDialog(
            stocks = stocks, ouvrages = ouvrages, plannings = plannings,
            loading = operationState.loading,
            onDismiss = { selectedAction = null },
            onSubmit = { selectedAction = null; viewModel.createDelivery(it) },
        )
        "Créer ou recevoir un transfert" -> TransferDialog(
            magasins = magasins, bases = bases, stocks = stocks,
            transfers = transfers, transferItems = transferItems,
            loading = operationState.loading,
            onDismiss = { selectedAction = null },
            onCreate = { selectedAction = null; viewModel.createTransfer(it) },
            onUpdate = { id, request -> selectedAction = null; viewModel.updateTransfer(id, request) },
        )
        "Réaliser un inventaire" -> InventoryDialog(
            stocks = stocks, loading = operationState.loading,
            onDismiss = { selectedAction = null },
            onSubmit = { selectedAction = null; viewModel.createInventory(it) },
        )
        "Ajuster un stock" -> AdjustmentDialog(
            stocks = stocks, employees = employees, loading = operationState.loading,
            onDismiss = { selectedAction = null },
            onSubmit = { stockId, fields -> selectedAction = null; viewModel.adjustStock(stockId, fields) },
        )
        "Enregistrer un retour terrain" -> FieldReturnDialog(
            stocks = stocks, loading = operationState.loading,
            onDismiss = { selectedAction = null },
            onSubmit = { selectedAction = null; viewModel.createFieldReturn(it) },
        )
    }
    purchaseToReceive?.let { row ->
        val loading = receptionState.loadingPurchaseId == row.purchase.id
        AlertDialog(
            onDismissRequest = { if (!loading) purchaseToReceive = null },
            title = { Text("Confirmer la réception") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Achat ${row.purchase.number}", fontWeight = FontWeight.Bold)
                    Text(row.purchase.supplierName.orEmpty().ifBlank { "Fournisseur non renseigné" })
                    Text("Articles réceptionnés", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                    PurchaseLines(
                        lines = purchaseItems.filter { it.item.purchaseId == row.purchase.id },
                    )
                    Text("Les ${row.itemCount} ligne(s) seront réceptionnées intégralement.")
                    Text("Montant : ${row.purchase.totalAriary} Ar")
                    Text("Magasin : ${row.baseName} · ${row.magasinName}")
                    Text("Le stock, les mouvements et la transaction DiameX seront mis à jour.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            },
            dismissButton = {
                TextButton(onClick = { purchaseToReceive = null }, enabled = !loading) { Text("Annuler") }
            },
            confirmButton = {
                Button(onClick = { viewModel.receivePurchase(row.purchase.id) }, enabled = !loading) {
                    if (loading) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    else Text("Réceptionner")
                }
            },
        )
    }
    (receptionState.message ?: receptionState.error)?.let { feedback ->
        AlertDialog(
            onDismissRequest = {
                purchaseToReceive = null
                viewModel.clearPurchaseReceptionFeedback()
            },
            title = { Text(if (receptionState.error == null) "Réception terminée" else "Réception impossible") },
            text = { Text(feedback) },
            confirmButton = {
                TextButton(onClick = {
                    purchaseToReceive = null
                    viewModel.clearPurchaseReceptionFeedback()
                }) { Text("OK") }
            },
        )
    }
    (operationState.message ?: operationState.error)?.let { feedback ->
        AlertDialog(
            onDismissRequest = viewModel::clearOperationFeedback,
            title = { Text(if (operationState.error == null) "Opération enregistrée" else "Opération impossible") },
            text = { Text(feedback) },
            confirmButton = {
                TextButton(onClick = viewModel::clearOperationFeedback) { Text("OK") }
            },
        )
    }
}

@Composable
private fun PurchaseLines(lines: List<PurchaseItemDisplayRow>, limit: Int? = null) {
    val displayed = limit?.let(lines::take) ?: lines
    if (displayed.isEmpty()) {
        Text("Détail des articles indisponible.", style = MaterialTheme.typography.bodySmall)
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        displayed.forEach { row ->
            Text(
                "• ${row.articleCode} — ${row.articleName}",
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                "  Quantité : ${row.item.orderedQuantity} ${row.unit} · Prix unitaire : ${row.item.unitPriceAriary} Ar" +
                    if (row.item.receivedQuantity.toBigDecimalOrNull()?.signum() == 1) " · Déjà reçu : ${row.item.receivedQuantity}" else "",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (limit != null && lines.size > limit) {
            Text("+ ${lines.size - limit} autre(s) article(s)", style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun HistoryScreen(viewModel: MainViewModel) {
    val movements by viewModel.movements.collectAsStateWithLifecycle()
    val outbox by viewModel.outbox.collectAsStateWithLifecycle()
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { SectionTitle("Historique") }
        if (outbox.isNotEmpty()) {
            item { Text("Opérations locales", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary) }
            items(outbox, key = { "local-${it.id}" }) { operation ->
                ActionRow(
                    title = operation.operationType.replace('_', ' '),
                    subtitle = "${operation.businessDate} · ${operation.status}" +
                        (operation.lastErrorMessage?.let { " · $it" } ?: ""),
                    warning = operation.status == "CONFLICT" || operation.status == "REJECTED",
                )
            }
        }
        item { Text("Registre serveur", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary) }
        if (movements.isEmpty()) {
            item { EmptyState("Aucun mouvement synchronisé", "Relancez la synchronisation après le déploiement de l'API d'historique.") }
        } else {
            items(movements, key = { it.movement.id }) { MovementRow(it) }
        }
    }
}

@Composable
private fun MovementRow(row: MovementDisplayRow) {
    val movement = row.movement
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("${row.articleCode} · ${row.articleName}", fontWeight = FontWeight.Bold)
            Text(movement.movementType.replace('_', ' '), color = MaterialTheme.colorScheme.primary)
            Text("${movement.movementDate} · Quantité ${movement.quantity}")
            Text(
                if (movement.magasinId == null) "${row.baseName} · Non ventilé (base)" else "${row.baseName} · ${row.magasinName.orEmpty()}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            movement.reference?.takeIf { it.isNotBlank() }?.let { Text("Référence : $it", style = MaterialTheme.typography.bodySmall) }
            movement.notes?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 3, overflow = TextOverflow.Ellipsis) }
        }
    }
}

@Composable
private fun SyncScreen(viewModel: MainViewModel, session: SessionUiState) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val outbox by viewModel.outbox.collectAsStateWithLifecycle()
    val conflicts by viewModel.conflicts.collectAsStateWithLifecycle()
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item { SectionTitle("Synchronisation") }
        item { ActionRow("Dernière synchronisation", state.lastSync ?: "Jamais sur cet appareil") }
        session.error?.let { error -> item { Text(error, color = MaterialTheme.colorScheme.error) } }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(onClick = viewModel::synchronize, enabled = state.online && !session.loading, modifier = Modifier.weight(1f)) {
                    Text(if (session.loading) "Synchronisation…" else "Synchroniser")
                }
                TextButton(onClick = viewModel::logout) { Text("Déconnexion") }
            }
        }
        item { Text("File locale · ${outbox.size}", fontWeight = FontWeight.Bold) }
        if (outbox.isEmpty()) item { EmptyState("Tout est à jour", "Aucune opération locale en attente.") }
        items(outbox, key = { it.id }) { ActionRow(it.operationType, it.status, warning = it.status == "REJECTED") }
        item { Text("Conflits · ${conflicts.size}", fontWeight = FontWeight.Bold) }
        items(conflicts, key = { it.id }) { ActionRow(it.code, it.message, warning = true) }
    }
}

@Composable
private fun EmptyState(title: String, message: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 32.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text(message, modifier = Modifier.padding(top = 6.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
