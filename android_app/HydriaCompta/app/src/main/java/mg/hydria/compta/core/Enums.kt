package mg.hydria.compta.core

/** Sens d'une ligne d'écriture. */
enum class Sens { DEBIT, CREDIT }

/** Classe du plan comptable (PCG — à confirmer §7 de la doc de fondation). */
enum class ClasseCompte(val chiffre: Int) {
    CAPITAUX(1), IMMOBILISATIONS(2), STOCKS(3), TIERS(4),
    FINANCIERS(5), CHARGES(6), PRODUITS(7), SPECIAUX(8), ANALYTIQUE(9);

    companion object {
        fun fromNumero(numero: String): ClasseCompte? =
            numero.firstOrNull()?.digitToIntOrNull()?.let { d -> entries.firstOrNull { it.chiffre == d } }
    }
}

/** Nature du compte pour la ventilation bilan / compte de résultat. */
enum class TypeCompte { ACTIF, PASSIF, CHARGE, PRODUIT, INDETERMINE }

/** Cycle de vie local d'une pièce comptable saisie hors ligne. */
enum class StatutPieceLocale { BROUILLON, PRETE, SOUMISE, VALIDEE, A_CORRIGER }

/** État de synchronisation d'un agrégat local. */
enum class SyncStatus { DRAFT, PENDING, SYNCED, CONFLICT, REJECTED }

/** État d'une ligne de l'outbox. */
enum class MutationStatus { QUEUED, IN_FLIGHT, ACKED, FAILED, CONFLICT }

/** Types de mutation acceptés par l'API mobile compta (V1). */
enum class MutationType(val wire: String) {
    PIECE_CREATE("piece.create"),
    PIECE_UPDATE("piece.update"),
    PIECE_SUBMIT("piece.submit"),
    TIERS_CREATE("tiers.create"),
    TIERS_UPDATE("tiers.update"),
    FACTURE_CREATE("facture.create"),
    FACTURE_FINALIZE("facture.finalize"),
    CAISSE_MOUVEMENT_CREATE("caisse.mouvement.create"),
    REGLEMENT_CREATE("reglement.create"),
    LETTRAGE_CREATE("lettrage.create");

    companion object {
        fun fromWire(value: String): MutationType? = entries.firstOrNull { it.wire == value }
    }
}

enum class TypeTiers { CLIENT, FOURNISSEUR }

enum class TypeFacture { DEVIS, FACTURE }

enum class StatutFacture { BROUILLON, EMISE, PARTIELLEMENT_PAYEE, PAYEE, EN_RETARD, ANNULEE }

enum class ModeReglement { ESPECES, MOBILE_MONEY, VIREMENT, CHEQUE }

enum class SensCaisse { ENTREE, SORTIE }

enum class ConflictResolution { NON_RESOLU, GARDER_LOCAL, GARDER_SERVEUR, FUSION }
