package mg.hydria.reunions

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import mg.hydria.reunions.conversations.ConversationsActivity
import mg.hydria.reunions.reunions.ReunionsActivity
import mg.hydria.reunions.representantes.RepresentantesActivity
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var session: SessionManager
    private lateinit var db: ReunionsDatabase
    private lateinit var sync: SyncManager
    private lateinit var textSyncStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        session = SessionManager(this)
        if (!session.isLoggedIn) {
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
            return
        }

        setContentView(R.layout.activity_main)
        db = ReunionsDatabase(this)
        sync = SyncManager(db)

        findViewById<TextView>(R.id.text_welcome).text =
            getString(R.string.app_name) + (session.employeNom?.let { " — $it" } ?: "")
        textSyncStatus = findViewById(R.id.text_sync_status)

        findViewById<android.widget.Button>(R.id.button_representantes).setOnClickListener {
            startActivity(Intent(this, RepresentantesActivity::class.java))
        }
        findViewById<android.widget.Button>(R.id.button_reunions).setOnClickListener {
            startActivity(Intent(this, ReunionsActivity::class.java))
        }
        findViewById<android.widget.Button>(R.id.button_conversations).setOnClickListener {
            startActivity(Intent(this, ConversationsActivity::class.java))
        }
        findViewById<android.widget.Button>(R.id.button_logout).setOnClickListener {
            session.clear()
            db.clearAll()
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }

        runSync()
    }

    private fun runSync() {
        val token = session.token ?: return
        textSyncStatus.text = getString(R.string.sync_in_progress)
        executor.execute {
            // Diagnostic temporaire (phase de mise au point) : affiche le nombre d'elements
            // recus et le detail de toute erreur HTTP, plutot qu'un simple succes/echec binaire.
            val statusParts = mutableListOf<String>()
            try {
                val reunionsResult = HydriaReunionsApi.bootstrap(token)
                if (reunionsResult.successful) {
                    val payload = reunionsResult.body.getJSONObject("payload")
                    val nbRepresentants = payload.optJSONArray("representants")?.length() ?: -1
                    sync.applyReunionsBootstrap(payload)
                    statusParts.add("Representantes recues : $nbRepresentants")
                } else {
                    statusParts.add("Erreur reunions (${reunionsResult.status}) : ${reunionsResult.error}")
                }
            } catch (e: Exception) {
                statusParts.add("Exception reunions : ${e.message}")
            }
            try {
                val messagingResult = HydriaReunionsApi.messagingBootstrap(token)
                if (messagingResult.successful) {
                    sync.applyMessagingBootstrap(messagingResult.body.getJSONObject("payload"))
                } else {
                    statusParts.add("Erreur messagerie (${messagingResult.status}) : ${messagingResult.error}")
                }
            } catch (e: Exception) {
                statusParts.add("Exception messagerie : ${e.message}")
            }
            runOnUiThread {
                textSyncStatus.text = statusParts.joinToString("  |  ")
            }
        }
    }
}
