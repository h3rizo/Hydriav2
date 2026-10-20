package mg.hydria.app.navigation.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.view.MotionEvent
import android.view.View
import androidx.core.graphics.ColorUtils
import mg.hydria.app.HydriaColors
import mg.hydria.app.navigation.geo.GeoMath
import mg.hydria.app.navigation.geo.IndicatorCandidate

class EdgeIndicatorsView(context: Context) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textSize = 12f * resources.displayMetrics.scaledDensity }
    private var candidates = emptyList<IndicatorCandidate>()
    private var clickListener: ((IndicatorCandidate) -> Unit)? = null
    private val hitPoints = mutableListOf<Pair<GeoMath.EdgePoint, IndicatorCandidate>>()
    private var pressedCandidate: IndicatorCandidate? = null

    fun submit(values: List<IndicatorCandidate>, onClick: (IndicatorCandidate) -> Unit) {
        candidates = values
        clickListener = onClick
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        hitPoints.clear()
        val padding = 54f * resources.displayMetrics.density
        candidates.forEach { candidate ->
            val point = GeoMath.projectBearingToEdge(candidate.relativeBearingDegrees, width.toFloat(), height.toFloat(), padding)
            hitPoints += point to candidate
            paint.color = if (candidate.isDestination) Color.rgb(242, 154, 56) else Color.rgb(85, 217, 231)
            paint.style = Paint.Style.FILL
            canvas.save()
            canvas.translate(point.x, point.y)
            canvas.rotate(point.rotationDegrees)
            val size = if (candidate.isDestination) 25f else 19f
            val path = Path().apply {
                moveTo(0f, -size); lineTo(size * 0.65f, size * 0.6f); lineTo(0f, size * 0.25f)
                lineTo(-size * 0.65f, size * 0.6f); close()
            }
            canvas.drawPath(path, paint)
            canvas.restore()
            val label = "${candidate.entity.name.take(14)} · ${GeoMath.formatDistance(candidate.distanceMeters)}"
            val labelX = (point.x - textPaint.measureText(label) / 2f).coerceIn(8f, width - textPaint.measureText(label) - 8f)
            val labelY = if (point.y < height / 2f) point.y + 38f else point.y - 30f
            // Pastille de libellé aux couleurs du thème (RECH_NAV-02) : surface + filet, texte du thème.
            // Le blanc codé en dur n'est lisible que sur un fond sombre, donc le texte suit la surface.
            paint.color = ColorUtils.setAlphaComponent(HydriaColors.surface, 205)
            val left = labelX - 6f
            val top = labelY - textPaint.textSize
            val right = labelX + textPaint.measureText(label) + 6f
            canvas.drawRoundRect(left, top, right, labelY + 6f, 8f, 8f, paint)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = resources.displayMetrics.density
            paint.color = HydriaColors.outline
            canvas.drawRoundRect(left, top, right, labelY + 6f, 8f, 8f, paint)
            paint.style = Paint.Style.FILL
            textPaint.color = HydriaColors.text
            canvas.drawText(label, labelX, labelY, textPaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        fun nearestHit(): Pair<GeoMath.EdgePoint, IndicatorCandidate>? =
            mg.hydria.shared.navigation.IndicatorSelection.nearestHit(
                hitPoints, event.x, event.y, 54f * resources.displayMetrics.density,
            ) { (point, _) -> mg.hydria.shared.navigation.ScreenPoint(point.x, point.y) }

        return when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                pressedCandidate = nearestHit()?.second
                pressedCandidate != null
            }
            MotionEvent.ACTION_UP -> {
                val releasedCandidate = nearestHit()?.second
                val selected = pressedCandidate
                pressedCandidate = null
                if (selected != null && releasedCandidate == selected) clickListener?.invoke(selected)
                selected != null
            }
            MotionEvent.ACTION_CANCEL -> {
                val wasPressed = pressedCandidate != null
                pressedCandidate = null
                wasPressed
            }
            else -> pressedCandidate != null
        }
    }
}
