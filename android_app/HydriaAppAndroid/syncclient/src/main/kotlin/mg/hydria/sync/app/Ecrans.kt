package mg.hydria.sync.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.format.DateTimeFormatter
import javax.swing.JFileChooser

private val VERT = Color(0xFF2E7D32)
private val ORANGE = Color(0xFFE65100)
private val ROUGE = Color(0xFFC62828)

val ThemeHydria = lightColorScheme(
    primary = Color(0xFF0B6FA4),
    onPrimary = Color.White,
    secondary = Color(0xFF3A7CA5),
    background = Color(0xFFF6F9FB),
    surface = Color.White,
    surfaceVariant = Color(0xFFE6EEF3),
    error = ROUGE,
)

@Composable
fun HydriaSyncApp(controller: SyncController) {
    val etat by controller.etat.collectAsState()
    // Des qu'on est connecte, la synchronisation automatique demarre (une premiere passe immediate).
    LaunchedEffect(etat.connecte) {
        if (etat.connecte && !etat.auto) controller.basculerAuto(true)
    }
    MaterialTheme(colorScheme = ThemeHydria) {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            if (etat.connecte) EcranPrincipal(etat, controller)
            else EcranConnexion(etat, controller)
        }
    }
}

// ====================================================================== connexion

@Composable
fun EcranConnexion(etat: EtatUi, controller: SyncController, memorisee: mg.hydria.sync.core.Config? = controller.configEnregistree()) {
    var url by remember { mutableStateOf(memorisee?.baseUrl ?: "https://www.hydria.mg") }
    var dossier by remember { mutableStateOf(memorisee?.root ?: (System.getProperty("user.home") + "\\Hydria")) }
    var utilisateur by remember { mutableStateOf(memorisee?.username ?: "") }
    var motDePasse by remember { mutableStateOf("") }
    var organisation by remember { mutableStateOf(memorisee?.organisation ?: "") }
    var avance by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Card(Modifier.width(520.dp), elevation = CardDefaults.cardElevation(4.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
            Column(Modifier.padding(28.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Hydria Sync", style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
                Text("Retrouvez les fichiers d'Hydria sur votre PC, et envoyez-y les vôtres.", style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(4.dp))
                OutlinedTextField(url, { url = it }, label = { Text("Serveur") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(dossier, { dossier = it }, label = { Text("Dossier de synchronisation") }, singleLine = true, modifier = Modifier.weight(1f))
                    OutlinedButton(onClick = { choisirDossier(dossier)?.let { dossier = it } }) { Text("Parcourir…") }
                }
                OutlinedTextField(utilisateur, { utilisateur = it }, label = { Text("Identifiant") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(
                    motDePasse, { motDePasse = it }, label = { Text("Mot de passe") }, singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    modifier = Modifier.fillMaxWidth(),
                )
                TextButton(onClick = { avance = !avance }) { Text(if (avance) "Masquer les options avancées" else "Options avancées") }
                if (avance) {
                    OutlinedTextField(
                        organisation, { organisation = it }, label = { Text("Organisation (identifiant, facultatif)") },
                        supportingText = { Text("Seulement si votre compte n'est rattaché à aucune organisation.") },
                        singleLine = true, modifier = Modifier.fillMaxWidth(),
                    )
                }
                etat.message?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
                Text(
                    "La première synchronisation télécharge dans ce dossier les fichiers auxquels votre compte a accès.",
                    style = MaterialTheme.typography.bodySmall, color = Color.Gray,
                )
                Button(
                    onClick = { controller.seConnecter(url, dossier, utilisateur, motDePasse, organisation) },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Se connecter") }
            }
        }
    }
}

private fun choisirDossier(actuel: String): String? {
    val selecteur = JFileChooser(actuel.takeIf { java.io.File(it).isDirectory } ?: System.getProperty("user.home"))
    selecteur.fileSelectionMode = JFileChooser.DIRECTORIES_ONLY
    selecteur.dialogTitle = "Dossier de synchronisation Hydria"
    return if (selecteur.showOpenDialog(null) == JFileChooser.APPROVE_OPTION) selecteur.selectedFile.absolutePath else null
}

// ====================================================================== ecran principal

@Composable
fun EcranPrincipal(etat: EtatUi, controller: SyncController) {
    var onglet by remember { mutableStateOf(0) }
    val config = etat.config ?: return
    val aVerifier = etat.erreurs.size + etat.ignores.size

    Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Hydria Sync", style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.primary)
                Text("${config.username} · ${config.baseUrl}", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                Text(config.root, style = MaterialTheme.typography.bodySmall, color = Color.Gray)
            }
            OutlinedButton(onClick = { controller.ouvrirDossier() }) {
                Icon(Icons.Default.FolderOpen, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Ouvrir le dossier")
            }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(onClick = { controller.deconnecter() }) {
                Icon(Icons.AutoMirrored.Filled.Logout, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Se déconnecter")
            }
        }

        etat.message?.let { Bandeau(it, onFermer = controller::effacerMessage) }

        CarteEtat(etat, onSynchroniser = controller::synchroniser)

        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Switch(checked = etat.auto, onCheckedChange = controller::basculerAuto)
            Text("Synchronisation automatique, toutes les")
            listOf(1, 5, 15, 30).forEach { minutes ->
                FilterChip(
                    selected = etat.intervalleMinutes == minutes, onClick = { controller.choisirIntervalle(minutes) },
                    label = { Text("$minutes min") },
                )
            }
        }

        TabRow(selectedTabIndex = onglet) {
            Tab(selected = onglet == 0, onClick = { onglet = 0 }, text = { Text("Conflits (${etat.conflits.size})") })
            Tab(selected = onglet == 1, onClick = { onglet = 1 }, text = { Text("À vérifier ($aVerifier)") })
            Tab(selected = onglet == 2, onClick = { onglet = 2 }, text = { Text("Journal") })
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when (onglet) {
                0 -> ListeConflits(etat.conflits, controller)
                1 -> ListeAVerifier(etat)
                else -> Journal(etat.journal)
            }
        }
    }
}

@Composable
private fun Bandeau(texte: String, onFermer: () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Color(0xFFFDECEA)), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 14.dp, top = 4.dp, bottom = 4.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Error, null, tint = ROUGE)
            Spacer(Modifier.width(10.dp))
            Text(texte, Modifier.weight(1f), color = ROUGE)
            IconButton(onClick = onFermer) { Icon(Icons.Default.Close, "Fermer") }
        }
    }
}

/** Titre et couleur de l'etat de synchronisation, selon ce qui s'est passe. */
internal fun titreEtat(etat: EtatUi): Pair<String, Color> = when {
    etat.enCours -> "Synchronisation en cours…" to MaterialTheme_primaire
    etat.derniereSynchro == null -> "Pas encore synchronisé" to Color.Gray
    etat.conflits.isNotEmpty() -> "${etat.conflits.size} conflit(s) à résoudre" to ORANGE
    etat.erreurs.isNotEmpty() -> "Terminée avec ${etat.erreurs.size} erreur(s)" to ROUGE
    else -> "À jour" to VERT
}

private val MaterialTheme_primaire = Color(0xFF0B6FA4)
private val HEURE = DateTimeFormatter.ofPattern("HH:mm:ss")

@Composable
private fun CarteEtat(etat: EtatUi, onSynchroniser: () -> Unit) {
    val (titre, couleur) = titreEtat(etat)
    Card(Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(2.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            when {
                etat.enCours -> CircularProgressIndicator(Modifier.size(32.dp), strokeWidth = 3.dp)
                couleur == VERT -> Icon(Icons.Default.CheckCircle, null, tint = couleur, modifier = Modifier.size(32.dp))
                else -> Icon(if (couleur == ROUGE) Icons.Default.Error else Icons.Default.Warning, null, tint = couleur, modifier = Modifier.size(32.dp))
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(titre, style = MaterialTheme.typography.titleMedium, color = couleur)
                Text(
                    etat.derniereSynchro?.let { "Dernière synchronisation : ${it.format(HEURE)}" } ?: "Aucune synchronisation terminée",
                    style = MaterialTheme.typography.bodySmall, color = Color.Gray,
                )
                etat.resume?.let {
                    Text(
                        "↓ ${it.telecharges} téléchargé(s)   ↑ ${it.envoyes} envoyé(s)   ⟳ ${it.misAJour} mis à jour   🗑 ${it.corbeille} en corbeille",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            Button(onClick = onSynchroniser, enabled = !etat.enCours) {
                Icon(Icons.Default.Sync, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Synchroniser maintenant")
            }
        }
    }
}

// ====================================================================== onglets

@Composable
private fun Vide(texte: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(texte, color = Color.Gray) }
}

@Composable
fun ListeConflits(conflits: List<ConflitUi>, controller: SyncController) {
    if (conflits.isEmpty()) {
        Vide("Aucun conflit. Tout est synchronisé.")
        return
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items(conflits, key = { it.id }) { conflit ->
            Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF4E5))) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(conflit.relPath.substringAfterLast('/'), style = MaterialTheme.typography.titleSmall)
                    Text(conflit.relPath.substringBeforeLast('/', ""), style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                    Text(
                        "Ce fichier a été modifié ici ET sur le serveur. Votre version est conservée ; celle du serveur est enregistrée à côté" +
                            (conflit.copie?.let { " (« ${it.substringAfterLast('/')} »)" } ?: "") + ".",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { controller.garderMaVersion(conflit.id) }) { Text("Garder ma version") }
                        OutlinedButton(onClick = { controller.prendreVersionServeur(conflit.id) }) { Text("Prendre celle du serveur") }
                        TextButton(onClick = { controller.ouvrirDossier(conflit.relPath) }) { Text("Voir dans le dossier") }
                    }
                }
            }
        }
    }
}

@Composable
fun ListeAVerifier(etat: EtatUi) {
    if (etat.erreurs.isEmpty() && etat.ignores.isEmpty()) {
        Vide("Rien à vérifier.")
        return
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items(etat.erreurs) { Text("✖ $it", color = ROUGE, style = MaterialTheme.typography.bodyMedium) }
        items(etat.ignores) { Text("• $it", color = Color.DarkGray, style = MaterialTheme.typography.bodyMedium) }
    }
}

@Composable
fun Journal(lignes: List<String>) {
    if (lignes.isEmpty()) {
        Vide("Le journal est vide.")
        return
    }
    SelectionContainer {
        LazyColumn(Modifier.fillMaxSize().background(Color.White)) {
            items(lignes.asReversed()) { Text(it, fontFamily = FontFamily.Monospace, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)) }
        }
    }
}
