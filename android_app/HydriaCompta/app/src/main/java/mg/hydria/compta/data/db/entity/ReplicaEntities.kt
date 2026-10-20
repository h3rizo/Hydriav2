package mg.hydria.compta.data.db.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.TypeCompte
import java.time.LocalDate

/**
 * Tables « réplique » : miroir en lecture seule des données serveur, jamais
 * éditées localement. Chaque ligne porte `revision` (curseur delta) et
 * `deletedAt` (tombstone).
 */

@Entity(tableName = "exercice")
data class ExerciceEntity(
    @PrimaryKey val id: String,
    val libelle: String,
    val debut: LocalDate,
    val fin: LocalDate,
    val cloture: Boolean,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(
    tableName = "compte",
    indices = [Index("numero"), Index("classe")],
)
data class CompteEntity(
    @PrimaryKey val id: String,
    val numero: String,
    val nom: String,
    val classe: Int?,
    val type: TypeCompte,
    val fournisseurObligatoire: Boolean = false,
    val employeObligatoire: Boolean = false,
    val necessiteOuvrage: Boolean = false,
    val charteVerification: String? = null,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(
    tableName = "journal",
    indices = [Index("code")],
)
data class JournalEntity(
    @PrimaryKey val id: String,
    val code: String,
    val nom: String,
    val compteContrepartie: String? = null,
    val baseId: String? = null,
    val revision: Long,
    val deletedAt: Long? = null,
)

/**
 * Grand livre importé (= lignes `BaseDiameX` du périmètre). Débit / crédit sont
 * dérivés côté serveur de `montant_in` / `montant_out`. Source des états
 * (grand livre, balance, balance âgée) recalculés sur l'appareil.
 */
@Entity(
    tableName = "ligne_grand_livre",
    indices = [
        Index("compteNumero", "dateMouvement"),
        Index("exerciceId"),
        Index("lettrageCode"),
        Index("tiersRef"),
    ],
)
data class LigneGrandLivreEntity(
    @PrimaryKey val id: String,
    val exerciceId: String?,
    val journalCode: String?,
    val dateMouvement: LocalDate,
    val datePiece: LocalDate?,
    val rec: Int?,
    val description: String,
    val compteNumero: String,
    val debit: Ariary,
    val credit: Ariary,
    val tiersRef: String? = null,
    val activ: String? = null,
    val financement: String? = null,
    val pieceScanUrl: String? = null,
    val lettrageCode: String? = null,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(
    tableName = "solde_reel",
    indices = [Index("exerciceId", "mois")],
)
data class SoldeReelEntity(
    @PrimaryKey val id: String,
    val compteNumero: String?,
    /** 1er du mois. */
    val mois: LocalDate,
    val montant: Ariary,
    val exerciceId: String?,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(
    tableName = "tiers",
    indices = [Index("codeTiers"), Index("type")],
)
data class TiersEntity(
    @PrimaryKey val id: String,
    val type: String, // TypeTiers.name
    val codeTiers: String? = null,
    val nom: String,
    val nif: String? = null,
    val stat: String? = null,
    val cin: String? = null,
    val telephone: String? = null,
    val email: String? = null,
    val adresse: String? = null,
    val actif: Boolean = true,
    val soldeCache: Ariary = Ariary.ZERO,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(tableName = "caisse")
data class CaisseEntity(
    @PrimaryKey val id: String,
    val nom: String,
    val compteNumero: String,
    val soldeOuverture: Ariary,
    val actif: Boolean = true,
    val revision: Long,
    val deletedAt: Long? = null,
)

/* ---- Barèmes paie, historisés par date d'effet (répliqués, calcul 100 % local) ---- */

@Entity(tableName = "bareme_irsa_tranche", indices = [Index("dateEffet", "ordre")])
data class BaremeIrsaTrancheEntity(
    @PrimaryKey val id: String,
    val dateEffet: LocalDate,
    val dateFinEffet: LocalDate? = null,
    val ordre: Int,
    val plafond: Ariary,
    /** Pourcentage, ex. "5" pour 5 %. */
    val taux: String,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(tableName = "bareme_cnaps", indices = [Index("dateEffet")])
data class BaremeCnapsEntity(
    @PrimaryKey val id: String,
    val dateEffet: LocalDate,
    val dateFinEffet: LocalDate? = null,
    val tauxSalarial: String,
    val tauxPatronal: String,
    val plafondAssiette: Ariary,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(tableName = "bareme_mutuelle", indices = [Index("dateEffet")])
data class BaremeMutuelleEntity(
    @PrimaryKey val id: String,
    val dateEffet: LocalDate,
    val dateFinEffet: LocalDate? = null,
    val nom: String,
    val taux: String,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(tableName = "smig", indices = [Index("dateEffet")])
data class SmigEntity(
    @PrimaryKey val id: String,
    val dateEffet: LocalDate,
    val montantMensuel: Ariary,
    val tauxHoraire: Ariary,
    val revision: Long,
    val deletedAt: Long? = null,
)

@Entity(tableName = "employe_paie", indices = [Index("matricule")])
data class EmployePaieEntity(
    @PrimaryKey val id: String,
    val matricule: String,
    val nom: String,
    val baseId: String?,
    val salaireBase: Ariary,
    val situationFamiliale: String? = null,
    val nbEnfants: Int = 0,
    val revision: Long,
    val deletedAt: Long? = null,
)
