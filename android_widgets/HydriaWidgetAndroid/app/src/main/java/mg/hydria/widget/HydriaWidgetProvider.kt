package mg.hydria.widget

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.view.View
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * App Widget Android classique (posé sur l'écran d'accueil, comme un
 * widget météo natif) affichant les mêmes 6 stats Hydria que le widget
 * desktop Electron : ouvrages, points d'eau, factures non pointées,
 * paiements forfaitaires à collecter aujourd'hui, réparations non
 * terminées, réparations à faire sous 7 jours.
 *
 * Séparé volontairement du widget "bouton flottant" (HydriaFloatingAndroid)
 * : celui-ci n'affiche QUE des données Hydria, pas de météo ni de menu
 * d'actions — un widget, une responsabilité.
 */
class HydriaWidgetProvider : AppWidgetProvider() {

    companion object {
        const val ACTION_REFRESH = "mg.hydria.widget.ACTION_REFRESH"
        private const val PAYMENT_CHANNEL_ID = "hydria_payment_changes"
        // CRITICAL : l'API expose deux découpages distincts pour ces stats
        // (cf. apps/core/views_widget.py, commentaire ligne ~1135) —
        // "_mises_a_jour_mois_courant_non_pointees" = récence d'ÉDITION de la
        // ligne en base (updated_at), alors que "_mois_courant_non_pointees"
        // = mois de la FACTURE elle-même (date_facture / mois du relevé + 1).
        // Les libellés "· Septembre" / "· avant Septembre" ci-dessous portent
        // sur la date de facture : utiliser les clés "_mois_courant"/"_mois_passes",
        // comme le fait déjà le widget desktop Electron (widget_meteo.html) —
        // sinon une facture du mois en cours mais non retouchée depuis
        // apparaît à tort dans "avant {MOIS}".
        private val paymentKeys = linkedMapOf<String, () -> String>(
            "factures_volumetriques_mois_courant_non_pointees" to { "Volumes non pointés · ${currentMonthLabel()}" },
            "factures_volumetriques_mois_passes_non_pointees" to { "Volumes non pointés · avant ${currentMonthLabel()}" },
            "factures_forfaitaires_mois_courant_non_pointees" to { "Forfaits non pointés · ${currentMonthLabel()}" },
            "factures_forfaitaires_mois_passes_non_pointees" to { "Forfaits non pointés · avant ${currentMonthLabel()}" },
            "diamex_748411_sans_scan_non_pointes" to { "DiameX forfaitaire à scanner" },
            "diamex_748411_avec_scan_non_pointes" to { "DiameX forfaitaire à pointer" },
            "diamex_707401_sans_scan_non_pointes" to { "DiameX volume à scanner" },
            "diamex_707401_avec_scan_non_pointes" to { "DiameX volume à pointer" },
            "factures_forfaitaires_a_collecter_aujourdhui" to { "Forfaits à collecter aujourd'hui" },
        )

        private fun currentMonthLabel(): String = java.text.SimpleDateFormat(
            "MMMM",
            java.util.Locale.FRANCE,
        ).format(java.util.Date()).replaceFirstChar { character ->
            if (character.isLowerCase()) character.titlecase(java.util.Locale.FRANCE)
            else character.toString()
        }

        fun requestUpdate(context: Context) {
            val intent = Intent(context, HydriaWidgetProvider::class.java).apply {
                action = ACTION_REFRESH
            }
            context.sendBroadcast(intent)
        }

        private fun detailPendingIntent(
            context: Context, appWidgetId: Int, requestCodeOffset: Int, statType: String, label: String
        ): android.app.PendingIntent {
            val intent = Intent(context, DetailActivity::class.java).apply {
                putExtra(DetailActivity.EXTRA_STAT_TYPE, statType)
                putExtra(DetailActivity.EXTRA_LABEL, label)
                putExtra(DetailActivity.EXTRA_APP_WIDGET_ID, appWidgetId)
                // FLAG_ACTIVITY_NEW_TASK requis : on lance une Activity
                // depuis un contexte non-Activity (RemoteViews/widget).
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            // requestCode unique par widget ET par tuile — sinon les
            // PendingIntent des différentes tuiles s'écrasent entre eux
            // (Android les considère alors comme "le même" clic possible).
            val requestCode = appWidgetId * 100 + requestCodeOffset
            return android.app.PendingIntent.getActivity(
                context, requestCode, intent,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE
            )
        }

        /**
         * Met à jour un widget. onFinished est appelé une fois le TRAVAIL
         * RÉELLEMENT terminé (y compris après la requête réseau
         * asynchrone) — voir onUpdate/onReceive pour pourquoi c'est
         * nécessaire (goAsync).
         */
        private fun updateWidget(
            context: Context,
            appWidgetManager: AppWidgetManager,
            appWidgetId: Int,
            onFinished: () -> Unit,
        ) {
            val views = RemoteViews(context.packageName, R.layout.hydria_widget)

            // Ouvre l'activité de config au tap sur le titre (permet de
            // se reconnecter/changer de compte sans devoir retirer et
            // recoller le widget).
            val configIntent = Intent(context, ConfigActivity::class.java).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
            }
            val configPendingIntent = android.app.PendingIntent.getActivity(
                context, appWidgetId, configIntent,
                android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.widget_title, configPendingIntent)
            views.setOnClickPendingIntent(R.id.widget_filters, configPendingIntent)
            val refreshIntent = Intent(context, HydriaWidgetProvider::class.java).apply {
                action = ACTION_REFRESH
            }
            val refreshPendingIntent = PendingIntent.getBroadcast(
                context,
                appWidgetId * 100 + 99,
                refreshIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            views.setOnClickPendingIntent(R.id.widget_refresh, refreshPendingIntent)

            val filters = TokenStore.getFilters(context, appWidgetId)
            views.setTextViewText(R.id.widget_filters, filters.displaySummary())
            val currentMonth = currentMonthLabel()

            // Liste défilante (un RemoteViews ne défile que via une collection) : les lignes sont fournies par
            // HydriaWidgetService depuis WidgetRowStore ; chaque tuile ouvre DetailActivity via ce modèle
            // d'intent complété (fill-in) par le type de stat et le libellé de la tuile.
            val serviceIntent = Intent(context, HydriaWidgetService::class.java).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
                data = android.net.Uri.parse(toUri(Intent.URI_INTENT_SCHEME))
            }
            views.setRemoteAdapter(R.id.widget_list, serviceIntent)
            val detailTemplate = Intent(context, DetailActivity::class.java).apply {
                putExtra(DetailActivity.EXTRA_APP_WIDGET_ID, appWidgetId)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            views.setPendingIntentTemplate(
                R.id.widget_list,
                android.app.PendingIntent.getActivity(
                    context, appWidgetId * 100 + 50, detailTemplate,
                    android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_MUTABLE
                )
            )

            appWidgetManager.updateAppWidget(appWidgetId, views)

            val token = TokenStore.getToken(context)
            if (token == null) {
                views.setTextViewText(R.id.widget_status, "Non connecté — taper le titre")
                appWidgetManager.updateAppWidget(appWidgetId, views)
                onFinished()
                return
            }

            views.setTextViewText(R.id.widget_status, "Chargement…")
            appWidgetManager.updateAppWidget(appWidgetId, views)

            // CRITICAL : sans goAsync() (voir onUpdate/onReceive), Android
            // peut considérer le BroadcastReceiver "terminé" dès le retour
            // de cette fonction et tuer le processus avant que cette
            // coroutine réseau ait fini — d'où les tirets "—" jamais
            // remplacés par les vraies stats malgré un appel réussi.
            CoroutineScope(Dispatchers.Main).launch {
                try {
                    val result = HydriaApi.fetchStats(token, filters)
                    if (result.success && result.stats != null) {
                        val stats = result.stats
                        maybeNotifyPaymentChanges(context, appWidgetId, stats)
                        // Compteurs « fait » : null si le serveur n'a pas encore l'API (404) → section masquée.
                        val realisations = HydriaApi.fetchRealisations(
                            token, filters, TokenStore.getRealisationsPeriode(context, appWidgetId),
                        )
                        WidgetRowStore.save(context, appWidgetId, buildRows(stats, currentMonth, realisations))
                        appWidgetManager.notifyAppWidgetViewDataChanged(appWidgetId, R.id.widget_list)

                        val now = java.text.SimpleDateFormat("HH:mm", java.util.Locale.FRANCE).format(java.util.Date())
                        views.setTextViewText(
                            R.id.widget_diamex_import,
                            "Dernière importation DiameX : ${result.lastDiamexImport ?: "inconnue"}",
                        )
                        views.setTextViewText(R.id.widget_status, "Mis à jour à $now")
                    } else {
                        views.setTextViewText(R.id.widget_status, result.error ?: "Erreur de chargement")
                        if (result.error == "Session expirée") {
                            TokenStore.clearToken(context)
                        }
                    }
                    appWidgetManager.updateAppWidget(appWidgetId, views)
                } finally {
                    onFinished()
                }
            }
        }

        private fun formatNumber(value: Double?): String {
            return value?.toLong()?.toString() ?: "—"
        }

        private fun formatKAr(value: Double?): String {
            if (value == null) return ""
            val amount = value / 1000.0
            return java.text.DecimalFormat("0.#").format(amount) + " K Ar"
        }

        private class Item(
            val key: String, val color: String, val label: String,
            val detailType: String, val detailLabel: String,
            val amount: Boolean = false,
        )

        /** Libellé + « 🏗️ N ouvrages [· 🚰 M pts d'eau] » (l'ouvrage d'abord). */
        private fun scopeLabel(stats: Map<String, Double>, key: String, baseLabel: String, withPoints: Boolean): String {
            val ouvrages = stats["${key}_ouvrages"] ?: return baseLabel
            val parts = mutableListOf("🏗️ ${ouvrages.toLong()} ouvrage${if (ouvrages > 1) "s" else ""}")
            if (withPoints) {
                stats["${key}_points_eau"]?.let { parts += "🚰 ${it.toLong()} pt${if (it > 1) "s" else ""} d'eau" }
            }
            return baseLabel + "\n" + parts.joinToString(" · ")
        }

        /** Libellé + « Forfait X · Volume Y · Mixte Z… » (les valeurs à 0 sont masquées). */
        private fun breakdownLabel(stats: Map<String, Double>, baseLabel: String, vararg parts: Pair<String, String>): String {
            if (parts.none { stats.containsKey(it.second) }) return baseLabel
            val text = parts
                .filter { (stats[it.second] ?: 0.0) > 0 }
                .joinToString(" · ") { "${it.first} ${stats[it.second]!!.toLong()}" }
            return if (text.isEmpty()) baseLabel else baseLabel + "\n" + text
        }

        /** Tuiles non nulles d'un groupe, rangées deux par ligne, avec un titre de section s'il y en a un. */
        private fun groupRows(stats: Map<String, Double>, title: String?, items: List<Item>): List<WidgetRow> {
            val tiles = items.filter { (stats[it.key] ?: 0.0) > 0 }.map {
                WidgetTile(
                    formatNumber(stats[it.key]), it.color, it.label,
                    if (it.amount) formatKAr(stats["${it.key}_montant"]) else "",
                    it.detailType, it.detailLabel,
                )
            }
            if (tiles.isEmpty()) return emptyList()
            val rows = mutableListOf<WidgetRow>()
            if (title != null) rows += WidgetRow.Header(title)
            tiles.chunked(2).forEach { rows += WidgetRow.Tiles(it[0], it.getOrNull(1)) }
            return rows
        }

        private fun estimateRows(stats: Map<String, Double>, currentKey: String, olderKey: String, month: String): List<WidgetRow> {
            val current = stats[currentKey] ?: 0.0
            val older = stats[olderKey] ?: 0.0
            if (current <= 0 && older <= 0) return emptyList()
            return listOf(WidgetRow.Note("≈ Impayé estimé · $month ${formatKAr(current)} · avant $month ${formatKAr(older)}"))
        }

        /** Compteurs « fait » affichés, dans l'ordre du widget Electron (REALISATIONS_DEFS). */
        private val realisationsDefs = listOf(
            Triple("pointages_volume", "💧 Volumes pointés", true),
            Triple("pointages_forfait", "💰 Forfaits pointés", true),
            Triple("indemnites_rbf_payees", "🪙 Indemnités RBF payées", true),
            Triple("reparations_terminees", "🔧 Réparations terminées", false),
            Triple("rehabilitations_terminees", "🏗️ Réhabilitations terminées", false),
            Triple("installations_terminees", "🚰 Installations terminées", false),
            Triple("autres_activites_terminees", "📆 Autres activités terminées", false),
        )

        /** periode → (titre de section, libellé de la période précédente à date équivalente). */
        private val periodes = mapOf(
            "jour" to ("FAIT AUJOURD'HUI" to "hier même heure"),
            "semaine" to ("FAIT CETTE SEMAINE" to "sem. dernière"),
            "mois" to ("FAIT CE MOIS-CI" to "mois dernier"),
        )

        private fun realisationsRows(data: HydriaApi.RealisationsResult?): List<WidgetRow> {
            if (data == null) return emptyList()
            val periode = data.periode.takeIf { it in periodes } ?: "jour"
            val (title, previousLabel) = periodes.getValue(periode)
            val tiles = realisationsDefs.mapNotNull { (key, label, withAmount) ->
                val bloc = data.compteurs[key] ?: return@mapNotNull null
                if (bloc.courant <= 0 && bloc.precedent <= 0) return@mapNotNull null
                val diff = bloc.courant - bloc.precedent
                val delta = when {
                    diff > 0 -> "▲ +$diff"
                    diff < 0 -> "▼ −${-diff}"
                    else -> "="
                } + " vs $previousLabel (${bloc.precedent})"
                val amount = if (withAmount) formatKAr(bloc.montant) + "\n" + delta else delta
                WidgetTile(bloc.courant.toString(), "#B9F3DF", label, amount, "", "")
            }
            val rows = mutableListOf<WidgetRow>(WidgetRow.Periode(title, periode))
            if (tiles.isEmpty()) rows += WidgetRow.Note("Rien de réalisé sur la période pour l'instant.")
            tiles.chunked(2).forEach { rows += WidgetRow.Tiles(it[0], it.getOrNull(1)) }
            val suivi = data.suiviDepuis?.let { iso ->
                runCatching {
                    val d = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.FRANCE).parse(iso.take(10))!!
                    "Suivi depuis le " + java.text.SimpleDateFormat("dd/MM/yyyy", java.util.Locale.FRANCE).format(d)
                }.getOrNull()
            } ?: "Suivi en cours de démarrage"
            rows += WidgetRow.Note("$suivi · RBF selon la dernière importation DiameX")
            return rows
        }

        private fun buildRows(
            stats: Map<String, Double>,
            month: String,
            realisations: HydriaApi.RealisationsResult? = null,
        ): List<WidgetRow> {
            fun scope(key: String, label: String, withPoints: Boolean) = scopeLabel(stats, key, label, withPoints)
            val rows = mutableListOf<WidgetRow>()

            rows += groupRows(stats, null, listOf(
                Item("ouvrages", "#FFFFFF",
                    breakdownLabel(stats, "🏗️ Ouvrages",
                        "Forfait" to "ouvrages_forfaitaires", "Volume" to "ouvrages_volumetriques",
                        "Mixte" to "ouvrages_mixtes", "Sans tarif" to "ouvrages_sans_tarif"),
                    "ouvrages", "🏗️ Ouvrages"),
                Item("points_eau", "#FFFFFF",
                    breakdownLabel(stats, "🚰 Points d'eau",
                        "Forfait" to "points_eau_forfaitaires", "Volume" to "points_eau_volumetriques",
                        "Coupés" to "points_eau_coupes", "Sans date" to "points_eau_sans_date"),
                    "points_eau", "🚰 Points d'eau"),
            ))
            // Même place que dans le widget Electron : juste après les compteurs généraux.
            rows += realisationsRows(realisations)

            rows += groupRows(stats, "VOLUMÉTRIQUE", listOf(
                Item("factures_volumetriques_mois_courant_non_pointees", "#FFD27A",
                    scope("factures_volumetriques_mois_courant_non_pointees", "💧 $month", true),
                    "factures_volumetriques_mois_courant_non_pointees", "💧 Volumes non pointés · $month", true),
                Item("factures_volumetriques_mois_passes_non_pointees", "#FFD27A",
                    scope("factures_volumetriques_mois_passes_non_pointees", "💧 Avant $month", true),
                    "factures_volumetriques_mois_passes_non_pointees", "💧 Volumes non pointés · avant $month", true),
                Item("diamex_707401_sans_scan_non_pointes", "#FFD27A", "📷 Sans scan · à scanner",
                    "diamex_707401_sans_scan_non_pointes", "📷 DiameX volume à scanner", true),
                Item("diamex_707401_avec_scan_non_pointes", "#FFD27A", "🧾 Avec scan · à pointer",
                    "diamex_707401_avec_scan_non_pointes", "🧾 DiameX volume à pointer", true),
            ))
            rows += estimateRows(stats, "estimation_impayee_volumetrique_mois_courant",
                "estimation_impayee_volumetrique_mois_anciens", month)

            rows += groupRows(stats, "FORFAITAIRE", listOf(
                Item("factures_forfaitaires_mois_courant_non_pointees", "#FFD27A",
                    scope("factures_forfaitaires_mois_courant_non_pointees", "💰 $month", true),
                    "factures_forfaitaires_mois_courant_non_pointees", "💰 Forfaits non pointés · $month", true),
                Item("factures_forfaitaires_mois_passes_non_pointees", "#FFD27A",
                    scope("factures_forfaitaires_mois_passes_non_pointees", "💰 Avant $month", true),
                    "factures_forfaitaires_mois_passes_non_pointees", "💰 Forfaits non pointés · avant $month", true),
                Item("diamex_748411_sans_scan_non_pointes", "#FFD27A", "📷 Sans scan · à scanner",
                    "diamex_748411_sans_scan_non_pointes", "📷 DiameX forfaitaire à scanner", true),
                Item("diamex_748411_avec_scan_non_pointes", "#FFD27A", "🧾 Avec scan · à pointer",
                    "diamex_748411_avec_scan_non_pointes", "🧾 DiameX forfaitaire à pointer", true),
            ))
            rows += estimateRows(stats, "estimation_impayee_forfaitaire_mois_courant",
                "estimation_impayee_forfaitaire_mois_anciens", month)

            rows += groupRows(stats, null, listOf(
                Item("factures_forfaitaires_a_collecter_aujourdhui", "#FFD27A",
                    scope("factures_forfaitaires_a_collecter_aujourdhui", "📅 Forfait aujourd'hui", true),
                    "factures_forfaitaires_jour", "📅 Forfait à collecter aujourd'hui", true),
                Item("rbf_points_depassement_plafond", "#FF8A80", "🚨 RBF au-dessus du plafond",
                    "rbf_points_depassement_plafond", "🚨 Indemnités RBF · au-dessus du plafond"),
                Item("rbf_points_sans_paiement_effectif", "#FF8A80", "🚫 RBF sans paiement effectif",
                    "rbf_points_sans_paiement_effectif", "🚫 Indemnités RBF · sans paiement effectif"),
            ))

            listOf(
                Triple("RÉPARATIONS", "reparations", "🔧 Réparations"),
                Triple("RÉHABILITATIONS", "rehabilitations", "🏗️ Réhabilitations"),
                Triple("INSTALLATIONS", "installations", "🚰 Installations"),
                Triple("AUTRES ACTIVITÉS", "autres_activites", "❗ Autres activités"),
            ).forEach { (title, prefix, detail) ->
                rows += groupRows(stats, title, listOf(
                    Item("${prefix}_echues", "#FF9B8F", scope("${prefix}_echues", "⚠️ Échues", false),
                        "${prefix}_echues", "$detail · échues"),
                    Item("${prefix}_a_venir", "#FFD27A", scope("${prefix}_a_venir", "📆 À venir", false),
                        "${prefix}_a_venir", "$detail · à venir"),
                ))
            }
            return rows
        }

        private fun maybeNotifyPaymentChanges(context: Context, appWidgetId: Int, stats: Map<String, Double>) {
            val current = JSONObject()
            paymentKeys.keys.forEach { key -> current.put(key, (stats[key] ?: 0.0).toInt()) }
            val previousRaw = TokenStore.getPaymentSnapshot(context, appWidgetId)
            TokenStore.savePaymentSnapshot(context, appWidgetId, current.toString())
            if (previousRaw.isNullOrBlank()) return

            val previous = runCatching { JSONObject(previousRaw) }.getOrNull() ?: return
            val changes = paymentKeys.mapNotNull { (key, label) ->
                val before = previous.optInt(key, 0)
                val after = current.optInt(key, 0)
                if (before == after) null else "${label()} : $before → $after"
            }
            if (changes.isEmpty()) return
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) return

            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(
                PAYMENT_CHANNEL_ID,
                "Changements de paiements Hydria",
                NotificationManager.IMPORTANCE_DEFAULT,
            ))
            val open = PendingIntent.getActivity(
                context,
                1700 + appWidgetId,
                Intent(context, ConfigActivity::class.java).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
            val body = changes.take(3).joinToString(" · ") +
                if (changes.size > 3) " · +${changes.size - 3} autre(s)" else ""
            manager.notify(1700 + appWidgetId, NotificationCompat.Builder(context, PAYMENT_CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("Paiements Hydria actualisés")
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setContentIntent(open)
                .build())
        }
    }

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        val pendingResult: BroadcastReceiver.PendingResult = goAsync()
        var remaining = appWidgetIds.size
        if (remaining == 0) {
            pendingResult.finish()
            return
        }
        appWidgetIds.forEach { id ->
            updateWidget(context, appWidgetManager, id) {
                remaining--
                if (remaining <= 0) {
                    runCatching { pendingResult.finish() }
                }
            }
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_REFRESH) {
            val pendingResult: BroadcastReceiver.PendingResult = goAsync()
            val appWidgetManager = AppWidgetManager.getInstance(context)
            val ids = appWidgetManager.getAppWidgetIds(
                android.content.ComponentName(context, HydriaWidgetProvider::class.java)
            )
            if (ids.isEmpty()) {
                pendingResult.finish()
                return
            }
            var remaining = ids.size
            ids.forEach { id ->
                updateWidget(context, appWidgetManager, id) {
                    remaining--
                    if (remaining <= 0) {
                        runCatching { pendingResult.finish() }
                    }
                }
            }
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        appWidgetIds.forEach {
            TokenStore.clearFilters(context, it)
            WidgetRowStore.clear(context, it)
        }
        super.onDeleted(context, appWidgetIds)
    }
}
