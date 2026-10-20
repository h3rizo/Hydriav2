package mg.hydria.planningdujourwidget

import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {
    private lateinit var subtitle: TextView
    private lateinit var title: TextView
    private lateinit var list: LinearLayout
    private lateinit var progress: ProgressBar
    private var token: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_detail)
        subtitle = findViewById(R.id.detail_subtitle)
        title = findViewById(R.id.detail_title)
        list = findViewById(R.id.detail_list)
        progress = findViewById(R.id.detail_progress)
        findViewById<ImageButton>(R.id.detail_refresh).setOnClickListener { load() }
        findViewById<View>(R.id.detail_open_web).setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.hydria.mg/widget/")))
        }
        title.text = "Activités du jour"
        token = TokenStore.getToken(this)
        if (token == null) {
            subtitle.text = "Connexion requise"
            list.removeAllViews()
            list.addView(message("Ouvrez Hydria · Activités du jour pour reconnecter le widget."))
        } else load()
    }

    private fun load() {
        val activeToken = token ?: return
        progress.visibility = View.VISIBLE
        lifecycleScope.launch {
            val today = PlanningDuJourWidgetProvider.todayIso()
            val result = HydriaApi.fetchActivites(activeToken, today, today)
            render(result)
        }
    }

    private fun render(result: HydriaApi.ActivitesResult) {
        progress.visibility = View.GONE
        list.removeAllViews()
        if (!result.success) {
            subtitle.text = "Chargement impossible"
            list.addView(message(result.error ?: "Erreur Hydria"))
            return
        }
        val sorted = result.activites.sortedWith(compareBy({ it.date }, { it.heure }))
        subtitle.text = "${sorted.size} activité${if (sorted.size > 1) "s" else ""} aujourd’hui"
        if (sorted.isEmpty()) {
            list.addView(message("Aucune activité planifiée aujourd’hui."))
            return
        }
        sorted.forEach { item -> list.addView(activiteRow(item)) }
    }

    private fun activiteRow(item: HydriaApi.PlanningActivite): View {
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) }
            setBackgroundResource(R.drawable.note_background)
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }
        val headerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        headerRow.addView(TextView(this).apply {
            text = item.activite
            setTextColor(ContextCompat.getColor(this@DetailActivity, R.color.text_primary))
            textSize = 15f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        })
        headerRow.addView(statutBadge(item))
        container.addView(headerRow)
        val timePart = if (item.heure.isNotBlank()) item.heure else "Toute la journée"
        val metaLines = listOfNotNull(
            timePart,
            item.ouvrage.takeIf { it.isNotBlank() },
            listOf(item.employe, item.base, item.commune).filter { it.isNotBlank() }.joinToString(" · ").takeIf { it.isNotBlank() },
        )
        container.addView(TextView(this).apply {
            text = metaLines.joinToString("\n")
            setTextColor(ContextCompat.getColor(this@DetailActivity, R.color.text_secondary))
            textSize = 12f
            setPadding(0, dp(6), 0, 0)
        })
        if (item.remarque.isNotBlank()) {
            container.addView(TextView(this).apply {
                text = item.remarque
                setTextColor(ContextCompat.getColor(this@DetailActivity, R.color.text_secondary))
                textSize = 11f
                setPadding(0, dp(6), 0, 0)
                setTypeface(typeface, android.graphics.Typeface.ITALIC)
            })
        }
        return container
    }

    private fun statutBadge(item: HydriaApi.PlanningActivite): TextView = TextView(this).apply {
        text = if (item.termine) "TERMINÉ" else "EN COURS"
        setTextColor(Color.parseColor("#071D25"))
        textSize = 10f
        setTypeface(typeface, android.graphics.Typeface.BOLD)
        setPadding(dp(8), dp(3), dp(8), dp(3))
        setBackgroundColor(ContextCompat.getColor(this@DetailActivity, if (item.termine) R.color.statut_termine else R.color.statut_en_cours))
    }

    private fun message(value: String) = TextView(this).apply {
        text = value
        gravity = Gravity.CENTER
        setTextColor(ContextCompat.getColor(this@DetailActivity, R.color.text_secondary))
        setPadding(dp(12), dp(22), dp(12), dp(22))
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
}
