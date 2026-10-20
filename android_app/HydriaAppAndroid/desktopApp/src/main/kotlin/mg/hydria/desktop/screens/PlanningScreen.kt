package mg.hydria.desktop.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CloudUpload
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
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.auth.LoginForm
import mg.hydria.shared.planning.PlanningActivityKind
import org.json.JSONObject

@Composable
fun PlanningScreen(session: DesktopSession) {
    if (!session.isAuthenticated) {
        LoginForm(session, "Requise pour le planning.")
        return
    }
    val scope = rememberCoroutineScope()
    val controller = remember(session) { PlanningController(session) }
    LaunchedEffect(controller) { controller.loadFromCache() }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Planning", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
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
                Text("Nouveau planning")
            }
            Text("${controller.pendingSaveCount} en file", style = MaterialTheme.typography.labelLarge)
            Button(
                onClick = { scope.launch { controller.drainQueue() } },
                enabled = !controller.busy && controller.pendingSaveCount > 0,
            ) {
                Icon(Icons.Filled.CloudUpload, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Synchroniser la file")
            }
            if (controller.busy) CircularProgressIndicator(modifier = Modifier.width(18.dp), strokeWidth = 2.dp)
        }

        if (controller.editorOpen) PlanningEditorDialog(controller)

        controller.message?.let {
            Spacer(Modifier.padding(3.dp))
            Text(it, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.padding(4.dp))
        if (!controller.loaded) {
            Text("Aucun planning en cache. Synchronisez le perimetre.", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }
        if (controller.days.isEmpty()) {
            Text("Aucune activite planifiee. Creez-en une avec « Nouveau planning ».", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }

        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(controller.days, key = { it.dateKey }) { day ->
                DayCell(
                    weekday = controller.shortWeekdayLabel(day.dateKey),
                    number = controller.dayNumberLabel(day.dateKey),
                    count = day.items.size,
                    selected = day.dateKey == controller.selectedDate,
                    onClick = { controller.selectDate(day.dateKey) },
                )
            }
        }

        Spacer(Modifier.padding(6.dp))
        val day = controller.selectedDay
        if (day == null) {
            Text("Choisissez une date.", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }
        val indicator = controller.dayIndicator(day)
        Text(
            controller.weekdayLabel(day.dateKey) + " " + controller.fullDateLabel(day.dateKey) +
                if (indicator.isNotBlank()) "  ·  $indicator" else "",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary,
        )
        Text("${day.items.size} activite(s)", style = MaterialTheme.typography.labelLarge)

        Spacer(Modifier.padding(3.dp))
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(day.items) { planning -> PlanningCard(controller, planning) }
        }
    }
}

@Composable
private fun DayCell(weekday: String, number: String, count: Int, selected: Boolean, onClick: () -> Unit) {
    val bg = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant
    val fg = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant
    Column(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(bg)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(weekday, style = MaterialTheme.typography.labelSmall, color = fg)
        Text(number, style = MaterialTheme.typography.titleMedium, color = fg, fontFamily = FontFamily.Monospace)
        Spacer(Modifier.padding(1.dp))
        Spacer(
            Modifier.size(6.dp).clip(CircleShape)
                .background(if (count > 0) fg else Color.Transparent),
        )
    }
}

@Composable
private fun PlanningCard(controller: PlanningController, planning: JSONObject) {
    val validated = planning.optBoolean("valide")
    val kindLabel = when (controller.activityKind(planning)) {
        PlanningActivityKind.VALIDATED -> "Valide"
        PlanningActivityKind.REPAIR -> "Reparation"
        PlanningActivityKind.REST -> "Repos / conge"
        PlanningActivityKind.OTHER -> "Activite"
    }
    Card {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    planning.optString("fiche_poste").ifBlank { planning.optString("type_activite", "Activite") },
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.weight(1f),
                )
                AssistChip(onClick = {}, label = { Text(if (validated) "Valide" else "A realiser", style = MaterialTheme.typography.labelSmall) })
            }
            val context = listOf(
                planning.optString("type_activite"), planning.optString("ouvrage_nom"),
                planning.optString("commune"), planning.optString("district"), planning.optString("region"),
            ).filter { it.isNotBlank() }.joinToString(" · ")
            if (context.isNotBlank()) Text(context, style = MaterialTheme.typography.bodySmall)
            val people = listOf(planning.optString("employe"), planning.optString("participants"))
                .filter { it.isNotBlank() }.joinToString(" · ")
            if (people.isNotBlank()) Text("Equipe : $people", style = MaterialTheme.typography.bodySmall)
            planning.optString("remarque").takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall)
            }
            val counters = listOfNotNull(
                planning.optInt("nb_avances").takeIf { it > 0 }?.let { "$it avance(s)" },
                planning.optInt("nb_deplacements").takeIf { it > 0 }?.let { "$it deplacement(s)" },
                planning.optInt("nb_livraisons").takeIf { it > 0 }?.let { "$it livraison(s)" },
                planning.optInt("nb_paiements").takeIf { it > 0 }?.let { "$it paiement(s)" },
            ).joinToString(" · ")
            if (counters.isNotBlank()) Text(counters, style = MaterialTheme.typography.bodySmall)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    planning.optString("statut").ifBlank { if (validated) "Valide" else "A realiser" } + "  ·  $kindLabel",
                    style = MaterialTheme.typography.labelMedium,
                    color = if (validated) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.tertiary,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { controller.openEditor(planning) }) {
                    Icon(Icons.Filled.Edit, contentDescription = null, modifier = Modifier.width(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text("Modifier")
                }
            }
        }
    }
}

@Composable
private fun PlanningEditorDialog(controller: PlanningController) {
    AlertDialog(
        onDismissRequest = { controller.closeEditor() },
        title = { Text(if (controller.editingExisting) "Modifier le planning" else "Nouveau planning") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                RefDropdown("Employe responsable", controller.employees, controller.fEmployee) { controller.fEmployee = it }
                RefAutocomplete("Ouvrage (facultatif)", controller.works, controller.fWork) { controller.setWork(it) }
                ActivityCascadeFields(controller.activities, controller.fActivity) { controller.fActivity = it }
                TargetAndComponentsFields(controller.targets, controller.fTarget, controller::setTarget,
                    controller.targetComponents, controller.fComponents, controller::toggleComponent)
                DateField("Date", controller.fDate, { controller.fDate = it }, maxToday = false)
                RefDropdown("Statut", controller.statuses, controller.fStatus) { controller.fStatus = it }
                OutlinedTextField(
                    value = controller.fRemark,
                    onValueChange = { controller.fRemark = it },
                    label = { Text("Remarque") },
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { Button(onClick = { controller.savePlanningForm() }) { Text("Enregistrer dans la file") } },
        dismissButton = { TextButton(onClick = { controller.closeEditor() }) { Text("Annuler") } },
    )
}
