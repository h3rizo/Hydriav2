package mg.hydria.shared.ui.intro

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.Easing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.layout.positionInParent
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.min
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import org.jetbrains.compose.resources.Font
import org.jetbrains.compose.resources.painterResource
import mg.hydria.shared.generated.resources.Res
import mg.hydria.shared.generated.resources.bricolage_grotesque_extrabold
import mg.hydria.shared.generated.resources.bricolage_grotesque_medium
import mg.hydria.shared.generated.resources.hydria_intro_vase
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sign
import kotlin.math.sin

// ─── Palette (identique à la version web) ─────────────────────────────────────
/** Fond du splash Hydria Terrain, à reprendre pour l'écran de démarrage système. */
val HydriaIntroBackground = Color(0xFF08171F)
private val Clay1 = Color(0xFFFFB347)
private val Clay2 = Color(0xFFF07A1A)
private val Clay3 = Color(0xFFB8420F)
private val Water = Color(0xFF4FC8E8)
private val ChipBg = Color(0xFF10242F)
private val ChipLine = Water.copy(alpha = 0.35f)
private val TextLight = Color(0xFFE4EEF2)
private val Muted = Color(0xFF9FB6C1)

// ─── Chronologie (secondes) ───────────────────────────────────────────────────
private const val CHIP_START = 0.75f
private const val CHIP_GAP = 0.15f
private const val CHIP_DUR = 1.9f
private const val RISE_START = 0.8f
private const val RISE_DUR = CHIP_START + 3 * CHIP_GAP + CHIP_DUR - RISE_START + 0.15f
private const val T_TEXT = RISE_START + RISE_DUR - 0.05f
private const val T_END = T_TEXT + 1.4f

private const val BIG = 1.4f     // taille des données au départ
private const val SMALL = 0.18f  // taille à l'embouchure

private val EaseBounce = CubicBezierEasing(0.3f, 1.4f, 0.5f, 1f)
private val EaseChip = CubicBezierEasing(0.3f, 0f, 0.65f, 1f)
private val EaseRise = CubicBezierEasing(0.4f, 0f, 0.3f, 1f)
private val EaseSettle = CubicBezierEasing(0.2f, 0.8f, 0.2f, 1f)
private val EaseOut = CubicBezierEasing(0f, 0f, 0.58f, 1f)
private val EaseDrop = CubicBezierEasing(0.2f, 0.8f, 0.4f, 1f)

private fun seg(now: Float, start: Float, dur: Float, easing: Easing = LinearEasing): Float =
    easing.transform(((now - start) / dur).coerceIn(0f, 1f))

private fun lerp(a: Float, b: Float, t: Float) = a + (b - a) * t
private fun bez(p0: Float, p1: Float, p2: Float, t: Float): Float { val u = 1 - t; return u * u * p0 + 2 * u * t * p1 + t * t * p2 }
private fun impactTime(i: Int) = CHIP_START + i * CHIP_GAP + CHIP_DUR * 0.93f

// ─── Les 4 données qui entrent dans le vase ───────────────────────────────────
private enum class FieldData(val label: String, val fromX: Float, val fromY: Float, val icon: List<String>) {
    RELEVE("Relevé", -1.2f, -1.25f, listOf("M4 16a8 8 0 1 1 16 0", "M12 16l4-5", "M3 20h18")),
    REPARATIONS("Réparations", 1.15f, -1.4f,
        listOf("M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-0.6-0.6-2.4z")),
    PLANNING("Planning", -1.6f, -0.35f,
        listOf("M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z", "M3 10h18M8 3v4M16 3v4", "M8 14h3M8 17h6")),
    POINTAGE("Pointage", 1.6f, -0.6f, listOf("M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0", "M12 7v5l3 2")),
}

/**
 * Intro animée Hydria Terrain (Android, Linux, Windows).
 *
 * @param animate passe `false` pour afficher directement l'état final
 *        (ex. sur Android quand l'utilisateur a désactivé les animations).
 * @param onFinished appelé à la fin, ou dès que l'utilisateur touche / clique l'écran.
 */
@Composable
fun HydriaIntro(
    modifier: Modifier = Modifier,
    animate: Boolean = true,
    onFinished: () -> Unit = {},
) {
    val time = remember { Animatable(if (animate) 0f else T_END) }
    val onDone by rememberUpdatedState(onFinished)
    val done = remember { mutableStateOf(false) }
    val finish = { if (!done.value) { done.value = true; onDone() } }

    LaunchedEffect(Unit) {
        if (animate) time.animateTo(T_END, tween((T_END * 1000).toInt(), easing = LinearEasing))
        else delay(1200)
        finish()
    }

    val bold = FontFamily(Font(Res.font.bricolage_grotesque_extrabold, FontWeight.ExtraBold))
    val medium = FontFamily(Font(Res.font.bricolage_grotesque_medium, FontWeight.Medium))
    val vasePainter = painterResource(Res.drawable.hydria_intro_vase)
    val density = LocalDensity.current
    val chipSizes = remember { mutableStateMapOf<FieldData, IntSize>() }
    var columnTop by remember { mutableStateOf(0f) }

    BoxWithConstraints(
        modifier
            .fillMaxSize()
            .background(HydriaIntroBackground)
            .pointerInput(Unit) { detectTapGestures { finish() } },
        contentAlignment = Alignment.Center,
    ) {
        val now = time.value
        val screenW = constraints.maxWidth.toFloat()
        val screenH = constraints.maxHeight.toFloat()
        val short = min(maxWidth, maxHeight)
        val vaseW = (short * 0.34f).coerceAtMost(190.dp)
        val vaseH = vaseW * (160f / 120f)
        val gap = (maxHeight * 0.04f).coerceIn(18.dp, 34.dp)
        val nameSize = with(density) { (short * 0.12f).coerceIn(40.dp, 64.dp).toSp() }
        val subSize = with(density) { (short * 0.05f).coerceIn(17.dp, 24.dp).toSp() }

        val w = with(density) { vaseW.toPx() }
        val h = with(density) { vaseH.toPx() }
        val dropPx = min(screenH * 0.2f, with(density) { 190.dp.toPx() })
        // Le vase part plus bas et remonte pendant que les données y entrent
        val sceneY = dropPx * (1f - seg(now, RISE_START, RISE_DUR, EaseRise))
        val mouthYLow = columnTop + dropPx + h * 0.065f
        val mouth = Offset(w / 2f, h * 0.065f)

        Column(
            Modifier.onGloballyPositioned { columnTop = it.positionInParent().y },
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(Modifier.size(vaseW, vaseH).graphicsLayer { translationY = sceneY }) {

                // Derrière le vase : halo d'eau + gouttes
                Canvas(Modifier.matchParentSize()) {
                    drawCircle(
                        brush = Brush.radialGradient(
                            0f to Water.copy(alpha = 0.18f), 0.62f to Color.Transparent,
                            center = Offset(w / 2f, h * 0.55f), radius = w * 0.95f,
                        ),
                        radius = w * 0.95f, center = Offset(w / 2f, h * 0.55f),
                        alpha = haloAlpha(now),
                    )
                    for (i in FieldData.entries.indices) for (k in 0..2) {
                        val p = (now - impactTime(i) - k * 0.03f) / 0.52f
                        if (p <= 0f || p >= 1f) continue
                        val e = EaseDrop.transform(p)
                        val ang = ((-90f + (k - 1) * 38f) * PI / 180f).toFloat()
                        val r = (26f + k * 6f) * density.density
                        drawCircle(
                            Water, radius = 3f * density.density * lerp(1f, 0.4f, e), alpha = 1f - e,
                            center = mouth + Offset(cos(ang) * r * e, (sin(ang) * r + 14f * density.density) * e),
                        )
                    }
                }

                // Les données, derrière le vase pour qu'elles « entrent » dedans
                Box(Modifier.offset(vaseW / 2, vaseH * 0.065f)) {
                    FieldData.entries.forEachIndexed { i, data ->
                        val raw = ((now - (CHIP_START + i * CHIP_GAP)) / CHIP_DUR).coerceIn(0f, 1f)
                        if (raw <= 0f || raw >= 1f) return@forEachIndexed
                        val t = EaseChip.transform(raw)
                        val size = chipSizes[data] ?: IntSize.Zero
                        val cw = size.width * BIG / 2f + 14f * density.density
                        val ch = size.height * BIG / 2f + 14f * density.density
                        val sx = sign(data.fromX) * min(abs(data.fromX * w), screenW / 2f - cw)
                        val sy = max(data.fromY * w * 1.25f, -(mouthYLow - ch - 20f * density.density))
                        val cx = sx * 0.35f
                        val cy = min(sy, -w * 0.3f) - w * 0.3f
                        val u = max(0f, (t - 0.1f) / 0.9f)
                        val s = if (t < 0.1f) lerp(0.7f, BIG, t / 0.1f) else BIG - (BIG - SMALL) * u.pow(1.7f)
                        val a = when { t < 0.1f -> t / 0.1f; t > 0.94f -> (1f - t) / 0.06f; else -> 1f }
                        DataChip(
                            data, medium,
                            Modifier
                                .centerOnOrigin()
                                .graphicsLayer {
                                    translationX = bez(sx, cx, 0f, t)
                                    translationY = bez(sy, cy, h * 0.16f, t)
                                    scaleX = s; scaleY = s
                                    rotationZ = (1f - t) * (if (data.fromX > 0) 7f else -7f)
                                    alpha = a
                                }
                                .onSizeChanged { chipSizes[data] = it },
                        )
                    }
                }

                // Le vase (image d'origine, non retouchée)
                Image(
                    vasePainter, contentDescription = null, contentScale = ContentScale.Fit,
                    modifier = Modifier.matchParentSize().graphicsLayer {
                        val p = seg(now, 0f, 0.6f, EaseBounce)
                        val (sqx, sqy) = squash(now)
                        alpha = p.coerceIn(0f, 1f)
                        translationY = (1f - p) * 14f * density.density
                        scaleX = lerp(0.85f, 1f, p) * sqx
                        scaleY = lerp(0.85f, 1f, p) * sqy
                        transformOrigin = TransformOrigin(0.5f, 1f)
                    },
                )

                // Devant le vase : onde à l'embouchure à chaque entrée
                Canvas(Modifier.matchParentSize()) {
                    for (i in FieldData.entries.indices) {
                        val p = (now - impactTime(i)) / 0.6f
                        if (p <= 0f || p >= 1f) continue
                        val e = EaseOut.transform(p)
                        val sc = lerp(0.4f, 1.6f, e)
                        val rw = w * 0.6f * sc
                        val rh = h * 0.1f * sc
                        drawOval(
                            Water, topLeft = mouth - Offset(rw / 2f, rh / 2f), size = Size(rw, rh),
                            alpha = lerp(0.9f, 0f, e), style = Stroke(2f * density.density),
                        )
                    }
                }
            }

            Spacer(Modifier.height(gap))
            Brand(now, bold, medium, nameSize, subSize)
        }
    }
}

/** Intensité du halo : monte avec chaque donnée, pulse à l'arrivée du nom. */
private fun haloAlpha(now: Float): Float {
    var a = 0.5f * seg(now, 0.2f, 0.9f, EaseOut)
    for (i in 0..3) {
        val p = seg(now, impactTime(i), 0.3f)
        if (p > 0f) a = max(a, lerp(0.5f + i * 0.1f, 0.7f + i * 0.1f, p))
    }
    val pulse = seg(now, T_TEXT - 0.15f, 1f, EaseOut)
    if (pulse > 0f) a = if (pulse < 0.5f) lerp(a, 1f, pulse / 0.5f) else lerp(1f, 0.8f, (pulse - 0.5f) / 0.5f)
    return a.coerceIn(0f, 1f)
}

/** Le vase « encaisse » chaque donnée : petit écrasement puis rebond. */
private fun squash(now: Float): Pair<Float, Float> {
    for (i in 3 downTo 0) {
        val raw = (now - impactTime(i)) / 0.38f
        if (raw <= 0f || raw >= 1f) continue
        val p = EaseOut.transform(raw)
        return when {
            p < 1f / 3f -> lerp(1f, 1.04f, p * 3f) to lerp(1f, 0.95f, p * 3f)
            p < 2f / 3f -> lerp(1.04f, 0.98f, p * 3f - 1f) to lerp(0.95f, 1.03f, p * 3f - 1f)
            else -> lerp(0.98f, 1f, p * 3f - 2f) to lerp(1.03f, 1f, p * 3f - 2f)
        }
    }
    return 1f to 1f
}

/** Place l'élément centré sur le point d'ancrage, sans occuper de place dans la mise en page. */
private fun Modifier.centerOnOrigin() = layout { measurable, _ ->
    val p = measurable.measure(Constraints())
    layout(0, 0) { p.place(-p.width / 2, -p.height / 2) }
}

@Composable
private fun DataChip(data: FieldData, font: FontFamily, modifier: Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        modifier
            .shadow(8.dp, shape)
            .clip(shape)
            .background(ChipBg)
            .border(1.dp, ChipLine, shape)
            .padding(start = 8.dp, end = 12.dp, top = 7.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        StrokeIcon(data.icon, Modifier.size(19.dp))
        Spacer(Modifier.width(7.dp))
        BasicText(data.label, style = TextStyle(color = TextLight, fontSize = 15.sp, fontFamily = font, fontWeight = FontWeight.Medium), maxLines = 1)
    }
}

/** Icônes au trait (grille 24×24), mêmes tracés que la version web. */
@Composable
private fun StrokeIcon(paths: List<String>, modifier: Modifier) {
    val parsed = remember(paths) { paths.map { PathParser().parsePathString(it).toPath() } }
    Canvas(modifier) {
        scale(size.minDimension / 24f, pivot = Offset.Zero) {
            parsed.forEach {
                drawPath(it, Water, style = Stroke(width = 2f, cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
        }
    }
}

@Composable
private fun Brand(now: Float, bold: FontFamily, medium: FontFamily, nameSize: TextUnit, subSize: TextUnit) {
    val density = LocalDensity.current
    val namePx = with(density) { nameSize.toPx() }
    Column(
        Modifier.semantics(mergeDescendants = true) { contentDescription = "Hydria Terrain" },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // « Hydria » lettre par lettre, en dégradé terre cuite
        Row {
            "Hydria".forEachIndexed { i, c ->
                val p = seg(now, T_TEXT + i * 0.06f, 0.42f, EaseBounce)
                BasicText(
                    c.toString(),
                    style = TextStyle(
                        brush = Brush.verticalGradient(listOf(Clay1, Clay2, Clay3)),
                        fontFamily = bold, fontWeight = FontWeight.ExtraBold,
                        fontSize = nameSize, letterSpacing = (-0.02).em,
                    ),
                    modifier = Modifier.graphicsLayer {
                        alpha = p.coerceIn(0f, 1f)
                        translationY = (1f - p) * 0.35f * namePx
                    },
                )
            }
        }
        Spacer(Modifier.height(6.dp))

        // « TERRAIN » qui se resserre, encadré de deux traits bleu eau
        val sp = seg(now, T_TEXT + 0.38f, 0.7f, EaseSettle)
        val lp = seg(now, T_TEXT + 0.53f, 0.6f, EaseSettle)
        val spacing = lerp(0.6f, 0.32f, sp)
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.graphicsLayer { alpha = sp }) {
            Rule(lp, TransformOrigin(1f, 0.5f))
            Spacer(Modifier.width(10.dp + (spacing * subSize.value).dp)) // compense l'espacement après le « N »
            BasicText(
                "TERRAIN",
                style = TextStyle(
                    color = Muted, fontFamily = medium, fontWeight = FontWeight.Medium,
                    fontSize = subSize, letterSpacing = spacing.em,
                ),
            )
            Spacer(Modifier.width(10.dp))
            Rule(lp, TransformOrigin(0f, 0.5f))
        }
    }
}

@Composable
private fun Rule(progress: Float, origin: TransformOrigin) {
    Box(
        Modifier
            .width(32.dp).height(2.dp)
            .graphicsLayer { scaleX = progress; transformOrigin = origin }
            .background(Water, RoundedCornerShape(2.dp)),
    )
}
