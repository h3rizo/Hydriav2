package mg.hydria.desktop.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudDownload
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Restore
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.auth.LoginForm
import mg.hydria.desktop.storage.DesktopPrefs
import mg.hydria.shared.navigation.model.GeoCategory
import kotlin.math.roundToInt

@Composable
fun NavigationScreen(session: DesktopSession, prefs: DesktopPrefs) {
    if (!session.isAuthenticated) {
        LoginForm(session, "Requise pour la navigation terrain.")
        return
    }
    val scope = rememberCoroutineScope()
    val controller = remember(session) { NavigationController(session, prefs) }
    LaunchedEffect(controller) { controller.loadFromCache() }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Navigation terrain", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            Text(session.employeeName, style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { session.logout() }) {
                Icon(Icons.Filled.Logout, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Deconnexion")
            }
        }
        Text(
            "Version poste de travail : sans carte ni GPS. Consultation des points cartographiés " +
                "(distance / cap calculés si vous saisissez une position).",
            style = MaterialTheme.typography.bodySmall,
        )

        Spacer(Modifier.padding(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = { scope.launch { controller.syncMap() } }, enabled = !controller.busy) {
                Icon(Icons.Filled.CloudDownload, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("Telecharger le perimetre")
            }
            TextButton(onClick = { controller.resetCursor() }, enabled = !controller.busy) {
                Icon(Icons.Filled.Restore, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Reinitialiser le curseur")
            }
            if (controller.busy) CircularProgressIndicator(modifier = Modifier.width(18.dp), strokeWidth = 2.dp)
        }

        controller.message?.let {
            Spacer(Modifier.padding(3.dp))
            Text(it, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.padding(4.dp))
        if (!controller.loaded) {
            Text("Aucune entite en cache. Telechargez le perimetre.", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(
                selected = controller.category == null,
                onClick = { controller.category = null },
                label = { Text("Tous (${controller.entities.size})") },
            )
            GeoCategory.entries.forEach { cat ->
                FilterChip(
                    selected = controller.category == cat,
                    onClick = { controller.category = cat },
                    label = { Text("${cat.label} (${controller.countByCategory(cat)})") },
                )
            }
        }

        Spacer(Modifier.padding(4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = controller.query,
                onValueChange = { controller.query = it },
                label = { Text("Nom, code, type") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = controller.originLat,
                onValueChange = { controller.originLat = it.trim() },
                label = { Text("Ma latitude") },
                singleLine = true,
                modifier = Modifier.width(150.dp),
            )
            OutlinedTextField(
                value = controller.originLon,
                onValueChange = { controller.originLon = it.trim() },
                label = { Text("Ma longitude") },
                singleLine = true,
                modifier = Modifier.width(150.dp),
            )
        }

        Spacer(Modifier.padding(4.dp))
        val rows = controller.rows
        Text("${rows.size} entite(s)", style = MaterialTheme.typography.labelLarge)
        Spacer(Modifier.padding(3.dp))
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            items(rows) { row -> EntityRow(row) }
        }
    }
}

@Composable
private fun EntityRow(row: NavigationController.Row) {
    Card {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            AssistChip(onClick = {}, label = { Text(row.category.shortLabel) })
            Column(Modifier.weight(1f)) {
                Text(row.name, style = MaterialTheme.typography.titleSmall)
                val sub = listOf(row.typeLabel, row.code).filter { it.isNotBlank() }.joinToString(" · ")
                if (sub.isNotBlank()) Text(sub, style = MaterialTheme.typography.bodySmall)
                Text(
                    "%.5f, %.5f".format(row.latitude, row.longitude),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                )
            }
            if (row.distanceMeters != null && row.bearingDegrees != null) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(formatDistance(row.distanceMeters), style = MaterialTheme.typography.titleSmall, fontFamily = FontFamily.Monospace)
                    Text("cap ${row.bearingDegrees.roundToInt()}°", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

private fun formatDistance(meters: Double): String =
    if (meters >= 1000) "%.1f km".format(meters / 1000) else "${meters.roundToInt()} m"
