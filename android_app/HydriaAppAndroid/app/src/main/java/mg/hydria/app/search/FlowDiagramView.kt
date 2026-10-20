package mg.hydria.app.search

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.text.TextUtils
import android.text.TextPaint
import android.view.View
import mg.hydria.app.HydriaColors
import java.util.Locale

/**
 * Dessin du diagramme de flux de la fiche commune. Toute la géométrie vient de [FlowDiagramLayout] ;
 * cette vue ne fait que tracer les rubans, les noeuds et leurs étiquettes. À placer dans un
 * HorizontalScrollView : la largeur dépend du nombre de colonnes.
 */
class FlowDiagramView(context: Context) : View(context) {
    private var layout: FlowLayout? = null
    private val density = resources.displayMetrics.density
    private val nodeWidth = 12 * density
    private val labelGap = 6 * density
    private var labelMaxWidth = 180 * density

    private val linkPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.BUTT }
    private val nodePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
    private val labelPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11.5f * density }
    private val labelHalo = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 11.5f * density; style = Paint.Style.STROKE; strokeWidth = 3f * density; strokeJoin = Paint.Join.ROUND
    }
    private val subPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 10.5f * density }
    private val subHalo = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 10.5f * density; style = Paint.Style.STROKE; strokeWidth = 3f * density; strokeJoin = Paint.Join.ROUND
    }
    private val headPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 11f * density; typeface = Typeface.DEFAULT_BOLD
    }
    private val path = Path()

    /** Paramètres de mise en page en pixels, à passer à [FlowDiagramLayout.build]. */
    val columnWidth get() = 210 * density
    val height get() = 380 * density
    val topMargin get() = 34 * density
    val bottomMargin get() = 8 * density
    val gap get() = 10 * density
    val leftMargin get() = 22 * density
    val labelWidth get() = 190 * density

    fun show(layout: FlowLayout) {
        this.layout = layout
        labelMaxWidth = columnWidth - nodeWidth - labelGap - 8 * density
        requestLayout()
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val l = layout
        setMeasuredDimension(Math.ceil((l?.width ?: 0f).toDouble()).toInt(), Math.ceil((l?.height ?: 0f).toDouble()).toInt())
    }

    private fun color(hex: String, alpha: Int = 255): Int {
        val base = runCatching { Color.parseColor(hex) }.getOrDefault(Color.GRAY)
        return Color.argb(alpha, Color.red(base), Color.green(base), Color.blue(base))
    }

    override fun onDraw(canvas: Canvas) {
        val l = layout ?: return
        labelPaint.color = HydriaColors.text
        subPaint.color = HydriaColors.textSecondary
        headPaint.color = HydriaColors.textSecondary
        labelHalo.color = HydriaColors.background
        subHalo.color = HydriaColors.background

        // En-têtes de colonnes
        l.columnTitles.forEachIndexed { index, title ->
            val x = l.nodes.firstOrNull { it.column == index }?.x ?: return@forEachIndexed
            val shown = TextUtils.ellipsize(title, headPaint, columnWidth - 8 * density, TextUtils.TruncateAt.END)
            canvas.drawText(shown, 0, shown.length, x, 18 * density, headPaint)
        }

        // Rubans
        l.links.forEach { link ->
            val x0 = link.from.x + nodeWidth
            val x1 = link.to.x
            val xm = (x0 + x1) / 2f
            val ya = link.y0 + link.thickness / 2f
            val yb = link.y1 + link.thickness / 2f
            path.reset()
            path.moveTo(x0, ya)
            path.cubicTo(xm, ya, xm, yb, x1, yb)
            linkPaint.strokeWidth = Math.max(link.thickness, 1f)
            linkPaint.color = color(link.color, 95)
            canvas.drawPath(path, linkPaint)
        }

        // Noeuds + étiquettes (libellé, puis effectif et part du total)
        l.nodes.forEach { node ->
            val h = Math.max(node.height, 2f * density)
            nodePaint.color = color(node.color)
            canvas.drawRoundRect(node.x, node.y, node.x + nodeWidth, node.y + h, 2 * density, 2 * density, nodePaint)

            val pct = if (l.total > 0) Math.round(node.count * 100f / l.total) else 0
            val title = TextUtils.ellipsize(node.label, labelPaint, labelMaxWidth, TextUtils.TruncateAt.END).toString()
            val detail = String.format(Locale.FRANCE, "%,d village(s) · %d %%", node.count, pct).replace(' ', ' ')
            val x = node.x + nodeWidth + labelGap
            val center = node.y + h / 2f
            canvas.drawText(title, x, center - 2 * density, labelHalo)
            canvas.drawText(title, x, center - 2 * density, labelPaint)
            canvas.drawText(detail, x, center + 12 * density, subHalo)
            canvas.drawText(detail, x, center + 12 * density, subPaint)
        }
    }
}
