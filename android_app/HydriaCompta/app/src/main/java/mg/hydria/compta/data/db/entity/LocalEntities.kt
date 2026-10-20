package mg.hydria.compta.data.db.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.ModeReglement
import mg.hydria.compta.core.SensCaisse
import mg.hydria.compta.core.StatutFacture
import mg.hydria.compta.core.StatutPieceLocale
import mg.hydria.compta.core.SyncStatus
import mg.hydria.compta.core.TypeFacture
import java.time.Instant
import java.time.LocalDate

/**
 * Agrégats créés / édités hors ligne. `localUuid` est la clé primaire (générée
 * client) ET la clé d'idempotence côté serveur. `baseRevision` = révision serveur
 * sur laquelle l'édition s'appuie (détection de conflit).
 */

@Entity(
    tableName = "piece_comptable",
    indices = [Index("syncStatus"), Index("exerciceId"), Index("date")],
)
data class PieceComptableEntity(
    @PrimaryKey val localUuid: String,
    val serverId: String? = null,
    val baseId: String?,
    val journalId: String?,
    val exerciceId: String?,
    val date: LocalDate,
    val reference: String? = null,
    val description: String,
    val statutLocal: StatutPieceLocale = StatutPieceLocale.BROUILLON,
    val equilibree: Boolean = false,
    val totalDebit: Ariary = Ariary.ZERO,
    val totalCredit: Ariary = Ariary.ZERO,
    val pieceLocaleUri: String? = null,
    val erreursValidation: String? = null, // JSON renvoyé par le serveur si rejet
    val syncStatus: SyncStatus = SyncStatus.DRAFT,
    val baseRevision: Long = 0,
    val updatedAtLocal: Instant = Instant.EPOCH,
)

@Entity(
    tableName = "ligne_ecriture",
    foreignKeys = [
        ForeignKey(
            entity = PieceComptableEntity::class,
            parentColumns = ["localUuid"],
            childColumns = ["pieceLocalUuid"],
            onDelete = ForeignKey.CASCADE,
        )
    ],
    indices = [Index("pieceLocalUuid"), Index("compteNumero")],
)
data class LigneEcritureEntity(
    @PrimaryKey val localUuid: String,
    val pieceLocalUuid: String,
    val compteNumero: String,
    val libelle: String? = null,
    val debit: Ariary = Ariary.ZERO,
    val credit: Ariary = Ariary.ZERO,
    val tiersId: String? = null,
    val activ: String? = null,
    val financement: String? = null,
    val ordre: Int = 0,
)

@Entity(
    tableName = "facture",
    indices = [Index("syncStatus"), Index("tiersId"), Index("numero", unique = true)],
)
data class FactureEntity(
    @PrimaryKey val localUuid: String,
    val serverId: String? = null,
    val type: TypeFacture,
    /** Numéro définitif alloué depuis la plage de l'appareil, dès la création offline. */
    val numero: String?,
    val numeroProvisoire: String,
    val tiersId: String,
    val date: LocalDate,
    val dateEcheance: LocalDate?,
    val statut: StatutFacture = StatutFacture.BROUILLON,
    val devise: String = "MGA",
    val totalHt: Ariary = Ariary.ZERO,
    val totalTva: Ariary = Ariary.ZERO,
    val totalTtc: Ariary = Ariary.ZERO,
    val remiseGlobalePct: String = "0",
    val notes: String? = null,
    val pdfUri: String? = null,
    val syncStatus: SyncStatus = SyncStatus.DRAFT,
    val baseRevision: Long = 0,
    val updatedAtLocal: Instant = Instant.EPOCH,
)

@Entity(
    tableName = "ligne_facture",
    foreignKeys = [
        ForeignKey(
            entity = FactureEntity::class,
            parentColumns = ["localUuid"],
            childColumns = ["factureLocalUuid"],
            onDelete = ForeignKey.CASCADE,
        )
    ],
    indices = [Index("factureLocalUuid")],
)
data class LigneFactureEntity(
    @PrimaryKey val localUuid: String,
    val factureLocalUuid: String,
    val designation: String,
    val quantite: String,
    val prixUnitaire: Ariary,
    val remisePct: String = "0",
    val tauxTva: String = "0.20",
    val compteProduitNumero: String? = null,
    val montantHt: Ariary = Ariary.ZERO,
    val montantTva: Ariary = Ariary.ZERO,
    val ordre: Int = 0,
)

@Entity(
    tableName = "mouvement_caisse",
    indices = [Index("syncStatus"), Index("caisseId"), Index("date")],
)
data class MouvementCaisseEntity(
    @PrimaryKey val localUuid: String,
    val serverId: String? = null,
    val caisseId: String,
    val date: LocalDate,
    val sens: SensCaisse,
    val montant: Ariary,
    val motif: String,
    val tiersId: String? = null,
    /** Lien optionnel vers une pièce comptable locale. */
    val pieceLocalUuid: String? = null,
    val pieceLocaleUri: String? = null,
    val syncStatus: SyncStatus = SyncStatus.DRAFT,
    val baseRevision: Long = 0,
    val updatedAtLocal: Instant = Instant.EPOCH,
)

@Entity(
    tableName = "reglement",
    indices = [Index("syncStatus"), Index("factureLocalUuid")],
)
data class ReglementEntity(
    @PrimaryKey val localUuid: String,
    val serverId: String? = null,
    val factureLocalUuid: String? = null,
    val mouvementCaisseLocalUuid: String? = null,
    val date: LocalDate,
    val montant: Ariary,
    val mode: ModeReglement,
    val reference: String? = null,
    val syncStatus: SyncStatus = SyncStatus.DRAFT,
    val baseRevision: Long = 0,
    val updatedAtLocal: Instant = Instant.EPOCH,
)

/** Overlay de lettrage local en attente de push. */
@Entity(tableName = "lettrage_local", indices = [Index("code"), Index("ligneGrandLivreId")])
data class LettrageLocalEntity(
    @PrimaryKey val localUuid: String,
    val code: String,
    val ligneGrandLivreId: String? = null,
    val ligneEcritureLocalUuid: String? = null,
    val date: LocalDate,
    val syncStatus: SyncStatus = SyncStatus.DRAFT,
)
