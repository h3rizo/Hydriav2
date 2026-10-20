package mg.hydria.compta.data.remote

import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.ClasseCompte
import mg.hydria.compta.core.TypeCompte
import mg.hydria.compta.data.db.entity.CompteEntity
import mg.hydria.compta.data.db.entity.ExerciceEntity
import mg.hydria.compta.data.db.entity.JournalEntity
import mg.hydria.compta.data.db.entity.LigneGrandLivreEntity
import mg.hydria.compta.data.db.entity.TiersEntity
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

/**
 * Traduit la charge utile `bootstrap` / `changes` en entités Room.
 *
 * V1 : les entités structurantes. À compléter (soldes_reels, caisses, barèmes,
 * employes_paie) au même modèle — voir doc de fondation §4.
 */
object BootstrapMapper {

    fun exercices(arr: JSONArray?): List<ExerciceEntity> = arr.mapObjects { o ->
        ExerciceEntity(
            id = o.getString("id"),
            libelle = o.getString("libelle"),
            debut = date(o, "debut"),
            fin = date(o, "fin"),
            cloture = o.optBoolean("cloture", false),
            revision = o.optLong("revision", 0),
            deletedAt = o.optLongOrNull("deleted_at"),
        )
    }

    fun comptes(arr: JSONArray?): List<CompteEntity> = arr.mapObjects { o ->
        val numero = o.getString("numero")
        CompteEntity(
            id = o.getString("id"),
            numero = numero,
            nom = o.getString("nom"),
            classe = ClasseCompte.fromNumero(numero)?.chiffre,
            type = typeCompte(o.optString("type")),
            fournisseurObligatoire = o.optBoolean("fournisseur_obligatoire", false),
            employeObligatoire = o.optBoolean("employe_obligatoire", false),
            necessiteOuvrage = o.optBoolean("necessite_ouvrage", false),
            charteVerification = o.optStringOrNull("charte_verification"),
            revision = o.optLong("revision", 0),
            deletedAt = o.optLongOrNull("deleted_at"),
        )
    }

    fun journaux(arr: JSONArray?): List<JournalEntity> = arr.mapObjects { o ->
        JournalEntity(
            id = o.getString("id"),
            code = o.getString("code"),
            nom = o.getString("nom"),
            compteContrepartie = o.optStringOrNull("compte_contrepartie"),
            baseId = o.optStringOrNull("base_id"),
            revision = o.optLong("revision", 0),
            deletedAt = o.optLongOrNull("deleted_at"),
        )
    }

    fun tiers(arr: JSONArray?): List<TiersEntity> = arr.mapObjects { o ->
        TiersEntity(
            id = o.getString("id"),
            type = o.optString("type", "CLIENT").uppercase(),
            codeTiers = o.optStringOrNull("code_tiers"),
            nom = o.getString("nom"),
            nif = o.optStringOrNull("nif"),
            stat = o.optStringOrNull("stat"),
            cin = o.optStringOrNull("cin"),
            telephone = o.optStringOrNull("telephone"),
            email = o.optStringOrNull("email"),
            adresse = o.optStringOrNull("adresse"),
            actif = o.optBoolean("actif", true),
            soldeCache = Ariary.parse(o.optStringOrNull("solde")),
            revision = o.optLong("revision", 0),
            deletedAt = o.optLongOrNull("deleted_at"),
        )
    }

    fun grandLivre(arr: JSONArray?): List<LigneGrandLivreEntity> = arr.mapObjects { o ->
        LigneGrandLivreEntity(
            id = o.getString("id"),
            exerciceId = o.optStringOrNull("exercice_id"),
            journalCode = o.optStringOrNull("journal_code"),
            dateMouvement = date(o, "date_mouvement"),
            datePiece = dateOrNull(o, "date_piece"),
            rec = if (o.has("rec") && !o.isNull("rec")) o.getInt("rec") else null,
            description = o.optString("description", ""),
            compteNumero = o.getString("compte_numero"),
            debit = Ariary.parse(o.optString("debit", "0")),
            credit = Ariary.parse(o.optString("credit", "0")),
            tiersRef = o.optStringOrNull("tiers_ref"),
            activ = o.optStringOrNull("activ"),
            financement = o.optStringOrNull("financement"),
            pieceScanUrl = o.optStringOrNull("piece_scan_url"),
            lettrageCode = o.optStringOrNull("lettrage_code"),
            revision = o.optLong("revision", 0),
            deletedAt = o.optLongOrNull("deleted_at"),
        )
    }

    // ---- helpers ----

    private fun typeCompte(raw: String?): TypeCompte = when (raw?.lowercase()) {
        "actif" -> TypeCompte.ACTIF
        "passif" -> TypeCompte.PASSIF
        "charge" -> TypeCompte.CHARGE
        "produit" -> TypeCompte.PRODUIT
        else -> TypeCompte.INDETERMINE
    }

    private fun date(o: JSONObject, key: String): LocalDate = LocalDate.parse(o.getString(key))
    private fun dateOrNull(o: JSONObject, key: String): LocalDate? =
        o.optStringOrNull(key)?.let { LocalDate.parse(it) }

    private inline fun <T> JSONArray?.mapObjects(block: (JSONObject) -> T): List<T> {
        if (this == null) return emptyList()
        return (0 until length()).map { block(getJSONObject(it)) }
    }

    private fun JSONObject.optStringOrNull(key: String): String? =
        if (has(key) && !isNull(key)) optString(key).takeIf { it.isNotEmpty() } else null

    private fun JSONObject.optLongOrNull(key: String): Long? =
        if (has(key) && !isNull(key)) optLong(key) else null
}
