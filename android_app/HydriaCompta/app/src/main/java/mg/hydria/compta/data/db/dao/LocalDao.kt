package mg.hydria.compta.data.db.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Update
import kotlinx.coroutines.flow.Flow
import mg.hydria.compta.core.SyncStatus
import mg.hydria.compta.data.db.entity.FactureEntity
import mg.hydria.compta.data.db.entity.LigneEcritureEntity
import mg.hydria.compta.data.db.entity.LigneFactureEntity
import mg.hydria.compta.data.db.entity.MouvementCaisseEntity
import mg.hydria.compta.data.db.entity.PieceComptableEntity
import mg.hydria.compta.data.db.entity.ReglementEntity

@Dao
interface PieceComptableDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertPiece(piece: PieceComptableEntity)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertLignes(lignes: List<LigneEcritureEntity>)
    @Query("DELETE FROM ligne_ecriture WHERE pieceLocalUuid = :pieceLocalUuid")
    suspend fun deleteLignes(pieceLocalUuid: String)

    @Transaction
    suspend fun replacePiece(piece: PieceComptableEntity, lignes: List<LigneEcritureEntity>) {
        upsertPiece(piece)
        deleteLignes(piece.localUuid)
        upsertLignes(lignes)
    }

    @Update suspend fun update(piece: PieceComptableEntity)

    @Query("SELECT * FROM piece_comptable WHERE localUuid = :localUuid")
    suspend fun byLocalUuid(localUuid: String): PieceComptableEntity?

    @Query("SELECT * FROM ligne_ecriture WHERE pieceLocalUuid = :pieceLocalUuid ORDER BY ordre")
    suspend fun lignesDe(pieceLocalUuid: String): List<LigneEcritureEntity>

    @Query("SELECT * FROM piece_comptable ORDER BY updatedAtLocal DESC")
    fun observeToutes(): Flow<List<PieceComptableEntity>>

    @Query("SELECT * FROM piece_comptable WHERE syncStatus IN (:statuts)")
    suspend fun parStatut(statuts: List<SyncStatus>): List<PieceComptableEntity>

    @Query("UPDATE piece_comptable SET serverId = :serverId, syncStatus = 'SYNCED' WHERE localUuid = :localUuid")
    suspend fun marquerSynced(localUuid: String, serverId: String)

    @Query("UPDATE piece_comptable SET syncStatus = :statut, erreursValidation = :erreurs WHERE localUuid = :localUuid")
    suspend fun marquer(localUuid: String, statut: SyncStatus, erreurs: String?)
}

@Dao
interface FactureDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertFacture(facture: FactureEntity)
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertLignes(lignes: List<LigneFactureEntity>)
    @Query("DELETE FROM ligne_facture WHERE factureLocalUuid = :factureLocalUuid")
    suspend fun deleteLignes(factureLocalUuid: String)

    @Transaction
    suspend fun replaceFacture(facture: FactureEntity, lignes: List<LigneFactureEntity>) {
        upsertFacture(facture)
        deleteLignes(facture.localUuid)
        upsertLignes(lignes)
    }

    @Query("SELECT * FROM facture WHERE localUuid = :localUuid")
    suspend fun byLocalUuid(localUuid: String): FactureEntity?

    @Query("SELECT * FROM facture ORDER BY date DESC")
    fun observeToutes(): Flow<List<FactureEntity>>

    @Query("SELECT * FROM facture WHERE statut IN ('EMISE','PARTIELLEMENT_PAYEE','EN_RETARD') ORDER BY dateEcheance")
    fun observeImpayees(): Flow<List<FactureEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsertReglement(reglement: ReglementEntity)

    @Query("SELECT * FROM reglement WHERE factureLocalUuid = :factureLocalUuid ORDER BY date")
    suspend fun reglementsDe(factureLocalUuid: String): List<ReglementEntity>
}

@Dao
interface CaisseMouvementDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun upsert(mouvement: MouvementCaisseEntity)

    @Query("SELECT * FROM mouvement_caisse WHERE caisseId = :caisseId ORDER BY date DESC, updatedAtLocal DESC")
    fun observe(caisseId: String): Flow<List<MouvementCaisseEntity>>

    @Query(
        """
        SELECT COALESCE(SUM(CASE WHEN sens = 'ENTREE' THEN montant ELSE -montant END), 0)
        FROM mouvement_caisse WHERE caisseId = :caisseId
        """
    )
    fun observeSoldeMouvements(caisseId: String): Flow<Long>

    @Query("SELECT * FROM mouvement_caisse WHERE localUuid = :localUuid")
    suspend fun byLocalUuid(localUuid: String): MouvementCaisseEntity?
}
