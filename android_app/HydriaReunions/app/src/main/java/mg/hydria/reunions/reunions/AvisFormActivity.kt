package mg.hydria.reunions.reunions

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.checkbox.MaterialCheckBox
import com.google.android.material.textfield.TextInputEditText
import mg.hydria.reunions.OutboxSyncer
import mg.hydria.reunions.R
import mg.hydria.reunions.ReunionsDatabase
import mg.hydria.reunions.SessionManager
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.concurrent.Executors

/** Saisie d'un avis pour une représentante — écrit d'abord en local (visible
 * immédiatement), puis tente de synchroniser avec le serveur. */
class AvisFormActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_REPRESENTANT_ID = "representant_id"
        const val EXTRA_REPRESENTANT_NOM = "representant_nom"
    }

    private val executor = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_avis_form)
        title = "Nouvel avis"

        val representantId = intent.getStringExtra(EXTRA_REPRESENTANT_ID) ?: return finish()
        findViewById<android.widget.TextView>(R.id.text_representant_nom).text =
            intent.getStringExtra(EXTRA_REPRESENTANT_NOM) ?: ""

        findViewById<android.widget.Button>(R.id.button_save).setOnClickListener {
            val payload = JSONObject().apply {
                put("representant_id", representantId)
                put("date_avis", SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date()))
                put("quantite_ok", findViewById<MaterialCheckBox>(R.id.check_quantite).isChecked)
                put("qualite_ok", findViewById<MaterialCheckBox>(R.id.check_qualite).isChecked)
                put("delai_reparation_ok", findViewById<MaterialCheckBox>(R.id.check_delai).isChecked)
                put("relation_gestionnaire_ok", findViewById<MaterialCheckBox>(R.id.check_relation).isChecked)
                put("probleme_technique", textOf(R.id.input_probleme_technique))
                put("probleme_recouvrement", textOf(R.id.input_probleme_recouvrement))
                put("probleme_regles_utilisation", textOf(R.id.input_probleme_regles))
                put("remarque", textOf(R.id.input_remarque))
            }

            val db = ReunionsDatabase(this)
            val outbox = OutboxSyncer(db, SessionManager(this))
            val avisId = outbox.enqueue("avis.upsert", payload)
            // Ecriture optimiste locale : visible immediatement dans l'historique,
            // meme avant confirmation serveur.
            db.upsert("avis", avisId, representantId, payload.put("id", avisId), payload.optString("date_avis"))

            Toast.makeText(this, "Avis enregistré (synchronisation en cours)", Toast.LENGTH_SHORT).show()
            executor.execute { outbox.flush() }
            finish()
        }
    }

    private fun textOf(id: Int): String = findViewById<TextInputEditText>(id).text?.toString()?.trim().orEmpty()
}
