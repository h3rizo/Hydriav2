package mg.hydria.bienetre.core.network

data class StoredTokens(val access: String, val refresh: String)

interface TokenStore {
    fun read(): StoredTokens?
    fun write(tokens: StoredTokens)
    fun clear()
}

