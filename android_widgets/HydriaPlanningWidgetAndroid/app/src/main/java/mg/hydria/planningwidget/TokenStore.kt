package mg.hydria.planningwidget

import android.content.Context

object TokenStore {
    private const val PREFS = "hydria_planning_widget"
    private const val TOKEN = "token"
    private const val MONTH_OFFSET = "month_offset"
    // Jour actuellement selectionne dans le calendrier (agenda affiche en dessous),
    // au format ISO yyyy-MM-dd. Vide = pas de selection explicite -> defaut
    // (aujourd'hui si le mois affiche est le mois courant, sinon 1er du mois affiche).
    private const val SELECTED_DATE_ISO = "selected_date_iso"
    private const val FILTRE_EMPLOYE = "filtre_employe"
    private const val FILTRE_BASE = "filtre_base"
    private const val FILTRE_REGION = "filtre_region"
    private const val FILTRE_DISTRICT = "filtre_district"
    private const val FILTRE_COMMUNE = "filtre_commune"
    private const val FILTRE_TYPES = "filtre_types"

    fun saveToken(context: Context, value: String) = prefs(context).edit().putString(TOKEN, value).apply()
    fun getToken(context: Context): String? = prefs(context).getString(TOKEN, null)
    fun clear(context: Context) = prefs(context).edit().clear().apply()
    fun getMonthOffset(context: Context): Int = prefs(context).getInt(MONTH_OFFSET, 0)
    fun saveMonthOffset(context: Context, value: Int) = prefs(context).edit().putInt(MONTH_OFFSET, value).apply()
    fun getSelectedDateIso(context: Context): String? = prefs(context).getString(SELECTED_DATE_ISO, null)
    fun saveSelectedDateIso(context: Context, value: String?) = prefs(context).edit().putString(SELECTED_DATE_ISO, value).apply()

    // "all" = pas de filtre (identique a la convention du widget web).
    fun getFiltreEmploye(context: Context): String = prefs(context).getString(FILTRE_EMPLOYE, "all") ?: "all"
    fun getFiltreBase(context: Context): String = prefs(context).getString(FILTRE_BASE, "all") ?: "all"
    fun getFiltreRegion(context: Context): String = prefs(context).getString(FILTRE_REGION, "all") ?: "all"
    fun getFiltreDistrict(context: Context): String = prefs(context).getString(FILTRE_DISTRICT, "all") ?: "all"
    fun getFiltreCommune(context: Context): String = prefs(context).getString(FILTRE_COMMUNE, "all") ?: "all"
    // Identifiants de type d'activite selectionnes, separes par des virgules (vide = tous).
    fun getFiltreTypes(context: Context): List<String> {
        val raw = prefs(context).getString(FILTRE_TYPES, "") ?: ""
        return if (raw.isBlank()) emptyList() else raw.split(",").filter { it.isNotBlank() }
    }

    fun saveFiltres(
        context: Context,
        employeId: String,
        baseId: String,
        regionId: String,
        districtId: String,
        communeId: String,
        typeIds: List<String>,
    ) {
        prefs(context).edit()
            .putString(FILTRE_EMPLOYE, employeId)
            .putString(FILTRE_BASE, baseId)
            .putString(FILTRE_REGION, regionId)
            .putString(FILTRE_DISTRICT, districtId)
            .putString(FILTRE_COMMUNE, communeId)
            .putString(FILTRE_TYPES, typeIds.joinToString(","))
            .apply()
    }

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
