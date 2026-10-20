package mg.hydria.desktop.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Logout
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import mg.hydria.desktop.auth.DesktopSession
import mg.hydria.desktop.auth.LoginForm
import org.json.JSONObject

@Composable
fun SearchScreen(session: DesktopSession) {
    if (!session.isAuthenticated) {
        LoginForm(session, "Requise pour la recherche. La calculatrice reste accessible sans connexion.")
    } else {
        SearchContent(session)
    }
}

private fun pairsToOptions(pairs: List<Pair<String, String>>): List<JSONObject> =
    pairs.map { JSONObject().put("id", it.first).put("label", it.second) }

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SearchContent(session: DesktopSession) {
    val scope = rememberCoroutineScope()
    val controller = remember(session) { SearchController(session) }

    fun run() = scope.launch { controller.run() }

    LaunchedEffect(controller.section) {
        if (controller.section == SearchSection.WORKS) controller.loadWorkFilters()
    }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Recherche", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            Text(session.employeeName, style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { session.logout() }) {
                Icon(Icons.Filled.Logout, contentDescription = null, modifier = Modifier.width(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Deconnexion")
            }
        }

        Spacer(Modifier.padding(4.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SearchSection.entries.forEach { s ->
                FilterChip(
                    selected = controller.section == s,
                    onClick = { controller.section = s; run() },
                    label = { Text(s.label) },
                )
            }
        }

        Spacer(Modifier.padding(4.dp))
        OutlinedTextField(
            value = controller.query,
            onValueChange = { controller.query = it },
            label = { Text("Nom, code, abonne...") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            trailingIcon = {
                IconButton(onClick = { run() }) { Icon(Icons.Filled.Search, contentDescription = "Rechercher") }
            },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { run() }),
        )

        Spacer(Modifier.padding(4.dp))
        when (controller.section) {
            SearchSection.ALL -> CategoryFilters(controller, ::run)
            SearchSection.PEOPLE -> PeopleFilters(controller, ::run)
            SearchSection.WORKS -> WorkFilters(controller, ::run)
        }

        Spacer(Modifier.padding(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (controller.loading) CircularProgressIndicator(modifier = Modifier.width(18.dp), strokeWidth = 2.dp)
            if (controller.total > 0) {
                Text(
                    "${controller.total} resultat${if (controller.total > 1) "s" else ""}",
                    style = MaterialTheme.typography.labelLarge,
                )
            }
            if (controller.offlineCopy) {
                AssistChip(onClick = {}, label = { Text("Copie hors ligne") })
            }
        }

        controller.message?.let {
            Spacer(Modifier.padding(4.dp))
            Text(it, style = MaterialTheme.typography.bodyMedium)
        }

        Spacer(Modifier.padding(4.dp))
        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(controller.results) { item -> ResultCard(item) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CategoryFilters(controller: SearchController, run: () -> Unit) {
    Column {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Categories", style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
            TextButton(onClick = { controller.selectAllTypes(); run() }) { Text("Tout") }
            TextButton(onClick = { controller.clearTypes(); run() }) { Text("Rien") }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            SearchController.ALL_TYPES.forEach { (id, label) ->
                FilterChip(
                    selected = id in controller.selectedTypes,
                    onClick = { controller.toggleType(id); run() },
                    label = { Text(label, style = MaterialTheme.typography.labelSmall) },
                )
            }
        }
    }
}

@Composable
private fun PeopleFilters(controller: SearchController, run: () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
        Box(Modifier.weight(1f)) {
            RefDropdown("Type", pairsToOptions(SearchController.PEOPLE_TYPES), controller.peopleType) {
                controller.peopleType = it; run()
            }
        }
        Box(Modifier.weight(1f)) {
            RefDropdown("Statut", pairsToOptions(SearchController.PEOPLE_STATUSES), controller.peopleStatus) {
                controller.peopleStatus = it; run()
            }
        }
    }
}

@Composable
private fun WorkFilters(controller: SearchController, run: () -> Unit) {
    Column {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
            Box(Modifier.weight(1f)) {
                RefDropdown("Region", controller.workOptions("regions"), controller.workRegion) {
                    controller.workRegion = it; run()
                }
            }
            Box(Modifier.weight(1f)) {
                RefDropdown("District", controller.workOptions("districts"), controller.workDistrict) {
                    controller.workDistrict = it; run()
                }
            }
        }
        Spacer(Modifier.padding(3.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
            Box(Modifier.weight(1f)) {
                RefDropdown("Commune", controller.workOptions("communes"), controller.workCommune) {
                    controller.workCommune = it; run()
                }
            }
            Box(Modifier.weight(1f)) {
                RefDropdown("Employe responsable", controller.workOptions("employees"), controller.workEmployee) {
                    controller.workEmployee = it; run()
                }
            }
        }
        Row {
            Spacer(Modifier.weight(1f))
            TextButton(onClick = { controller.resetWorkFilters(); run() }) { Text("Reinitialiser les filtres") }
        }
    }
}

@Composable
private fun ResultCard(item: JSONObject) {
    val title = item.optString("title").ifBlank { item.optString("nom").ifBlank { item.optString("name", "Sans nom") } }
    val subtitle = item.optString("subtitle").ifBlank { item.optString("sous_titre") }
    val type = item.optString("type_display").ifBlank { item.optString("type") }
    val contact = item.optString("contact").takeIf { it.isNotBlank() && it != "-" }

    Card {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (type.isNotBlank()) {
                Box(Modifier.width(84.dp)) {
                    AssistChip(onClick = {}, label = { Text(type, style = MaterialTheme.typography.labelSmall) })
                }
            }
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium)
                if (subtitle.isNotBlank()) {
                    Text(subtitle, style = MaterialTheme.typography.bodySmall)
                }
                if (contact != null) {
                    Text(contact, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
                }
            }
        }
    }
}
