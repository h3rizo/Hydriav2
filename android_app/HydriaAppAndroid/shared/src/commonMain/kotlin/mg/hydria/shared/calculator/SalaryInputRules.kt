package mg.hydria.shared.calculator

enum class SalaryBasis { NET, GROSS }
enum class SalaryMode { STANDARD, PRORATA, DAILY, GUARDIAN }

data class SalaryDraft(
    val basis: SalaryBasis = SalaryBasis.NET,
    val mode: SalaryMode = SalaryMode.STANDARD,
    val target: String = "",
    val dependents: String = "0",
    val days: String = "",
    val nightHours: String = "56",
    val sundayHours: String = "",
    val officialHolidayHours: String = "",
    val decreePaidHolidayHours: String = "",
    val mayFirstHours: String = "",
    val replacementHours: String = "",
    val ordinaryReplacementHours: String = "",
)


enum class SalaryInputError { TARGET, DEPENDENTS, DAYS, HOURS, ORDINARY_REPLACEMENT }

object SalaryInputRules {
    fun <N : Comparable<N>> validate(target: N, zero: N, dependents: Int, mode: SalaryMode, days: Int,
        hours: List<N>, ordinaryReplacement: N, replacement: N): SalaryInputError? = when {
        target <= zero -> SalaryInputError.TARGET
        dependents < 0 -> SalaryInputError.DEPENDENTS
        mode in setOf(SalaryMode.PRORATA, SalaryMode.DAILY) && days <= 0 -> SalaryInputError.DAYS
        hours.any { it < zero } -> SalaryInputError.HOURS
        ordinaryReplacement > replacement -> SalaryInputError.ORDINARY_REPLACEMENT
        else -> null
    }
}

interface GrossSearchArithmetic<N> {
    val zero: N
    val one: N
    val cent: N
    fun add(left: N, right: N): N
    fun subtract(left: N, right: N): N
    fun twice(value: N): N
    fun midpoint(lower: N, upper: N): N
    fun absolute(value: N): N
    fun roundWhole(value: N): N
}

/** Recherche historique conservée, y compris le nombre d'itérations et le départage. */
class GrossSalarySearch<N : Comparable<N>>(private val arithmetic: GrossSearchArithmetic<N>) {
    fun solve(target: N, netForGross: (N) -> N): N {
        var lower = arithmetic.zero
        var upper = maxOf(target, arithmetic.one)
        repeat(100) {
            if (netForGross(upper) >= target) return@repeat
            upper = arithmetic.twice(upper)
        }
        var estimate = upper
        repeat(100) {
            estimate = arithmetic.midpoint(lower, upper)
            val net = netForGross(estimate)
            if (arithmetic.absolute(arithmetic.subtract(net, target)) <= arithmetic.cent) return@repeat
            if (net < target) lower = estimate else upper = estimate
        }
        val rounded = arithmetic.roundWhole(estimate)
        return listOf(maxOf(arithmetic.subtract(rounded, arithmetic.one), arithmetic.zero),
            maxOf(rounded, arithmetic.zero), arithmetic.add(rounded, arithmetic.one))
            .minWith(compareBy<N> { arithmetic.absolute(arithmetic.subtract(netForGross(it), target)) }.thenBy { it })
    }
}
