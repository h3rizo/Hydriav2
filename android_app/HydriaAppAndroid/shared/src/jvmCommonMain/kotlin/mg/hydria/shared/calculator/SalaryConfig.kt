package mg.hydria.shared.calculator

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.security.MessageDigest

/**
 * Types + logique de validation/parsing pure, extraits de
 * mg.hydria.app.calculator.SalaryConfigRepository (Phase 1 de la migration
 * KMP, module pilote Calculatrice). La classe SalaryConfigRepository
 * elle-meme reste dans app/ (elle depend de TerrainDatabase, Android) et
 * delegue a SalaryConfigParser ci-dessous.
 */
data class IrsaBracket(
    val order: Int,
    val upperBound: BigDecimal,
    val ratePercent: BigDecimal,
)

data class SalaryParameters(
    val minimumSalary: BigDecimal,
    val cnapsCeilingMultiplier: BigDecimal,
    val cnapsEmployeeRate: BigDecimal,
    val healthMutualMatchesCnaps: Boolean,
    val dependentIrsaDeduction: BigDecimal,
    val minimumIrsa: BigDecimal,
    val prorataReferenceDays: BigDecimal,
    val guardianReferenceHours: BigDecimal,
    val employeeReferenceHours: BigDecimal,
    val guardianDefaultNightHours: BigDecimal,
    val nightRate: BigDecimal,
    val sundayRate: BigDecimal,
    val officialHolidayRate: BigDecimal,
    val decreePaidHolidayRate: BigDecimal,
    val mayFirstRate: BigDecimal,
    val guardianReplacementRate: BigDecimal,
    val guardianOrdinaryReplacementExtraRate: BigDecimal,
    val taxableBaseFloorIncrement: BigDecimal,
    val netRoundingIncrement: BigDecimal,
)

data class SalaryConfig(
    val id: String,
    val organisation: String,
    val version: String,
    val formulaVersion: Int,
    val effectiveFrom: String,
    val serverUpdatedAt: String,
    val checksum: String,
    val localSyncedAt: Long,
    val parameters: SalaryParameters,
    val brackets: List<IrsaBracket>,
)

sealed class SalaryConfigUpdate {
    data class Updated(val config: SalaryConfig) : SalaryConfigUpdate()
    data class Rejected(val reason: String) : SalaryConfigUpdate()
}

object SalaryConfigParser {
    const val SUPPORTED_FORMULA_VERSION = 1

    fun parse(json: JSONObject): SalaryConfig? = runCatching {
        require(json.getInt("formula_version") == SUPPORTED_FORMULA_VERSION)
        require(json.getString("organisation").isNotBlank())
        require(json.getString("version").isNotBlank())
        val values = json.getJSONObject("parameters")
        fun decimal(key: String): BigDecimal = BigDecimal(values.getString(key))
        val parameters = SalaryParameters(
            minimumSalary = decimal("minimum_salary"),
            cnapsCeilingMultiplier = decimal("cnaps_ceiling_multiplier"),
            cnapsEmployeeRate = decimal("cnaps_employee_rate"),
            healthMutualMatchesCnaps = values.getBoolean("health_mutual_matches_cnaps"),
            dependentIrsaDeduction = decimal("dependent_irsa_deduction"),
            minimumIrsa = decimal("minimum_irsa"),
            prorataReferenceDays = decimal("prorata_reference_days"),
            guardianReferenceHours = decimal("guardian_reference_hours"),
            employeeReferenceHours = decimal("employee_reference_hours"),
            guardianDefaultNightHours = decimal("guardian_default_night_hours"),
            nightRate = decimal("night_rate"),
            sundayRate = decimal("sunday_rate"),
            officialHolidayRate = decimal("official_holiday_rate"),
            decreePaidHolidayRate = decimal("decree_paid_holiday_rate"),
            mayFirstRate = decimal("may_first_rate"),
            guardianReplacementRate = decimal("guardian_replacement_rate"),
            guardianOrdinaryReplacementExtraRate = decimal("guardian_ordinary_replacement_extra_rate"),
            taxableBaseFloorIncrement = decimal("taxable_base_floor_increment"),
            netRoundingIncrement = decimal("net_rounding_increment"),
        )
        val rows = json.getJSONArray("irsa_brackets")
        val brackets = buildList {
            for (index in 0 until rows.length()) {
                val row = rows.getJSONObject(index)
                add(IrsaBracket(row.getInt("order"), BigDecimal(row.getString("upper_bound")), BigDecimal(row.getString("rate_percent"))))
            }
        }.sortedWith(compareBy(IrsaBracket::order, IrsaBracket::upperBound))
        require(SalaryConfigurationRules.valid(json.getInt("formula_version"), SUPPORTED_FORMULA_VERSION,
            json.getString("organisation"), json.getString("version"),
            brackets.map { SalaryCalculationBracket(it.order, it.upperBound, it.ratePercent) }, BigDecimal.ZERO,
            parameters.minimumSalary, listOf(parameters.cnapsCeilingMultiplier, parameters.prorataReferenceDays,
                parameters.guardianReferenceHours, parameters.employeeReferenceHours,
                parameters.taxableBaseFloorIncrement, parameters.netRoundingIncrement), parameters.healthMutualMatchesCnaps))
        SalaryConfig(
            id = json.getString("configuration_id"),
            organisation = json.getString("organisation"),
            version = json.getString("version"),
            formulaVersion = json.getInt("formula_version"),
            effectiveFrom = json.getString("effective_from"),
            serverUpdatedAt = json.getString("server_updated_at"),
            checksum = json.getString("checksum"),
            localSyncedAt = json.optLong("local_synced_at"),
            parameters = parameters,
            brackets = brackets,
        )
    }.getOrNull()

    fun checksumOf(configuration: JSONObject): String {
        val copy = JSONObject(configuration.toString()).apply { remove("checksum"); remove("local_synced_at") }
        return MessageDigest.getInstance("SHA-256").digest(canonical(copy).toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun canonical(value: Any?): String = when (value) {
        null, JSONObject.NULL -> "null"
        is JSONObject -> value.keys().asSequence().toList().sorted().joinToString(prefix = "{", postfix = "}", separator = ",") { key ->
            "${JSONObject.quote(key)}:${canonical(value.get(key))}"
        }
        is JSONArray -> (0 until value.length()).joinToString(prefix = "[", postfix = "]", separator = ",") { canonical(value.get(it)) }
        is String -> JSONObject.quote(value)
        is Boolean, is Number -> value.toString()
        else -> JSONObject.quote(value.toString())
    }
}
