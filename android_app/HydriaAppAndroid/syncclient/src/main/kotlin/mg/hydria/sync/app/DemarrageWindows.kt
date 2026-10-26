package mg.hydria.sync.app

/**
 * Demarrage de l'application a l'ouverture de la session Windows, par la cle de registre standard
 * `HKCU\...\Run` : propre a l'utilisateur, sans droits administrateur, desactivable a tout moment
 * (aussi depuis Windows : Parametres > Applications > Demarrage). Aucun reglage de securite n'est modifie.
 *
 * Ne fonctionne qu'avec l'application installee (`HydriaSync.exe`) : lancee par `gradlew run`, le processus est
 * `java.exe` et ce reglage est indisponible plutot que de pointer vers le mauvais programme.
 */
object DemarrageWindows {
    const val CLE_RUN = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    const val NOM = "HydriaSync"
    const val ARGUMENT_REDUIT = "--minimise"

    /** Commande enregistree : le chemin entre guillemets (il contient souvent des espaces) puis l'option de demarrage reduit. */
    fun commande(exe: String) = "\"$exe\" $ARGUMENT_REDUIT"

    /** Chemin de `HydriaSync.exe` si on tourne depuis l'application installee, sinon `null`. */
    fun cheminExecutable(): String? =
        ProcessHandle.current().info().command().orElse(null)?.takeIf { it.endsWith("HydriaSync.exe", ignoreCase = true) }

    private fun reg(vararg arguments: String): Pair<Int, String> {
        val processus = ProcessBuilder(listOf("reg") + arguments).redirectErrorStream(true).start()
        val sortie = processus.inputStream.bufferedReader().readText()
        return processus.waitFor() to sortie
    }

    fun valeur(cle: String = CLE_RUN, nom: String = NOM): String? {
        val (code, sortie) = reg("query", cle, "/v", nom)
        if (code != 0) return null
        return Regex("""${Regex.escape(nom)}\s+REG_SZ\s+(.*)""").find(sortie)?.groupValues?.get(1)?.trim()
    }

    fun estActif(cle: String = CLE_RUN, nom: String = NOM): Boolean = valeur(cle, nom) != null

    /** Contenu d'un fichier `.reg` qui ecrit la valeur ; `\` et `"` y sont echappes (`\\`, `\"`). */
    internal fun contenuReg(exe: String, cle: String, nom: String): String {
        fun echapper(s: String) = s.replace("\\", "\\\\").replace("\"", "\\\"")
        val cleLongue = if (cle.startsWith("HKCU\\", ignoreCase = true)) "HKEY_CURRENT_USER\\" + cle.substring(5) else cle
        return "Windows Registry Editor Version 5.00\r\n\r\n[$cleLongue]\r\n\"${echapper(nom)}\"=\"${echapper(commande(exe))}\"\r\n"
    }

    /**
     * Ecrit (ou met a jour si l'application a ete deplacee) l'entree de demarrage.
     * Via `reg import` : `reg add /d` ne sait pas recevoir une valeur contenant des guillemets depuis Java
     * (la valeur doit contenir les guillemets autour du chemin, qui comporte des espaces).
     */
    fun activer(exe: String, cle: String = CLE_RUN, nom: String = NOM): Boolean {
        val fichier = java.nio.file.Files.createTempFile("hydria-sync-run-", ".reg")
        return try {
            // UTF-16 avec BOM : le format que reg.exe lit sans ambiguite, y compris pour un chemin accentue.
            java.nio.file.Files.write(fichier, byteArrayOf(0xFF.toByte(), 0xFE.toByte()) + contenuReg(exe, cle, nom).toByteArray(Charsets.UTF_16LE))
            reg("import", fichier.toString()).first == 0
        } finally {
            runCatching { java.nio.file.Files.deleteIfExists(fichier) }
        }
    }

    fun desactiver(cle: String = CLE_RUN, nom: String = NOM): Boolean {
        if (!estActif(cle, nom)) return true
        return reg("delete", cle, "/v", nom, "/f").first == 0
    }
}
