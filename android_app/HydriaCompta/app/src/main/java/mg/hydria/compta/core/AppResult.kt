package mg.hydria.compta.core

/** Résultat d'opération sans exception qui traverse les couches. */
sealed interface AppResult<out T> {
    data class Ok<T>(val value: T) : AppResult<T>
    data class Err(val kind: ErrorKind, val message: String, val cause: Throwable? = null) : AppResult<Nothing>

    enum class ErrorKind { NETWORK, AUTH, SERVER, VALIDATION, CONFLICT, LOCAL }
}

inline fun <T, R> AppResult<T>.map(transform: (T) -> R): AppResult<R> = when (this) {
    is AppResult.Ok -> AppResult.Ok(transform(value))
    is AppResult.Err -> this
}

inline fun <T> AppResult<T>.onOk(block: (T) -> Unit): AppResult<T> {
    if (this is AppResult.Ok) block(value)
    return this
}

inline fun <T> AppResult<T>.onErr(block: (AppResult.Err) -> Unit): AppResult<T> {
    if (this is AppResult.Err) block(this)
    return this
}
