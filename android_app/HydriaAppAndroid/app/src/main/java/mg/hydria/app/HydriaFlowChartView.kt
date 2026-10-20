package mg.hydria.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.view.View

/**
 * Courbe des débits de source (L/s) avec la ligne du seuil minimum en pointillés.
 * Les points sous le seuil sont dessinés en couleur d'erreur.
 */
class HydriaFlowChartView(context: Context) : View(context) {
    data class Point(val label: String, val value: Double)

    private var points: List<Point> = emptyList()
    private var threshold: Double? = null

    private val density = resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 2.5f * density }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val limit = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1.5f * density
        pathEffect = DashPathEffect(floatArrayOf(8f * density, 5f * density), 0f)
    }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10.5f * density }

    /** [points] dans l'ordre chronologique (du plus ancien au plus récent). */
    fun setData(points: List<Point>, threshold: Double?) {
        this.points = points
        this.threshold = threshold
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (points.isEmpty()) return
        val left = 40f * density
        val right = width - 10f * density
        val top = 10f * density
        val bottom = height - 22f * density
        val values = points.map { it.value } + listOfNotNull(threshold)
        val max = values.max().let { if (it <= 0.0) 1.0 else it * 1.12 }
        val min = 0.0
        fun x(i: Int) = if (points.size == 1) (left + right) / 2 else left + (right - left) * i / (points.size - 1)
        fun y(v: Double) = (bottom - (bottom - top) * ((v - min) / (max - min))).toFloat()

        text.color = HydriaColors.textSecondary
        text.textAlign = Paint.Align.RIGHT
        canvas.drawText(String.format("%.2f", max), left - 4 * density, top + 8 * density, text)
        canvas.drawText("0", left - 4 * density, bottom, text)
        line.color = HydriaColors.outline
        canvas.drawLine(left, bottom, right, bottom, line)

        threshold?.let {
            limit.color = HydriaColors.error
            val ty = y(it)
            canvas.drawLine(left, ty, right, ty, limit)
            text.color = HydriaColors.error
            text.textAlign = Paint.Align.LEFT
            canvas.drawText("seuil ${String.format("%.3f", it)}", left + 4 * density, ty - 4 * density, text)
        }

        line.color = HydriaColors.cyan
        val path = Path()
        points.forEachIndexed { i, p -> if (i == 0) path.moveTo(x(i), y(p.value)) else path.lineTo(x(i), y(p.value)) }
        canvas.drawPath(path, line)
        points.forEachIndexed { i, p ->
            val below = threshold?.let { p.value < it } == true
            dot.color = if (below) HydriaColors.error else HydriaColors.cyan
            canvas.drawCircle(x(i), y(p.value), 4f * density, dot)
        }

        text.color = HydriaColors.textSecondary
        text.textAlign = Paint.Align.LEFT
        canvas.drawText(points.first().label, left, height - 6 * density, text)
        if (points.size > 1) {
            text.textAlign = Paint.Align.RIGHT
            canvas.drawText(points.last().label, right, height - 6 * density, text)
        }
    }
}
