package mg.hydria.app.pointage

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import mg.hydria.app.HydriaApi
import mg.hydria.app.R
import org.json.JSONArray
import java.time.LocalDate
import java.time.ZonedDateTime

/**
 * Rappels de pointage locaux : une notification 10 min avant l'ouverture de chaque créneau
 * que l'employé a déclaré « prévu ». Programmés avec AlarmManager depuis le calendrier
 * renvoyé par le serveur (8 jours), donc sans Firebase et sans réseau au moment du rappel.
 *
 * Alarme inexacte (setAndAllowWhileIdle) : pas de permission spéciale, quelques minutes de
 * tolérance suffisent pour une fenêtre de 2 à 3 heures.
 */
object PointageReminders {
    const val CHANNEL = "pointage_rappels"
    const val LEAD_MINUTES = 10L
    const val EXTRA_TYPE = "type"
    const val EXTRA_DATE = "date"
    const val EXTRA_ACCOUNT = "account"

    data class Trigger(val date: String, val creneau: PointageRules.Creneau, val atMs: Long)

    /** Rappels futurs à programmer, depuis `calendrier` : [{date, matin, aprem, nuit}, …]. */
    fun triggers(calendrier: JSONArray, nowMs: Long): List<Trigger> {
        val result = mutableListOf<Trigger>()
        for (i in 0 until calendrier.length()) {
            val day = calendrier.getJSONObject(i)
            val date = runCatching { LocalDate.parse(day.optString("date")) }.getOrNull() ?: continue
            PointageRules.CRENEAUX.forEach { creneau ->
                if (!day.optBoolean(creneau.type)) return@forEach
                val at = ZonedDateTime.of(date, creneau.debut.minusMinutes(LEAD_MINUTES), PointageRules.ZONE)
                    .toInstant().toEpochMilli()
                if (at > nowMs) result += Trigger(date.toString(), creneau, at)
            }
        }
        return result
    }

    private fun requestCode(trigger: Trigger): Int =
        LocalDate.parse(trigger.date).toEpochDay().toInt() * 3 + PointageRules.CRENEAUX.indexOf(trigger.creneau)

    private fun pendingIntent(context: Context, code: Int, trigger: Trigger?, account: String, flags: Int): PendingIntent? {
        val intent = Intent(context, PointageReminderReceiver::class.java).apply {
            if (trigger != null) {
                putExtra(EXTRA_TYPE, trigger.creneau.type)
                putExtra(EXTRA_DATE, trigger.date)
                putExtra(EXTRA_ACCOUNT, account)
            }
        }
        return PendingIntent.getBroadcast(context, code, intent, flags or PendingIntent.FLAG_IMMUTABLE)
    }

    /** Remplace toutes les alarmes par celles du nouveau calendrier. */
    fun schedule(context: Context, account: String, calendrier: JSONArray) {
        val app = context.applicationContext
        PointageStore.saveUpcoming(account, calendrier)
        val alarms = app.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        PointageStore.alarmCodes().forEach { code ->
            pendingIntent(app, code, null, account, PendingIntent.FLAG_NO_CREATE)?.let(alarms::cancel)
        }
        val codes = mutableSetOf<Int>()
        triggers(calendrier, System.currentTimeMillis()).forEach { trigger ->
            val code = requestCode(trigger)
            val pi = pendingIntent(app, code, trigger, account, PendingIntent.FLAG_UPDATE_CURRENT) ?: return@forEach
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger.atMs, pi)
            codes += code
        }
        PointageStore.saveAlarmCodes(codes)
    }

    /** Après un redémarrage du téléphone (les alarmes sont perdues) ou une mise à jour de l'app. */
    fun rescheduleFromStore(context: Context) {
        schedule(context, PointageStore.upcomingAccount(), PointageStore.upcoming())
    }

    /** Rafraîchit le calendrier depuis le serveur (appelé pendant la synchronisation). Silencieux si hors ligne. */
    fun refreshFromServer(context: Context, token: String, account: String) {
        val response = runCatching { HydriaApi.pointageToday(token) }.getOrNull() ?: return
        if (!response.successful) return
        PointageStore.saveToday(account, response.body)
        response.body.optJSONArray("calendrier")?.let { schedule(context, account, it) }
    }

    /** Créneau déjà pointé (validé, ou enregistré sur le téléphone en attente d'envoi) ? */
    fun dejaFait(account: String, type: String): Boolean {
        if (PointageStore.todayEntries(account).any { it.type == type && it.status != PointageStore.REFUSE }) return true
        val plannings = PointageStore.cachedToday(account)?.optJSONArray("plannings") ?: return false
        for (i in 0 until plannings.length()) {
            val creneaux = plannings.getJSONObject(i).optJSONArray("creneaux") ?: continue
            for (j in 0 until creneaux.length()) {
                val c = creneaux.getJSONObject(j)
                if (c.optString("type") == type && c.optString("statut") == "ok") return true
            }
        }
        return false
    }

    fun notify(context: Context, type: String, date: String, account: String) {
        val creneau = PointageRules.CRENEAUX.firstOrNull { it.type == type } ?: return
        val now = ZonedDateTime.now(PointageRules.ZONE)
        // Alarme retardée (mode veille) : plus de rappel si la fenêtre est passée ou si ce n'est plus le bon jour.
        if (date != now.toLocalDate().toString() || now.toLocalTime() > creneau.fin) return
        if (dejaFait(account, type)) return
        if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return

        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "Rappels de pointage", NotificationManager.IMPORTANCE_HIGH))
        val open = PendingIntent.getActivity(
            context, 0, Intent(context, PointageActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_pointage)
            .setContentTitle("Pointage ${creneau.label.lowercase()}")
            .setContentText("Pointez votre position entre %02dh et %02dh.".format(creneau.debut.hour, creneau.fin.hour))
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        manager.notify(PointageRules.CRENEAUX.indexOf(creneau) + 4200, notification)
    }
}

class PointageReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        PointageReminders.notify(
            context,
            intent.getStringExtra(PointageReminders.EXTRA_TYPE) ?: return,
            intent.getStringExtra(PointageReminders.EXTRA_DATE) ?: return,
            intent.getStringExtra(PointageReminders.EXTRA_ACCOUNT).orEmpty(),
        )
    }
}

class PointageBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED || intent.action == Intent.ACTION_MY_PACKAGE_REPLACED) {
            PointageReminders.rescheduleFromStore(context)
        }
    }
}
