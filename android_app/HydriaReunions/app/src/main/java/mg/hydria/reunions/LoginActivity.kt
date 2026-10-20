package mg.hydria.reunions

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.CheckBox
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import java.util.concurrent.Executors

class LoginActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var session: SessionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        session = SessionManager(this)

        if (session.isLoggedIn) {
            goToMain()
            return
        }

        setContentView(R.layout.activity_login)

        val inputUsername = findViewById<TextInputEditText>(R.id.input_username)
        val inputPassword = findViewById<TextInputEditText>(R.id.input_password)
        val checkboxRememberMe = findViewById<CheckBox>(R.id.checkbox_remember_me)
        val textError = findViewById<TextView>(R.id.text_error)
        val progress = findViewById<ProgressBar>(R.id.progress_login)
        val buttonLogin = findViewById<MaterialButton>(R.id.button_login)

        buttonLogin.setOnClickListener {
            val username = inputUsername.text?.toString()?.trim().orEmpty()
            val password = inputPassword.text?.toString()?.trim().orEmpty()
            if (username.isEmpty() || password.isEmpty()) {
                textError.text = getString(R.string.login_error_generic)
                textError.visibility = View.VISIBLE
                return@setOnClickListener
            }

            textError.visibility = View.GONE
            progress.visibility = View.VISIBLE
            buttonLogin.isEnabled = false

            executor.execute {
                val result = HydriaReunionsApi.login(username, password, deviceLabel = android.os.Build.MODEL ?: "Android")
                runOnUiThread {
                    progress.visibility = View.GONE
                    buttonLogin.isEnabled = true
                    if (result.successful && result.body.optBoolean("success", true)) {
                        session.save(
                            token = result.body.getString("token"),
                            employeId = result.body.optString("employe_id", null),
                            employeNom = result.body.optString("employe_nom", null),
                            rememberMe = checkboxRememberMe.isChecked,
                        )
                        goToMain()
                    } else {
                        textError.text = result.error.ifBlank { getString(R.string.login_error_generic) }
                        textError.visibility = View.VISIBLE
                    }
                }
            }
        }
    }

    private fun goToMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }
}
