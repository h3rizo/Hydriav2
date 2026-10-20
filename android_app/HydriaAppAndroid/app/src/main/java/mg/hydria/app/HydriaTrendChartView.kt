package mg.hydria.app

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.View

/** Courbes multiples (évolution des points au fil du temps) ; la série « moi » est épaissie. */
class HydriaTrendChartView(context: Context) : View(context) {
    data class Series(val name: String, val values: List<Int>, val mine: Boolean)

    private var labels: List<String> = emptyList()
    private var series: List<Series> = emptyList()

    private val density = resources.displayMetrics.density
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10.5f * density }

    fun setData(labels: List<String>, series: List<Series>) {
        this.labels = labels
        this.series = series
        invalidate()
    }

    private fun colorFor(index: Int, mine: Boolean): Int =
        if (mine) HydriaColors.cyan else intArrayOf(HydriaColors.vase, HydriaColors.warning, HydriaColors.success, HydriaColors.textSecondary)[index % 4]

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val count = labels.size
        if (count == 0 || series.isEmpty()) return
        val left = 36f * density
        val right = width - 10f * density
        val top = 8f * density
        val bottom = height - 40f * density
        val max = (series.flatMap { it.values }.maxOrNull() ?: 0).let { if (it <= 0) 1.0 else it * 1.1 }
        fun x(i: Int) = if (count == 1) (left + right) / 2 else left + (right - left) * i / (count - 1)
        fun y(v: Int) = (bottom - (bottom - top) * (v / max)).toFloat()

        text.color = HydriaColors.textSecondary
        text.textAlign = Paint.Align.RIGHT
        canvas.drawText(max.toInt().toString(), left - 4 * density, top + 8 * density, text)
        canvas.drawText("0", left - 4 * density, bottom, text)
        stroke.color = HydriaColors.outline
        stroke.strokeWidth = density
        canvas.drawLine(left, bottom, right, bottom, stroke)

        series.forEachIndexed { index, s ->
            val color = colorFor(index, s.mine)
            stroke.color = color
            stroke.strokeWidth = (if (s.mine) 3.5f else 2f) * density
            val path = Path()
            s.values.forEachIndexed { i, v -> if (i == 0) path.moveTo(x(i), y(v)) else path.lineTo(x(i), y(v)) }
            canvas.drawPath(path, stroke)
            dot.color = color
            s.values.forEachIndexed { i, v -> canvas.drawCircle(x(i), y(v), (if (s.mine) 3.5f else 2.5f) * density, dot) }
        }

        text.color = HydriaColors.textSecondary
        text.textAlign = Paint.Align.LEFT
        canvas.drawText(labels.first(), left, bottom + 14 * density, text)
        if (count > 1) {
            text.textAlign = Paint.Align.RIGHT
            canvas.drawText(labels.last(), right, bottom + 14 * density, text)
        }
        // Légende
        var lx = left
        series.forEachIndexed { index, s ->
            dot.color = colorFor(index, s.mine)
            canvas.drawCircle(lx + 4 * density, height - 8 * density, 4 * density, dot)
            text.color = HydriaColors.text
            text.textAlign = Paint.Align.LEFT
            val label = if (s.mine) "Moi" else s.name.take(10)
            canvas.drawText(label, lx + 11 * density, height - 4 * density, text)
            lx += 18 * density + text.measureText(label)
        }
    }
}
