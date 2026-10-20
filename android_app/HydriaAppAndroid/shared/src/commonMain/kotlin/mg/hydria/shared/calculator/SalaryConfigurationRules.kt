package mg.hydria.shared.calculator

object SalaryConfigurationRules {
    fun <N : Comparable<N>> valid(formulaVersion: Int, supportedVersion: Int, organisation: String, version: String,
        brackets: List<SalaryCalculationBracket<N>>, zero: N, minimumSalary: N,
        positiveParameters: List<N>, healthMutualMatchesCnaps: Boolean): Boolean =
        formulaVersion == supportedVersion && organisation.isNotBlank() && version.isNotBlank() &&
            brackets.isNotEmpty() && brackets.map { it.order }.distinct().size == brackets.size &&
            brackets.zipWithNext().all { (first, second) -> second.upperBound > first.upperBound } &&
            brackets.all { it.upperBound > zero && it.ratePercent >= zero } &&
            minimumSalary >= zero && positiveParameters.all { it > zero } && healthMutualMatchesCnaps
}
