package mg.hydria.reunions.representantes

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import mg.hydria.reunions.HydriaReunionsApi
import mg.hydria.reunions.R
import mg.hydria.reunions.ReunionsDatabase
import mg.hydria.reunions.SessionManager
import mg.hydria.reunions.SyncManager
import mg.hydria.reunions.ui.SimpleListAdapter
import org.json.JSONObject
import java.util.concurrent.Executors

/** Liste des représentantes des usagers, hors ligne par défaut (base locale),
 * avec tirer-pour-rafraîchir qui relance une synchronisation complète. */
class RepresentantesActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var db: ReunionsDatabase
    private lateinit var session: SessionManager
    private lateinit var adapter: SimpleListAdapter<JSONObject>
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var textEmpty: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_list)
        title = getString(R.string.menu_representantes)

        db = ReunionsDatabase(this)
        session = SessionManager(this)
        swipeRefresh = findViewById(R.id.swipe_refresh)
        textEmpty = findViewById(R.id.text_empty)

        adapter = SimpleListAdapter(
            items = emptyList(),
            title = { it.optString("nom").ifBlank { "Sans nom" } },
            subtitle = { "${it.optString("village_nom")} · ${it.optString("commune_nom")}" },
            onClick = { representant ->
                startActivity(
                    Intent(this, RepresentantDetailActivity::class.java)
                        .putExtra(RepresentantDetailActivity.EXTRA_REPRESENTANT_JSON, representant.toString()),
                )
            },
        )
        findViewById<RecyclerView>(R.id.recycler_view).apply {
            layoutManager = LinearLayoutManager(this@RepresentantesActivity)
            adapter = this@RepresentantesActivity.adapter
        }

        swipeRefresh.setOnRefreshListener { refreshFromServer() }
        loadFromLocalDb()
    }

    override fun onResume() {
        super.onResume()
        loadFromLocalDb()
    }

    private fun loadFromLocalDb() {
        val items = db.all("representantes").sortedBy { it.optString("nom") }
        adapter.submitList(items)
        textEmpty.visibility = if (items.isEmpty()) android.view.View.VISIBLE else android.view.View.GONE
    }

    private fun refreshFromServer() {
        val token = session.token
        if (token == null) {
            swipeRefresh.isRefreshing = false
            return
        }
        executor.execute {
            val result = HydriaReunionsApi.bootstrap(token)
            if (result.successful) {
                SyncManager(db).applyReunionsBootstrap(result.body.getJSONObject("payload"))
            }
            runOnUiThread {
                swipeRefresh.isRefreshing = false
                loadFromLocalDb()
            }
        }
    }
}
