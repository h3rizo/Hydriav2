package mg.hydria.shared.database

import org.json.JSONObject

/**
 * Facade Android pour la memoire de la calculatrice de salaire (table
 * calculatorState) et le cache local des baremes serveur actifs (table
 * salaryCalculationConfig), cf. Calculator.sq. Miroir de
 * TerrainDatabase.saveCalculatorState()/calculatorState()/
 * clearCalculatorMemory()/activeSalaryConfig()/salaryConfigChecksum()/
 * replaceActiveSalaryConfig() (app/).
 *
 * BRANCHEE SUR L'APP : CalculatorRepository/SalaryConfigRepository (app/)
 * passent desormais par OfflineStore, qui migre une fois au demarrage le
 * brouillon calculatorState existant (le bareme salaryCalculationConfig,
 * lui, est un cache serveur resynchronise par checksum - pas de migration
 * necessaire) puis route tout ici, avec le meme filet de secours que
 * HydriaSyncQueueGateway.
 */
object HydriaCalculatorGateway {

    private fun db() = HydriaSharedDatabaseHolder.database

    fun saveState(accountKey: String, payload: JSONObject, now: Long = System.currentTimeMillis()) {
        require(accountKey.isNotBlank())
        db().calculatorQueries.upsertState(accountKey, payload.toString(), now)
    }

    fun state(accountKey: String): JSONObject? {
        if (accountKey.isBlank()) return null
        return db().calculatorQueries.selectState(accountKey).executeAsOneOrNull()?.let {
            runCatching { JSONObject(it) }.getOrNull()
        }
    }

    fun clearState(accountKey: String) {
        if (accountKey.isNotBlank()) db().calculatorQueries.deleteState(accountKey)
    }

    fun activeSalaryConfig(accountKey: String, organisationKey: String = "global"): JSONObject? {
        if (accountKey.isBlank()) return null
        val row = db().calculatorQueries.selectActiveConfig(accountKey, organisationKey).executeAsOneOrNull()
            ?: return null
        return runCatching { JSONObject(row.payload).put("local_synced_at", row.syncedAt) }.getOrNull()
    }

    fun salaryConfigChecksum(accountKey: String, organisationKey: String = "global"): String =
        activeSalaryConfig(accountKey, organisationKey)?.optString("checksum").orEmpty()

    fun replaceActiveSalaryConfig(accountKey: String, configuration: JSONObject, now: Long = System.currentTimeMillis()) {
        require(accountKey.isNotBlank())
        val organisation = configuration.getString("organisation")
        val database = db()
        database.transaction {
            database.calculatorQueries.deactivateAll(accountKey, organisation)
            database.calculatorQueries.insertConfig(
                accountKey = accountKey,
                organisationKey = organisation,
                formulaVersion = configuration.getInt("formula_version").toLong(),
                configVersion = configuration.getString("version"),
                checksum = configuration.getString("checksum"),
                payload = configuration.toString(),
                effectiveFrom = configuration.optString("effective_from").takeIf { it.isNotBlank() },
                effectiveTo = configuration.optString("effective_until").takeIf { it.isNotBlank() },
                serverUpdatedAt = configuration.getString("server_updated_at"),
                syncedAt = now,
            )
        }
    }
}
