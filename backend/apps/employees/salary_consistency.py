from decimal import Decimal


GRILLE_CALC_FIELDS = (
    'majoration_nuit_gardien',
    'majoration_dimanche_gardien',
    'montant_jours_feries_gardien',
    'montant_remplacement_gardien',
    'salaire_brut_total',
    'charge_cnaps_employe',
    'base_imposable',
    'deduction_impots',
    'irsa',
    'mutuelle_sante',
    'salaire_net',
)


def _to_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    return Decimal(str(value))


def refresh_grille_calculs(grille, persist=True):
    """
    Recalcule la grille avec la logique courante et persiste si des champs changent.
    Retourne True si la grille a ete modifiee.
    """
    before = {field: _to_decimal(getattr(grille, field, 0)) for field in GRILLE_CALC_FIELDS}
    grille.calculer_tous_les_champs()

    changed = any(_to_decimal(getattr(grille, field, 0)) != before[field] for field in GRILLE_CALC_FIELDS)
    if changed and persist:
        grille.save()
    return changed


def expected_salaire_values_from_grille(grille):
    cnaps = _to_decimal(getattr(grille, 'charge_cnaps_employe', 0))
    return {
        'salaire_net_paye': _to_decimal(getattr(grille, 'salaire_net', 0)),
        'irsa_paye': _to_decimal(getattr(grille, 'irsa', 0)),
        'cnaps_paye': cnaps * Decimal('14'),
        'fmfp_paye': cnaps,
        'mutuelle_sante_paye': _to_decimal(getattr(grille, 'mutuelle_sante', 0)),
    }


def sync_salaire_with_grille(salaire, persist=True, refresh_grille=True):
    """
    Aligne les montants du paiement salaire sur la grille courante.
    Retourne la liste des champs salaire modifies.
    """
    grille = salaire.grille_salaire
    if refresh_grille:
        refresh_grille_calculs(grille, persist=persist)

    expected = expected_salaire_values_from_grille(grille)
    changed_fields = []
    for field_name, expected_value in expected.items():
        if _to_decimal(getattr(salaire, field_name, 0)) != expected_value:
            setattr(salaire, field_name, expected_value)
            changed_fields.append(field_name)

    if changed_fields and persist:
        salaire.save(update_fields=changed_fields)

    return changed_fields

