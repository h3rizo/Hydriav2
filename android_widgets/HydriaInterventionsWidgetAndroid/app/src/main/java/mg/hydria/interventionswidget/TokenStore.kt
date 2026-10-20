package mg.hydria.interventionswidget

import android.content.Context

object TokenStore {
    private const val PREFS = "hydria_interventions_widget"
    private const val TOKEN = "token"
    private const val LAST_UNSEEN = "last_unseen"
    private const val LAST_EVENT_ID = "last_event_id"

    fun saveToken(context: Context, value: String) = prefs(context).edit().putString(TOKEN, value).apply()
    fun getToken(context: Context): String? = prefs(context).getString(TOKEN, null)
    fun clear(context: Context) = prefs(context).edit().clear().apply()
    fun getLastUnseen(context: Context): Int = prefs(context).getInt(LAST_UNSEEN, -1)
    fun saveLastUnseen(context: Context, value: Int) = prefs(context).edit().putInt(LAST_UNSEEN, value).apply()
    fun getLastEventId(context: Context): String? = prefs(context).getString(LAST_EVENT_ID, null)
    fun saveLastEventId(context: Context, value: String) = prefs(context).edit().putString(LAST_EVENT_ID, value).apply()
    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
