package mg.hydria.app.volume

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import mg.hydria.app.*
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import java.util.concurrent.Executors

class VolumeActivity : AppCompatActivity() {
    private companion object {
        /** Clé du cache volumétrique (par compte) : dernier journal d'encaissement confirmé. */
        const val LAST_JOURNAL_KEY = "last_journal"
        /** Au-delà de ce nombre de jours, une date d'encaissement demande une confirmation. */
        const val OLD_COLLECTION_DAYS = 31L
    }

    private lateinit var store: OfflineStore
    private lateinit var repository: VolumeRepository
    private lateinit var root: LinearLayout
    private lateinit var body: LinearLayout
    private lateinit var works: HydriaAutocomplete
    private lateinit var monthButton: Button
    private var monthValue: YearMonth = YearMonth.now(ZoneId.of("Indian/Antananarivo"))
    private lateinit var status: TextView
    private var summary: TextView? = null
    private var pointButton: Button? = null
    private var tabButtons: List<Button> = emptyList()
    private var workRows = emptyList<JSONObject>()
    private var pack: JSONObject? = null
    private var stage = VolumeWorkflow.Stage.BILLING
    private var calculated = false
    private var selectedEntryId: String? = null
    private var showPointed = false
    private val selected = linkedSetOf<String>()
    private val executor = Executors.newSingleThreadExecutor()
    private var busy = false
    private val scanner = registerForActivityResult(ScanContract()) { result -> result.contents?.let(::resolveQr) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        HydriaColors.bind(this)
        store = OfflineStore(this)
        if (store.token.isNullOrBlank()) { finish(); return }
        repository = VolumeRepository(store)
        stage = VolumeWorkflow.Stage.entries.getOrElse(savedInstanceState?.getInt("stage") ?: 0) { VolumeWorkflow.Stage.BILLING }
        root = column(12)
        setContentView(root)
        val title = LinearLayout(this)
        title.addView(label("Volumétrique", 23f), LinearLayout.LayoutParams(0, -2, 1f))
        action(title, "Outils") { toolsMenu() }
        root.addView(title)
        val tabs = LinearLayout(this)
        tabButtons = VolumeWorkflow.Stage.entries.map { target ->
            Button(this).apply {
                text = target.title
                HydriaUi.secondaryButton(this, active = target == stage)
                setOnClickListener { if (!busy) { stage = target; selected.clear(); selectedEntryId = null; render() } }
            }
        }
        tabButtons.forEach { tabs.addView(it, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) }) }
        root.addView(tabs, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })
        // "Tous les ouvrages" (id vide) est ajouté par loadWorks() : necessaire pour
        // Encaissement (voir selectionKey()), sans objet pour Facturation/Pointage
        // qui exigent toujours un ouvrage precis.
        works = HydriaAutocomplete(this, emptyList(), "Rechercher un ouvrage (vide = tous)…")
        root.addView(works, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6); bottomMargin = dp(6) })
        monthValue = savedInstanceState?.getString("month")?.let(YearMonth::parse)
            ?: YearMonth.now(ZoneId.of("Indian/Antananarivo"))
        val filters = LinearLayout(this)
        monthButton = Button(this).apply {
            HydriaUi.secondaryButton(this)
            text = monthValue.toString()
            setOnClickListener { pickMonth() }
        }
        filters.addView(monthButton, LinearLayout.LayoutParams(0, -2, 1f))
        action(filters, "Ouvrir") { openPeriod() }
        root.addView(filters)
        status = label("", 12f)
        root.addView(status)
        body = column(0)
        root.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f))
        loadWorks()
        // Sur un telephone neuf (ou apres reinstallation), le cache "ouvrages" est
        // vide tant que personne n'a fait Outils > Actualiser les ouvrages - on le
        // charge donc tout de suite si on est en ligne, pour que le selecteur ne
        // s'affiche pas vide au premier lancement.
        if (workRows.size <= 1 && online()) refreshOuvrages()
        works.onSelected = { clearChangedPeriod() }
        savedInstanceState?.getString("work")?.let { id -> workRows.indexOfFirst { it.optString("id") == id }.takeIf { it >= 0 }?.let { works.select(it) } }
        root.post { safely {
            openCached(); calculated = savedInstanceState?.getBoolean("calculated") ?: false
            val knownIds = rows().filterNot { it.optBoolean("pointee") }.map { it.getString("id") }.toSet()
            selected.addAll(savedInstanceState?.getStringArrayList("selected").orEmpty().filter { it in knownIds })
            selectedEntryId = savedInstanceState?.getString("entry")
            render()
        } }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("month", monthValue.toString())
        outState.putString("work", currentWorkId())
        outState.putInt("stage", stage.ordinal); outState.putBoolean("calculated", calculated)
        outState.putStringArrayList("selected", ArrayList(selected)); outState.putString("entry", selectedEntryId)
        super.onSaveInstanceState(outState)
    }
    override fun onDestroy() { executor.shutdown(); super.onDestroy() }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun column(padding: Int = 12) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(padding), dp(padding), dp(padding), dp(padding))
        setBackgroundColor(HydriaColors.background)
    }
    private fun label(value: String, size: Float = 14f) = TextView(this).apply {
        text = value; textSize = size; setTextColor(HydriaColors.text); setPadding(0, dp(6), 0, dp(6))
    }
    private fun action(parent: LinearLayout, value: String, callback: () -> Unit): Button = Button(this).apply {
        text = value
        HydriaUi.secondaryButton(this)
        setOnClickListener { safely { check(!busy) { "Opération en cours" }; callback() } }
        parent.addView(this, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6); bottomMargin = dp(6) })
    }
    private fun message(value: String) { Toast.makeText(this, value, Toast.LENGTH_LONG).show() }
    private fun safely(callback: () -> Unit) { try { callback() } catch (e: Exception) { message(e.message ?: "Action impossible") } }
    private fun online(): Boolean {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return manager.getNetworkCapabilities(manager.activeNetwork)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true
    }
    private fun background(callback: () -> Unit) {
        busy = true; status.text = "Chargement en cours…"
        works.isEnabled = false; monthButton.isEnabled = false
        executor.execute {
            var failure: String? = null
            try { callback() } catch (e: Exception) { failure = e.message ?: "Connexion interrompue" }
            runOnUiThread { busy = false; if (!isDestroyed) { works.isEnabled = true; monthButton.isEnabled = true; render(); failure?.let { status.text = it; message(it) } } }
        }
    }
    private fun toolsMenu() {
        AlertDialog.Builder(this).setTitle("Données et synchronisation")
            .setItems(arrayOf("Actualiser les ouvrages", "Actualiser cette période", "Synchroniser", "Historique / récapitulatifs", "Retour")) { _, index -> safely {
                when(index) {
                    0 -> refreshOuvrages()
                    1 -> download(stage == VolumeWorkflow.Stage.BILLING && calculated)
                    2 -> synchronize()
                    3 -> history()
                    4 -> finish()
                }
            } }.show()
    }
    private fun loadWorks() {
        val previous = if (works.selectedIndex >= 0) currentWorkId() else null
        val values = repository.read("ouvrages")?.optJSONArray("ouvrages") ?: JSONArray()
        val fetched = (0 until values.length()).map(values::getJSONObject)
        val tousLesOuvrages = JSONObject().put("id", "").put("nom", "Tous les ouvrages")
        workRows = listOf(tousLesOuvrages) + fetched
        works.labels = workRows.map { it.getString("nom") }
        workRows.indexOfFirst { it.optString("id") == previous }.takeIf { it >= 0 }?.let { works.select(it) }
    }
    private fun refreshOuvrages() = background {
        val result = HydriaNetwork.volumeBootstrap(store.token!!); check(result.successful) { result.error }
        repository.write("ouvrages", result.body); runOnUiThread { loadWorks() }
    }
    private fun pickMonth() {
        val noms = listOf("Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre")
        val annees = (monthValue.year - 3..monthValue.year + 1).toList()
        val form = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val anneeSpinner = Spinner(this).apply {
            HydriaUi.styleSpinner(this)
            adapter = ArrayAdapter(this@VolumeActivity, android.R.layout.simple_spinner_dropdown_item, annees.map { it.toString() })
            setSelection(annees.indexOf(monthValue.year).coerceAtLeast(0))
        }
        val moisSpinner = Spinner(this).apply {
            HydriaUi.styleSpinner(this)
            adapter = ArrayAdapter(this@VolumeActivity, android.R.layout.simple_spinner_dropdown_item, noms)
            setSelection(monthValue.monthValue - 1)
        }
        form.addView(anneeSpinner, LinearLayout.LayoutParams(0, -2, 1f))
        form.addView(moisSpinner, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(8) })
        AlertDialog.Builder(this).setTitle("Choisir le mois").setView(form)
            .setNegativeButton("Annuler", null)
            .setPositiveButton("Valider") { _, _ ->
                monthValue = YearMonth.of(annees[anneeSpinner.selectedItemPosition], moisSpinner.selectedItemPosition + 1)
                monthButton.text = monthValue.toString()
                clearChangedPeriod()
            }.show()
    }
    /** Ouvrage choisi dans l'autocomplétion ; champ vide = « Tous les ouvrages » (id vide). */
    private fun currentWorkId(): String = workRows.getOrNull(works.selectedIndex)?.optString("id").orEmpty()

    private fun selectionKey(): Pair<String, String> {
        check(workRows.size > 1) { "Actualisez les ouvrages depuis Outils" }
        val id = currentWorkId()
        check(id.isNotBlank() || stage == VolumeWorkflow.Stage.COLLECTION) { "Choisissez un ouvrage pour ${stage.title}" }
        return id to monthValue.toString()
    }
    private fun openCached() {
        val (id, period) = selectionKey()
        pack = repository.read("pack:$id:$period")
        selected.clear(); selectedEntryId = null; calculated = false; render()
    }
    private fun clearChangedPeriod() {
        val current = pack ?: return
        if (currentWorkId() != current.optString("ouvrage_id") || monthValue.toString() != current.optString("mois")) {
            pack = null; selected.clear(); selectedEntryId = null; calculated = false; render()
        }
    }
    private fun openPeriod() { if (online()) download(false) else openCached() }
    private fun download(showCalculation: Boolean) {
        val (id, period) = selectionKey()
        background {
            val result = HydriaNetwork.volumeBootstrap(store.token!!, id, period)
            check(result.successful) { result.error }; repository.savePack(result.body)
            runOnUiThread { pack = result.body; selected.clear(); selectedEntryId = null; calculated = showCalculation }
        }
    }
    private fun rows() = pack?.let(repository::invoices) ?: emptyList()
    private fun actions(row: JSONObject) = repository.actions(row.getString("id"))
    private fun conflicted(row: JSONObject) = VolumeWorkflow.conflicted(row, repository.pending())
    private fun chosen() = rows().filter { it.getString("id") in selected }.also { check(it.isNotEmpty()) { "Sélectionnez les factures" } }
    private fun entries(): List<JSONObject> =
        mg.hydria.shared.volume.VolumeWorkflowGateway.reconciledEntries(
            pack?.optJSONArray("diamex") ?: JSONArray(), repository.pending(), rows())
    private fun currentEntry() = entries().firstOrNull { it.optString("id") == selectedEntryId }
    private fun updateSummary() {
        val invoices = rows().filter { it.getString("id") in selected }
        val total = VolumeWorkflow.total(invoices)
        summary?.text = "${invoices.size} facture(s) sélectionnée(s) · $total Ar" + if (stage == VolumeWorkflow.Stage.POINTING) {
            currentEntry()?.let { "\nDiameX : ${it.optString("montant")} Ar · Écart : ${total - VolumeWorkflow.amount(it)} Ar" } ?: "\nSélectionnez une ligne DiameX à droite"
        } else ""
        pointButton?.isEnabled = !busy && VolumeWorkflow.matches(invoices, currentEntry())
    }
    private fun render() {
        tabButtons.forEachIndexed { index, button -> HydriaUi.secondaryButton(button, active = VolumeWorkflow.Stage.entries[index] == stage) }
        body.removeAllViews(); summary = null; pointButton = null
        val all = rows()
        status.text = "${stage.title} · ${pack?.optString("mois") ?: "Période à ouvrir"} · ${all.size} relevés\n${repository.pending().size} opération(s) à synchroniser" +
            (pack?.let { " · données du ${it.optString("generated_at").take(10)}" } ?: "")
        body.addView(label(stage.title, 22f))
        if (stage == VolumeWorkflow.Stage.BILLING) {
            body.addView(label("Le calcul porte sur tous les relevés de l'ouvrage et du mois choisis."))
            action(body, "Calculer les factures de tout le lot") {
                if (online()) download(true) else { openCached(); check(pack != null) { "Préchargez cette période avant de partir hors ligne" }; calculated = true; render() }
            }.let(HydriaUi::primaryButton)
            if (!calculated) return
            val valid = all.filter(VolumeWorkflow::calculable)
            body.addView(label("${all.size} relevés · ${valid.size} calculables · Total ${VolumeWorkflow.total(valid)} Ar", 18f))
            action(body, "Enregistrer toutes les factures calculées") {
                val batch = valid.filter { !it.optBoolean("imprimee") && !it.optBoolean("encaissee") && !it.optBoolean("pointee") && "validate" !in actions(it) }
                check(batch.isNotEmpty()) { "Aucune facture à enregistrer : le lot est déjà validé, verrouillé ou en attente" }
                confirmBatch("validate", batch)
            }.let(HydriaUi::primaryButton)
            action(body, "Imprimer les factures du lot · A4/PDF") { printInvoices(valid) }
            action(body, "Confirmer l'impression réalisée du lot") { confirmBatch("printed", valid.filter { !it.optBoolean("imprimee") && "printed" !in actions(it) }) }
            all.forEach { row ->
                val texte = "${row.optString("idxls")} · ${row.optString("abonne")}\n${row.optString("numero")} · ${row.optString("montant", "—")} Ar" +
                    if (row.optString("erreur_calcul").isNotBlank()) "\n${row.optString("erreur_calcul")}" else "\n${state(row)}"
                body.addView(label(texte).apply { HydriaUi.card(this); setPadding(dp(12), dp(10), dp(12), dp(10)) },
                    LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(4); bottomMargin = dp(4) })
            }
            return
        }
        if (pack == null) { body.addView(label("Ouvrez un ouvrage et un mois. Sans réseau, les données doivent déjà être préchargées.")); return }
        summary = label("", 18f); body.addView(summary)
        if (stage == VolumeWorkflow.Stage.COLLECTION) {
            body.addView(label("Factures non pointées de cet ouvrage/mois. Cochez les factures à la main ou ajoutez-les au scan."))
            val commands = LinearLayout(this)
            action(commands, "Scanner QR") { scanner.launch(ScanOptions().setDesiredBarcodeFormats(ScanOptions.QR_CODE).setPrompt("Scanner une facture à encaisser").setBeepEnabled(false)) }
            action(commands, "Saisir le numéro") {
                val input = EditText(this)
                AlertDialog.Builder(this).setTitle("Numéro de facture / QR").setView(input).setPositiveButton("Ajouter") { _, _ -> resolveQr(input.text.toString()) }.setNegativeButton("Annuler", null).show()
            }
            body.addView(commands)
            action(body, "Valider l'encaissement de la sélection") { collect() }.let(HydriaUi::primaryButton)
            action(body, "Imprimer le dernier récapitulatif d'encaissement") { lastRecap() }
            VolumeWorkflow.unpointed(all).filter { it.optBoolean("validee") || "validate" in actions(it) }
                .forEach { row -> checkbox(body, row, VolumeWorkflow.collectable(row, actions(row))) }
        } else {
            body.addView(label("Cochez les relevés à gauche et choisissez l'écriture DiameX à droite. Le total doit être identique."))
            val pointedRowsCount = all.count { it.optBoolean("pointee") }
            val pointedEntriesCount = entries().count { it.optBoolean("pointee") }
            if (pointedRowsCount + pointedEntriesCount > 0) {
                action(body, if (showPointed) "Masquer les éléments déjà pointés" else "Afficher les éléments déjà pointés (${pointedRowsCount + pointedEntriesCount})") {
                    showPointed = !showPointed; render()
                }
            }
            pointButton = action(body, "Pointer les relevés sur la ligne DiameX") {
                val invoices = chosen(); val entry = currentEntry()
                check(VolumeWorkflow.matches(invoices, entry)) { "Le total des relevés doit correspondre à la ligne DiameX" }
                confirmBatch("point", invoices, JSONObject().put("diamex_id", entry!!.getString("id")))
            }
            val comparison = LinearLayout(this)
            val left = column(6); val right = column(6)
            val width = maxOf(dp(300), resources.displayMetrics.widthPixels / 2 - dp(20))
            comparison.addView(left, LinearLayout.LayoutParams(width, -2)); comparison.addView(right, LinearLayout.LayoutParams(width, -2))
            left.addView(label("RELEVÉS", 18f)); right.addView(label("LIGNES DIAMEX", 18f))
            val visibleRows = if (showPointed) all else all.filterNot { it.optBoolean("pointee") }
            visibleRows.forEach { row -> checkbox(left, row, !row.optBoolean("pointee") && "point" !in actions(row) && (row.optBoolean("validee") || "validate" in actions(row))) }
            if (visibleRows.isEmpty()) left.addView(label("Aucun relevé à pointer"))
            val visibleEntries = if (showPointed) entries() else entries().filterNot { it.optBoolean("pointee") }
            val radioGroup = RadioGroup(this)
            visibleEntries.forEach { entry -> radioGroup.addView(RadioButton(this).apply {
                id = android.view.View.generateViewId(); isAllCaps = false; setTextColor(HydriaColors.text)
                text = "${entry.optString("date")} · ${entry.optString("numero")} / ${entry.optString("base")}\n${entry.optString("description")}\n${entry.optString("montant")} Ar" + if (entry.optBoolean("pointee")) " · Déjà pointée" else ""
                isEnabled = !entry.optBoolean("pointee"); isChecked = entry.optString("id") == selectedEntryId
                setOnCheckedChangeListener { _, checked -> if (checked) { selectedEntryId = entry.getString("id"); updateSummary() } }
            }) }
            right.addView(radioGroup)
            if (visibleEntries.isEmpty()) right.addView(label("Aucune ligne DiameX pour cette période"))
            body.addView(HorizontalScrollView(this).apply { addView(comparison) })
        }
        updateSummary()
    }
    private fun state(row: JSONObject): String =
        VolumeWorkflow.statusLabel(row, actions(row), conflicted(row))
    private fun checkbox(parent: LinearLayout, row: JSONObject, enabled: Boolean) {
        parent.addView(CheckBox(this).apply {
            text = "${row.optString("idxls")} · ${row.optString("abonne")}\n${row.optString("numero")} · ${row.optString("montant")} Ar\n${state(row)}"
            textSize = 15f; setTextColor(HydriaColors.text); isEnabled = enabled && !conflicted(row); isChecked = isEnabled && row.getString("id") in selected
            HydriaUi.card(this)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnCheckedChangeListener { _, checked -> if (checked) selected.add(row.getString("id")) else selected.remove(row.getString("id")); updateSummary() }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(4); bottomMargin = dp(4) })
    }
    private fun resolveQr(raw: String) = safely {
        val row = VolumeQr.find(raw.trim(), rows()) ?: error("Facture absente de cet ouvrage/mois")
        check(!conflicted(row)) { "Vérifiez le conflit serveur de cette facture" }
        check(VolumeWorkflow.collectable(row, actions(row))) { "Facture déjà encaissée, pointée ou non validée" }
        selected.add(row.getString("id")); render(); message("Facture ajoutée : ${row.optString("abonne")}")
    }
    private fun printInvoices(invoices: List<JSONObject>) {
        check(invoices.isNotEmpty()) { "Aucune facture à imprimer" }
        check(invoices.none(::conflicted)) { "Vérifiez les conflits du lot avant de l'imprimer" }
        check(invoices.all { it.optBoolean("validee") || "validate" in actions(it) }) { "Enregistrez le lot avant l'impression" }
        VolumePrinter.print(this, invoices)
    }
    private fun confirmBatch(action: String, invoices: List<JSONObject>, extra: JSONObject = JSONObject()) {
        check(invoices.isNotEmpty()) { "Aucune facture concernée" }
        check(invoices.none(::conflicted)) { "Vérifiez les conflits avant de poursuivre" }
        if (action != "validate") check(invoices.all { it.optBoolean("validee") || "validate" in actions(it) }) { "Enregistrez d'abord la facturation" }
        check(action in setOf("validate", "printed") || invoices.size <= 500) { "Sélectionnez au maximum 500 factures pour une opération" }
        val title = when(action) { "validate" -> "Enregistrer le lot calculé"; "collect" -> "Confirmer l'encaissement"; "printed" -> "Confirmer l'impression réalisée"; else -> "Confirmer le pointage" }
        // Journal « code · nom » et date JJ/MM/AAAA : l'agent relit ce qu'il va poster avant de confirmer.
        val posting = listOf(journalLabel(extra.optString("journal_code")), HydriaDates.display(extra.optString("date")))
            .filter { it.isNotBlank() }.joinToString(" · ")
        AlertDialog.Builder(this).setTitle(title).setMessage("${invoices.size} factures · ${VolumeWorkflow.total(invoices)} Ar\n$posting\nConservation locale, puis validation serveur à la synchronisation.")
            .setNegativeButton("Annuler", null).setPositiveButton("Confirmer") { _, _ -> safely {
                val recap = if (action == "collect") VolumeWorkflow.recap(invoices, rows(), extra.getString("date"), extra.getString("journal_code")) else null
                // Chaque appel enqueue() est deja atomique pour ses propres ecritures locales
                // (cf. VolumeRepository/OfflineStore.volumeWriteBatch) ; on ne les enveloppe plus
                // dans une transaction SQLite brute commune, qui ne garantirait plus rien depuis
                // que syncQueue/volumeCache peuvent vivre sur une base differente de TerrainDatabase.
                var receiptId: String? = null
                invoices.chunked(500).forEach { receiptId = repository.enqueue(action, it, extra, recap) }
                // Journal mémorisé une fois l'encaissement confirmé : présélectionné la prochaine fois (CALC_VOL-01).
                if (action == "collect") runCatching { repository.write(LAST_JOURNAL_KEY, JSONObject().put("code", extra.getString("journal_code"))) }
                selected.clear(); selectedEntryId = null; render()
                if (online()) synchronize { if (recap != null) showRecap(receiptId!!) }
                else if (recap != null) showRecap(receiptId!!)
            } }.show()
    }
    /** [initialDate] / [initialJournal] : valeurs déjà choisies, reprises par « Corriger la date » (sinon aujourd'hui / dernier journal). */
    private fun collect(initialDate: String? = null, initialJournal: String? = null) {
        val invoices = chosen()
        check(invoices.all { VolumeWorkflow.collectable(it, actions(it)) }) { "Une facture est déjà encaissée ou pointée" }
        val journals = pack?.optJSONArray("journaux") ?: JSONArray()
        check(journals.length() > 0) { "Actualisez les journaux avec cette période" }
        val form = column()
        val journal = Spinner(this).apply {
            adapter = ArrayAdapter(this@VolumeActivity, android.R.layout.simple_spinner_dropdown_item,
                (0 until journals.length()).map { journals.getJSONObject(it).let { j -> "${j.optString("code")} · ${j.optString("nom")}" } })
            HydriaUi.styleSpinner(this)
            // Dernier journal utilisé sur ce téléphone (par compte), s'il est toujours autorisé : sinon la
            // première entrée de la liste serait retenue d'office et un toucher distrait suffirait à se tromper.
            val last = initialJournal ?: repository.read(LAST_JOURNAL_KEY)?.optString("code").orEmpty()
            (0 until journals.length()).firstOrNull { journals.getJSONObject(it).optString("code") == last }?.let { setSelection(it) }
        }
        // Date au sélecteur (JJ/MM/AAAA) : aujourd'hui à Madagascar par défaut, jamais dans le futur (le serveur la refuse).
        val date = HydriaUi.dateField(this, initialDate)
        form.addView(label("Journal d'encaissement"))
        form.addView(journal, LinearLayout.LayoutParams(-1, dp(52)))
        form.addView(label("Date d'encaissement"))
        form.addView(date, LinearLayout.LayoutParams(-1, dp(52)))
        AlertDialog.Builder(this).setTitle("Date et journal d'encaissement").setView(form).setNegativeButton("Annuler", null)
            .setPositiveButton("Continuer") { _, _ -> safely {
                val extra = JSONObject().put("date", date.iso)
                    .put("journal_code", journals.getJSONObject(journal.selectedItemPosition).getString("code"))
                val daysAgo = ChronoUnit.DAYS.between(LocalDate.parse(date.iso), HydriaDates.today())
                check(daysAgo >= 0) { "La date d'encaissement ne peut pas être dans le futur." }
                if (daysAgo <= OLD_COLLECTION_DAYS) confirmBatch("collect", invoices, extra)
                else AlertDialog.Builder(this).setTitle("Date ancienne ?")
                    .setMessage("Cet encaissement serait daté du ${HydriaDates.display(date.iso)}, soit il y a $daysAgo jours. Vérifiez la date avant de continuer : la recette sera comptabilisée à cette date.")
                    .setNegativeButton("Corriger la date") { _, _ -> safely { collect(extra.getString("date"), extra.getString("journal_code")) } }
                    .setPositiveButton("Continuer") { _, _ -> safely { confirmBatch("collect", invoices, extra) } }.show()
            } }.show()
    }
    /** « code · nom » d'un journal de la période ouverte, pour la boîte de confirmation ; le code seul s'il est inconnu. */
    private fun journalLabel(code: String): String {
        val journals = pack?.optJSONArray("journaux") ?: return code
        return (0 until journals.length()).map { journals.getJSONObject(it) }.firstOrNull { it.optString("code") == code }
            ?.let { "${it.optString("code")} · ${it.optString("nom")}" } ?: code
    }
    private fun lastRecap() {
        val current = pack ?: error("Ouvrez une période")
        val id = repository.read("last_recap:${current.getString("ouvrage_id")}:${current.getString("mois")}")?.optString("id") ?: error("Aucun encaissement enregistré ici pour cette période")
        showRecap(id)
    }
    private fun showRecap(id: String) {
        val recap = repository.read("recap:$id") ?: error("Récapitulatif non disponible")
        AlertDialog.Builder(this).setTitle("Récapitulatif d'encaissement")
            .setMessage("${recap.getString("ouvrage")} · ${recap.getString("mois")}\n${recap.getJSONArray("factures").length()} factures · ${recap.getString("total")} Ar\n${recap.getString("date")} · ${recap.getString("journal")}\n${recap.getString("etat")}")
            .setPositiveButton("Imprimer A4 / PDF") { _, _ -> safely { VolumeRecapPrinter.print(this, repository.read("recap:$id")!!) } }
            .setNegativeButton("Fermer", null).show()
    }
    /**
     * Chaque opération a son propre try/catch (CALC_VOL-02) : un refus ne bloque ni les suivantes ni la
     * suite (récapitulatif), qui est toujours appelée. Une opération refusée reste dans la file en
     * erreur ; son message est préfixé par l'ouvrage, le mois et le montant concernés.
     * Une coupure réseau (IOException : délai dépassé, hôte injoignable…) est enregistrée puis arrête la
     * passe, comme QueueSyncEngine : les opérations suivantes échoueraient de la même façon, après avoir
     * chacune attendu leur propre délai (15 s de connexion, 120 s de lecture).
     */
    private fun synchronize(after: () -> Unit = {}) { background {
        val failures = mutableListOf<String>()
        var interrupted = false
        for (item in repository.pending()) {
            val payload = item.getJSONObject("payload")
            fun refused(reason: String) {
                failures += "${runCatching { repository.describe(payload) }.getOrDefault("Opération")} : $reason"
            }
            try {
                val result = repository.syncOne(store.token!!, payload)
                if (!result.successful) refused(result.error)
            } catch (e: java.io.IOException) {
                refused(e.message ?: "Connexion interrompue")
                interrupted = true
                break
            } catch (e: Exception) {
                refused(e.message ?: "Connexion interrompue")
            }
        }
        runOnUiThread { if (!isDestroyed) after() }
        if (failures.isNotEmpty()) {
            val others = if (failures.size > 1) "\n(+ ${failures.size - 1} autre(s) opération(s) refusée(s))" else ""
            val stopped = if (interrupted) "\nSynchronisation interrompue : connexion indisponible. Réessayez avec du réseau." else ""
            error(failures.first() + others + stopped)
        }
    } }

    private fun history() {
        val audits = repository.history()
        if (audits.isEmpty()) { message("Aucune opération volumétrique sur ce téléphone"); return }
        AlertDialog.Builder(this).setTitle("Historique local · 200 dernières opérations")
            .setItems(audits.map { audit ->
                val p = audit.getJSONObject("payload")
                "${p.optString("action")} · ${audit.optString("etat")} · ${p.getJSONArray("factures").length()} facture(s)"
            }.toTypedArray()) { _, index ->
                val audit = audits[index]
                val payload = audit.getJSONObject("payload")
                val id = payload.getString("local_uuid")
                val rows = payload.getJSONArray("factures")
                val total = (0 until rows.length()).map { rows.getJSONObject(it).optString("montant", "0").toBigDecimal() }
                    .fold(BigDecimal.ZERO, BigDecimal::add)
                val detail = "${payload.optString("action")} · $total Ar\nRéférence : $id\n${audit.optString("erreur")}\n${audit.optString("note")}"
                val dialog = AlertDialog.Builder(this).setTitle("Détail de l'opération").setMessage(detail).setPositiveButton("Fermer", null)
                if (repository.read("recap:$id") != null) dialog.setNegativeButton("Réimprimer le récap") { _, _ -> safely { showRecap(id) } }
                if (repository.pending().any { it.getString("local_uuid") == id && it.getJSONObject("payload").has("_sync_conflict") }) {
                    dialog.setNeutralButton("Vérification manuelle") { _, _ ->
                        val note = EditText(this).apply { hint = "Résultat de la vérification et référence comptable" }
                        AlertDialog.Builder(this).setTitle("Clôturer cette opération refusée")
                            .setMessage("Vérifiez le paiement en comptabilité et traitez tout argent reçu avant de clôturer. La trace restera dans l'historique local. Cette action ne comptabilise ni ne rembourse un paiement.")
                            .setView(note).setNegativeButton("Annuler", null)
                            .setPositiveButton("Clôturer après vérification") { _, _ -> safely {
                                repository.reviewConflict(id, note.text.toString()); render()
                            } }.show()
                    }
                }
                dialog.show()
            }.setNegativeButton("Fermer", null).show()
    }
}
