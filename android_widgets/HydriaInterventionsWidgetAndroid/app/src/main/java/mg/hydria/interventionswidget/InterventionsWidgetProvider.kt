package mg.hydria.interventionswidget

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.view.View
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class InterventionsWidgetProvider : AppWidgetProvider() {
    companion object {
        const val ACTION_REFRESH = "mg.hydria.interventionswidget.ACTION_REFRESH"
        const val ACTION_MARK_SEEN = "mg.hydria.interventionswidget.ACTION_MARK_SEEN"
        private const val EXTRA_PLANNING_ID = "planning_id"
        private const val CHANNEL_ID = "hydria_recent_interventions"

        fun requestUpdate(context: Context) {
            context.sendBroadcast(Intent(context, InterventionsWidgetProvider::class.java).setAction(ACTION_REFRESH))
        }
    }

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        // Conserver le dernier contenu pendant une actualisation periodique.
        // Lors du premier ajout, le layout affiche deja "Actualisation…".
        refresh(context)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action != ACTION_REFRESH && intent.action != ACTION_MARK_SEEN) return
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val token = TokenStore.getToken(context)
                val result = when {
                    token == null -> HydriaApi.QueueResult(false, error = "Connectez le widget")
                    intent.action == ACTION_MARK_SEEN -> {
                        val planningId = intent.getStringExtra(EXTRA_PLANNING_ID).orEmpty()
                        if (planningId.isBlank()) HydriaApi.fetchQueue(token) else HydriaApi.markSeen(token, planningId)
                    }
                    else -> HydriaApi.fetchQueue(token)
                }
                updateAll(context, result)
            } finally { pending.finish() }
        }
    }

    private fun refresh(context: Context) {
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val token = TokenStore.getToken(context)
                val result = if (token == null) HydriaApi.QueueResult(false, error = "Touchez pour vous connecter")
                    else HydriaApi.fetchQueue(token)
                updateAll(context, result)
            } finally { pending.finish() }
        }
    }

    private suspend fun updateAll(context: Context, result: HydriaApi.QueueResult) {
        val manager = AppWidgetManager.getInstance(context)
        val ids = manager.getAppWidgetIds(ComponentName(context, InterventionsWidgetProvider::class.java))

        // Afficher les donnees textuelles sans attendre la photo. Une photo
        // volumineuse ne doit jamais laisser le widget bloque sur Actualisation.
        withContext(Dispatchers.Main) {
            ids.forEach { manager.updateAppWidget(it, contentViews(context, it, result, null)) }
            maybeNotify(context, result)
        }

        val token = TokenStore.getToken(context)
        val photo = if (result.success && token != null) {
            result.current?.photos?.firstOrNull { !it.isVideo }?.let {
                HydriaApi.fetchPhoto(token, it.url, 700)
            }
        } else null
        if (photo != null) {
            withContext(Dispatchers.Main) {
                ids.forEach { manager.updateAppWidget(it, contentViews(context, it, result, photo)) }
            }
        }
    }

    private fun contentViews(context: Context, widgetId: Int, result: HydriaApi.QueueResult, photo: android.graphics.Bitmap?): RemoteViews {
        return RemoteViews(context.packageName, R.layout.interventions_widget).apply {
            setTextViewText(R.id.widget_unseen, result.weekCount.toString())
            val item = result.current
            when {
                !result.success -> {
                    setTextViewText(R.id.widget_activity, "Widget indisponible")
                    setTextViewText(R.id.widget_ouvrage, result.error ?: "Erreur de chargement")
                    setTextViewText(R.id.widget_employee, "Touchez pour configurer")
                    setViewVisibility(R.id.widget_seen, View.GONE)
                }
                item == null -> {
                    setTextViewText(R.id.widget_activity, "Tout est vu")
                    setTextViewText(R.id.widget_ouvrage, "Aucune nouvelle réparation")
                    setTextViewText(R.id.widget_employee, "Hydria est à jour")
                    setViewVisibility(R.id.widget_seen, View.GONE)
                }
                else -> {
                    setTextViewText(R.id.widget_activity, item.activity)
                    setTextViewText(R.id.widget_ouvrage, item.ouvrage)
                    setTextViewText(R.id.widget_employee, listOf(item.employee, item.base).filter { it.isNotBlank() }.joinToString(" · "))
                    setTextViewText(R.id.widget_date, item.createdAt)
                    setViewVisibility(R.id.widget_seen, View.VISIBLE)
                }
            }
            if (photo != null) {
                setImageViewBitmap(R.id.widget_photo, photo)
                setViewVisibility(R.id.widget_photo, View.VISIBLE)
            } else setViewVisibility(R.id.widget_photo, View.GONE)
            bindCommonActions(context, this, widgetId, item)
        }
    }

    private fun bindCommonActions(context: Context, views: RemoteViews, widgetId: Int, item: HydriaApi.Intervention?) {
        val detailClass = if (TokenStore.getToken(context) == null) ConfigActivity::class.java else DetailActivity::class.java
        val openIntent = Intent(context, detailClass).putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
        views.setOnClickPendingIntent(R.id.widget_content, PendingIntent.getActivity(context, widgetId, openIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        val refreshIntent = Intent(context, InterventionsWidgetProvider::class.java).setAction(ACTION_REFRESH)
        views.setOnClickPendingIntent(R.id.widget_refresh, PendingIntent.getBroadcast(context, widgetId, refreshIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        if (item != null) {
            val seenIntent = Intent(context, InterventionsWidgetProvider::class.java).setAction(ACTION_MARK_SEEN).putExtra(EXTRA_PLANNING_ID, item.id)
            views.setOnClickPendingIntent(R.id.widget_seen, PendingIntent.getBroadcast(context, item.id.hashCode(), seenIntent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
        }
    }

    private fun maybeNotify(context: Context, result: HydriaApi.QueueResult) {
        if (!result.success) return
        val previous = TokenStore.getLastUnseen(context)
        TokenStore.saveLastUnseen(context, result.unseenCount)
        val latest = result.latestEvent ?: return
        val previousEventId = TokenStore.getLastEventId(context)
        TokenStore.saveLastEventId(context, latest.id)
        if (previousEventId == null || previousEventId == latest.id) return
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "Nouvelles réparations Hydria", NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(context, 991, Intent(context, DetailActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        manager.notify(991, NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Nouvelle réparation Hydria")
            .setContentText("${latest.activity} · ${latest.ouvrage}")
            .setNumber(result.unseenCount).setAutoCancel(true).setContentIntent(open).build())
    }
}
