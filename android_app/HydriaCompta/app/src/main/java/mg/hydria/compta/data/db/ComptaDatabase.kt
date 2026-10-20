package mg.hydria.compta.data.db

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import mg.hydria.compta.data.db.dao.BaremePaieDao
import mg.hydria.compta.data.db.dao.CaisseMouvementDao
import mg.hydria.compta.data.db.dao.ConflictDao
import mg.hydria.compta.data.db.dao.FactureDao
import mg.hydria.compta.data.db.dao.GrandLivreDao
import mg.hydria.compta.data.db.dao.InvoiceRangeDao
import mg.hydria.compta.data.db.dao.OutboxDao
import mg.hydria.compta.data.db.dao.PendingDocumentDao
import mg.hydria.compta.data.db.dao.PieceComptableDao
import mg.hydria.compta.data.db.dao.ReferentielDao
import mg.hydria.compta.data.db.dao.SyncStateDao
import mg.hydria.compta.data.db.dao.TiersDao
import mg.hydria.compta.data.db.entity.BaremeCnapsEntity
import mg.hydria.compta.data.db.entity.BaremeIrsaTrancheEntity
import mg.hydria.compta.data.db.entity.BaremeMutuelleEntity
import mg.hydria.compta.data.db.entity.CaisseEntity
import mg.hydria.compta.data.db.entity.CompteEntity
import mg.hydria.compta.data.db.entity.ConflictEntity
import mg.hydria.compta.data.db.entity.DeviceInvoiceRangeEntity
import mg.hydria.compta.data.db.entity.EmployePaieEntity
import mg.hydria.compta.data.db.entity.ExerciceEntity
import mg.hydria.compta.data.db.entity.FactureEntity
import mg.hydria.compta.data.db.entity.JournalEntity
import mg.hydria.compta.data.db.entity.LettrageLocalEntity
import mg.hydria.compta.data.db.entity.LigneEcritureEntity
import mg.hydria.compta.data.db.entity.LigneFactureEntity
import mg.hydria.compta.data.db.entity.LigneGrandLivreEntity
import mg.hydria.compta.data.db.entity.MouvementCaisseEntity
import mg.hydria.compta.data.db.entity.OutboxMutationEntity
import mg.hydria.compta.data.db.entity.PendingDocumentEntity
import mg.hydria.compta.data.db.entity.PieceComptableEntity
import mg.hydria.compta.data.db.entity.ReglementEntity
import mg.hydria.compta.data.db.entity.SmigEntity
import mg.hydria.compta.data.db.entity.SoldeReelEntity
import mg.hydria.compta.data.db.entity.SyncStateEntity
import mg.hydria.compta.data.db.entity.TiersEntity

@Database(
    version = 1,
    exportSchema = true,
    entities = [
        // Réplique
        ExerciceEntity::class, CompteEntity::class, JournalEntity::class,
        LigneGrandLivreEntity::class, SoldeReelEntity::class, TiersEntity::class,
        CaisseEntity::class, BaremeIrsaTrancheEntity::class, BaremeCnapsEntity::class,
        BaremeMutuelleEntity::class, SmigEntity::class, EmployePaieEntity::class,
        // Agrégats locaux
        PieceComptableEntity::class, LigneEcritureEntity::class,
        FactureEntity::class, LigneFactureEntity::class,
        MouvementCaisseEntity::class, ReglementEntity::class, LettrageLocalEntity::class,
        // Infra sync
        OutboxMutationEntity::class, SyncStateEntity::class, ConflictEntity::class,
        DeviceInvoiceRangeEntity::class, PendingDocumentEntity::class,
    ],
)
@TypeConverters(Converters::class)
abstract class ComptaDatabase : RoomDatabase() {
    abstract fun referentielDao(): ReferentielDao
    abstract fun grandLivreDao(): GrandLivreDao
    abstract fun tiersDao(): TiersDao
    abstract fun baremePaieDao(): BaremePaieDao
    abstract fun pieceComptableDao(): PieceComptableDao
    abstract fun factureDao(): FactureDao
    abstract fun caisseMouvementDao(): CaisseMouvementDao
    abstract fun outboxDao(): OutboxDao
    abstract fun syncStateDao(): SyncStateDao
    abstract fun conflictDao(): ConflictDao
    abstract fun invoiceRangeDao(): InvoiceRangeDao
    abstract fun pendingDocumentDao(): PendingDocumentDao

    companion object {
        const val NAME = "hydria_compta.db"
    }
}
