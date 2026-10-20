package mg.hydria.app.calculator

/**
 * Relais fin vers le module partage `shared` (Phase 1 de la migration KMP).
 * Le code reel a demenage vers
 * shared/src/jvmCommonMain/kotlin/mg/hydria/shared/calculator/SalaryEngine.kt.
 */
typealias SalaryBasis = mg.hydria.shared.calculator.SalaryBasis
typealias SalaryMode = mg.hydria.shared.calculator.SalaryMode
typealias SalaryDraft = mg.hydria.shared.calculator.SalaryDraft
typealias SalaryInput = mg.hydria.shared.calculator.SalaryInput
typealias SalaryInputError = mg.hydria.shared.calculator.SalaryInputError
typealias IrsaBracketResult = mg.hydria.shared.calculator.IrsaBracketResult
typealias SalaryMajorations = mg.hydria.shared.calculator.SalaryMajorations
typealias SalaryResult = mg.hydria.shared.calculator.SalaryResult
typealias SalarySimulation = mg.hydria.shared.calculator.SalarySimulation
typealias SalaryEngine = mg.hydria.shared.calculator.SalaryEngine
