package mg.hydria.desktop.screens

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import org.json.JSONObject

/** Libellé d'un item de référence Hydria : `label` sinon `nom`. */
fun refLabel(o: JSONObject): String = o.optString("label").ifBlank { o.optString("nom", "?") }

/**
 * Liste déroulante sur une liste de références (`{id, label|nom}`), partagée par
 * les formulaires Réparations / Planning Desktop.
 */
@Composable
fun RefDropdown(
    label: String,
    options: List<JSONObject>,
    selectedId: String,
    onSelect: (String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    val current = options.firstOrNull { it.optString("id") == selectedId }?.let(::refLabel) ?: "Choisir..."
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium)
        Box {
            OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) { Text(current) }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                options.forEach { o ->
                    DropdownMenuItem(
                        text = { Text(refLabel(o)) },
                        onClick = { onSelect(o.optString("id")); open = false },
                    )
                }
            }
        }
    }
}
