package mg.hydria.app.calculator

import mg.hydria.app.OfflineStore
import org.json.JSONObject

/**
 * Relais fin vers le module partage `shared` pour les types + la logique
 * de validation/parsing pure (Phase 1 de la migration KMP). Voir
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/calculator/SalaryConfig.kt.
 *
 * SalaryConfigRepository reste ici : il depend de TerrainDatabase
 * (Android/SQLite), qui n'a pas sa place dans shared/ (sa migration, c'est
 * la Phase 2 - base locale). Il delegue tout le calcul/la validation au
 * parseur partage.
 */
typealias IrsaBracket = mg.hydria.shared.calculator.IrsaBracket
typealias SalaryParameters = mg.hydria.shared.calculator.SalaryParameters
typealias SalaryConfig = mg.hydria.shared.calculator.SalaryConfig
typealias SalaryConfigUpdate = mg.hydria.shared.calculator.SalaryConfigUpdate

class SalaryConfigRepository(
    private val store: OfflineStore,
    private val accountKey: String,
) {
    fun current(): SalaryConfig? =
        store.activeSalaryConfig(accountKey)?.let { mg.hydria.shared.calculator.SalaryConfigParser.parse(it) }

    fun checksum(): String = store.salaryConfigChecksum(accountKey)

    fun validateAndActivate(configuration: JSONObject): SalaryConfigUpdate {
        val receivedChecksum = configuration.optString("checksum").lowercase()
        if (receivedChecksum.length != 64 || mg.hydria.shared.calculator.SalaryConfigParser.checksumOf(configuration) != receivedChecksum) {
            return mg.hydria.shared.calculator.SalaryConfigUpdate.Rejected("checksum_invalid")
        }
        val parsed = mg.hydria.shared.calculator.SalaryConfigParser.parse(configuration) ?: return mg.hydria.shared.calculator.SalaryConfigUpdate.Rejected(
            if (configuration.optInt("formula_version", -1) != mg.hydria.shared.calculator.SalaryConfigParser.SUPPORTED_FORMULA_VERSION) {
                "formula_incompatible"
            } else {
                "config_incomplete"
            }
        )
        store.replaceActiveSalaryConfig(accountKey, configuration)
        return mg.hydria.shared.calculator.SalaryConfigUpdate.Updated(
            store.activeSalaryConfig(accountKey)?.let { mg.hydria.shared.calculator.SalaryConfigParser.parse(it) } ?: parsed
        )
    }
}
