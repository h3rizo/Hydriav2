package mg.hydria.logistique.feature.main

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import mg.hydria.logistique.database.BaseEntity
import mg.hydria.logistique.database.EmployeeEntity
import mg.hydria.logistique.database.MagasinEntity
import mg.hydria.logistique.database.OuvrageEntity
import mg.hydria.logistique.database.PlanningEntity
import mg.hydria.logistique.database.StockDisplayRow
import mg.hydria.logistique.database.TransferEntity
import mg.hydria.logistique.database.TransferItemEntity
import mg.hydria.logistique.network.CreateTransferRequest
import mg.hydria.logistique.network.DeliveryRequest
import mg.hydria.logistique.network.FieldReturnRequest
import mg.hydria.logistique.network.TransferLineRequest
import mg.hydria.logistique.network.UpdateTransferRequest
import java.time.LocalDate

@Composable
internal fun DeliveryDialog(
    stocks: List<StockDisplayRow>, ouvrages: List<OuvrageEntity>, plannings: List<PlanningEntity>,
    loading: Boolean, onDismiss: () -> Unit, onSubmit: (DeliveryRequest) -> Unit,
) {
    var stock by remember { mutableStateOf<StockDisplayRow?>(null) }
    var ouvrage by remember { mutableStateOf<OuvrageEntity?>(null) }
    var planning by remember { mutableStateOf<PlanningEntity?>(null) }
    var quantity by remember { mutableStateOf("") }
    var number by remember { mutableStateOf("") }
    var delivered by remember { mutableStateOf(false) }
    var date by remember { mutableStateOf(LocalDate.now().toString()) }
    val eligiblePlannings = plannings.filter { it.ouvrageId == ouvrage?.id }
    FormDialog("Effectuer une livraison", loading, onDismiss, {
        val selected = stock ?: return@FormDialog
        val selectedPlanning = planning ?: return@FormDialog
        onSubmit(DeliveryRequest(selectedPlanning.id, selected.stock.articleId, quantity, selected.magasinName.orEmpty(), number, if (delivered) "livre" else "en_attente", if (delivered) date else null))
    }, stock != null && ouvrage != null && planning != null && positive(quantity)) {
        Picker("Article, base et magasin", stocks, stock, { "${it.articleCode} · ${it.articleName} · ${it.baseName} · ${it.magasinName ?: "Non ventilé"}" }) { stock = it }
        Picker("Ouvrage *", ouvrages, ouvrage, { it.name }) { ouvrage = it; planning = null }
        Picker("Planning *", eligiblePlannings, planning, { it.businessDate.take(16).replace('T', ' ') }) { planning = it }
        NumberField("Quantité *", quantity) { quantity = it }
        OutlinedTextField(number, { number = it }, Modifier.fillMaxWidth(), label = { Text("Numéro de bon (facultatif)") })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(!delivered, { delivered = false }, { Text("En attente") })
            FilterChip(delivered, { delivered = true }, { Text("Livré") })
        }
        if (delivered) OutlinedTextField(date, { date = it }, Modifier.fillMaxWidth(), label = { Text("Date d’utilisation * (AAAA-MM-JJ)") })
    }
}

@Composable
internal fun TransferDialog(
    magasins: List<MagasinEntity>, bases: List<BaseEntity>, stocks: List<StockDisplayRow>,
    transfers: List<TransferEntity>, transferItems: List<TransferItemEntity>, loading: Boolean,
    onDismiss: () -> Unit, onCreate: (CreateTransferRequest) -> Unit,
    onUpdate: (String, UpdateTransferRequest) -> Unit,
) {
    var createMode by remember { mutableStateOf(true) }
    var origin by remember { mutableStateOf<MagasinEntity?>(null) }
    var destination by remember { mutableStateOf<MagasinEntity?>(null) }
    var stock by remember { mutableStateOf<StockDisplayRow?>(null) }
    var quantity by remember { mutableStateOf("") }
    var expected by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var transfer by remember { mutableStateOf<TransferEntity?>(null) }
    val received = remember { mutableStateMapOf<String, String>() }
    val lines = transferItems.filter { it.transferId == transfer?.id }
    val origins = magasins
    val originStocks = stocks.filter { it.stock.magasinId == origin?.id && it.stock.availableQuantity.toBigDecimalOrNull()?.signum() == 1 }
    FormDialog("Créer ou recevoir un transfert", loading, onDismiss, {
        if (createMode) {
            val o = origin ?: return@FormDialog; val d = destination ?: return@FormDialog; val s = stock ?: return@FormDialog
            onCreate(CreateTransferRequest(o.id, d.id, expected.ifBlank { null }, notes, listOf(TransferLineRequest(s.stock.articleId, quantity))))
        } else {
            val t = transfer ?: return@FormDialog
            onUpdate(t.id, UpdateTransferRequest("recevoir", lines.associate { it.id to (received[it.id] ?: it.sentQuantity) }))
        }
    }, if (createMode) origin != null && destination != null && origin?.id != destination?.id && stock != null && positive(quantity) else transfer != null && lines.all { validReceived(received[it.id] ?: it.sentQuantity, it.sentQuantity) }) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(createMode, { createMode = true }, { Text("Créer") })
            FilterChip(!createMode, { createMode = false }, { Text("Recevoir") })
        }
        if (createMode) {
            Picker("Magasin d’origine *", origins, origin, { magasinLabel(it, bases) }) { origin = it; stock = null }
            Picker("Magasin de destination *", magasins.filter { it.id != origin?.id }, destination, { magasinLabel(it, bases) }) { destination = it }
            Picker("Article *", originStocks, stock, { "${it.articleCode} · ${it.articleName} · disponible ${it.stock.availableQuantity}" }) { stock = it }
            NumberField("Quantité *", quantity) { quantity = it }
            OutlinedTextField(expected, { expected = it }, Modifier.fillMaxWidth(), label = { Text("Arrivée prévue (facultative, ISO)") })
            OutlinedTextField(notes, { notes = it }, Modifier.fillMaxWidth(), label = { Text("Notes") })
        } else {
            Picker("Transfert en transit *", transfers.filter { it.status == "en_cours" }, transfer, { it.number.orEmpty() }) {
                transfer = it; received.clear()
            }
            lines.forEach { line ->
                NumberField("Quantité reçue (envoyée ${line.sentQuantity})", received[line.id] ?: line.sentQuantity) { received[line.id] = it }
            }
        }
    }
}

@Composable
internal fun InventoryDialog(stocks: List<StockDisplayRow>, loading: Boolean, onDismiss: () -> Unit, onSubmit: (Map<String, String>) -> Unit) {
    var stock by remember { mutableStateOf<StockDisplayRow?>(null) }; var quantity by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(LocalDate.now().toString()) }; var notes by remember { mutableStateOf("") }; var reconciled by remember { mutableStateOf(false) }
    FormDialog("Nouvel inventaire", loading, onDismiss, {
        val s = stock ?: return@FormDialog
        onSubmit(mapOf("designation_id" to s.stock.articleId, "base_id" to s.stock.baseId, "magasin_id" to s.stock.magasinId.orEmpty(), "quantity" to quantity, "inventory_date" to date, "notes" to notes, "rapproche" to reconciled.toString()))
    }, stock != null && quantity.toBigDecimalOrNull() != null) {
        Picker("Article, base et magasin *", stocks, stock, { stockLabel(it) }) { stock = it }
        NumberField("Quantité inventoriée *", quantity) { quantity = it }
        OutlinedTextField(date, { date = it }, Modifier.fillMaxWidth(), label = { Text("Date d’inventaire *") })
        OutlinedTextField(notes, { notes = it }, Modifier.fillMaxWidth(), label = { Text("Notes") })
        CheckRow("Rapproché", reconciled) { reconciled = it }
    }
}

@Composable
internal fun AdjustmentDialog(stocks: List<StockDisplayRow>, employees: List<EmployeeEntity>, loading: Boolean, onDismiss: () -> Unit, onSubmit: (String, Map<String, String>) -> Unit) {
    var stock by remember { mutableStateOf<StockDisplayRow?>(null) }; var quantity by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(LocalDate.now().toString()) }; var state by remember { mutableStateOf("bon") }; var reconciled by remember { mutableStateOf(false) }; var employee by remember { mutableStateOf<EmployeeEntity?>(null) }
    FormDialog("Ajuster le stock", loading, onDismiss, {
        val s = stock ?: return@FormDialog; val id = s.stock.stockId ?: return@FormDialog
        onSubmit(id, mapOf("adjust_type" to "set", "quantity" to quantity, "inventory_date" to date, "etat" to state, "rapproche" to if (reconciled) "on" else "", "magasin_id" to s.stock.magasinId.orEmpty(), "utilisateur_id" to employee?.id.orEmpty(), "notes" to "Ajustement depuis l’application Android"))
    }, stock?.stock?.stockId != null && quantity.toBigDecimalOrNull()?.signum()?.let { it >= 0 } == true) {
        Picker("Désignation, base et magasin *", stocks, stock, { stockLabel(it) }) { stock = it }
        stock?.let { Text("Stock actuel : ${it.stock.currentQuantity}") }
        NumberField("Nouvelle quantité *", quantity) { quantity = it }
        OutlinedTextField(date, { date = it }, Modifier.fillMaxWidth(), label = { Text("Date d’inventaire *") })
        Picker("État", listOf("bon", "moyen", "mauvais", "hs"), state, { it.replaceFirstChar(Char::uppercase) }) { state = it }
        Picker("Utilisateur", employees, employee, { it.displayName }) { employee = it }
        CheckRow("Rapproché", reconciled) { reconciled = it }
        Text("Photo : l’envoi différé sera ajouté avec le module photo sécurisé.")
    }
}

@Composable
internal fun FieldReturnDialog(stocks: List<StockDisplayRow>, loading: Boolean, onDismiss: () -> Unit, onSubmit: (FieldReturnRequest) -> Unit) {
    var stock by remember { mutableStateOf<StockDisplayRow?>(null) }; var quantity by remember { mutableStateOf("") }; var date by remember { mutableStateOf(LocalDate.now().toString()) }; var reference by remember { mutableStateOf("") }; var notes by remember { mutableStateOf("") }
    FormDialog("Retour terrain sans bon", loading, onDismiss, {
        val s = stock ?: return@FormDialog
        onSubmit(FieldReturnRequest(s.stock.articleId, s.stock.baseId, s.stock.magasinId, quantity, date, reference, notes))
    }, stock != null && positive(quantity)) {
        Picker("Article et base *", stocks, stock, { stockLabel(it) }) { stock = it }
        NumberField("Quantité positive *", quantity) { quantity = it }
        OutlinedTextField(date, { date = it }, Modifier.fillMaxWidth(), label = { Text("Date de l’opération *") })
        OutlinedTextField(reference, { reference = it }, Modifier.fillMaxWidth(), label = { Text("Référence facultative") })
        OutlinedTextField(notes, { notes = it }, Modifier.fillMaxWidth(), label = { Text("Notes facultatives") })
    }
}

@Composable
private fun FormDialog(title: String, loading: Boolean, onDismiss: () -> Unit, onSubmit: () -> Unit, valid: Boolean, content: @Composable () -> Unit) {
    AlertDialog(onDismissRequest = { if (!loading) onDismiss() }, title = { Text(title) }, text = {
        LazyColumn(Modifier.heightIn(max = 520.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) { item { content() } }
    }, dismissButton = { TextButton(onClick = onDismiss, enabled = !loading) { Text("Annuler") } }, confirmButton = { Button(onClick = onSubmit, enabled = valid && !loading) { Text(if (loading) "Enregistrement…" else "Enregistrer") } })
}

@Composable
private fun <T> Picker(label: String, items: List<T>, selected: T?, text: (T) -> String, onSelect: (T) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Column { Text(label); Box { Button(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) { Text(selected?.let(text) ?: "Sélectionner") }; DropdownMenu(expanded, { expanded = false }) { items.forEach { item -> DropdownMenuItem({ Text(text(item)) }, { onSelect(item); expanded = false }) } } } }
}

@Composable private fun NumberField(label: String, value: String, onChange: (String) -> Unit) = OutlinedTextField(value, onChange, Modifier.fillMaxWidth(), label = { Text(label) }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true)
@Composable private fun CheckRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) { Checkbox(checked, onChange); Text(label, Modifier.padding(top = 12.dp)) } }
private fun positive(value: String) = value.toBigDecimalOrNull()?.signum() == 1
private fun validReceived(value: String, sent: String): Boolean { val v = value.toBigDecimalOrNull() ?: return false; val s = sent.toBigDecimalOrNull() ?: return false; return v.signum() >= 0 && v <= s }
private fun stockLabel(row: StockDisplayRow) = "${row.articleCode} · ${row.articleName} · ${row.baseName} · ${row.magasinName ?: "Non ventilé"}"
private fun magasinLabel(item: MagasinEntity, bases: List<BaseEntity>) = "${bases.firstOrNull { it.id == item.baseId }?.name.orEmpty()} · ${item.name}"
