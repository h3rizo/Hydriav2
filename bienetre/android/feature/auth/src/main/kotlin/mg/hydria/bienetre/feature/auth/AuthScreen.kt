package mg.hydria.bienetre.feature.auth

import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import mg.hydria.bienetre.core.designsystem.BienetreBrandLogo

private enum class AuthMode { Login, Register }

@Composable
fun AuthRoute(viewModel: AuthViewModel = hiltViewModel()) {
    val formState by viewModel.formState.collectAsStateWithLifecycle()
    AuthScreen(
        formState = formState,
        onLogin = viewModel::login,
        onRegister = viewModel::register,
        onMessageShown = viewModel::clearMessage,
    )
}

@Composable
fun AuthScreen(
    formState: AuthFormState,
    onLogin: (String, String) -> Unit,
    onRegister: (String, String, String, String) -> Unit,
    onMessageShown: () -> Unit,
) {
    var mode by remember { mutableStateOf(AuthMode.Login) }
    var username by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(formState.message) {
        formState.message?.let {
            snackbar.showSnackbar(it)
            onMessageShown()
        }
    }

    Scaffold(snackbarHost = { SnackbarHost(snackbar) }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 28.dp, vertical = 40.dp),
            verticalArrangement = Arrangement.Center,
        ) {
            BienetreBrandLogo(Modifier.size(112.dp))
            Spacer(Modifier.height(18.dp))
            Text("Bien-être", style = MaterialTheme.typography.displaySmall)
            Text(
                "Votre santé, vos habitudes, un pas après l’autre.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(32.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilterChip(
                    selected = mode == AuthMode.Login,
                    onClick = { mode = AuthMode.Login },
                    label = { Text("Connexion") },
                )
                FilterChip(
                    selected = mode == AuthMode.Register,
                    onClick = { mode = AuthMode.Register },
                    label = { Text("Créer un compte") },
                )
            }
            Spacer(Modifier.height(20.dp))
            AnimatedContent(targetState = mode, label = "auth-mode") { selectedMode ->
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    OutlinedTextField(
                        value = username,
                        onValueChange = { username = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Identifiant") },
                        singleLine = true,
                        enabled = !formState.isSubmitting,
                    )
                    if (selectedMode == AuthMode.Register) {
                        OutlinedTextField(
                            value = email,
                            onValueChange = { email = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Adresse e-mail") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                            singleLine = true,
                            enabled = !formState.isSubmitting,
                        )
                    }
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Mot de passe") },
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        singleLine = true,
                        enabled = !formState.isSubmitting,
                    )
                    if (selectedMode == AuthMode.Register) {
                        OutlinedTextField(
                            value = confirmation,
                            onValueChange = { confirmation = it },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Confirmer le mot de passe") },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                            singleLine = true,
                            enabled = !formState.isSubmitting,
                        )
                    }
                    Button(
                        onClick = {
                            if (selectedMode == AuthMode.Login) onLogin(username, password)
                            else onRegister(username, email, password, confirmation)
                        },
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                        enabled = !formState.isSubmitting,
                    ) {
                        if (formState.isSubmitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.height(22.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                        } else {
                            Text(if (selectedMode == AuthMode.Login) "Se connecter" else "Créer mon compte")
                        }
                    }
                }
            }
        }
    }
}
