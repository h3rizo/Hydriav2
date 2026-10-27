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
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.LightMode
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
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.ui.text.style.TextOverflow
import mg.hydria.sync.core.Phase
import mg.hydria.sync.core.Progression
import mg.hydria.sync.core.formaterDuree
import mg.hydria.sync.core.formaterOctets
import mg.hydria.sync.core.libelle
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
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
    onSurfaceVariant = Color(0xFF5F6B73),
    error = ROUGE,
    errorContainer = Color(0xFFFDECEA),
    onErrorContainer = ROUGE,
    tertiaryContainer = Color(0xFFFFF4E5),
    onTertiaryContainer = Color(0xFF3E2A00),
)

val ThemeHydriaSombre = darkColorScheme(
    primary = Color(0xFF63B3E4),
    onPrimary = Color(0xFF00334D),
    secondary = Color(0xFF8FBBD6),
    background = Color(0xFF10181E),
    surface = Color(0xFF18222A),
    surfaceVariant = Color(0xFF24323C),
    onSurfaceVariant = Color(0xFFA9B7C0),
    error = Color(0xFFEF9A9A),
    errorContainer = Color(0xFF3B1F1F),
    onErrorContainer = Color(0xFFFFB4AB),
    tertiaryContainer = Color(0xFF3A2A12),
    onTertiaryContainer = Color(0xFFFFE0B2),
)

/** Reglages de la fenetre que le controleur de synchronisation ne connait pas (theme, demarrage avec Windows). */
data class OptionsUi(
    val sombre: Boolean = false,
    val onBasculerTheme: () -> Unit = {},
    /** `null` : indisponible (lancement hors de l'application installee). */
    val demarrageWindows: Boolean? = null,
    val onDemarrageWindows: (Boolean) -> Unit = {},
)

/** Vrai quand le theme sombre est actif : sert a eclaircir les couleurs d'etat (vert, orange, rouge). */
internal val LocalSombre = compositionLocalOf { false }

@Composable
private fun couleurEtat(couleur: Color): Color {
    if (!LocalSombre.current) return if (couleur == Color.Gray) MaterialTheme.colorScheme.onSurfaceVariant else couleur
    return when (couleur) {
        VERT -> Color(0xFF66BB6A)
        ORANGE -> Color(0xFFFFB74D)
        ROUGE -> Color(0xFFEF9A9A)
        MaterialTheme_primaire -> Color(0xFF63B3E4)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
}

@Composable
fun HydriaSyncApp(controller: SyncController, options: OptionsUi = OptionsUi()) {
    val etat by controller.etat.collectAsState()
    // Des qu'on est connecte, la synchronisation automatique demarre (une premiere passe immediate).
    LaunchedEffect(etat.connecte) {
        if (etat.connecte && !etat.auto) controller.basculerAuto(true)
    }
    CompositionLocalProvider(LocalSombre provides options.sombre) {
        MaterialTheme(colorScheme = if (options.sombre) ThemeHydriaSombre else ThemeHydria) {
            Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                if (etat.connecte) EcranPrincipal(etat, controller, options)
                else Box(Modifier.fillMaxSize()) {
                    EcranConnexion(etat, controller)
                    BoutonTheme(options, Modifier.align(Alignment.TopEnd).padding(12.dp))
                }
            }
        }
    }
}

@Composable
private fun BoutonTheme(options: OptionsUi, modifier: Modifier = Modifier) {
    IconButton(onClick = options.onBasculerTheme, modifier = modifier) {
        Icon(
            if (options.sombre) Icons.Default.LightMode else Icons.Default.DarkMode,
            contentDescription = if (options.sombre) "Passer en mode clair" else "Passer en mode sombre",
        )
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
        Card(Modifier.width(520.dp), elevation = CardDefaults.cardElevation(4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
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
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
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
fun EcranPrincipal(etat: EtatUi, controller: SyncController, options: OptionsUi = OptionsUi()) {
    var onglet by remember { mutableStateOf(0) }
    val config = etat.config ?: return
    val aVerifier = etat.erreurs.size + etat.ignores.size

    Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Hydria Sync", style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.primary)
                Text("${config.username} · ${config.baseUrl}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(config.root, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            BoutonTheme(options)
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
        options.demarrageWindows?.let { actif ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Switch(checked = actif, onCheckedChange = options.onDemarrageWindows)
                Text("Démarrer Hydria Sync avec Windows (réduit dans la zone de notification)")
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
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(start = 14.dp, top = 4.dp, bottom = 4.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Error, null, tint = MaterialTheme.colorScheme.onErrorContainer)
            Spacer(Modifier.width(10.dp))
            Text(texte, Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer)
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
    val (titre, couleurBrute) = titreEtat(etat)
    val couleur = couleurEtat(couleurBrute)
    Card(Modifier.fillMaxWidth(), elevation = CardDefaults.cardElevation(2.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            when {
                etat.enCours -> CircularProgressIndicator(Modifier.size(32.dp), strokeWidth = 3.dp)
                couleurBrute == VERT -> Icon(Icons.Default.CheckCircle, null, tint = couleur, modifier = Modifier.size(32.dp))
                else -> Icon(if (couleurBrute == ROUGE) Icons.Default.Error else Icons.Default.Warning, null, tint = couleur, modifier = Modifier.size(32.dp))
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(titre, style = MaterialTheme.typography.titleMedium, color = couleur)
                Text(
                    etat.derniereSynchro?.let { "Dernière synchronisation : ${it.format(HEURE)}" } ?: "Aucune synchronisation terminée",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                etat.resume?.let {
                    Text(
                        "↓ ${it.telecharges} téléchargé(s)   ↑ ${it.envoyes} envoyé(s)   ⟳ ${it.misAJour} mis à jour   🗑 ${it.corbeille} en corbeille",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                etat.progression?.takeIf { etat.enCours }?.let { LigneProgression(it) }
            }
            Button(onClick = onSynchroniser, enabled = !etat.enCours) {
                Icon(Icons.Default.Sync, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text("Synchroniser maintenant")
            }
        }
    }
}

/** Barre et texte d'avancement : « 340 sur 1 052 fichiers · 187 Mo sur 657 Mo · environ 12 min restantes ». */
@Composable
internal fun LigneProgression(p: Progression) {
    Column(Modifier.fillMaxWidth().padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        val fraction = p.fraction
        if (fraction != null) LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth())
        else LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        val detail = when (p.phase) {
            Phase.PREPARATION -> "Recherche des changements sur le serveur…"
            Phase.RECEPTION -> buildString {
                append("${p.libelle()}  ·  ${formaterOctets(p.octetsFaits)} sur ${formaterOctets(p.octetsTotal)}")
                p.restantSecondes?.let { append("  ·  environ ${formaterDuree(it)} restantes") }
            }
            Phase.ENVOI -> p.libelle()
        }
        Text(detail, style = MaterialTheme.typography.bodySmall)
        p.courant?.let {
            Text(
                (if (p.phase == Phase.ENVOI) "↑ " else "↓ ") + it,
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

// ====================================================================== onglets

@Composable
private fun Vide(texte: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text(texte, color = MaterialTheme.colorScheme.onSurfaceVariant) }
}

@Composable
fun ListeConflits(conflits: List<ConflitUi>, controller: SyncController) {
    if (conflits.isEmpty()) {
        Vide("Aucun conflit. Tout est synchronisé.")
        return
    }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items(conflits, key = { it.id }) { conflit ->
            Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.tertiaryContainer, contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
            )) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(conflit.relPath.substringAfterLast('/'), style = MaterialTheme.typography.titleSmall)
                    Text(conflit.relPath.substringBeforeLast('/', ""), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
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
        items(etat.erreurs) { Text("✖ $it", color = couleurEtat(ROUGE), style = MaterialTheme.typography.bodyMedium) }
        items(etat.ignores) { Text("• $it", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium) }
    }
}

@Composable
fun Journal(lignes: List<String>) {
    if (lignes.isEmpty()) {
        Vide("Le journal est vide.")
        return
    }
    SelectionContainer {
        LazyColumn(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface)) {
            items(lignes.asReversed()) { Text(it, fontFamily = FontFamily.Monospace, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)) }
        }
    }
}
