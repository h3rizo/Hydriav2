package mg.hydria.widget

import android.content.Context

/**
 * Stockage local du token d'authentification Hydria (obtenu via
 * /widget/api/login/, voir HydriaApi.kt). Même principe que le widget
 * desktop Electron : connexion une fois, token réutilisé ensuite pour
 * tous les rafraîchissements automatiques du widget.
 */
object TokenStore {
    private const val PREFS_NAME = "hydria_widget_prefs"
    private const val KEY_TOKEN = "hydria_token"
    private const val KEY_PAYMENT_SNAPSHOT_PREFIX = "payment_snapshot_"
    private const val KEY_REALISATIONS_PERIODE_PREFIX = "realisations_periode_"

    data class Filters(
        val organisationId: String = "all",
        val employeeId: String = "all",
        val regionId: String = "all",
        val districtId: String = "all",
        val communeId: String = "all",
        val organisationName: String = "Toutes les organisations",
        val employeeName: String = "Tous les agents de recouvrement",
        val regionName: String = "Toutes les régions",
        val districtName: String = "Tous les districts",
        val communeName: String = "Toutes les communes",
    ) {
        fun displaySummary(): String {
            val values = mutableListOf<String>()
            if (organisationId != "all") values += organisationName
            if (employeeId != "all") values += employeeName
            if (regionId != "all") values += regionName
            if (districtId != "all") values += districtName
            if (communeId != "all") values += communeName
            return if (values.isEmpty()) "Tous les périmètres" else values.joinToString(" · ")
        }
    }

    fun saveToken(context: Context, token: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_TOKEN, token)
            .apply()
    }

    fun getToken(context: Context): String? {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_TOKEN, null)
    }

    fun clearToken(context: Context) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_TOKEN)
            .apply()
    }

    fun getPaymentSnapshot(context: Context, appWidgetId: Int): String? =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString("$KEY_PAYMENT_SNAPSHOT_PREFIX$appWidgetId", null)

    fun savePaymentSnapshot(context: Context, appWidgetId: Int, value: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString("$KEY_PAYMENT_SNAPSHOT_PREFIX$appWidgetId", value).apply()
    }

    /** Période des compteurs « fait » (jour | semaine | mois), mémorisée par widget. */
    fun getRealisationsPeriode(context: Context, appWidgetId: Int): String =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString("$KEY_REALISATIONS_PERIODE_PREFIX$appWidgetId", null)
            ?.takeIf { it in listOf("jour", "semaine", "mois") } ?: "jour"

    fun saveRealisationsPeriode(context: Context, appWidgetId: Int, periode: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString("$KEY_REALISATIONS_PERIODE_PREFIX$appWidgetId", periode).apply()
    }

    fun saveFilters(context: Context, appWidgetId: Int, filters: Filters) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(filterKey(appWidgetId, "organisation"), filters.organisationId)
            .putString(filterKey(appWidgetId, "employee"), filters.employeeId)
            .putString(filterKey(appWidgetId, "region"), filters.regionId)
            .putString(filterKey(appWidgetId, "district"), filters.districtId)
            .putString(filterKey(appWidgetId, "commune"), filters.communeId)
            .putString(filterKey(appWidgetId, "organisation_name"), filters.organisationName)
            .putString(filterKey(appWidgetId, "employee_name"), filters.employeeName)
            .putString(filterKey(appWidgetId, "region_name"), filters.regionName)
            .putString(filterKey(appWidgetId, "district_name"), filters.districtName)
            .putString(filterKey(appWidgetId, "commune_name"), filters.communeName)
            .apply()
    }

    fun getFilters(context: Context, appWidgetId: Int): Filters {
        val preferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return Filters(
            organisationId = preferences.getString(filterKey(appWidgetId, "organisation"), "all") ?: "all",
            employeeId = preferences.getString(filterKey(appWidgetId, "employee"), "all") ?: "all",
            regionId = preferences.getString(filterKey(appWidgetId, "region"), "all") ?: "all",
            districtId = preferences.getString(filterKey(appWidgetId, "district"), "all") ?: "all",
            communeId = preferences.getString(filterKey(appWidgetId, "commune"), "all") ?: "all",
            organisationName = preferences.getString(filterKey(appWidgetId, "organisation_name"), "Toutes les organisations") ?: "Toutes les organisations",
            employeeName = preferences.getString(filterKey(appWidgetId, "employee_name"), "Tous les agents de recouvrement") ?: "Tous les agents de recouvrement",
            regionName = preferences.getString(filterKey(appWidgetId, "region_name"), "Toutes les régions") ?: "Toutes les régions",
            districtName = preferences.getString(filterKey(appWidgetId, "district_name"), "Tous les districts") ?: "Tous les districts",
            communeName = preferences.getString(filterKey(appWidgetId, "commune_name"), "Toutes les communes") ?: "Toutes les communes",
        )
    }

    fun clearFilters(context: Context, appWidgetId: Int) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .remove(filterKey(appWidgetId, "organisation"))
            .remove(filterKey(appWidgetId, "employee"))
            .remove(filterKey(appWidgetId, "region"))
            .remove(filterKey(appWidgetId, "district"))
            .remove(filterKey(appWidgetId, "commune"))
            .remove(filterKey(appWidgetId, "organisation_name"))
            .remove(filterKey(appWidgetId, "employee_name"))
            .remove(filterKey(appWidgetId, "region_name"))
            .remove(filterKey(appWidgetId, "district_name"))
            .remove(filterKey(appWidgetId, "commune_name"))
            .remove("$KEY_PAYMENT_SNAPSHOT_PREFIX$appWidgetId")
            .remove("$KEY_REALISATIONS_PERIODE_PREFIX$appWidgetId")
            .apply()
    }

    private fun filterKey(appWidgetId: Int, name: String) = "widget_${appWidgetId}_filter_$name"
}
