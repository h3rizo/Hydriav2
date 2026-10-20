package mg.hydria.desktop.screens

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.PopupProperties
import mg.hydria.shared.rules.forms.ActivityCascadeTree
import mg.hydria.shared.rules.forms.AutocompleteMatch
import mg.hydria.shared.rules.forms.WorkTarget
import org.json.JSONObject

/**
 * Champ Ouvrage avec autocomplétion (même règle que l'app Android :
 * sans accents, n'importe où dans le nom, plusieurs mots). [selectedId] vide =
 * aucun choix ; toute saisie qui ne correspond plus au choix le vide.
 */
@Composable
fun RefAutocomplete(
    label: String,
    options: List<JSONObject>,
    selectedId: String,
    placeholder: String = "Rechercher un ouvrage…",
    onSelect: (String) -> Unit,
) {
    val labels = remember(options) { options.map(::refLabel) }
    val selectedLabel = options.indexOfFirst { it.optString("id") == selectedId }.takeIf { it >= 0 }?.let { labels[it] }.orEmpty()
    var text by remember { mutableStateOf(selectedLabel) }
    var open by remember { mutableStateOf(false) }
    // Choix fait par code (ouverture d'un formulaire existant) : afficher son libellé.
    LaunchedEffect(selectedId, options) { if (selectedId.isNotBlank()) text = selectedLabel }
    val matches = remember(text, labels) { AutocompleteMatch.filter(labels, if (text == selectedLabel) "" else text).take(60) }

    Column {
        Box {
            OutlinedTextField(
                value = text,
                onValueChange = { value ->
                    text = value
                    open = true
                    if (selectedId.isNotBlank() && value != selectedLabel) onSelect("")
                },
                label = { Text(label) },
                placeholder = { Text(placeholder) },
                singleLine = true,
                trailingIcon = { Text("▾") },
                modifier = Modifier.fillMaxWidth().onFocusChanged { if (it.isFocused) open = true },
            )
            DropdownMenu(
                expanded = open && matches.isNotEmpty(),
                onDismissRequest = { open = false },
                // Ne pas voler le focus : on continue de taper pendant que la liste est ouverte.
                properties = PopupProperties(focusable = false),
                modifier = Modifier.heightIn(max = 320.dp),
            ) {
                matches.forEach { index ->
                    DropdownMenuItem(
                        text = { Text(labels[index]) },
                        onClick = {
                            text = labels[index]
                            open = false
                            onSelect(options[index].optString("id"))
                        },
                    )
                }
            }
        }
        if (text.isNotBlank() && selectedId.isBlank() && !open) {
            Text("Choisissez un ouvrage dans la liste", color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall)
        }
    }
}

/**
 * Cascade Groupe > Type d'activité > Activité (même arbre que l'app Android).
 * [showGroup] = false : groupe masqué (réparations : « Opérations sur les ouvrages »).
 */
@Composable
fun ActivityCascadeFields(
    activities: List<JSONObject>,
    selectedId: String,
    showGroup: Boolean = true,
    onSelect: (String) -> Unit,
) {
    val tree = remember(activities, showGroup) {
        if (showGroup) ActivityCascadeTree.build(activities) else ActivityCascadeTree.buildWithoutGroups(activities)
    }
    val path = remember(tree, selectedId) { ActivityCascadeTree.pathOf(tree, selectedId) }
    var group by remember(tree) { mutableStateOf(path?.first ?: 0) }
    var type by remember(tree) { mutableStateOf(path?.second ?: 0) }
    LaunchedEffect(path) { path?.let { group = it.first; type = it.second } }

    fun options(names: List<String>) = names.mapIndexed { i, n -> JSONObject().put("id", i.toString()).put("label", n) }
    val types = tree.getOrNull(group)?.children.orEmpty()
    val acts = types.getOrNull(type)?.children.orEmpty()

    Column {
        if (showGroup) {
            RefDropdown("Groupe", options(tree.map { it.name }), group.toString()) {
                group = it.toInt(); type = 0; onSelect("")
            }
        }
        RefDropdown("Type d'activité", options(types.map { it.name }), type.toString()) {
            type = it.toInt(); onSelect("")
        }
        RefDropdown(
            "Activité",
            acts.map { JSONObject().put("id", it.activity?.optString("id").orEmpty()).put("label", it.name) },
            selectedId,
        ) { onSelect(it) }
    }
}

/** Cible (point d'eau / équipement de l'ouvrage) puis composants concernés, cochables. */
@Composable
fun TargetAndComponentsFields(
    targets: List<WorkTarget>,
    targetKey: String,
    onTarget: (String) -> Unit,
    components: List<JSONObject>,
    selectedComponents: Set<String>,
    onToggle: (String, Boolean) -> Unit,
) {
    val targetOptions = listOf(JSONObject().put("id", "").put("label", "Aucune cible précisée")) +
        targets.map { JSONObject().put("id", it.key).put("label", it.label) }
    Column {
        RefDropdown("Cible (point d'eau ou équipement)", targetOptions, targetKey) { onTarget(it) }
        Text("Composants concernés", style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(top = 6.dp))
        when {
            targets.isEmpty() -> Hint("Aucun point d'eau ni équipement connu pour cet ouvrage (synchronisez le périmètre).")
            targetKey.isBlank() -> Hint("Choisissez d'abord une cible (point d'eau ou équipement) ci-dessus.")
            components.isEmpty() -> Hint("Aucun composant défini pour ce type.")
            else -> components.forEach { c ->
                val id = c.optString("id")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = id in selectedComponents, onCheckedChange = { onToggle(id, it) })
                    Text(c.optString("nom"))
                }
            }
        }
    }
}

@Composable
private fun Hint(value: String) =
    Text(value, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

