package mg.hydria.compta.core

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale

/**
 * Montant en Ariary, stocké en centièmes (aligné sur les `DecimalField(decimal_places=2)`
 * du backend Django). Jamais de `Double` dans la logique monétaire.
 */
@JvmInline
value class Ariary(val centimes: Long) : Comparable<Ariary> {

    operator fun plus(other: Ariary) = Ariary(centimes + other.centimes)
    operator fun minus(other: Ariary) = Ariary(centimes - other.centimes)
    operator fun unaryMinus() = Ariary(-centimes)

    /** Multiplication par une quantité/pourcentage, arrondi HALF_UP au centième. */
    operator fun times(factor: BigDecimal): Ariary =
        Ariary(toBigDecimal().multiply(factor).setScale(2, RoundingMode.HALF_UP).movePointRight(2).toLong())

    val isZero: Boolean get() = centimes == 0L
    val isNegative: Boolean get() = centimes < 0L

    fun toBigDecimal(): BigDecimal = BigDecimal.valueOf(centimes, 2)

    /** Arrondi à l'Ariary entier (les centimes n'ont pas cours à Madagascar). */
    fun arrondiEntier(mode: RoundingMode = RoundingMode.HALF_UP): Ariary =
        Ariary(toBigDecimal().setScale(0, mode).movePointRight(2).toLong())

    /** Arrondi supérieur à la centaine d'Ariary (factures d'eau). */
    fun arrondiCentaineSup(): Ariary {
        val ariary = toBigDecimal().setScale(0, RoundingMode.CEILING).toLong()
        val up = ((ariary + 99) / 100) * 100
        return fromAriary(up)
    }

    override fun compareTo(other: Ariary): Int = centimes.compareTo(other.centimes)

    fun format(locale: Locale = FR): String {
        val symbols = DecimalFormatSymbols(locale).apply { groupingSeparator = ' ' }
        return DecimalFormat("#,##0", symbols).format(toBigDecimal().setScale(0, RoundingMode.HALF_UP)) + " Ar"
    }

    companion object {
        val ZERO = Ariary(0)
        private val FR = Locale.FRANCE

        fun fromAriary(ariary: Long) = Ariary(ariary * 100)
        fun fromAriary(ariary: Int) = Ariary(ariary.toLong() * 100)
        fun fromBigDecimal(value: BigDecimal) =
            Ariary(value.setScale(2, RoundingMode.HALF_UP).movePointRight(2).toLong())

        /** Depuis la représentation texte du backend ("12345.67"). */
        fun parse(raw: String?): Ariary =
            if (raw.isNullOrBlank()) ZERO else fromBigDecimal(BigDecimal(raw.trim()))
    }
}

fun Iterable<Ariary>.sum(): Ariary = fold(Ariary.ZERO) { acc, a -> acc + a }
