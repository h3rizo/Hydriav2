package mg.hydria.compta.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.AppResult
import mg.hydria.compta.data.db.dao.GrandLivreDao
import mg.hydria.compta.data.db.entity.CompteEntity
import mg.hydria.compta.data.db.entity.ExerciceEntity
import mg.hydria.compta.data.db.entity.LigneGrandLivreEntity
import mg.hydria.compta.data.db.entity.TiersEntity
import mg.hydria.compta.data.db.entity.SyncStateKeys
import mg.hydria.compta.di.AppGraph
import org.json.JSONArray
import org.json.JSONObject
import java.time.format.DateTimeFormatter

private val DATE_FMT = DateTimeFormatter.ofPattern("dd/MM/yy")

@Composable
private fun <T> flowState(initial: T, vararg keys: Any?, flow: () -> Flow<T>): T {
    val s by produceState(initial, *keys) {
        withContext(Dispatchers.IO) { flow().flowOn(Dispatchers.IO).collect { value = it } }
    }
    return s
}

@Composable
private fun ExerciceSelector(
    exercices: List<ExerciceEntity>,
    selected: String?,
    onSelect: (String?) -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FilterChip(selected = selected == null, onClick = { onSelect(null) }, label = { Text("Tous") })
        exercices.forEach { ex ->
            FilterChip(
                selected = selected == ex.id,
                onClick = { onSelect(ex.id) },
                label = { Text(ex.libelle) },
            )
        }
    }
}

@Composable
private fun SearchField(value: String, onChange: (String) -> Unit, hint: String) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(hint) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
    )
}

/* ------------------------------------------------------------------ */

@Composable
fun GrandLivreScreen(graph: AppGraph, padding: PaddingValues) {
    val exercices = flowState(emptyList<ExerciceEntity>()) { graph.database.referentielDao().observeExercices() }
    var exerciceId by rememberSaveable { mutableStateOf<String?>(null) }
    var filtre by rememberSaveable { mutableStateOf("") }
    val lignes = flowState(emptyList<LigneGrandLivreEntity>(), exerciceId, filtre.trim()) {
        graph.database.grandLivreDao().observeRecentes(exerciceId, filtre.trim(), 500)
    }

    Column(Modifier.fillMaxSize().padding(padding)) {
        ExerciceSelector(exercices, exerciceId) { exerciceId = it }
        SearchField(filtre, { filtre = it }, "Compte ou libellé")
        Text(
            "${lignes.size} ligne(s) — 500 max",
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        HorizontalDivider()
        LazyColumn(Modifier.fillMaxSize()) {
            items(lignes, key = { it.id }) { l ->
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("${l.dateMouvement.format(DATE_FMT)}  ·  ${l.compteNumero}",
                            style = MaterialTheme.typography.labelLarge)
                        val montant = if (l.debit.isZero) "-${l.credit.format()}" else l.debit.format()
                        Text(montant, style = MaterialTheme.typography.labelLarge)
                    }
                    Text(
                        l.description.ifBlank { "(sans libellé)" },
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                HorizontalDivider()
            }
        }
    }
}

@Composable
fun BalanceScreen(graph: AppGraph, padding: PaddingValues) {
    val exercices = flowState(emptyList<ExerciceEntity>()) { graph.database.referentielDao().observeExercices() }
    var exerciceId by rememberSaveable { mutableStateOf<String?>(null) }
    val effectif = exerciceId ?: exercices.firstOrNull()?.id

    val soldes = flowState(emptyList<GrandLivreDao.SoldeCompte>(), effectif) {
        graph.database.grandLivreDao().observeBalance(effectif ?: "—")
    }

    Column(Modifier.fillMaxSize().padding(padding)) {
        ExerciceSelector(exercices, effectif) { exerciceId = it ?: exercices.firstOrNull()?.id }
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Compte", style = MaterialTheme.typography.labelMedium)
            Text("Débit  /  Crédit", style = MaterialTheme.typography.labelMedium)
        }
        HorizontalDivider()
        LazyColumn(Modifier.fillMaxSize()) {
            items(soldes, key = { it.compteNumero }) { s ->
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(s.compteNumero, style = MaterialTheme.typography.bodyMedium)
                    Text(
                        "${s.totalDebit.format()}  /  ${s.totalCredit.format()}",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                HorizontalDivider()
            }
        }
    }
}

@Composable
fun ComptesScreen(graph: AppGraph, padding: PaddingValues) {
    var filtre by rememberSaveable { mutableStateOf("") }
    val comptes = flowState(emptyList<CompteEntity>(), filtre.trim()) {
        graph.database.referentielDao().observeComptesFiltres(filtre.trim())
    }
    Column(Modifier.fillMaxSize().padding(padding)) {
        SearchField(filtre, { filtre = it }, "Numéro ou nom de compte")
        HorizontalDivider()
        LazyColumn(Modifier.fillMaxSize()) {
            items(comptes, key = { it.id }) { c ->
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
                    Text("${c.numero}  ·  ${c.nom}", style = MaterialTheme.typography.bodyMedium)
                    Text(c.type.name.lowercase(), style = MaterialTheme.typography.labelSmall)
                }
                HorizontalDivider()
            }
        }
    }
}

/* ------------------------------------------------------------------ */

private data class SoldeLigne(val label: String, val solde: Ariary, val count: Int, val edf: Ariary = Ariary.ZERO)

private fun JSONArray.toSoldeLignes(): List<SoldeLigne> = (0 until length()).map {
    val o = getJSONObject(it)
    SoldeLigne(
        label = o.optString("label"),
        solde = Ariary.parse(o.optString("solde")),
        count = o.optInt("count"),
        edf = Ariary.parse(o.optString("edf", "0")),
    )
}

@Composable
fun SoldesScreen(graph: AppGraph, padding: PaddingValues) {
    val raw = flowState<String?>(null) { graph.database.syncStateDao().observe(SyncStateKeys.SOLDES_JSON) }
    val json = remember(raw) { raw?.takeIf { it.isNotBlank() }?.let { runCatching { JSONObject(it) }.getOrNull() } }

    if (json == null) {
        Column(Modifier.fillMaxSize().padding(padding).padding(24.dp)) {
            Text("Soldes non encore synchronisés.", style = MaterialTheme.typography.bodyMedium)
            Text("Lance une synchronisation depuis l'accueil.", style = MaterialTheme.typography.bodySmall)
        }
        return
    }

    val caisses = json.optJSONArray("caisses")?.toSoldeLignes().orEmpty()
    val banques = json.optJSONArray("banques")?.toSoldeLignes().orEmpty()
    val financements = json.optJSONArray("financements")?.toSoldeLignes().orEmpty()
    val totaux = json.optJSONObject("totaux") ?: JSONObject()
    val mois = json.optString("mois").takeIf { it.isNotBlank() && it != "null" }

    LazyColumn(Modifier.fillMaxSize().padding(padding)) {
        item {
            Text(
                "Cumul depuis l'origine" + (mois?.let { " · jusqu'à $it" } ?: ""),
                style = MaterialTheme.typography.labelMedium,
                modifier = Modifier.padding(16.dp, 12.dp),
            )
        }
        soldeSection("Caisses", caisses, Ariary.parse(totaux.optString("caisses")))
        soldeSection("Comptes en banque", banques, Ariary.parse(totaux.optString("banques")))
        soldeSection("Financements (bailleurs)", financements, Ariary.parse(totaux.optString("financements")))
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.soldeSection(
    titre: String,
    lignes: List<SoldeLigne>,
    total: Ariary,
) {
    item {
        Column {
            HorizontalDivider()
            Row(
                Modifier.fillMaxWidth().padding(16.dp, 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(titre, style = MaterialTheme.typography.titleSmall)
                Text(total.format(), style = MaterialTheme.typography.titleSmall)
            }
        }
    }
    if (lignes.isEmpty()) {
        item { Text("(aucun)", style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(16.dp, 4.dp)) }
    }
    items(lignes, key = { titre + it.label }) { l ->
        Row(
            Modifier.fillMaxWidth().padding(16.dp, 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column {
                Text(l.label, style = MaterialTheme.typography.bodyMedium)
                Text("${l.count} ligne(s)", style = MaterialTheme.typography.labelSmall)
            }
            Text(l.solde.format(), style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
fun TiersScreen(graph: AppGraph, padding: PaddingValues) {
    var filtre by rememberSaveable { mutableStateOf("") }
    val tiers = flowState(emptyList<TiersEntity>(), filtre.trim()) {
        graph.database.tiersDao().observeFiltres(filtre.trim(), 300)
    }
    Column(Modifier.fillMaxSize().padding(padding)) {
        SearchField(filtre, { filtre = it }, "Nom, code tiers ou NIF")
        Text(
            "${tiers.size} tiers — 300 max",
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )
        HorizontalDivider()
        LazyColumn(Modifier.fillMaxSize()) {
            items(tiers, key = { it.id }) { t ->
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
                    Text(t.nom, style = MaterialTheme.typography.bodyMedium)
                    val meta = listOfNotNull(
                        t.codeTiers?.let { "Code $it" },
                        t.nif?.let { "NIF $it" },
                        t.telephone,
                    ).joinToString("  ·  ")
                    if (meta.isNotBlank()) {
                        Text(meta, style = MaterialTheme.typography.labelSmall)
                    }
                }
                HorizontalDivider()
            }
        }
    }
}

/* ------------------------------------------------------------------ */
// Vérification des scans — reprend accounting/verification_scans_recap.html
// et son détail (api_detail_scans) de compta.hydria.mg, en lecture seule.
// La vérification elle-même (existence des fichiers sur le lecteur réseau)
// reste une action web/desktop ; le mobile consulte le résultat déjà calculé
// (ScanVerificationCache), rafraîchi à la sync initiale ou manuellement.

private data class VerifMoisLigne(
    val mois: String,
    val total: Int,
    val valides: Int,
    val liensMorts: Int,
    val sansScan: Int,
    val tauxValides: Int,
)

private data class VerifFichierLigne(
    val fichier: String,
    val total: Int,
    val valides: Int,
    val liensMorts: Int,
    val sansScan: Int,
    val moisList: List<VerifMoisLigne>,
)

private fun JSONObject.toVerifFichiers(): List<VerifFichierLigne> {
    val arr = optJSONArray("fichiers") ?: JSONArray()
    return (0 until arr.length()).map { i ->
        val o = arr.getJSONObject(i)
        val moisArr = o.optJSONArray("mois") ?: JSONArray()
        VerifFichierLigne(
            fichier = o.optString("fichier"),
            total = o.optInt("total"),
            valides = o.optInt("scans_valides"),
            liensMorts = o.optInt("liens_morts"),
            sansScan = o.optInt("sans_scan"),
            moisList = (0 until moisArr.length()).map { j ->
                val m = moisArr.getJSONObject(j)
                VerifMoisLigne(
                    mois = m.optString("mois"),
                    total = m.optInt("total"),
                    valides = m.optInt("scans_valides"),
                    liensMorts = m.optInt("liens_morts"),
                    sansScan = m.optInt("sans_scan"),
                    tauxValides = m.optInt("taux_valides"),
                )
            },
        )
    }
}

private fun tauxCouleur(taux: Int) = when {
    taux >= 90 -> Couleur.SUCCES
    taux >= 50 -> Couleur.ATTENTION
    else -> Couleur.ERREUR
}

private enum class Couleur { SUCCES, ATTENTION, ERREUR, NEUTRE }

@Composable
private fun couleurDe(c: Couleur) = when (c) {
    Couleur.SUCCES -> MaterialTheme.colorScheme.primary
    Couleur.ATTENTION -> MaterialTheme.colorScheme.tertiary
    Couleur.ERREUR -> MaterialTheme.colorScheme.error
    Couleur.NEUTRE -> MaterialTheme.colorScheme.onSurfaceVariant
}

@Composable
fun VerificationScansScreen(
    graph: AppGraph,
    padding: PaddingValues,
    onOuvrirDetail: (mois: String, fichier: String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    val raw = flowState<String?>(null) { graph.database.syncStateDao().observe(SyncStateKeys.VERIFICATION_SCANS_JSON) }
    val json = remember(raw) { raw?.takeIf { it.isNotBlank() }?.let { runCatching { JSONObject(it) }.getOrNull() } }
    var rafraichissement by remember { mutableStateOf(false) }
    var erreur by remember { mutableStateOf<String?>(null) }

    fun rafraichir() {
        rafraichissement = true; erreur = null
        scope.launch {
            when (val r = withContext(Dispatchers.IO) { graph.syncRepository.rafraichirVerificationScans() }) {
                is AppResult.Err -> erreur = r.message
                is AppResult.Ok -> Unit
            }
            rafraichissement = false
        }
    }

    Column(Modifier.fillMaxSize().padding(padding)) {
        Row(
            Modifier.fillMaxWidth().padding(16.dp, 12.dp, 16.dp, 0.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Récapitulatif par fichier", style = MaterialTheme.typography.titleSmall)
            TextButton(enabled = !rafraichissement, onClick = ::rafraichir) {
                Text(if (rafraichissement) "Rafraîchissement…" else "Rafraîchir")
            }
        }
        erreur?.let {
            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp, 4.dp))
        }

        if (json == null) {
            Column(Modifier.padding(16.dp)) {
                Text("Aucune donnée de vérification synchronisée.", style = MaterialTheme.typography.bodyMedium)
                Text(
                    "Touchez « Rafraîchir » ci-dessus, ou relancez une synchronisation depuis l'accueil.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            return
        }

        val fichiers = remember(json) { json.toVerifFichiers() }
        val dateVerif = json.optString("date_derniere_verif").takeIf { it.isNotBlank() && it != "null" }

        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Column(Modifier.padding(16.dp, 8.dp, 16.dp, 12.dp)) {
                    Text(
                        "${json.optInt("total_entries")} opération(s) nécessitant un scan" +
                            (dateVerif?.let { " · vérifié le $it" } ?: " · jamais vérifié"),
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                        Text("✔ ${json.optInt("taux_scans_valides")}%", color = couleurDe(Couleur.SUCCES))
                        Text("✖ ${json.optInt("taux_liens_morts")}%", color = couleurDe(Couleur.ERREUR))
                        Text("— ${json.optInt("taux_sans_scan")}%", color = couleurDe(Couleur.NEUTRE))
                    }
                }
                HorizontalDivider()
            }
            if (fichiers.isEmpty()) {
                item {
                    Text(
                        "Aucune opération à scanner pour ce périmètre.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                }
            }
            fichiers.forEach { f ->
                item {
                    Column(Modifier.fillMaxWidth().padding(16.dp, 10.dp, 16.dp, 2.dp)) {
                        Text(f.fichier, style = MaterialTheme.typography.titleSmall)
                        Text(
                            "${f.total} opé. · ${f.valides} valides · ${f.liensMorts} liens morts · ${f.sansScan} sans scan",
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                }
                items(f.moisList, key = { f.fichier + "|" + it.mois }) { m ->
                    Row(
                        Modifier.fillMaxWidth()
                            .clickable { onOuvrirDetail(m.mois, f.fichier) }
                            .padding(horizontal = 28.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column {
                            Text(m.mois, style = MaterialTheme.typography.bodyMedium)
                            Text("${m.total} opé.", style = MaterialTheme.typography.labelSmall)
                        }
                        Text("${m.tauxValides}% valides", color = couleurDe(tauxCouleur(m.tauxValides)))
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

private val STATUTS_SCAN = listOf(
    "all" to "Tous",
    "valides" to "Valides",
    "liens_morts" to "Liens morts",
    "sans_scan" to "Sans scan",
)

@Composable
fun VerificationScansDetailScreen(
    graph: AppGraph,
    mois: String,
    fichier: String,
    padding: PaddingValues,
) {
    var statut by rememberSaveable { mutableStateOf("all") }
    var page by rememberSaveable { mutableStateOf(1) }
    var chargement by remember { mutableStateOf(true) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var reponse by remember { mutableStateOf<JSONObject?>(null) }

    LaunchedEffect(statut, page) {
        chargement = true; erreur = null
        when (val r = withContext(Dispatchers.IO) {
            graph.syncRepository.chargerDetailVerificationScans(mois, fichier, statut, page)
        }) {
            is AppResult.Ok -> reponse = r.value
            is AppResult.Err -> erreur = r.message
        }
        chargement = false
    }

    Column(Modifier.fillMaxSize().padding(padding)) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            STATUTS_SCAN.forEach { (value, label) ->
                FilterChip(
                    selected = statut == value,
                    onClick = { if (statut != value) { statut = value; page = 1 } },
                    label = { Text(label) },
                )
            }
        }
        HorizontalDivider()
        erreur?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(16.dp)) }
        if (chargement) {
            Row(Modifier.fillMaxWidth().padding(24.dp), horizontalArrangement = Arrangement.Center) {
                CircularProgressIndicator()
            }
        }

        val entries = reponse?.optJSONArray("entries") ?: JSONArray()
        val pagination = reponse?.optJSONObject("pagination")

        LazyColumn(Modifier.fillMaxSize().weight(1f)) {
            items(entries.length(), key = { i -> entries.getJSONObject(i).optInt("id") }) { i ->
                val e = entries.getJSONObject(i)
                Column(Modifier.fillMaxWidth().padding(16.dp, 10.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(
                            "${e.optString("date_rec")}  ·  ${e.optString("compte_code")}",
                            style = MaterialTheme.typography.labelLarge,
                        )
                        val montantIn = Ariary.parse(e.optString("montant_in"))
                        val montantOut = Ariary.parse(e.optString("montant_out"))
                        Text(
                            if (!montantIn.isZero) montantIn.format() else "-${montantOut.format()}",
                            style = MaterialTheme.typography.labelLarge,
                        )
                    }
                    Text(
                        e.optString("description").ifBlank { "(sans libellé)" },
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        e.optString("scan_label"),
                        style = MaterialTheme.typography.labelSmall,
                        color = couleurDe(
                            when (e.optString("scan_statut")) {
                                "valide" -> Couleur.SUCCES
                                "lien_mort", "sans_scan" -> Couleur.ERREUR
                                else -> Couleur.NEUTRE
                            },
                        ),
                        modifier = Modifier.padding(top = 2.dp),
                    )
                    e.optString("scan_absolu").takeIf { it.isNotBlank() }?.let { chemin ->
                        Text(
                            chemin,
                            style = MaterialTheme.typography.labelSmall,
                            color = couleurDe(Couleur.NEUTRE),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
                HorizontalDivider()
            }
            if (!chargement && entries.length() == 0) {
                item {
                    Text(
                        "Aucune opération pour ce filtre.",
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(16.dp),
                    )
                }
            }
        }

        pagination?.let { p ->
            HorizontalDivider()
            Row(
                Modifier.fillMaxWidth().padding(16.dp, 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                TextButton(
                    enabled = p.optBoolean("has_previous"),
                    onClick = { page = (page - 1).coerceAtLeast(1) },
                ) { Text("◀ Précédent") }
                Text(
                    "Page ${p.optInt("current_page")}/${p.optInt("total_pages")} · ${p.optInt("total_entries")} au total",
                    style = MaterialTheme.typography.labelSmall,
                )
                TextButton(
                    enabled = p.optBoolean("has_next"),
                    onClick = { page += 1 },
                ) { Text("Suivant ▶") }
            }
        }
    }
}
