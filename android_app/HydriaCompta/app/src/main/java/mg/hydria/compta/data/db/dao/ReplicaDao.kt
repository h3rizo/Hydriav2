package mg.hydria.compta.data.db.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow
import mg.hydria.compta.core.Ariary
import mg.hydria.compta.data.db.entity.BaremeCnapsEntity
import mg.hydria.compta.data.db.entity.BaremeIrsaTrancheEntity
import mg.hydria.compta.data.db.entity.BaremeMutuelleEntity
import mg.hydria.compta.data.db.entity.CaisseEntity
import mg.hydria.compta.data.db.entity.CompteEntity
import mg.hydria.compta.data.db.entity.EmployePaieEntity
import mg.hydria.compta.data.db.entity.ExerciceEntity
import mg.hydria.compta.data.db.entity.JournalEntity
import mg.hydria.compta.data.db.entity.LigneGrandLivreEntity
import mg.hydria.compta.data.db.entity.SmigEntity
import mg.hydria.compta.data.db.entity.SoldeReelEntity
import mg.hydria.compta.data.db.entity.TiersEntity
import java.time.LocalDate

@Dao
interface ReferentielDao {

    @Upsert suspend fun upsertExercices(rows: List<ExerciceEntity>)
    @Upsert suspend fun upsertComptes(rows: List<CompteEntity>)
    @Upsert suspend fun upsertJournaux(rows: List<JournalEntity>)
    @Upsert suspend fun upsertCaisses(rows: List<CaisseEntity>)
    @Upsert suspend fun upsertSoldesReels(rows: List<SoldeReelEntity>)

    @Query("DELETE FROM compte WHERE id IN (:ids)") suspend fun deleteComptes(ids: List<String>)
    @Query("DELETE FROM journal WHERE id IN (:ids)") suspend fun deleteJournaux(ids: List<String>)

    @Query("SELECT * FROM exercice WHERE deletedAt IS NULL ORDER BY debut DESC")
    fun observeExercices(): Flow<List<ExerciceEntity>>

    @Query("SELECT * FROM compte WHERE deletedAt IS NULL ORDER BY numero")
    fun observeComptes(): Flow<List<CompteEntity>>

    @Query(
        """
        SELECT * FROM compte WHERE deletedAt IS NULL
          AND (:filtre = '' OR numero LIKE '%' || :filtre || '%' OR nom LIKE '%' || :filtre || '%')
        ORDER BY numero
        """
    )
    fun observeComptesFiltres(filtre: String): Flow<List<CompteEntity>>

    @Query("SELECT * FROM compte WHERE numero = :numero AND deletedAt IS NULL LIMIT 1")
    suspend fun compteParNumero(numero: String): CompteEntity?

    @Query("SELECT * FROM journal WHERE deletedAt IS NULL ORDER BY code")
    fun observeJournaux(): Flow<List<JournalEntity>>

    @Query("SELECT * FROM caisse WHERE actif = 1 AND deletedAt IS NULL ORDER BY nom")
    fun observeCaisses(): Flow<List<CaisseEntity>>

    @Query("SELECT MAX(revision) FROM exercice")
    suspend fun maxRevisionExercice(): Long?

    @Query("SELECT COUNT(*) FROM ligne_grand_livre")
    suspend fun countGrandLivre(): Int

    @Query("SELECT COUNT(*) FROM compte WHERE deletedAt IS NULL")
    fun observeCountComptes(): Flow<Int>

    @Query("SELECT COUNT(*) FROM journal WHERE deletedAt IS NULL")
    fun observeCountJournaux(): Flow<Int>

    @Query("SELECT COUNT(*) FROM exercice")
    fun observeCountExercices(): Flow<Int>

    @Query("SELECT COUNT(*) FROM ligne_grand_livre WHERE deletedAt IS NULL")
    fun observeCountGrandLivre(): Flow<Int>
}

@Dao
interface GrandLivreDao {

    @Upsert suspend fun upsert(rows: List<LigneGrandLivreEntity>)

    @Query("DELETE FROM ligne_grand_livre WHERE id IN (:ids)")
    suspend fun delete(ids: List<String>)

    @Query(
        """
        SELECT * FROM ligne_grand_livre
        WHERE compteNumero = :compteNumero
          AND (:exerciceId IS NULL OR exerciceId = :exerciceId)
          AND deletedAt IS NULL
        ORDER BY dateMouvement, rec
        """
    )
    fun observeCompte(compteNumero: String, exerciceId: String?): Flow<List<LigneGrandLivreEntity>>

    @Query(
        """
        SELECT * FROM ligne_grand_livre
        WHERE deletedAt IS NULL
          AND (:exerciceId IS NULL OR exerciceId = :exerciceId)
          AND (:filtre = '' OR compteNumero LIKE '%' || :filtre || '%' OR description LIKE '%' || :filtre || '%')
        ORDER BY dateMouvement DESC, rec DESC
        LIMIT :limit
        """
    )
    fun observeRecentes(exerciceId: String?, filtre: String, limit: Int): Flow<List<LigneGrandLivreEntity>>

    data class SoldeCompte(
        val compteNumero: String,
        val totalDebitCentimes: Long,
        val totalCreditCentimes: Long,
    ) {
        val totalDebit: Ariary get() = Ariary(totalDebitCentimes)
        val totalCredit: Ariary get() = Ariary(totalCreditCentimes)
    }

    /** Balance générale : agrégat par compte pour un exercice. */
    @Query(
        """
        SELECT compteNumero AS compteNumero,
               IFNULL(SUM(debit), 0) AS totalDebitCentimes,
               IFNULL(SUM(credit), 0) AS totalCreditCentimes
        FROM ligne_grand_livre
        WHERE exerciceId = :exerciceId AND deletedAt IS NULL
        GROUP BY compteNumero
        ORDER BY compteNumero
        """
    )
    fun observeBalance(exerciceId: String): Flow<List<SoldeCompte>>

    @Query(
        """
        SELECT * FROM ligne_grand_livre
        WHERE deletedAt IS NULL
          AND (lettrageCode IS NULL OR lettrageCode = '')
          AND tiersRef = :tiersRef
        ORDER BY dateMouvement
        """
    )
    suspend fun lignesNonLettrees(tiersRef: String): List<LigneGrandLivreEntity>

    @Query("SELECT MAX(revision) FROM ligne_grand_livre")
    suspend fun maxRevision(): Long?
}

@Dao
interface TiersDao {

    @Upsert suspend fun upsert(rows: List<TiersEntity>)

    @Query("DELETE FROM tiers WHERE id IN (:ids)")
    suspend fun delete(ids: List<String>)

    @Query("SELECT * FROM tiers WHERE deletedAt IS NULL AND (:type IS NULL OR type = :type) ORDER BY nom")
    fun observe(type: String?): Flow<List<TiersEntity>>

    @Query(
        """
        SELECT * FROM tiers WHERE deletedAt IS NULL
          AND (:filtre = '' OR nom LIKE '%' || :filtre || '%' OR codeTiers LIKE '%' || :filtre || '%'
               OR nif LIKE '%' || :filtre || '%')
        ORDER BY nom
        LIMIT :limit
        """
    )
    fun observeFiltres(filtre: String, limit: Int): Flow<List<TiersEntity>>

    @Query("SELECT * FROM tiers WHERE id = :id LIMIT 1")
    suspend fun byId(id: String): TiersEntity?

    @Query("SELECT COUNT(*) FROM tiers WHERE deletedAt IS NULL")
    fun observeCount(): Flow<Int>

    @Query("SELECT MAX(revision) FROM tiers")
    suspend fun maxRevision(): Long?
}

@Dao
interface BaremePaieDao {

    @Upsert suspend fun upsertIrsa(rows: List<BaremeIrsaTrancheEntity>)
    @Upsert suspend fun upsertCnaps(rows: List<BaremeCnapsEntity>)
    @Upsert suspend fun upsertMutuelle(rows: List<BaremeMutuelleEntity>)
    @Upsert suspend fun upsertSmig(rows: List<SmigEntity>)
    @Upsert suspend fun upsertEmployes(rows: List<EmployePaieEntity>)

    @Query(
        """
        SELECT * FROM bareme_irsa_tranche
        WHERE dateEffet <= :date AND (dateFinEffet IS NULL OR dateFinEffet >= :date)
        ORDER BY ordre
        """
    )
    suspend fun tranchesIrsaAuDate(date: LocalDate): List<BaremeIrsaTrancheEntity>

    @Query(
        """
        SELECT * FROM bareme_cnaps
        WHERE dateEffet <= :date AND (dateFinEffet IS NULL OR dateFinEffet >= :date)
        ORDER BY dateEffet DESC LIMIT 1
        """
    )
    suspend fun cnapsAuDate(date: LocalDate): BaremeCnapsEntity?

    @Query("SELECT * FROM employe_paie WHERE deletedAt IS NULL ORDER BY nom")
    fun observeEmployes(): Flow<List<EmployePaieEntity>>
}
