package mg.hydria.desktop.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Print
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.auth.LoginForm
import org.json.JSONObject
import java.time.YearMonth

private val MONTHS = listOf("Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août",
    "Septembre", "Octobre", "Novembre", "Décembre")

@Composable
fun VolumeScreen(session: DesktopSession) {
    if (!session.isAuthenticated) {
        LoginForm(session, "Requise pour le volumétrique.")
        return
    }
    val scope = rememberCoroutineScope()
    val c = remember(session) { VolumeController(session) }
    LaunchedEffect(c) {
        c.init()
        // Poste neuf : cache "ouvrages" vide -> chargement immediat (cf. VolumeActivity).
        if (c.works.size <= 1) c.refreshWorks()
    }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Volumétrique", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            Text(session.employeeName, style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { session.logout() }) {
                Icon(Icons.Filled.Logout, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(4.dp)); Text("Déconnexion")
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            VolumeStage.entries.forEach { s ->
                FilterChip(selected = c.stage == s, onClick = { c.selectStage(s) }, label = { Text(s.title) }, enabled = !c.busy)
            }
        }

        Spacer(Modifier.padding(3.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Bottom) {
            Box(Modifier.widthIn(min = 260.dp, max = 380.dp)) {
                RefAutocomplete("Ouvrage (vide = tous)", c.works.map { JSONObject(it.toString()).put("label", it.optString("nom")) }, c.workId) { c.selectWork(it) }
            }
            MonthPicker(c.month, enabled = !c.busy) { c.selectMonth(it) }
            Button(onClick = { scope.launch { c.openPeriod() } }, enabled = !c.busy) {
                Icon(Icons.Filled.FolderOpen, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp)); Text("Ouvrir")
            }
            ToolsMenu(c, enabled = !c.busy,
                onRefreshWorks = { scope.launch { c.refreshWorks() } },
                onRefreshPeriod = { scope.launch { c.refreshPeriod() } },
                onSync = { scope.launch { c.synchronize() } })
            if (c.busy) CircularProgressIndicator(modifier = Modifier.width(18.dp), strokeWidth = 2.dp)
        }

        Spacer(Modifier.padding(3.dp))
        Text(c.statusLine(), style = MaterialTheme.typography.bodySmall)
        c.message?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.tertiary) }
        Spacer(Modifier.padding(4.dp))
        HorizontalDivider()
        Spacer(Modifier.padding(4.dp))

        Box(Modifier.weight(1f).fillMaxWidth()) {
            when {
                c.stage == VolumeStage.BILLING -> BillingStage(c) { scope.launch { c.calculate() } }
                c.pack == null -> Text("Ouvrez un ouvrage et un mois. Sans réseau, les données doivent déjà être préchargées.")
                c.stage == VolumeStage.COLLECTION -> CollectionStage(c)
                else -> PointingStage(c)
            }
        }
    }

    c.confirmation?.let { conf ->
        AlertDialog(
            onDismissRequest = { c.cancelConfirmation() },
            title = { Text(conf.title) },
            text = {
                Text("${conf.invoices.size} factures · ${c.total(conf.invoices)} Ar\n" +
                    "${conf.extra.optString("journal_code")} ${conf.extra.optString("date")}\n" +
                    "Conservation locale, puis validation serveur à la synchronisation.")
            },
            confirmButton = { Button(onClick = { scope.launch { c.confirm() } }) { Text("Confirmer") } },
            dismissButton = { TextButton(onClick = { c.cancelConfirmation() }) { Text("Annuler") } },
        )
    }
    if (c.collectFormOpen) CollectDialog(c)
    c.recapShown?.let { RecapDialog(c, it) }
    if (c.historyOpen) HistoryDialog(c)
    if (c.reviewOpen) ReviewDialog(c)
}

@Composable
private fun MonthPicker(value: YearMonth, enabled: Boolean, onChange: (YearMonth) -> Unit) {
    val years = (YearMonth.now().year - 3..YearMonth.now().year + 1).map { JSONObject().put("id", it.toString()).put("label", it.toString()) }
    val months = MONTHS.mapIndexed { i, n -> JSONObject().put("id", (i + 1).toString()).put("label", n) }
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.width(110.dp)) {
            RefDropdown("Année", years, value.year.toString()) { if (enabled) onChange(YearMonth.of(it.toInt(), value.monthValue)) }
        }
        Box(Modifier.width(150.dp)) {
            RefDropdown("Mois", months, value.monthValue.toString()) { if (enabled) onChange(YearMonth.of(value.year, it.toInt())) }
        }
    }
}

@Composable
private fun ToolsMenu(c: VolumeController, enabled: Boolean, onRefreshWorks: () -> Unit, onRefreshPeriod: () -> Unit, onSync: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { open = true }, enabled = enabled) {
            Icon(Icons.Filled.MoreVert, contentDescription = null, modifier = Modifier.width(16.dp))
            Spacer(Modifier.width(6.dp)); Text("Outils")
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            DropdownMenuItem(text = { Text("Actualiser les ouvrages") }, onClick = { open = false; onRefreshWorks() })
            DropdownMenuItem(text = { Text("Actualiser cette période") }, onClick = { open = false; onRefreshPeriod() })
            DropdownMenuItem(text = { Text("Synchroniser (${c.pending().size} en file)") }, onClick = { open = false; onSync() },
                leadingIcon = { Icon(Icons.Filled.CloudUpload, contentDescription = null) })
            DropdownMenuItem(text = { Text("Historique / récapitulatifs") }, onClick = { open = false; c.openHistory() },
                leadingIcon = { Icon(Icons.Filled.History, contentDescription = null) })
        }
    }
}

// ── Facturation ──

@Composable
private fun BillingStage(c: VolumeController, onCalculate: () -> Unit) {
    val scope = rememberCoroutineScope()
    val all = c.rows()
    LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        item {
            Text("Le calcul porte sur tous les relevés de l'ouvrage et du mois choisis.")
            Spacer(Modifier.padding(3.dp))
            Button(onClick = onCalculate, enabled = !c.busy) { Text("Calculer les factures de tout le lot") }
        }
        if (!c.calculated) return@LazyColumn
        val valid = all.filter(c::calculable)
        item {
            Text("${all.size} relevés · ${valid.size} calculables · Total ${c.total(valid)} Ar", style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 6.dp)) {
                Button(onClick = { c.saveBatch() }, enabled = !c.busy) { Text("Enregistrer toutes les factures calculées") }
                OutlinedButton(onClick = { scope.launch { c.printInvoices() } }, enabled = !c.busy) {
                    Icon(Icons.Filled.Print, contentDescription = null, modifier = Modifier.width(16.dp))
                    Spacer(Modifier.width(6.dp)); Text("Imprimer les factures du lot · A4/PDF")
                }
                OutlinedButton(onClick = { c.confirmPrinted() }, enabled = !c.busy) { Text("Confirmer l'impression réalisée du lot") }
            }
        }
        items(all, key = { it.optString("id") }) { row ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
                    Text("${row.optString("idxls")} · ${row.optString("abonne")}", style = MaterialTheme.typography.titleSmall)
                    Text("${row.optString("numero")} · ${row.optString("montant", "—")} Ar")
                    val err = row.optString("erreur_calcul")
                    if (err.isNotBlank()) Text(err, color = MaterialTheme.colorScheme.error)
                    else Text(c.state(row), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

// ── Encaissement ──

@Composable
private fun CollectionStage(c: VolumeController) {
    var code by remember { mutableStateOf("") }
    val rows = c.rows().filterNot { it.optBoolean("pointee") }.filter(c::validated)
    LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        item {
            Summary(c)
            Text("Factures non pointées de cet ouvrage/mois. Cochez les factures à la main ou scannez/saisissez leur numéro.")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(vertical = 6.dp)) {
                OutlinedTextField(
                    value = code, onValueChange = { code = it }, singleLine = true,
                    label = { Text("QR / numéro de facture (douchette ou clavier, Entrée)") },
                    // Une douchette USB « tape » le contenu du QR puis Entrée.
                    modifier = Modifier.width(460.dp).onPreviewKeyEvent {
                        if (it.key != Key.Enter && it.key != Key.NumPadEnter) return@onPreviewKeyEvent false
                        if (it.type == KeyEventType.KeyDown && code.isNotBlank()) { c.addByCode(code); code = "" }
                        true
                    },
                )
                OutlinedButton(onClick = { c.addByCode(code); code = "" }, enabled = !c.busy) { Text("Ajouter") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { c.openCollect() }, enabled = !c.busy && c.selected.isNotEmpty()) { Text("Valider l'encaissement de la sélection") }
                OutlinedButton(onClick = { c.showLastRecap() }, enabled = !c.busy) { Text("Imprimer le dernier récapitulatif d'encaissement") }
            }
        }
        items(rows, key = { it.optString("id") }) { row -> InvoiceCheck(c, row, c.collectable(row)) }
        if (rows.isEmpty()) item { Text("Aucune facture validée à encaisser pour cette période.") }
    }
}

// ── Pointage DiameX ──

@Composable
private fun PointingStage(c: VolumeController) {
    val all = c.rows()
    val entries = c.entries()
    val pointedCount = all.count { it.optBoolean("pointee") } + entries.count { it.optBoolean("pointee") }
    val visibleRows = if (c.showPointed) all else all.filterNot { it.optBoolean("pointee") }
    val visibleEntries = if (c.showPointed) entries else entries.filterNot { it.optBoolean("pointee") }
    Column(Modifier.fillMaxSize()) {
        Summary(c)
        Text("Cochez les relevés à gauche et choisissez l'écriture DiameX à droite. Le total doit être identique.")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 6.dp)) {
            Button(onClick = { c.point() }, enabled = !c.busy && c.pointMatches()) { Text("Pointer les relevés sur la ligne DiameX") }
            if (pointedCount > 0) OutlinedButton(onClick = { c.showPointed = !c.showPointed }) {
                Text(if (c.showPointed) "Masquer les éléments déjà pointés" else "Afficher les éléments déjà pointés ($pointedCount)")
            }
        }
        Row(Modifier.weight(1f).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                item { Text("RELEVÉS", style = MaterialTheme.typography.titleMedium) }
                items(visibleRows, key = { it.optString("id") }) { row ->
                    InvoiceCheck(c, row, !row.optBoolean("pointee") && "point" !in c.actions(row) && c.validated(row))
                }
                if (visibleRows.isEmpty()) item { Text("Aucun relevé à pointer") }
            }
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                item { Text("LIGNES DIAMEX", style = MaterialTheme.typography.titleMedium) }
                items(visibleEntries, key = { "d:" + it.optString("id") }) { entry ->
                    val pointed = entry.optBoolean("pointee")
                    val chosen = entry.optString("id") == c.selectedEntryId
                    Card(
                        Modifier.fillMaxWidth().clickable(enabled = !pointed) { c.selectedEntryId = entry.getString("id") },
                        colors = if (chosen) CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer) else CardDefaults.cardColors(),
                    ) {
                        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = chosen, onClick = { c.selectedEntryId = entry.getString("id") }, enabled = !pointed)
                            Column {
                                Text("${entry.optString("date")} · ${entry.optString("numero")} / ${entry.optString("base")}", style = MaterialTheme.typography.titleSmall)
                                Text(entry.optString("description"), style = MaterialTheme.typography.bodySmall)
                                Text("${entry.optString("montant")} Ar" + if (pointed) " · Déjà pointée" else "")
                            }
                        }
                    }
                }
                if (visibleEntries.isEmpty()) item { Text("Aucune ligne DiameX pour cette période") }
            }
        }
    }
}

@Composable
private fun Summary(c: VolumeController) {
    val invoices = c.selectedRows()
    val total = c.total(invoices)
    var text = "${invoices.size} facture(s) sélectionnée(s) · $total Ar"
    if (c.stage == VolumeStage.POINTING) {
        text += c.currentEntry()?.let { "\nDiameX : ${it.optString("montant")} Ar · Écart : ${total - c.amount(it)} Ar" }
            ?: "\nSélectionnez une ligne DiameX à droite"
    }
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 4.dp))
}

@Composable
private fun InvoiceCheck(c: VolumeController, row: JSONObject, enabled: Boolean) {
    val active = enabled && !c.conflicted(row)
    val checked = active && row.getString("id") in c.selected
    Card(Modifier.fillMaxWidth().clickable(enabled = active) { c.toggle(row, !checked) }) {
        Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = checked, onCheckedChange = { c.toggle(row, it) }, enabled = active)
            Column {
                Text("${row.optString("idxls")} · ${row.optString("abonne")}", style = MaterialTheme.typography.titleSmall)
                Text("${row.optString("numero")} · ${row.optString("montant")} Ar")
                Text(c.state(row), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

// ── Dialogues ──

@Composable
private fun CollectDialog(c: VolumeController) {
    val journals = c.journals().mapIndexed { i, j ->
        JSONObject().put("id", i.toString()).put("label", "${j.optString("code")} · ${j.optString("nom")}")
    }
    AlertDialog(
        onDismissRequest = { c.closeCollect() },
        title = { Text("Date et journal d'encaissement") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                RefDropdown("Journal", journals, c.collectJournal.toString()) { c.collectJournal = it.toInt() }
                DateField("Date d'encaissement", c.collectDate, { c.collectDate = it })
            }
        },
        confirmButton = { Button(onClick = { c.continueCollect() }) { Text("Continuer") } },
        dismissButton = { TextButton(onClick = { c.closeCollect() }) { Text("Annuler") } },
    )
}

@Composable
private fun RecapDialog(c: VolumeController, recap: JSONObject) {
    AlertDialog(
        onDismissRequest = { c.closeRecap() },
        title = { Text("Récapitulatif d'encaissement") },
        text = {
            Text("${recap.optString("ouvrage")} · ${recap.optString("mois")}\n" +
                "${recap.optJSONArray("factures")?.length() ?: 0} factures · ${recap.optString("total")} Ar\n" +
                "${recap.optString("date")} · ${recap.optString("journal")}\n${recap.optString("etat")}")
        },
        confirmButton = { Button(onClick = { c.printRecap() }) { Text("Imprimer A4 / PDF") } },
        dismissButton = { TextButton(onClick = { c.closeRecap() }) { Text("Fermer") } },
    )
}

@Composable
private fun HistoryDialog(c: VolumeController) {
    val detail = c.historyDetail
    if (detail == null) {
        val audits = c.history()
        AlertDialog(
            onDismissRequest = { c.closeHistory() },
            title = { Text("Historique local · 200 dernières opérations") },
            text = {
                LazyColumn(Modifier.heightIn(max = 460.dp).widthIn(min = 420.dp)) {
                    items(audits) { audit ->
                        val p = audit.getJSONObject("payload")
                        Text("${p.optString("action")} · ${audit.optString("etat")} · ${p.getJSONArray("factures").length()} facture(s)",
                            modifier = Modifier.fillMaxWidth().clickable { c.openDetail(audit) }.padding(vertical = 8.dp))
                        HorizontalDivider()
                    }
                }
            },
            confirmButton = { TextButton(onClick = { c.closeHistory() }) { Text("Fermer") } },
        )
    } else {
        val payload = detail.getJSONObject("payload")
        AlertDialog(
            onDismissRequest = { c.closeDetail() },
            title = { Text("Détail de l'opération") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text("${payload.optString("action")} · ${c.detailTotal(detail)} Ar\nRéférence : ${c.detailId(detail)}\n" +
                        "${detail.optString("erreur")}\n${detail.optString("note")}")
                }
            },
            confirmButton = {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (c.canReview(detail)) OutlinedButton(onClick = { c.openReview() }) { Text("Vérification manuelle") }
                    if (c.hasRecap(detail)) OutlinedButton(onClick = { c.reprintFromHistory(detail) }) { Text("Réimprimer le récap") }
                    TextButton(onClick = { c.closeDetail() }) { Text("Retour") }
                }
            },
        )
    }
}

@Composable
private fun ReviewDialog(c: VolumeController) {
    AlertDialog(
        onDismissRequest = { c.closeReview() },
        title = { Text("Clôturer cette opération refusée") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Vérifiez le paiement en comptabilité et traitez tout argent reçu avant de clôturer. " +
                    "La trace restera dans l'historique local. Cette action ne comptabilise ni ne rembourse un paiement.")
                OutlinedTextField(value = c.reviewNote, onValueChange = { c.reviewNote = it }, minLines = 2,
                    label = { Text("Résultat de la vérification et référence comptable") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = { Button(onClick = { c.submitReview() }) { Text("Clôturer après vérification") } },
        dismissButton = { TextButton(onClick = { c.closeReview() }) { Text("Annuler") } },
    )
}
