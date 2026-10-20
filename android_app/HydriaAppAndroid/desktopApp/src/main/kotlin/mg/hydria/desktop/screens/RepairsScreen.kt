package mg.hydria.desktop.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AddAPhoto
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Done
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.auth.LoginForm
import org.json.JSONObject
import java.awt.FileDialog
import java.io.File

@Composable
fun RepairsScreen(session: DesktopSession) {
    if (!session.isAuthenticated) {
        LoginForm(session, "Requise pour les reparations.")
        return
    }
    val scope = rememberCoroutineScope()
    val controller = remember(session) { RepairsController(session) }
    LaunchedEffect(controller) { controller.loadFromCache() }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Reparations", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
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
            OutlinedButton(onClick = { controller.openEditor(null) }, enabled = !controller.busy) {
                Icon(Icons.Filled.Add, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Nouvelle reparation")
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

        if (controller.editorOpen) RepairEditorDialog(controller)

        Spacer(Modifier.padding(2.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            ToggleRow("Terminees", controller.showCompleted) { controller.showCompleted = it }
            ToggleRow("Hors perimetre", controller.showOutside) { controller.showOutside = it }
        }

        controller.message?.let {
            Spacer(Modifier.padding(3.dp))
            Text(it, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.padding(4.dp))
        if (!controller.loaded) {
            Text(
                "Aucune reparation en cache. Synchronisez le perimetre.",
                style = MaterialTheme.typography.bodyMedium,
            )
            return@Column
        }

        val groups = controller.groups
        Text(
            "${groups.sumOf { it.repairs.size }} reparation(s) affichee(s) · ${groups.size} ouvrage(s)" +
                if (controller.showCompleted) " · ${controller.completedCount} terminee(s)" else "",
            style = MaterialTheme.typography.labelLarge,
        )
        Spacer(Modifier.padding(3.dp))
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            groups.forEach { group ->
                item(key = "h:${group.ouvrage}") {
                    Text(
                        group.ouvrage,
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                items(
                    count = group.repairs.size,
                    key = { idx -> "r:${group.ouvrage}:${group.repairs[idx].optString("id")}:$idx" },
                ) { idx ->
                    RepairCard(controller, group.repairs[idx])
                }
            }
        }
    }
}

@Composable
private fun RepairEditorDialog(controller: RepairsController) {
    AlertDialog(
        onDismissRequest = { controller.closeEditor() },
        title = { Text(if (controller.editingExisting) "Modifier la reparation" else "Nouvelle reparation") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                RefDropdown("Employe responsable", controller.employees, controller.fEmployee) { controller.fEmployee = it }
                RefAutocomplete("Ouvrage (obligatoire)", controller.works, controller.fWork) { controller.setWork(it) }
                ActivityCascadeFields(controller.activities, controller.fActivity, showGroup = false) { controller.fActivity = it }
                TargetAndComponentsFields(controller.targets, controller.fTarget, controller::setTarget,
                    controller.targetComponents, controller.fComponents, controller::toggleComponent)
                DateField("Date", controller.fDate, { controller.fDate = it }, maxToday = false)
                RefDropdown("Statut", controller.statuses, controller.fStatus) { controller.fStatus = it }
                RefDropdown("Priorite", controller.priorities, controller.fPriority) { controller.fPriority = it }
                OutlinedTextField(
                    value = controller.fRemark,
                    onValueChange = { controller.fRemark = it },
                    label = { Text("Remarque") },
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
                // La photo se joint a une reparation qui existe deja cote serveur
                // (route /reparation/<id>/photo/) : indisponible tant que "Nouvelle
                // reparation" n'a pas ete enregistree au moins une fois (pas encore d'id).
                OutlinedButton(
                    onClick = {
                        val id = controller.editingId ?: return@OutlinedButton
                        pickPhotoFile()?.let { controller.addPhoto(id, it) }
                    },
                    enabled = controller.editingExisting,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Filled.AddAPhoto, contentDescription = null, modifier = Modifier.width(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Ajouter une photo")
                }
                if (!controller.editingExisting) {
                    Text(
                        "Disponible apres le premier enregistrement de cette reparation.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = { Button(onClick = { controller.saveRepairForm() }) { Text("Enregistrer dans la file") } },
        dismissButton = { TextButton(onClick = { controller.closeEditor() }) { Text("Annuler") } },
    )
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Switch(checked = checked, onCheckedChange = onChange)
        Spacer(Modifier.width(6.dp))
        Text(label, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun RepairCard(controller: RepairsController, repair: JSONObject) {
    val completed = controller.isCompleted(repair)
    val outside = repair.optBoolean("hors_perimetre")
    // « 224 j » + RETARD, « AUJ. » ou « dans 5 j » : même libellé que l'app Android (calculé dans :shared).
    val overdue = controller.overdueLabel(repair)
    val late = !completed && overdue?.late == true

    Card {
        Row(modifier = Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.widthIn(min = 56.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    when {
                        completed -> "OK"
                        overdue == null -> "--"
                        else -> overdue.value
                    },
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    color = when {
                        completed -> MaterialTheme.colorScheme.primary
                        late -> MaterialTheme.colorScheme.error
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
                if (!completed && overdue != null && overdue.caption.isNotBlank()) {
                    Text(
                        overdue.caption,
                        style = MaterialTheme.typography.labelSmall,
                        color = if (late) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(controller.activityLabel(repair), style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    AssistChip(onClick = {}, label = { Text(controller.priorityLabel(repair), style = MaterialTheme.typography.labelSmall) })
                }
                val statut = repair.optString("statut", "En cours")
                val date = repair.optString("date_prevue_display").ifBlank { repair.optString("date_prevue") }
                Text("$statut · $date", style = MaterialTheme.typography.bodySmall)
                val team = listOf(repair.optString("assigne_a"), repair.optString("participants"))
                    .filter { it.isNotBlank() }.joinToString(" · ")
                if (team.isNotBlank()) Text("Equipe : $team", style = MaterialTheme.typography.bodySmall)

                Spacer(Modifier.padding(3.dp))
                when {
                    outside -> Text("Consultation uniquement (hors perimetre).", style = MaterialTheme.typography.bodySmall)
                    else -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (completed) {
                            Text("Terminee · part a la prochaine synchronisation.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                        } else {
                            Button(onClick = { controller.markDone(repair) }, enabled = !controller.busy) {
                                Icon(Icons.Filled.Done, contentDescription = null, modifier = Modifier.width(16.dp))
                                Spacer(Modifier.width(6.dp))
                                Text("Marquer terminee")
                            }
                        }
                        TextButton(onClick = { controller.openEditor(repair) }, enabled = !controller.busy) {
                            Icon(Icons.Filled.Edit, contentDescription = null, modifier = Modifier.width(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Modifier")
                        }
                        // Preuve avant/apres travaux : s'accumule cote serveur, jamais remplacee.
                        // Photo uniquement (jpg/png/webp, 5 Mo max) : le serveur n'accepte pas la video.
                        TextButton(
                            onClick = {
                                val id = repair.optString("id")
                                if (id.isBlank()) return@TextButton
                                pickPhotoFile()?.let { controller.addPhoto(id, it) }
                            },
                            enabled = !controller.busy,
                        ) {
                            Icon(Icons.Filled.AddAPhoto, contentDescription = null, modifier = Modifier.width(16.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("Ajouter une photo")
                        }
                    }
                }
            }
        }
    }
}

/** Boite de dialogue native (AWT) : la seule facon simple de choisir un fichier
 * existant sur le disque en Compose Desktop, sans dependance supplementaire.
 * Bloque le thread appelant (celui de l'UI Compose Desktop) jusqu'a la fermeture
 * de la boite, comme n'importe quelle appli Swing - comportement natif attendu. */
private fun pickPhotoFile(): File? {
    val dialog = FileDialog(null as java.awt.Frame?, "Choisir une photo", FileDialog.LOAD)
    dialog.setFilenameFilter { _, name ->
        name.substringAfterLast('.', "").lowercase() in setOf("jpg", "jpeg", "png", "webp")
    }
    dialog.isVisible = true
    val name = dialog.file ?: return null
    val dir = dialog.directory ?: return null
    return File(dir, name)
}
