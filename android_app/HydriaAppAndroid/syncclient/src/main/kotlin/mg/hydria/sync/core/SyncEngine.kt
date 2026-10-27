package mg.hydria.sync.core

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.UUID

class Rapport {
    var telecharges = 0
    var envoyes = 0
    var misAJour = 0
    var corbeille = 0
    val conflits = mutableListOf<String>()
    val erreurs = mutableListOf<String>()
    val ignores = mutableListOf<String>()

    val propre: Boolean get() = erreurs.isEmpty() && conflits.isEmpty()

    fun resume(): String = buildString {
        append("Téléchargés : $telecharges | Envoyés : $envoyes | Mis à jour sur le serveur : $misAJour | Mis en corbeille : $corbeille")
        append(" | Conflits : ${conflits.size} | Erreurs : ${erreurs.size}")
    }
}

internal fun sha256Hex(octets: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(octets).joinToString("") { "%02x".format(it) }

internal fun sha256Hex(fichier: Path): String {
    val digest = MessageDigest.getInstance("SHA-256")
    Files.newInputStream(fichier).use { entree ->
        val tampon = ByteArray(1 shl 16)
        while (true) {
            val lu = entree.read(tampon)
            if (lu < 0) break
            digest.update(tampon, 0, lu)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}

/**
 * Synchronisation bidirectionnelle entre le dossier [racine] et le serveur.
 *
 * Regles de securite (v1) :
 *  - un fichier modifie des deux cotes n'est JAMAIS ecrase : la version locale est conservee et celle du
 *    serveur est enregistree a cote (« nom (conflit serveur vN).ext ») ;
 *  - un fichier supprime sur le serveur est deplace dans `.hydria-sync/corbeille`, jamais detruit ;
 *  - une suppression locale n'est pas propagee au serveur (sauf `propagerSuppressions`) ;
 *  - tout telechargement est verifie par SHA-256 avant d'etre place.
 */
class SyncEngine(
    private val api: SyncApi,
    private val racine: Path,
    private val config: Config,
    /** Avancement publie a chaque fichier (barre de progression de la fenetre). */
    private val progression: (Progression) -> Unit = {},
    private val journal: (String) -> Unit = {},
) {
    private lateinit var etat: Etat
    private lateinit var arbre: Arbre
    private lateinit var rapport: Rapport
    private val raisons = mutableMapOf<String, String>()
    private val conflitsSignales = mutableSetOf<String>()

    // avancement de la reception (total connu des le debut)
    private var aRecevoir = 0
    private var recus = 0
    private var octetsARecevoir = 0L
    private var octetsRecus = 0L
    private var debutReception = 0L

    companion object {
        /** Les `seq` sont attribues avant le commit cote serveur : on relit les derniers pour ne rien rater. */
        const val RECOUVREMENT = 100L
        private const val TAILLE_PAGE = 500
        private val STAMP = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
    }

    suspend fun synchroniser(): Rapport {
        rapport = Rapport()
        raisons.clear()
        conflitsSignales.clear()
        aRecevoir = 0; recus = 0; octetsARecevoir = 0; octetsRecus = 0; debutReception = System.currentTimeMillis()
        signaler(Phase.PREPARATION, null)
        Files.createDirectories(racine)
        etat = Etat.charger(racine)
        arbre = Arbre(etat)
        arbre.charger(api.arborescence(config.organisation))
        creerDossiers()
        try {
            val pages = lirePages()
            annoncer(pages)
            reprendre()
            tirer(pages)
            pousser()
        } finally {
            etat.enregistrer(racine)
        }
        for (fichier in etat.enAttente.values) {
            rapport.erreurs += "${fichier.nom} : ${raisons[fichier.id] ?: "téléchargement non terminé"} (sera repris à la prochaine synchronisation)"
        }
        journal(rapport.resume())
        return rapport
    }

    // ================================================================== dossiers

    private fun absolu(rel: String): Path = racine.resolve(rel)

    private fun creerDossier(segments: List<String>) {
        Files.createDirectories(segments.fold(racine) { chemin, segment -> chemin.resolve(segment) })
    }

    /** Dossiers prets a recevoir des fichiers : un par domaine lisible et par ouvrage visible (avec ses categories). */
    private fun creerDossiers() {
        for (domaine in arbre.domaines.filter { it.lecture }) {
            for (categorie in domaine.categories) {
                creerDossier(listOf("Organisation", arbre.libelleDomaine(domaine.code),
                    arbre.libelleCategorieOrganisation(domaine.code, categorie.code)))
            }
        }
        val categoriesOuvrage = arbre.categoriesEntite.filter { it.typesEntite.isEmpty() || "ouvrage" in it.typesEntite }
        for (ouvrage in arbre.ouvrages()) {
            val segments = arbre.segments(ouvrage)
            creerDossier(segments)
            for (categorie in categoriesOuvrage) creerDossier(segments + arbre.libelleCategorieEntite(categorie.code))
        }
    }

    // ================================================================== serveur -> PC

    private suspend fun reprendre() {
        for ((id, fichier) in etat.enAttente.entries.toList()) {
            try {
                recevoir(fichier)
                etat.enAttente.remove(id)
            } catch (e: ErreurReseau) {
                throw e
            } catch (e: ErreurAuthentification) {
                throw e
            } catch (e: Exception) {
                // la relecture du journal (recouvrement) peut corriger une fiche perimee : on ne signale qu'a la fin
                raisons[id] = e.message ?: e::class.simpleName.orEmpty()
            }
        }
    }

    private fun signaler(phase: Phase, courant: String?) {
        progression(
            Progression(
                phase = phase, fait = recus, total = aRecevoir, octetsFaits = octetsRecus, octetsTotal = octetsARecevoir,
                courant = courant, debutMs = debutReception, maintenantMs = System.currentTimeMillis(),
                envoyes = rapport.envoyes,
            ),
        )
    }

    /** Lit toute la liste des changements (du JSON leger) avant de traiter : c'est ce qui donne le total de la progression. */
    private suspend fun lirePages(): List<ChangesPage> {
        val pages = mutableListOf<ChangesPage>()
        var depuis = maxOf(0L, etat.curseur - RECOUVREMENT)
        while (true) {
            val page = api.changements(depuis, TAILLE_PAGE, config.organisation, config.deviceLabel)
            pages += page
            if (!page.hasMore) break
            depuis = page.nextSeq
        }
        return pages
    }

    /** Nombre et poids des fichiers a telecharger : a reprendre + nouveaux ou modifies sur le serveur. */
    private fun annoncer(pages: List<ChangesPage>) {
        val aTelecharger = linkedMapOf<String, FichierDto>()
        for (f in etat.enAttente.values) aTelecharger[f.id] = f
        for (page in pages) for (c in page.changes) {
            val f = c.fichier ?: continue
            if (c.action == "delete" || f.deletedAt != null || f.statut != "complet") continue
            val suivi = etat.fichiers[f.id]
            if (suivi != null && suivi.version >= f.version) continue
            aTelecharger[f.id] = f
        }
        aRecevoir = aTelecharger.size
        octetsARecevoir = aTelecharger.values.sumOf { it.taille }
        debutReception = System.currentTimeMillis()
        signaler(Phase.RECEPTION, null)
    }

    private suspend fun tirer(pages: List<ChangesPage>) {
        for (page in pages) {
            for (changement in page.changes) {
                try {
                    traiter(changement)
                } catch (e: ErreurReseau) {
                    throw e
                } catch (e: ErreurAuthentification) {
                    throw e
                } catch (e: Exception) {
                    val fichier = changement.fichier
                    if (fichier != null) {
                        etat.enAttente[fichier.id] = fichier
                        raisons[fichier.id] = e.message ?: e::class.simpleName.orEmpty()
                    } else {
                        rapport.erreurs += "${changement.entityType} : ${e.message}"
                    }
                }
            }
            etat.curseur = maxOf(etat.curseur, page.nextSeq)
            etat.enregistrer(racine)
        }
    }

    private suspend fun traiter(c: ChangeDto) {
        c.chemin?.let { arbre.assurerChemin(it) }
        val fichier = c.fichier
        if (fichier == null) {
            if (c.entityType == "ouvrage" && c.action != "delete") {
                c.entityId?.let { arbre.element(it) }?.let { creerDossier(arbre.segments(it)) }
            }
            return
        }
        if (c.action == "delete" || fichier.deletedAt != null) {
            mettreEnCorbeille(fichier.id)
            return
        }
        if (fichier.statut == "complet") recevoir(fichier)
    }

    /** Dossier local de destination d'un fichier du serveur. */
    private fun dossierDe(f: FichierDto): List<String> =
        if (f.portee == "organisation") {
            val domaine = f.domaine ?: "operationnel"
            listOf("Organisation", arbre.libelleDomaine(domaine), arbre.libelleCategorieOrganisation(domaine, f.categorie))
        } else {
            val element = f.entityId?.let { arbre.element(it) }
            val base = element?.let { arbre.segments(it) }
                ?: listOf("Territoire", "Emplacement inconnu", "${f.entityType}_${f.entityId?.take(8)}")
            base + arbre.libelleCategorieEntite(f.categorie)
        }

    private fun nomFichier(nom: String): String {
        val extension = nom.substringAfterLast('.', "").takeIf { it.isNotEmpty() && it.length <= 10 }
        val base = if (extension != null) nom.dropLast(extension.length + 1) else nom
        val propre = Noms.assainir(base).take(Noms.LONGUEUR_MAX + 20)
        return if (extension != null) "$propre.${Noms.assainir(extension)}" else propre
    }

    /** Chemin relatif libre pour ce fichier : suffixe « (id) » si un autre fichier occupe deja le nom. */
    private fun cheminPour(f: FichierDto, courant: String?): String {
        val dossier = dossierDe(f).joinToString("/")
        val nom = nomFichier(f.nom)
        fun libre(candidat: String): Boolean {
            if (candidat.equals(courant, ignoreCase = true)) return true
            if (etat.fichiers.values.any { it.id != f.id && it.relPath.equals(candidat, ignoreCase = true) }) return false
            return !Files.exists(absolu(candidat))
        }
        val direct = "$dossier/$nom"
        if (libre(direct)) return direct
        val point = nom.lastIndexOf('.')
        val avecId = if (point > 0) "${nom.substring(0, point)} (${f.id.take(8)})${nom.substring(point)}" else "$nom (${f.id.take(8)})"
        return "$dossier/$avecId"
    }

    private fun modifieLocalement(s: FichierSuivi): Boolean {
        val p = absolu(s.relPath)
        if (!Files.isRegularFile(p)) return false
        if (Files.size(p) == s.taille && Files.getLastModifiedTime(p).toMillis() == s.mtime) return false
        return sha256Hex(p) != s.sha256
    }

    private suspend fun recevoir(f: FichierDto) {
        val suivi = etat.fichiers[f.id]
        if (suivi != null && suivi.version >= f.version) return // deja a jour (ou relecture du recouvrement)

        if (suivi != null && suivi.conflit) {
            etat.fichiers[f.id] = suivi.copy(conflitVersionServeur = f.version, conflitShaServeur = f.sha256)
            return
        }
        if (suivi != null && f.sha256 == suivi.sha256 && Files.isRegularFile(absolu(suivi.relPath))) {
            renommerSiBesoin(suivi, f) // le serveur n'a change que le nom
            return
        }
        if (suivi != null && modifieLocalement(suivi)) {
            declarerConflit(suivi, f)
            return
        }

        signaler(Phase.RECEPTION, f.nom)
        val octets = api.telecharger(f)
        val sha = sha256Hex(octets)
        check(sha == f.sha256) { "intégrité : SHA-256 reçu différent de celui annoncé" }
        val rel = cheminPour(f, suivi?.relPath)
        placer(rel, octets)
        if (suivi != null && !suivi.relPath.equals(rel, ignoreCase = true)) Files.deleteIfExists(absolu(suivi.relPath))
        etat.fichiers[f.id] = FichierSuivi(f.id, rel, f.version, sha, octets.size.toLong(), mtime(rel))
        etat.enAttente.remove(f.id)
        rapport.telecharges++
        recus++
        octetsRecus += octets.size
        journal("↓ $rel")
        signaler(Phase.RECEPTION, rel.substringAfterLast('/'))
    }

    private fun renommerSiBesoin(suivi: FichierSuivi, f: FichierDto) {
        val rel = cheminPour(f, suivi.relPath)
        if (!rel.equals(suivi.relPath, ignoreCase = true)) {
            Files.createDirectories(absolu(rel).parent)
            Files.move(absolu(suivi.relPath), absolu(rel), StandardCopyOption.REPLACE_EXISTING)
            journal("↻ ${suivi.relPath} → $rel")
        }
        etat.fichiers[f.id] = suivi.copy(relPath = rel, version = f.version, mtime = mtime(rel))
    }

    private fun placer(rel: String, octets: ByteArray) {
        val cible = absolu(rel)
        Files.createDirectories(cible.parent)
        val temporaires = racine.resolve(Etat.DOSSIER).resolve("tmp")
        Files.createDirectories(temporaires)
        val temporaire = temporaires.resolve(UUID.randomUUID().toString())
        Files.write(temporaire, octets)
        Files.move(temporaire, cible, StandardCopyOption.REPLACE_EXISTING)
    }

    private fun mtime(rel: String): Long = Files.getLastModifiedTime(absolu(rel)).toMillis()

    private suspend fun declarerConflit(suivi: FichierSuivi, serveur: FichierDto) {
        val octets = api.telecharger(serveur)
        check(sha256Hex(octets) == serveur.sha256) { "intégrité : copie de conflit corrompue" }
        val copie = cheminCopieConflit(suivi.relPath, serveur.version)
        placer(copie, octets)
        etat.fichiers[suivi.id] = suivi.copy(
            conflit = true, conflitVersionServeur = serveur.version, conflitShaServeur = serveur.sha256, conflitCopie = copie,
        )
        signalerConflit(suivi.id, "${suivi.relPath} : modifié ici ET sur le serveur. Version du serveur enregistrée dans « $copie ».")
        journal("⚠ conflit : ${suivi.relPath}")
    }

    private fun cheminCopieConflit(rel: String, version: Int): String {
        val point = rel.lastIndexOf('.')
        val sepDossier = rel.lastIndexOf('/')
        val base = if (point > sepDossier) rel.substring(0, point) else rel
        val extension = if (point > sepDossier) rel.substring(point) else ""
        return "$base (conflit serveur v$version)$extension"
    }

    private fun mettreEnCorbeille(id: String) {
        val suivi = etat.fichiers[id] ?: run { etat.enAttente.remove(id); return }
        val p = absolu(suivi.relPath)
        if (Files.isRegularFile(p)) {
            if (modifieLocalement(suivi)) {
                rapport.ignores += "${suivi.relPath} : supprimé sur le serveur mais modifié ici, conservé (il sera renvoyé comme nouveau fichier)."
            } else {
                val destination = racine.resolve(Etat.DOSSIER).resolve("corbeille")
                    .resolve(LocalDateTime.now().format(STAMP)).resolve(suivi.relPath)
                Files.createDirectories(destination.parent)
                Files.move(p, destination, StandardCopyOption.REPLACE_EXISTING)
                rapport.corbeille++
                journal("🗑 ${suivi.relPath}")
            }
        }
        etat.fichiers.remove(id)
    }

    // ================================================================== PC -> serveur

    private val noms_ignores = setOf("desktop.ini", "thumbs.db", ".ds_store")

    private fun ignore(p: Path): Boolean {
        val nom = p.fileName.toString()
        val minuscule = nom.lowercase()
        return nom.startsWith("~$") || nom.startsWith(".~lock") || minuscule.endsWith(".tmp") ||
            minuscule.endsWith(".hydria-tmp") || minuscule in noms_ignores
    }

    private suspend fun pousser() {
        // 1) fichiers suivis qui ont disparu du disque
        for (suivi in etat.fichiers.values.toList()) {
            if (suivi.conflit || suivi.supprimeLocalement) continue
            if (Files.exists(absolu(suivi.relPath))) continue
            if (config.propagerSuppressions) {
                when (val r = api.supprimer(suivi.id, suivi.version)) {
                    is Resultat.Ok -> { etat.fichiers.remove(suivi.id); journal("✖ supprimé sur le serveur : ${suivi.relPath}") }
                    is Resultat.Conflit -> signalerConflit(suivi.id, "${suivi.relPath} : suppression refusée, le serveur a une version plus récente.")
                    is Resultat.Refus -> rapport.erreurs += "${suivi.relPath} : suppression refusée (${r.message})"
                }
            } else {
                etat.fichiers[suivi.id] = suivi.copy(supprimeLocalement = true)
                rapport.ignores += "${suivi.relPath} : supprimé ici, conservé sur le serveur (suppressions non propagées)."
            }
        }

        // 2) parcours du disque
        val suivisParChemin = etat.fichiers.values.associateBy { it.relPath.lowercase() }
        val copiesConflit = etat.fichiers.values.mapNotNull { it.conflitCopie?.lowercase() }.toSet()
        val fichiers = Files.walk(racine).use { flux ->
            flux.filter { Files.isRegularFile(it) }
                .filter { !racine.relativize(it).startsWith(Etat.DOSSIER) }
                .filter { !ignore(it) }
                .toList()
        }.sortedBy { it.toString() }

        for (p in fichiers) {
            val rel = racine.relativize(p).toString().replace('\\', '/')
            if (rel.lowercase() in copiesConflit) continue
            try {
                val suivi = suivisParChemin[rel.lowercase()]
                if (suivi != null) examiner(suivi, p) else deposer(rel, p)
            } catch (e: ErreurReseau) {
                throw e
            } catch (e: ErreurAuthentification) {
                throw e
            } catch (e: Exception) {
                rapport.erreurs += "$rel : ${e.message}"
            }
        }
    }

    private suspend fun deposer(rel: String, p: Path) {
        val segments = rel.split('/')
        val cible = arbre.resoudre(segments.dropLast(1)) ?: run {
            rapport.ignores += "$rel : emplacement non reconnu, non synchronisé (mettez-le dans le dossier d'une catégorie)."
            return
        }
        val sha = sha256Hex(p)
        if (etat.refuses[rel] == sha) return
        val nom = p.fileName.toString()
        when (val r = api.deposer(nom, Files.readAllBytes(p), cible, config.organisation)) {
            is Resultat.Ok -> {
                val f = r.fichier
                etat.fichiers[f.id] = FichierSuivi(f.id, rel, f.version, f.sha256, f.taille, mtime(rel))
                etat.refuses.remove(rel)
                rapport.envoyes++
                journal("↑ $rel")
                signaler(Phase.ENVOI, rel.substringAfterLast('/'))
            }
            is Resultat.Refus -> {
                etat.refuses[rel] = sha
                rapport.erreurs += "$rel : refusé par le serveur (${r.code ?: r.statut}) ${r.message}"
            }
            is Resultat.Conflit -> rapport.erreurs += "$rel : conflit inattendu au dépôt."
        }
    }

    private suspend fun examiner(suivi: FichierSuivi, p: Path) {
        if (suivi.conflit) {
            resoudreConflit(suivi, p)
            return
        }
        if (Files.size(p) == suivi.taille && Files.getLastModifiedTime(p).toMillis() == suivi.mtime) return
        val sha = sha256Hex(p)
        if (sha == suivi.sha256) {
            etat.fichiers[suivi.id] = suivi.copy(mtime = Files.getLastModifiedTime(p).toMillis())
            return
        }
        if (etat.refuses[suivi.relPath] == sha) return
        envoyerVersion(suivi, p, sha, suivi.version)
    }

    private suspend fun envoyerVersion(suivi: FichierSuivi, p: Path, sha: String, versionAttendue: Int) {
        val nomLocal = p.fileName.toString()
        when (val r = api.remplacer(suivi.id, versionAttendue, null, Files.readAllBytes(p), nomLocal)) {
            is Resultat.Ok -> {
                val f = r.fichier
                etat.fichiers[suivi.id] = suivi.copy(
                    version = f.version, sha256 = f.sha256, taille = f.taille, mtime = mtime(suivi.relPath),
                    conflit = false, conflitVersionServeur = null, conflitShaServeur = null, conflitCopie = null,
                )
                etat.refuses.remove(suivi.relPath)
                rapport.misAJour++
                journal("↑ (nouvelle version) ${suivi.relPath}")
                signaler(Phase.ENVOI, suivi.relPath.substringAfterLast('/'))
            }
            is Resultat.Conflit -> r.fichierServeur?.let { declarerConflit(suivi, it) }
                ?: signalerConflit(suivi.id, "${suivi.relPath} : le serveur a une version plus récente.")
            is Resultat.Refus -> {
                etat.refuses[suivi.relPath] = sha
                rapport.erreurs += "${suivi.relPath} : refusé par le serveur (${r.code ?: r.statut}) ${r.message}"
            }
        }
    }

    /**
     * Conflit en cours. Deux issues choisies par l'utilisateur :
     *  - il met la version du serveur a la place de la sienne (contenu identique a celui du serveur) : on s'aligne ;
     *  - il supprime la copie « (conflit serveur …) » : il garde sa version, qu'on envoie par-dessus celle du serveur.
     */
    private suspend fun resoudreConflit(suivi: FichierSuivi, p: Path) {
        val shaLocal = sha256Hex(p)
        val copie = suivi.conflitCopie?.let { absolu(it) }
        when {
            suivi.conflitShaServeur != null && shaLocal == suivi.conflitShaServeur -> {
                etat.fichiers[suivi.id] = suivi.copy(
                    version = suivi.conflitVersionServeur ?: suivi.version, sha256 = shaLocal,
                    taille = Files.size(p), mtime = Files.getLastModifiedTime(p).toMillis(),
                    conflit = false, conflitVersionServeur = null, conflitShaServeur = null, conflitCopie = null,
                )
                copie?.let { Files.deleteIfExists(it) }
                journal("✔ conflit résolu (version du serveur adoptée) : ${suivi.relPath}")
            }
            copie != null && !Files.exists(copie) -> {
                journal("✔ conflit résolu (version locale conservée) : ${suivi.relPath}")
                envoyerVersion(suivi, p, shaLocal, suivi.conflitVersionServeur ?: suivi.version)
            }
            else -> signalerConflit(suivi.id, "${suivi.relPath} : conflit non résolu. Supprimez « ${suivi.conflitCopie} » pour garder votre version, ou remplacez votre fichier par cette copie pour adopter celle du serveur.")
        }
    }

    /** Un conflit n'est annonce qu'une fois par synchronisation, quel que soit l'endroit ou on le decouvre. */
    private fun signalerConflit(id: String, message: String) {
        if (conflitsSignales.add(id)) rapport.conflits += message
    }
}
