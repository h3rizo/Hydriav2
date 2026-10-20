package mg.hydria.shared.readings

import mg.hydria.shared.planning.IsoDate

enum class ReadingError {
    POINT_REQUIRED, INVALID_INDEX, INDEX_DECREASED, NEGATIVE_NON_BILLABLE, NEGATIVE_BILLED_VOLUME, INVALID_CAMPAIGN_DATE,
    /** Remarque manquante alors que la consommation est nulle (règle serveur, voir [ReadingValidation.validateRemark]). */
    REMARK_REQUIRED_ZERO_CONSUMPTION,
    /** Remarque manquante alors que le volume non facturé est différent de 0. */
    REMARK_REQUIRED_NON_BILLABLE,
}

object ReadingValidation {
    /** En dessous de cet écart, deux index sont considérés égaux (consommation nulle). */
    private const val ZERO_CONSUMPTION_TOLERANCE = 1e-9

    fun consumption(newIndex: Double, previousIndex: Double): Double = newIndex - previousIndex
    fun socialCardVolume(bidonCount: Int): Double = kotlin.math.round(bidonCount * 2.0) / 100.0
    fun socialCardsVolume(volumes: List<Double>): Double = volumes.sum()
    fun billedVolume(consumption: Double, socialCardsVolume: Double, nonBillable: Double): Double =
        consumption - socialCardsVolume - nonBillable

    /**
     * Préserve l'ordre des contrôles et la tolérance du formulaire historique. La date de campagne doit
     * exister au calendrier (« 2026-02-30 » donne [ReadingError.INVALID_CAMPAIGN_DATE], comme une date vide) :
     * une date tapée au clavier (Desktop) ne part ainsi jamais au serveur.
     */
    fun validate(hasPoint: Boolean, newIndex: Double?, oldIndex: Double, nonBillable: Double,
        socialVolume: Double, campaignDate: String?): ReadingError? = when {
        !hasPoint -> ReadingError.POINT_REQUIRED
        newIndex == null -> ReadingError.INVALID_INDEX
        newIndex < oldIndex -> ReadingError.INDEX_DECREASED
        nonBillable < 0 -> ReadingError.NEGATIVE_NON_BILLABLE
        billedVolume(consumption(newIndex, oldIndex), socialVolume, nonBillable) < -0.001 -> ReadingError.NEGATIVE_BILLED_VOLUME
        campaignDate.isNullOrBlank() || !IsoDate.isReal(campaignDate) -> ReadingError.INVALID_CAMPAIGN_DATE
        else -> null
    }

    /**
     * Règle de `backend/apps/billing/views_releves.py` : la remarque est obligatoire si la consommation
     * est nulle OU si le volume non facturé est différent de 0 (le serveur refuse sinon, en HTTP 400).
     * Même ordre que le serveur : consommation nulle d'abord. [consumption] null = index pas encore saisi
     * (seul le volume non facturé peut alors rendre la remarque obligatoire).
     * Séparée de [validate] pour ne pas changer le contrat des écrans qui l'appellent déjà.
     */
    fun remarkRequirement(consumption: Double?, nonBillable: Double): ReadingError? = when {
        consumption != null && kotlin.math.abs(consumption) < ZERO_CONSUMPTION_TOLERANCE ->
            ReadingError.REMARK_REQUIRED_ZERO_CONSUMPTION
        nonBillable != 0.0 -> ReadingError.REMARK_REQUIRED_NON_BILLABLE
        else -> null
    }

    fun remarkRequired(consumption: Double?, nonBillable: Double): Boolean =
        remarkRequirement(consumption, nonBillable) != null

    /** Erreur de remarque (null = conforme). Une remarque blanche compte pour vide, comme `.strip()` côté serveur. */
    fun validateRemark(consumption: Double?, nonBillable: Double, remark: String?): ReadingError? =
        remarkRequirement(consumption, nonBillable)?.takeIf { remark.isNullOrBlank() }
}
