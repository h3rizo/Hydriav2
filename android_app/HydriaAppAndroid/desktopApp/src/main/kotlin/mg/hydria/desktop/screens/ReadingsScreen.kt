package mg.hydria.desktop.screens

import mg.hydria.shared.rules.readings.ReadingPointListRules
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ElevatedCard
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.auth.LoginForm
import org.json.JSONObject

@Composable
fun ReadingsScreen(session: DesktopSession) {
    if (!session.isAuthenticated) {
        LoginForm(session, "Requise pour les releves.")
        return
    }
    val scope = rememberCoroutineScope()
    val controller = remember(session) { ReadingsController(session) }
    LaunchedEffect(controller) { controller.loadFromCache() }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Releves", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            Text(session.employeeName, style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { session.logout() }) {
                Icon(Icons.Filled.Logout, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Deconnexion")
            }
        }

        Spacer(Modifier.padding(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = { scope.launch { controller.syncPerimeter() } }, enabled = !controller.busy) {
                Icon(Icons.Filled.Sync, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Synchroniser le perimetre")
            }
            Text("${controller.pendingCount} en file", style = MaterialTheme.typography.labelLarge)
            Button(
                onClick = { scope.launch { controller.drainQueue() } },
                enabled = !controller.busy && controller.pendingCount > 0,
            ) {
                Icon(Icons.Filled.CloudUpload, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Synchroniser la file")
            }
            if (controller.busy) CircularProgressIndicator(modifier = Modifier.width(18.dp), strokeWidth = 2.dp)
        }

        controller.message?.let {
            Spacer(Modifier.padding(3.dp))
            Text(it, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.padding(4.dp))
        if (controller.ouvrages.isEmpty()) {
            Text(
                "Aucun ouvrage en cache. Synchronisez le perimetre pour demarrer une campagne.",
                style = MaterialTheme.typography.bodyMedium,
            )
            return@Column
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            OuvragePicker(controller)
            DateField(
                label = "Date de campagne",
                iso = controller.campaignDate,
                onChange = { controller.changeCampaignDate(it) },
                modifier = Modifier.width(200.dp),
            )
        }

        Spacer(Modifier.padding(6.dp))
        OutlinedTextField(
            value = controller.pointSearch,
            onValueChange = { controller.pointSearch = it },
            label = { Text("Rechercher un point (nom ou idxls)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        if (controller.showParcelFilter) {
            Spacer(Modifier.padding(2.dp))
            ParcelPicker(controller)
        }
        Spacer(Modifier.padding(4.dp))
        Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            LazyColumn(
                modifier = Modifier.weight(1f).fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                items(controller.visiblePoints) { point ->
                    PointRow(
                        point = point,
                        title = controller.pointLabel(point),
                        selected = controller.selectedPoint?.optString("id") == point.optString("id"),
                        pending = controller.hasPendingReading(point),
                        draft = controller.hasDraft(point),
                        onClick = { controller.selectPoint(point) },
                    )
                }
                if (controller.visiblePoints.isEmpty()) {
                    item {
                        Text(
                            if (controller.points.isNotEmpty()) "Aucun point ne correspond a la recherche."
                            else "Aucun point a relever pour cet ouvrage.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
            Box(Modifier.weight(1f).fillMaxSize()) {
                val point = controller.selectedPoint
                if (point == null) {
                    Text("Choisissez un point d'eau a gauche.", style = MaterialTheme.typography.bodyMedium)
                } else {
                    // Un formulaire neuf par point : défilement remis en haut, focus sur « Nouvel index ».
                    key(point.optString("id")) { EntryForm(controller, point) }
                }
            }
        }
    }
}

@Composable
private fun OuvragePicker(controller: ReadingsController) {
    var expanded by remember { mutableStateOf(false) }
    val label = controller.selectedOuvrage?.optString("nom")?.takeIf { it.isNotBlank() } ?: "Choisir un ouvrage"
    Box {
        OutlinedButton(onClick = { expanded = true }) { Text(label) }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            controller.ouvrages.forEach { ouvrage ->
                DropdownMenuItem(
                    text = { Text(ouvrage.optString("nom", "Ouvrage")) },
                    onClick = {
                        controller.selectOuvrage(ouvrage.optString("id"))
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun ParcelPicker(controller: ReadingsController) {
    var expanded by remember { mutableStateOf(false) }
    val parcels = controller.parcels
    val current = parcels.firstOrNull { it.id == controller.parcelId }
    val label = current?.let { "Parcelle : ${it.label} (${it.count})" } ?: "Parcelle : toutes (${controller.points.size})"
    Box {
        OutlinedButton(onClick = { expanded = true }) { Text(label) }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(
                text = { Text("Toutes les parcelles (${controller.points.size})") },
                onClick = { controller.parcelId = ReadingPointListRules.ALL_PARCELS; expanded = false },
            )
            parcels.forEach { parcel ->
                DropdownMenuItem(
                    text = { Text("${parcel.label} (${parcel.count})") },
                    onClick = { controller.parcelId = parcel.id; expanded = false },
                )
            }
        }
    }
}

@Composable
private fun PointRow(point: JSONObject, title: String, selected: Boolean, pending: Boolean, draft: Boolean, onClick: () -> Unit) {
    val last = point.optJSONObject("dernier_releve")?.optDouble("nouvel_index", 0.0) ?: 0.0
    Card(onClick = onClick) {
        Column(Modifier.fillMaxWidth().padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    title,
                    style = MaterialTheme.typography.titleSmall,
                    color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.weight(1f),
                )
                if (draft) AssistChip(onClick = onClick, label = { Text("brouillon", style = MaterialTheme.typography.labelSmall) })
                if (pending) AssistChip(onClick = onClick, label = { Text("a corriger", style = MaterialTheme.typography.labelSmall) })
            }
            val lastDate = formatReleveDate(point.optJSONObject("dernier_releve")?.optString("date_releve"))
            Text(
                "Dernier index : $last" + if (lastDate.isNotEmpty()) " (le $lastDate)" else "",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun EntryForm(controller: ReadingsController, point: JSONObject) {
    val focusRequester = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    // Le formulaire s'ouvre avec le curseur dans « Nouvel index » : on tape le chiffre sans cliquer.
    LaunchedEffect(Unit) { runCatching { focusRequester.requestFocus() } }

    ElevatedCard(Modifier.fillMaxSize()) {
        // Les champs défilent ; le bouton d'enregistrement reste en bas de la carte, toujours visible.
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(point.optString("nom", point.optString("code", "Point")), style = MaterialTheme.typography.titleMedium)
            Text(
                "Dernier index : ${controller.oldIndex}" +
                    if (controller.oldIndexDate.isNotEmpty()) " (le ${controller.oldIndexDate})" else "",
                style = MaterialTheme.typography.bodySmall,
            )
            if (controller.correcting) {
                Text(
                    "Ce releve est deja en file. L'enregistrer remplacera l'entree existante.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.tertiary,
                )
            }
            if (controller.draftRestored) {
                Text(
                    "Brouillon repris : la saisie non enregistree de ce point a ete retrouvee.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.tertiary,
                )
            }

            OutlinedTextField(
                value = controller.newIndexInput,
                onValueChange = { controller.newIndexInput = it },
                label = { Text("Nouvel index (m3)") },
                singleLine = true,
                // Entrée sur l'index ne fait que valider la saisie (le champ perd le curseur) : elle n'enregistre
                // JAMAIS (décision 5 ter n°1). L'enregistrement reste un geste volontaire sur le bouton.
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
                modifier = Modifier.fillMaxWidth().focusRequester(focusRequester),
            )
            OutlinedTextField(
                value = controller.nonBilledInput,
                onValueChange = { controller.nonBilledInput = it },
                label = { Text("Volume non facture (m3)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            val remarkErrorText = controller.remarkErrorText
            OutlinedTextField(
                value = controller.remark,
                onValueChange = { controller.remark = it },
                label = { Text(if (controller.remarkRequired) "Remarque (obligatoire)" else "Remarque (optionnelle)") },
                isError = remarkErrorText != null,
                supportingText = if (remarkErrorText != null) { { Text(remarkErrorText) } } else null,
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            if (controller.isKiosque) SocialCardsSection(controller)

            val consumption = controller.consumption
            val billed = controller.billedVolume
            if (consumption != null && billed != null) {
                Text(
                    buildString {
                        append("Consommation : ${"%+.2f".format(consumption)} m3")
                        if (controller.socialVolume > 0) append("   -   cartes ${"%.2f".format(controller.socialVolume)} m3")
                        append("   =   facture ${"%.2f".format(billed)} m3")
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    fontFamily = FontFamily.Monospace,
                )
            }
        }

        Button(
            onClick = { controller.save() },
            enabled = !controller.busy && controller.validationError == null,
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 16.dp),
        ) {
            Text(if (controller.correcting) "Corriger le releve · point suivant" else "Enregistrer · point suivant")
        }
    }
}

@Composable
private fun SocialCardsSection(controller: ReadingsController) {
    var pickerOpen by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Cartes sociales (bidons 20 L)", style = MaterialTheme.typography.titleSmall)
        if (controller.socialCards.isEmpty()) {
            Text(
                "Aucune carte ajoutee. Choisissez une carte rattachee a ce point, puis le nombre de bidons.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
        controller.socialCards.forEach { card ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(card.beneficiaire.ifBlank { "Carte" }, style = MaterialTheme.typography.bodyMedium)
                    if (card.numero.isNotBlank()) Text(card.numero, style = MaterialTheme.typography.bodySmall)
                }
                OutlinedTextField(
                    value = if (card.bidons > 0) card.bidons.toString() else "",
                    onValueChange = { controller.setSocialBidons(card.id, it.filter { c -> c.isDigit() }.take(2).toIntOrNull() ?: 0) },
                    label = { Text("Bidons") },
                    singleLine = true,
                    modifier = Modifier.width(110.dp),
                )
                IconButton(onClick = { controller.removeSocialCard(card.id) }) {
                    Icon(Icons.Filled.Delete, contentDescription = "Retirer la carte")
                }
            }
        }
        val available = controller.availableSocialCards
        Box {
            OutlinedButton(onClick = { pickerOpen = true }, enabled = available.isNotEmpty()) {
                Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (available.isEmpty()) "Aucune carte disponible" else "Ajouter une carte")
            }
            DropdownMenu(expanded = pickerOpen, onDismissRequest = { pickerOpen = false }) {
                available.forEach { c ->
                    DropdownMenuItem(
                        text = { Text("${c.optString("numero_carte")} · ${c.optString("beneficiaire")}") },
                        onClick = { controller.addSocialCard(c); pickerOpen = false },
                    )
                }
            }
        }
    }
}
