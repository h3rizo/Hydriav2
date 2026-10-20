package mg.hydria.interventionswidget

import android.app.Dialog
import android.graphics.Bitmap
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {
    private lateinit var title: TextView
    private lateinit var meta: TextView
    private lateinit var note: TextView
    private lateinit var unseen: TextView
    private lateinit var gallery: LinearLayout
    private lateinit var progress: ProgressBar
    private lateinit var seenButton: Button
    private var current: HydriaApi.Intervention? = null
    private var token: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_detail)
        title = findViewById(R.id.detail_title)
        meta = findViewById(R.id.detail_meta)
        note = findViewById(R.id.detail_note)
        unseen = findViewById(R.id.detail_unseen)
        gallery = findViewById(R.id.detail_gallery)
        progress = findViewById(R.id.detail_progress)
        seenButton = findViewById(R.id.detail_seen)
        findViewById<View>(R.id.detail_refresh).setOnClickListener { load() }
        seenButton.setOnClickListener { markSeen() }
        token = TokenStore.getToken(this)
        if (token == null) {
            title.text = "Connexion requise"
            meta.text = "Ouvrez Hydria · Interventions pour reconnecter le widget."
            seenButton.visibility = View.GONE
        } else load()
    }

    private fun load() {
        val activeToken = token ?: return
        progress.visibility = View.VISIBLE
        seenButton.isEnabled = false
        lifecycleScope.launch {
            render(HydriaApi.fetchQueue(activeToken))
        }
    }

    private fun markSeen() {
        val item = current ?: return
        val activeToken = token ?: return
        progress.visibility = View.VISIBLE
        seenButton.isEnabled = false
        lifecycleScope.launch {
            val result = HydriaApi.markSeen(activeToken, item.id)
            render(result)
            InterventionsWidgetProvider.requestUpdate(this@DetailActivity)
        }
    }

    private fun render(result: HydriaApi.QueueResult) {
        progress.visibility = View.GONE
        gallery.removeAllViews()
        if (!result.success) {
            title.text = "Chargement impossible"
            meta.text = result.error
            note.text = ""
            seenButton.visibility = View.GONE
            return
        }
        unseen.text = "${result.weekCount} cette semaine · ${result.unseenCount} non vue${if (result.unseenCount > 1) "s" else ""}"
        current = result.current
        val item = result.current
        if (item == null) {
            title.text = "Tout est vu"
            meta.text = "Aucune nouvelle saisie de réparation."
            note.text = "Le widget affichera automatiquement la prochaine publication."
            seenButton.visibility = View.GONE
            return
        }
        title.text = item.activity
        meta.text = buildString {
            append(item.ouvrage)
            append("\n")
            append(item.employee)
            if (item.base.isNotBlank()) append(" · ${item.base}")
            if (item.createdAt.isNotBlank()) append("\nSaisie le ${item.createdAt}")
            if (item.interventionDate.isNotBlank()) append(" · intervention ${item.interventionDate}")
            if (item.status.isNotBlank()) append("\n${item.status}")
        }
        note.text = item.note.ifBlank { "Aucune remarque." }
        seenButton.visibility = View.VISIBLE
        seenButton.isEnabled = true
        if (item.photos.isEmpty()) {
            gallery.addView(message("Aucune photo jointe."))
        } else item.photos.forEach { photo ->
            if (photo.isVideo) gallery.addView(message("Vidéo : ${photo.name}")) else loadPhoto(photo)
        }
    }

    private fun loadPhoto(photo: HydriaApi.Photo) {
        val image = ImageView(this).apply {
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(220)).apply { bottomMargin = dp(12) }
            scaleType = ImageView.ScaleType.CENTER_CROP
            setBackgroundColor(ContextCompat.getColor(this@DetailActivity, R.color.surface_muted))
            contentDescription = "Agrandir ${photo.name}"
        }
        gallery.addView(image)
        lifecycleScope.launch {
            val bitmap = HydriaApi.fetchPhoto(token ?: return@launch, photo.url)
            if (bitmap != null) {
                image.setImageBitmap(bitmap)
                image.setOnClickListener { showFullScreen(bitmap) }
            } else {
                image.scaleType = ImageView.ScaleType.CENTER
                image.setImageResource(android.R.drawable.ic_menu_report_image)
            }
        }
    }

    private fun showFullScreen(bitmap: Bitmap) {
        Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen).apply {
            val image = ImageView(this@DetailActivity).apply {
                setImageBitmap(bitmap)
                scaleType = ImageView.ScaleType.FIT_CENTER
                setBackgroundColor(android.graphics.Color.BLACK)
                setOnClickListener { dismiss() }
            }
            setContentView(image, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            show()
        }
    }

    private fun message(value: String) = TextView(this).apply {
        text = value
        gravity = Gravity.CENTER
        setTextColor(ContextCompat.getColor(this@DetailActivity, R.color.text_secondary))
        setPadding(dp(12), dp(22), dp(12), dp(22))
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
