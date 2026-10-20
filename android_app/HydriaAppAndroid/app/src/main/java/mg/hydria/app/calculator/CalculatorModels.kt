package mg.hydria.app.calculator

/**
 * Relais fin vers le module partage `shared` (Phase 1 de la migration KMP,
 * module pilote Calculatrice). Le code reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/calculator/CalculatorModels.kt ;
 * ce fichier ne fait plus que le pointer, pour ne rien casser des appels
 * existants (AdvancedCalculatorActivity, CalculatorRepository) pendant la
 * transition.
 */
typealias CalculatorTab = mg.hydria.shared.calculator.CalculatorTab
typealias CalculationLine = mg.hydria.shared.calculator.CalculationLine
typealias CalculatorState = mg.hydria.shared.calculator.CalculatorState

object CalculatorEngine {
    fun recalculate(lines: List<CalculationLine>): List<CalculationLine> =
        mg.hydria.shared.calculator.CalculatorEngine.recalculate(lines)
}
