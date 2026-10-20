package mg.hydria.compta.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.AccountBox
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mg.hydria.compta.core.AppResult
import mg.hydria.compta.di.AppGraph
import mg.hydria.compta.sync.SyncStatus

private enum class Etape { CHARGEMENT, LOGIN, SYNC_INITIALE, ACCUEIL }

@Composable
fun AppRoot(graph: AppGraph) {
    val session by graph.session.session.collectAsState()
    var besoinSync by remember { mutableStateOf<Boolean?>(null) }
    var erreurFatale by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(session) {
        besoinSync = try {
            if (session == null) null
            else withContext(Dispatchers.IO) { graph.syncRepository.besoinSyncInitiale() }
        } catch (t: Throwable) {
            android.util.Log.e("AppRoot", "Initialisation impossible", t)
            erreurFatale = "${t.javaClass.simpleName} : ${t.message}"
            null
        }
    }

    erreurFatale?.let { message ->
        Centre {
            Text("Impossible de démarrer", style = MaterialTheme.typography.titleMedium)
            Text(
                message,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(16.dp),
            )
            Button(onClick = { erreurFatale = null; besoinSync = null }) { Text("Réessayer") }
        }
        return
    }

    val etape = when {
        session == null -> Etape.LOGIN
        besoinSync == null -> Etape.CHARGEMENT
        besoinSync == true -> Etape.SYNC_INITIALE
        else -> Etape.ACCUEIL
    }

    when (etape) {
        Etape.CHARGEMENT -> Centre { CircularProgressIndicator() }
        Etape.LOGIN -> LoginScreen(graph)
        Etape.SYNC_INITIALE -> SyncGateScreen(graph, onTermine = { besoinSync = false })
        Etape.ACCUEIL -> MainShell(graph)
    }
}

@Composable
private fun Centre(content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
        content = { content() },
    )
}

@Composable
private fun LoginScreen(graph: AppGraph) {
    val scope = rememberCoroutineScope()
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var erreur by remember { mutableStateOf<String?>(null) }
    var enCours by remember { mutableStateOf(false) }

    Centre {
        Text("Hydria Compta", style = MaterialTheme.typography.headlineMedium)
        Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(username, { username = it }, label = { Text("Identifiant") })
            OutlinedTextField(
                password, { password = it }, label = { Text("Mot de passe") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            )
            erreur?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(
                enabled = !enCours && username.isNotBlank() && password.isNotBlank(),
                onClick = {
                    enCours = true; erreur = null
                    scope.launch {
                        // AppRoot route ensuite vers l'écran de préparation qui lance
                        // la sync initiale (source unique, pas de course).
                        when (val r = graph.authRepository.login(username.trim(), password)) {
                            is AppResult.Ok -> Unit
                            is AppResult.Err -> erreur = r.message
                        }
                        enCours = false
                    }
                },
            ) { Text(if (enCours) "Connexion…" else "Se connecter") }
        }
    }
}

@Composable
private fun SyncGateScreen(graph: AppGraph, onTermine: () -> Unit) {
    val scope = rememberCoroutineScope()
    var etapeTexte by remember { mutableStateOf("Préparation des données comptables…") }
    var erreur by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        val r = withContext(Dispatchers.IO) {
            graph.syncRepository.runInitialSync { etape -> etapeTexte = etape }
        }
        when (r) {
            is AppResult.Ok -> {
                withContext(Dispatchers.IO) { graph.syncManager.planifierPullPeriodique() }
                onTermine()
            }
            is AppResult.Err -> erreur = r.message
        }
    }

    Centre {
        if (erreur == null) CircularProgressIndicator()
        Text(etapeTexte, Modifier.padding(top = 16.dp))
        erreur?.let {
            val message = if (it.contains("404")) {
                "$it\n\nLes endpoints comptables ne sont pas encore déployés sur le serveur " +
                    "(/api/mobile/v1/compta/…). La connexion, elle, fonctionne."
            } else it
            Text(message, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp))
            Button(onClick = { erreur = null; scope.launch {
                val r = withContext(Dispatchers.IO) { graph.syncRepository.runInitialSync { t -> etapeTexte = t } }
                when (r) {
                    is AppResult.Ok -> onTermine()
                    is AppResult.Err -> erreur = r.message
                }
            } }) { Text("Réessayer") }
            OutlinedButton(onClick = {
                scope.launch {
                    withContext(Dispatchers.IO) { graph.syncRepository.forcerModeHorsLigne() }
                    onTermine()
                }
            }, modifier = Modifier.padding(top = 8.dp)) { Text("Continuer hors ligne") }
        }
    }
}

@Composable
private fun compteFlow(flow: () -> kotlinx.coroutines.flow.Flow<Int>): Int {
    val v by produceState(initialValue = -1) {
        withContext(Dispatchers.IO) { flow().flowOn(Dispatchers.IO).collect { value = it } }
    }
    return v
}

private enum class Onglet(val titre: String, val icone: androidx.compose.ui.graphics.vector.ImageVector) {
    ACCUEIL("Accueil", Icons.Filled.Home),
    SOLDES("Soldes", Icons.Filled.AccountBox),
    GRAND_LIVRE("Grand livre", Icons.AutoMirrored.Filled.List),
    BALANCE("Balance", Icons.Filled.DateRange),
    COMPTES("Comptes", Icons.Filled.Menu),
    TIERS("Tiers", Icons.Filled.Person),
}

/**
 * Écrans secondaires atteints depuis un onglet (pas de place pour un 7e onglet
 * dans la barre de navigation) : pile minimale à 2 niveaux, sans NavHost — la
 * saisie d'écriture suivra probablement le même mécanisme.
 */
private sealed class EcranSecondaire {
    data object VerificationScans : EcranSecondaire()
    data class VerificationScansDetail(val mois: String, val fichier: String) : EcranSecondaire()
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainShell(graph: AppGraph) {
    var onglet by rememberSaveable { mutableStateOf(Onglet.ACCUEIL) }
    var secondaire by remember { mutableStateOf<EcranSecondaire?>(null) }
    val status by produceState<SyncStatus?>(initialValue = null) {
        val manager = withContext(Dispatchers.IO) { graph.syncManager }
        manager.status.collect { value = it }
    }

    val titre = when (val s = secondaire) {
        null -> onglet.titre
        EcranSecondaire.VerificationScans -> "Vérification des scans"
        is EcranSecondaire.VerificationScansDetail -> "${s.fichier} · ${s.mois}"
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(titre) },
                navigationIcon = {
                    if (secondaire != null) {
                        IconButton(onClick = {
                            secondaire = if (secondaire is EcranSecondaire.VerificationScansDetail) {
                                EcranSecondaire.VerificationScans
                            } else {
                                null
                            }
                        }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Retour")
                        }
                    }
                },
                actions = { status?.let { SyncStatusChip(it) } },
            )
        },
        bottomBar = {
            if (secondaire == null) {
                NavigationBar {
                    Onglet.entries.forEach { o ->
                        NavigationBarItem(
                            selected = onglet == o,
                            onClick = { onglet = o },
                            icon = { Icon(o.icone, contentDescription = o.titre) },
                            label = { Text(o.titre, style = MaterialTheme.typography.labelSmall) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        when (val s = secondaire) {
            EcranSecondaire.VerificationScans -> VerificationScansScreen(graph, padding) { mois, fichier ->
                secondaire = EcranSecondaire.VerificationScansDetail(mois, fichier)
            }
            is EcranSecondaire.VerificationScansDetail ->
                VerificationScansDetailScreen(graph, s.mois, s.fichier, padding)
            null -> when (onglet) {
                Onglet.ACCUEIL -> AccueilScreen(graph, padding) { secondaire = EcranSecondaire.VerificationScans }
                Onglet.SOLDES -> SoldesScreen(graph, padding)
                Onglet.GRAND_LIVRE -> GrandLivreScreen(graph, padding)
                Onglet.BALANCE -> BalanceScreen(graph, padding)
                Onglet.COMPTES -> ComptesScreen(graph, padding)
                Onglet.TIERS -> TiersScreen(graph, padding)
            }
        }
    }
}

@Composable
private fun AccueilScreen(
    graph: AppGraph,
    padding: androidx.compose.foundation.layout.PaddingValues,
    onOuvrirVerificationScans: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val comptes = compteFlow { graph.database.referentielDao().observeCountComptes() }
    val journaux = compteFlow { graph.database.referentielDao().observeCountJournaux() }
    val exercices = compteFlow { graph.database.referentielDao().observeCountExercices() }
    val grandLivre = compteFlow { graph.database.referentielDao().observeCountGrandLivre() }
    val tiers = compteFlow { graph.database.tiersDao().observeCount() }
    val conflits = compteFlow { graph.database.conflictDao().observeCountOuverts() }

    var resyncEnCours by remember { mutableStateOf(false) }
    var resyncMessage by remember { mutableStateOf<String?>(null) }

    Column(
        Modifier.fillMaxSize().padding(padding).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        fun n(v: Int) = if (v < 0) "…" else v.toString()
        Text("Réplique locale", style = MaterialTheme.typography.titleMedium)
        Text("Comptes : ${n(comptes)}")
        Text("Journaux : ${n(journaux)}")
        Text("Exercices : ${n(exercices)}")
        Text("Lignes de grand livre : ${n(grandLivre)}")
        Text("Tiers : ${n(tiers)}")
        Text("Conflits à revoir : ${n(conflits)}")

        resyncMessage?.let {
            Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        Button(
            enabled = !resyncEnCours,
            onClick = {
                resyncEnCours = true; resyncMessage = null
                scope.launch {
                    val r = withContext(Dispatchers.IO) {
                        graph.syncRepository.runResyncComplete { resyncMessage = it }
                    }
                    resyncMessage = when (r) {
                        is AppResult.Ok -> "Resynchronisation terminée"
                        is AppResult.Err -> "Échec : ${r.message}"
                    }
                    resyncEnCours = false
                }
            },
        ) { Text(if (resyncEnCours) "Resynchronisation…" else "Resynchroniser (complet)") }

        OutlinedButton(onClick = onOuvrirVerificationScans) { Text("Vérification des scans →") }

        Text(
            "Saisie d'écritures, caisse et paie : prochaine étape (écriture → outbox → serveur).",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SyncStatusChip(status: SyncStatus) {
    SuggestionChip(onClick = {}, label = { Text(status.libelle) })
}
