package mg.hydria.bienetre.feature.progress

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material.icons.outlined.Collections
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.MonitorWeight
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.decodeToImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mg.hydria.bienetre.core.designsystem.AuroraBackground
import mg.hydria.bienetre.core.designsystem.SectionTitle
import mg.hydria.bienetre.core.designsystem.WellnessCard
import mg.hydria.bienetre.core.designsystem.WellnessEmerald
import mg.hydria.bienetre.core.designsystem.WellnessGold
import mg.hydria.bienetre.core.designsystem.WellnessOrange
import mg.hydria.bienetre.core.designsystem.WellnessSky
import mg.hydria.bienetre.core.model.BodyMeasurement
import mg.hydria.bienetre.core.model.ProgressOverview
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.io.File
import java.util.Locale
import kotlin.math.abs

@Composable
fun ProgressRoute(
    onBack: () -> Unit,
    onSessionExpired: () -> Unit,
    viewModel: ProgressViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state) { if (state == ProgressUiState.SessionExpired) onSessionExpired() }
    ProgressScreen(
        state = state,
        onBack = onBack,
        onRetry = viewModel::load,
        onAdd = viewModel::add,
        onSelectPhoto = viewModel::selectPhoto,
        onClearPhoto = viewModel::clearSelectedPhoto,
        onUploadPhoto = viewModel::uploadPhoto,
    )
}

@Composable
fun ProgressScreen(
    state: ProgressUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onAdd: (String, String, String, String) -> Unit,
    onSelectPhoto: (ByteArray, String, String) -> Unit = { _, _, _ -> },
    onClearPhoto: () -> Unit = {},
    onUploadPhoto: (String, String) -> Unit = { _, _ -> },
) {
    AuroraBackground(Modifier.fillMaxSize()) {
        when (state) {
            ProgressUiState.Loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            ProgressUiState.SessionExpired -> Unit
            is ProgressUiState.Error -> ErrorState(state.message, onBack, onRetry)
            is ProgressUiState.Content -> ProgressContent(state, onBack, onAdd, onSelectPhoto, onClearPhoto, onUploadPhoto)
        }
    }
}

@Composable
private fun ProgressContent(
    state: ProgressUiState.Content,
    onBack: () -> Unit,
    onAdd: (String, String, String, String) -> Unit,
    onSelectPhoto: (ByteArray, String, String) -> Unit,
    onClearPhoto: () -> Unit,
    onUploadPhoto: (String, String) -> Unit,
) {
    var dialogOpen by remember { mutableStateOf(false) }
    var photoDialogOpen by remember { mutableStateOf(false) }
    var fullscreenPhoto by remember { mutableStateOf<PrivateProgressPhoto?>(null) }
    Box(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(20.dp, 22.dp, 20.dp, 96.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            item { Header(onBack) }
            state.message?.let { message -> item { WellnessCard(Modifier.fillMaxWidth(), emphasized = true) { Text(message) } } }
            if (state.data.measurements.isEmpty()) {
                item { EmptyProgress() }
            } else {
                item { Summary(state.data) }
                item { WeightChart(state.data.measurements) }
                item { SectionTitle("Historique", "Vos mesures les plus récentes") }
                items(state.data.measurements, key = { it.id }) { MeasurementRow(it) }
            }
            item { PhotoSection(state.photos, onOpenAdd = { photoDialogOpen = true }, onOpenPhoto = { fullscreenPhoto = it }) }
        }
        FloatingActionButton(
            onClick = { dialogOpen = true },
            modifier = Modifier.align(Alignment.BottomEnd).padding(22.dp),
            containerColor = WellnessOrange,
        ) { Icon(Icons.Outlined.Add, contentDescription = "Ajouter une mesure") }
    }
    if (dialogOpen) {
        AddMeasurementDialog(
            saving = state.saving,
            onDismiss = { if (!state.saving) dialogOpen = false },
            onSave = { date, weight, muscle, fat -> onAdd(date, weight, muscle, fat); dialogOpen = false },
        )
    }
    if (photoDialogOpen) {
        AddPhotoDialog(
            pending = state.pendingPhoto,
            uploading = state.uploadingPhoto,
            onSelected = onSelectPhoto,
            onClear = onClearPhoto,
            onDismiss = { if (!state.uploadingPhoto) photoDialogOpen = false },
            onUpload = { date, note -> onUploadPhoto(date, note); photoDialogOpen = false },
        )
    }
    fullscreenPhoto?.let { photo -> FullscreenPhoto(photo) { fullscreenPhoto = null } }
}

@Composable
private fun Header(onBack: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Retour") }
        Column(Modifier.padding(start = 6.dp)) {
            Text("ÉVOLUTION CORPORELLE", color = WellnessOrange, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.8.sp)
            Text("Votre progression", style = MaterialTheme.typography.displaySmall)
        }
    }
}

@Composable
private fun Summary(data: ProgressOverview) {
    val latest = data.latest ?: return
    LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        item { MetricCard("Poids", latest.weightKg, "kg", WellnessEmerald) }
        item { MetricCard("Muscle", latest.muscleMassKg, "kg", WellnessSky) }
        item { MetricCard("Graisse", latest.fatMassKg, "kg", WellnessGold) }
        item {
            WellnessCard(Modifier.width(170.dp), emphasized = true) {
                Text("Évolution", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                val delta = data.weightDelta
                Text(
                    delta?.let { "${if (it > 0) "+" else ""}${format(it)} kg" } ?: "—",
                    Modifier.padding(top = 8.dp),
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                    color = when { delta == null -> MaterialTheme.colorScheme.onSurface; abs(delta) < 0.05 -> WellnessGold; delta < 0 -> WellnessEmerald; else -> WellnessOrange },
                )
                Text("depuis la mesure précédente", Modifier.padding(top = 5.dp), fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun MetricCard(label: String, value: Double?, unit: String, color: androidx.compose.ui.graphics.Color) {
    WellnessCard(Modifier.width(170.dp)) {
        Icon(Icons.Outlined.MonitorWeight, null, tint = color)
        Text(label, Modifier.padding(top = 10.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        Text(value?.let { "${format(it)} $unit" } ?: "—", Modifier.padding(top = 5.dp), fontSize = 24.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun WeightChart(measurements: List<BodyMeasurement>) {
    val points = measurements.asReversed().mapNotNull { it.weightKg }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("Courbe du poids", "Tendance des ${points.size} dernières mesures renseignées")
        WellnessCard(Modifier.fillMaxWidth()) {
            if (points.size < 2) {
                Text("Ajoutez au moins deux poids pour afficher la courbe.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                val lineColor = WellnessEmerald
                val gridColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.18f)
                Canvas(Modifier.fillMaxWidth().height(180.dp)) {
                    repeat(4) { row ->
                        val y = size.height * row / 3f
                        drawLine(gridColor, Offset(0f, y), Offset(size.width, y), strokeWidth = 1.dp.toPx())
                    }
                    val min = points.min()
                    val max = points.max()
                    val range = (max - min).takeIf { it > 0.01 } ?: 1.0
                    val path = Path()
                    points.forEachIndexed { index, value ->
                        val x = size.width * index / (points.size - 1).toFloat()
                        val y = size.height - ((value - min) / range).toFloat() * size.height
                        if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
                        drawCircle(lineColor, radius = 4.dp.toPx(), center = Offset(x, y))
                    }
                    drawPath(path, lineColor, style = Stroke(width = 3.dp.toPx(), cap = StrokeCap.Round))
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("${format(points.first())} kg", fontSize = 12.sp)
                    Text("${format(points.last())} kg", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun MeasurementRow(value: BodyMeasurement) {
    WellnessCard(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text(formatDate(value.date), fontWeight = FontWeight.Bold)
                Text(
                    listOfNotNull(value.muscleMassKg?.let { "Muscle ${format(it)} kg" }, value.fatMassKg?.let { "Graisse ${format(it)} kg" }).joinToString("  •  ").ifBlank { "Composition non renseignée" },
                    Modifier.padding(top = 5.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
            }
            Text(value.weightKg?.let { "${format(it)} kg" } ?: "—", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = WellnessEmerald)
        }
    }
}

@Composable
private fun EmptyProgress() {
    WellnessCard(Modifier.fillMaxWidth(), emphasized = true) {
        Icon(Icons.Outlined.MonitorWeight, null, tint = WellnessEmerald)
        Text("Aucune mesure", Modifier.padding(top = 12.dp), style = MaterialTheme.typography.titleLarge)
        Text("Ajoutez votre première mesure pour suivre une évolution réelle, sans estimation.", Modifier.padding(top = 7.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun AddMeasurementDialog(saving: Boolean, onDismiss: () -> Unit, onSave: (String, String, String, String) -> Unit) {
    var date by remember { mutableStateOf(LocalDate.now().toString()) }
    var weight by remember { mutableStateOf("") }
    var muscle by remember { mutableStateOf("") }
    var fat by remember { mutableStateOf("") }
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Nouvelle mesure") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                MeasureField("Date (AAAA-MM-JJ)", date) { date = it }
                MeasureField("Poids (kg)", weight) { weight = it }
                MeasureField("Masse musculaire (kg)", muscle) { muscle = it }
                MeasureField("Masse graisseuse (kg)", fat) { fat = it }
                Text("Une seule valeur corporelle suffit. Les champs non mesurés restent vides.", fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { Button(onClick = { onSave(date, weight, muscle, fat) }, enabled = !saving) { if (saving) CircularProgressIndicator(Modifier.height(18.dp)) else Text("Enregistrer") } },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !saving) { Text("Annuler") } },
        shape = RoundedCornerShape(28.dp),
    )
}

@Composable
private fun PhotoSection(
    photos: List<PrivateProgressPhoto>,
    onOpenAdd: () -> Unit,
    onOpenPhoto: (PrivateProgressPhoto) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            SectionTitle("Photos privées", "Première et dernière progression")
            TextButton(onClick = onOpenAdd) { Icon(Icons.Outlined.Add, null); Text("Ajouter") }
        }
        if (photos.isEmpty()) {
            WellnessCard(Modifier.fillMaxWidth()) {
                Icon(Icons.Outlined.Collections, null, tint = WellnessSky)
                Text("Aucune photo enregistrée", Modifier.padding(top = 10.dp), fontWeight = FontWeight.Bold)
                Text("Les images restent accessibles uniquement par votre session authentifiée.", Modifier.padding(top = 5.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            }
        } else {
            val first = photos.first()
            val latest = photos.last()
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                ComparisonPhoto("Première", first, Modifier.weight(1f), onOpenPhoto)
                ComparisonPhoto("Dernière", latest, Modifier.weight(1f), onOpenPhoto)
            }
            LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                items(photos, key = { it.metadata.id }) { photo ->
                    Column(Modifier.width(112.dp).clickable { onOpenPhoto(photo) }) {
                        PrivateImage(photo.bytes, Modifier.fillMaxWidth().height(118.dp))
                        Text(formatDate(photo.metadata.date), Modifier.padding(top = 6.dp), fontSize = 11.sp, maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
private fun ComparisonPhoto(label: String, photo: PrivateProgressPhoto, modifier: Modifier, onOpen: (PrivateProgressPhoto) -> Unit) {
    WellnessCard(modifier.clickable { onOpen(photo) }) {
        Text(label.uppercase(Locale.FRANCE), color = WellnessOrange, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp)
        PrivateImage(photo.bytes, Modifier.fillMaxWidth().height(180.dp).padding(top = 9.dp))
        Text(formatDate(photo.metadata.date), Modifier.padding(top = 8.dp), fontWeight = FontWeight.SemiBold)
        if (photo.metadata.note.isNotBlank()) Text(photo.metadata.note, Modifier.padding(top = 4.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, maxLines = 2)
    }
}

@Composable
private fun PrivateImage(bytes: ByteArray, modifier: Modifier) {
    val bitmap = remember(bytes) { runCatching { bytes.decodeToImageBitmap() }.getOrNull() }
    if (bitmap == null) {
        Box(modifier.clip(RoundedCornerShape(18.dp)), contentAlignment = Alignment.Center) { Icon(Icons.Outlined.Collections, null) }
    } else {
        Image(bitmap, contentDescription = "Photo de progression privée", modifier = modifier.clip(RoundedCornerShape(18.dp)), contentScale = ContentScale.Crop)
    }
}

@Composable
private fun AddPhotoDialog(
    pending: PendingProgressPhoto?,
    uploading: Boolean,
    onSelected: (ByteArray, String, String) -> Unit,
    onClear: () -> Unit,
    onDismiss: () -> Unit,
    onUpload: (String, String) -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var cameraTarget by remember { mutableStateOf<CameraTarget?>(null) }
    var date by remember { mutableStateOf(LocalDate.now().toString()) }
    var note by remember { mutableStateOf("") }
    fun consume(uri: Uri, fallbackMime: String? = null) {
        scope.launch {
            readSelection(context, uri, fallbackMime)?.let { onSelected(it.bytes, it.mimeType, it.filename) }
        }
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> uri?.let(::consume) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val target = cameraTarget
        if (success && target != null) {
            scope.launch {
                try {
                    readSelection(context, target.uri, "image/jpeg")?.let { onSelected(it.bytes, it.mimeType, it.filename) }
                } finally {
                    target.file.delete()
                    cameraTarget = null
                }
            }
        } else {
            target?.file?.delete()
            cameraTarget = null
        }
    }
    androidx.compose.material3.AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Photo de progression") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (pending == null) {
                    Button(
                        onClick = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Icon(Icons.Outlined.Collections, null); Text("Choisir dans la galerie", Modifier.padding(start = 8.dp)) }
                    Button(
                        onClick = {
                            val target = createCameraTarget(context)
                            cameraTarget = target
                            camera.launch(target.uri)
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Icon(Icons.Outlined.CameraAlt, null); Text("Prendre une photo", Modifier.padding(start = 8.dp)) }
                } else {
                    PrivateImage(pending.bytes, Modifier.fillMaxWidth().height(220.dp))
                    TextButton(onClick = onClear) { Text("Changer la photo") }
                }
                MeasureField("Date (AAAA-MM-JJ)", date) { date = it }
                OutlinedTextField(note, { if (it.length <= 255) note = it }, Modifier.fillMaxWidth(), label = { Text("Note facultative") }, minLines = 2)
                Text("JPEG, PNG ou WebP · 10 Mo maximum. Aucun accès global à votre galerie n’est demandé.", fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { Button(onClick = { onUpload(date, note) }, enabled = pending != null && !uploading) { if (uploading) CircularProgressIndicator(Modifier.height(18.dp)) else Text("Envoyer") } },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !uploading) { Text("Annuler") } },
        shape = RoundedCornerShape(28.dp),
    )
}

@Composable
private fun FullscreenPhoto(photo: PrivateProgressPhoto, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize()) {
            PrivateImage(photo.bytes, Modifier.fillMaxSize())
            IconButton(onClick = onDismiss, modifier = Modifier.align(Alignment.TopEnd).padding(12.dp)) {
                Icon(Icons.Outlined.Close, contentDescription = "Fermer")
            }
            WellnessCard(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(12.dp)) {
                Text(formatDate(photo.metadata.date), fontWeight = FontWeight.Bold)
                if (photo.metadata.note.isNotBlank()) Text(photo.metadata.note, Modifier.padding(top = 5.dp))
            }
        }
    }
}

private data class SelectedImage(val bytes: ByteArray, val mimeType: String, val filename: String)
private data class CameraTarget(val file: File, val uri: Uri)

private suspend fun readSelection(context: Context, uri: Uri, fallbackMime: String?): SelectedImage? = withContext(Dispatchers.IO) {
    val mime = context.contentResolver.getType(uri) ?: fallbackMime ?: return@withContext null
    val extension = when (mime) { "image/jpeg" -> "jpg"; "image/png" -> "png"; "image/webp" -> "webp"; else -> return@withContext null }
    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readNBytes(10 * 1024 * 1024 + 1) } ?: return@withContext null
    SelectedImage(bytes, mime, "progress-${System.currentTimeMillis()}.$extension")
}

private fun createCameraTarget(context: Context): CameraTarget {
    val directory = File(context.cacheDir, "private-captures").apply { mkdirs() }
    val file = File.createTempFile("progress-", ".jpg", directory)
    return CameraTarget(file, FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file))
}

@Composable
private fun MeasureField(label: String, value: String, onValueChange: (String) -> Unit) {
    OutlinedTextField(value, onValueChange, Modifier.fillMaxWidth(), label = { Text(label) }, singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
}

@Composable
private fun ErrorState(message: String, onBack: () -> Unit, onRetry: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        Text("Progression indisponible", style = MaterialTheme.typography.headlineSmall)
        Text(message, Modifier.padding(top = 8.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(Modifier.padding(top = 18.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            TextButton(onClick = onBack) { Text("Retour") }
            Button(onClick = onRetry) { Icon(Icons.Outlined.Refresh, null); Text("Réessayer", Modifier.padding(start = 8.dp)) }
        }
    }
}

private fun format(value: Double) = String.format(Locale.FRANCE, "%.1f", value)
private fun formatDate(value: String): String = runCatching { LocalDate.parse(value).format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.FRANCE)) }.getOrDefault(value)
