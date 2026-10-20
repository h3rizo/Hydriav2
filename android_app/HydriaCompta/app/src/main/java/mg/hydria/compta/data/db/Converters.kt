package mg.hydria.compta.data.db

import androidx.room.TypeConverter
import mg.hydria.compta.core.Ariary
import mg.hydria.compta.core.ConflictResolution
import mg.hydria.compta.core.ModeReglement
import mg.hydria.compta.core.MutationStatus
import mg.hydria.compta.core.MutationType
import mg.hydria.compta.core.SensCaisse
import mg.hydria.compta.core.StatutFacture
import mg.hydria.compta.core.StatutPieceLocale
import mg.hydria.compta.core.SyncStatus
import mg.hydria.compta.core.TypeCompte
import mg.hydria.compta.core.TypeFacture
import java.time.Instant
import java.time.LocalDate

class Converters {

    @TypeConverter fun ariaryToLong(v: Ariary?): Long? = v?.centimes
    @TypeConverter fun longToAriary(v: Long?): Ariary? = v?.let(::Ariary)

    @TypeConverter fun dateToString(v: LocalDate?): String? = v?.toString()
    @TypeConverter fun stringToDate(v: String?): LocalDate? = v?.let { LocalDate.parse(it) }

    @TypeConverter fun instantToLong(v: Instant?): Long? = v?.toEpochMilli()
    @TypeConverter fun longToInstant(v: Long?): Instant? = v?.let { Instant.ofEpochMilli(it) }

    @TypeConverter fun typeCompteToString(v: TypeCompte?): String? = v?.name
    @TypeConverter fun stringToTypeCompte(v: String?): TypeCompte? = v?.let(TypeCompte::valueOf)

    @TypeConverter fun statutPieceToString(v: StatutPieceLocale?): String? = v?.name
    @TypeConverter fun stringToStatutPiece(v: String?): StatutPieceLocale? = v?.let(StatutPieceLocale::valueOf)

    @TypeConverter fun syncStatusToString(v: SyncStatus?): String? = v?.name
    @TypeConverter fun stringToSyncStatus(v: String?): SyncStatus? = v?.let(SyncStatus::valueOf)

    @TypeConverter fun mutationStatusToString(v: MutationStatus?): String? = v?.name
    @TypeConverter fun stringToMutationStatus(v: String?): MutationStatus? = v?.let(MutationStatus::valueOf)

    @TypeConverter fun mutationTypeToString(v: MutationType?): String? = v?.name
    @TypeConverter fun stringToMutationType(v: String?): MutationType? = v?.let(MutationType::valueOf)

    @TypeConverter fun typeFactureToString(v: TypeFacture?): String? = v?.name
    @TypeConverter fun stringToTypeFacture(v: String?): TypeFacture? = v?.let(TypeFacture::valueOf)

    @TypeConverter fun statutFactureToString(v: StatutFacture?): String? = v?.name
    @TypeConverter fun stringToStatutFacture(v: String?): StatutFacture? = v?.let(StatutFacture::valueOf)

    @TypeConverter fun modeReglementToString(v: ModeReglement?): String? = v?.name
    @TypeConverter fun stringToModeReglement(v: String?): ModeReglement? = v?.let(ModeReglement::valueOf)

    @TypeConverter fun sensCaisseToString(v: SensCaisse?): String? = v?.name
    @TypeConverter fun stringToSensCaisse(v: String?): SensCaisse? = v?.let(SensCaisse::valueOf)

    @TypeConverter fun conflictResToString(v: ConflictResolution?): String? = v?.name
    @TypeConverter fun stringToConflictRes(v: String?): ConflictResolution? = v?.let(ConflictResolution::valueOf)
}
