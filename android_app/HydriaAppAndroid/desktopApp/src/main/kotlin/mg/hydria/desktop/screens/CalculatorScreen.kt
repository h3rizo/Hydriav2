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
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Card
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import mg.hydria.shared.calculator.CalculationLine
import mg.hydria.shared.calculator.CalculatorEngine
import mg.hydria.shared.calculator.ExpressionError

/**
 * Ecran pilote du portage Desktop : reutilise tel quel le moteur de calcul de
 * :shared ([CalculatorEngine]), qui vit deja en jvmCommonMain. Aucune logique
 * metier ici, uniquement l'UI Compose.
 */
@Composable
fun CalculatorScreen() {
    var lines by remember {
        mutableStateOf(CalculatorEngine.recalculate(listOf(CalculationLine())))
    }

    fun update(next: List<CalculationLine>) {
        lines = CalculatorEngine.recalculate(next.ifEmpty { listOf(CalculationLine()) })
    }

    Column(Modifier.fillMaxSize()) {
        Text("Calculatrice", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Reference d'une ligne precedente : L1, L2, ...  ·  virgule ou point pour les decimales",
            style = MaterialTheme.typography.bodySmall,
        )
        Spacer(Modifier.padding(6.dp))

        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            itemsIndexed(lines, key = { _, line -> line.localId }) { index, line ->
                CalculationRow(
                    number = index + 1,
                    line = line,
                    onLabel = { value ->
                        update(lines.toMutableList().also { it[index] = it[index].copy(label = value) })
                    },
                    onExpression = { value ->
                        update(lines.toMutableList().also { it[index] = it[index].copy(expression = value) })
                    },
                    onDelete = { update(lines.filterIndexed { i, _ -> i != index }) },
                    deletable = lines.size > 1,
                )
            }
        }

        Spacer(Modifier.padding(4.dp))
        OutlinedButton(onClick = { update(lines + CalculationLine()) }) {
            Icon(Icons.Filled.Add, contentDescription = null)
            Spacer(Modifier.width(6.dp))
            Text("Ajouter une ligne")
        }
    }
}

@Composable
private fun CalculationRow(
    number: Int,
    line: CalculationLine,
    onLabel: (String) -> Unit,
    onExpression: (String) -> Unit,
    onDelete: () -> Unit,
    deletable: Boolean,
) {
    Card {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("L$number", style = MaterialTheme.typography.labelLarge, fontFamily = FontFamily.Monospace)
            OutlinedTextField(
                value = line.label,
                onValueChange = onLabel,
                label = { Text("Libelle") },
                singleLine = true,
                modifier = Modifier.width(220.dp),
            )
            OutlinedTextField(
                value = line.expression,
                onValueChange = onExpression,
                label = { Text("Expression") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            Column(modifier = Modifier.width(200.dp), horizontalAlignment = Alignment.End) {
                val error = line.error
                if (error != null) {
                    Text(
                        errorMessage(error),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall,
                    )
                } else {
                    Text(
                        line.result?.toPlainString() ?: "-",
                        style = MaterialTheme.typography.titleMedium,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
            IconButton(onClick = onDelete, enabled = deletable) {
                Icon(Icons.Filled.Delete, contentDescription = "Supprimer la ligne")
            }
        }
    }
}

private fun errorMessage(error: ExpressionError): String = when (error) {
    ExpressionError.INVALID_REFERENCE -> "Reference de ligne invalide"
    ExpressionError.MISSING_LINE -> "Ligne referencee absente"
    ExpressionError.CURRENT_OR_FUTURE_REFERENCE -> "Reference a la ligne courante ou suivante"
    ExpressionError.LINE_HAS_ERROR -> "La ligne referencee est en erreur"
    ExpressionError.LINE_NO_RESULT -> "La ligne referencee n'a pas de resultat"
    ExpressionError.DIVISION_BY_ZERO -> "Division par zero"
    ExpressionError.NON_NUMERIC -> "Valeur non numerique"
    ExpressionError.INCOMPLETE_EXPRESSION -> "Expression incomplete"
    ExpressionError.MISSING_CLOSING_PARENTHESIS -> "Parenthese fermante manquante"
    ExpressionError.INVALID_NUMBER -> "Nombre invalide"
    ExpressionError.FORBIDDEN_CHARACTER -> "Caractere non autorise"
    ExpressionError.RESULT_TOO_LARGE -> "Resultat trop grand"
}
