package mg.hydria.bienetre.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun BienetreBrandLogo(
    modifier: Modifier = Modifier,
    contentDescription: String? = "Logo Bien-être Hydria",
) {
    Image(
        painter = painterResource(R.drawable.bienetre_arm_logo),
        contentDescription = contentDescription,
        modifier = modifier.clip(RoundedCornerShape(24.dp)),
        contentScale = ContentScale.Crop,
    )
}

@Composable
fun AuroraBackground(
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit,
) {
    val background = MaterialTheme.colorScheme.background
    CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onBackground) {
        Box(
            modifier = modifier
                .background(background)
                .background(
                    Brush.radialGradient(
                        colors = listOf(
                            MaterialTheme.colorScheme.secondary.copy(alpha = 0.17f),
                            Color.Transparent,
                        ),
                        radius = 820f,
                        center = androidx.compose.ui.geometry.Offset(80f, 100f),
                    ),
                )
                .background(
                    Brush.radialGradient(
                        colors = listOf(
                            MaterialTheme.colorScheme.tertiary.copy(alpha = 0.10f),
                            Color.Transparent,
                        ),
                        radius = 760f,
                        center = androidx.compose.ui.geometry.Offset(900f, 140f),
                    ),
                ),
            content = content,
        )
    }
}

@Composable
fun WellnessCard(
    modifier: Modifier = Modifier,
    emphasized: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(if (emphasized) 30.dp else 24.dp)
    val surface = if (emphasized) {
        Brush.linearGradient(
            listOf(
                MaterialTheme.colorScheme.primary.copy(alpha = 0.14f),
                MaterialTheme.colorScheme.surface.copy(alpha = 0.94f),
            ),
        )
    } else {
        Brush.linearGradient(
            listOf(
                MaterialTheme.colorScheme.surface.copy(alpha = 0.90f),
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.66f),
            ),
        )
    }
    CompositionLocalProvider(LocalContentColor provides MaterialTheme.colorScheme.onSurface) {
        Column(
            modifier = modifier
                .clip(shape)
                .background(surface)
                .border(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.75f), shape)
                .padding(20.dp),
            content = content,
        )
    }
}

@Composable
fun SectionTitle(kicker: String, title: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(
            text = kicker.uppercase(),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            letterSpacing = 1.8.sp,
        )
        Text(
            text = title,
            modifier = Modifier.padding(top = 5.dp),
            style = MaterialTheme.typography.titleLarge,
        )
    }
}
