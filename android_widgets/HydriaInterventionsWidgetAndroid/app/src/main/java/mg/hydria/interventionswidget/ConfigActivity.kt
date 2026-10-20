package mg.hydria.interventionswidget

import android.Manifest
import android.app.Activity
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

class ConfigActivity : AppCompatActivity() {
    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID
    private lateinit var username: EditText
    private lateinit var password: EditText
    private lateinit var status: TextView
    private lateinit var loginButton: Button
    private lateinit var addButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(Activity.RESULT_CANCELED)
        setContentView(R.layout.activity_config)
        appWidgetId = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        username = findViewById(R.id.username)
        password = findViewById(R.id.password)
        status = findViewById(R.id.config_status)
        loginButton = findViewById(R.id.login_button)
        addButton = findViewById(R.id.add_widget_button)

        loginButton.setOnClickListener { login() }
        addButton.setOnClickListener { completeConfiguration() }
        if (TokenStore.getToken(this) != null) showConnected()
    }

    private fun login() {
        val user = username.text.toString().trim()
        val secret = password.text.toString()
        if (user.isBlank() || secret.isBlank()) {
            status.text = "Saisissez votre identifiant et votre mot de passe."
            return
        }
        loginButton.isEnabled = false
        status.text = "Connexion à Hydria…"
        lifecycleScope.launch {
            val result = HydriaApi.login(user, secret)
            loginButton.isEnabled = true
            if (result.success && result.token != null) {
                TokenStore.saveToken(this@ConfigActivity, result.token)
                password.text.clear()
                requestNotifications()
                showConnected()
                InterventionsWidgetProvider.requestUpdate(this@ConfigActivity)
            } else status.text = result.error ?: "Connexion impossible"
        }
    }

    private fun showConnected() {
        status.text = "Connecté. Les réparations non vues seront présentées une par une."
        addButton.visibility = View.VISIBLE
        loginButton.text = "Reconnecter"
    }

    private fun requestNotifications() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 42)
        }
    }

    private fun completeConfiguration() {
        if (appWidgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
            setResult(Activity.RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId))
            InterventionsWidgetProvider.requestUpdate(this)
            finish()
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = AppWidgetManager.getInstance(this)
            if (manager.isRequestPinAppWidgetSupported) {
                val provider = ComponentName(this, InterventionsWidgetProvider::class.java)
                val callback = PendingIntent.getBroadcast(this, 843, Intent(this, InterventionsWidgetProvider::class.java).setAction(InterventionsWidgetProvider.ACTION_REFRESH), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                manager.requestPinAppWidget(provider, null, callback)
                status.text = "Confirmez l’ajout proposé par Android."
                return
            }
        }
        status.text = "Maintenez un espace vide sur l’écran d’accueil, puis choisissez Widgets > Hydria · Interventions."
    }
}
