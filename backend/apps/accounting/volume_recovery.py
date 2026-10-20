"""
Helper partage de recouvrement volumetrique (croise Releve / DiameX).

Extrait de apps/planning/views_volumetrique_global.py pour etre reutilise par les
3 pages /plannings/volumetrique/ (matriciel), /details/ et /global/, sur le meme
modele que la matrice mensuelle de la page comptabilite dashboard-paiements-volume :

 - "prevu"                 = somme des montants de releves (montant > 0, hors
                             periodes coupees)
 - "paye"                  = somme des transactions DiameX compte 707401
                             rattachees a l'ouvrage / mois de facturation
 - "non pointe en compta"  = releves sans couple (numeroDiameX, baseDiameX)
 - "non pointe en releve"  = transactions DiameX sans couple releve correspondant

Les fonctions sont pures (pas de request, pas de render) : chaque vue passe ses
releves deja filtres + son scope d'ouvrages, et recupere un dict `kpis` pret pour
le partiel templates/planning/_volume_kpi_blocks.html.
"""
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.utils import timezone

NOMS_MOIS_FR = [
    '', 'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre',
]


def _pair_key(numero_diamex, base_diamex):
    num = str(numero_diamex or '').strip().lower()
    base = str(base_diamex or '').strip().lower()
    if not num or not base:
        return ''
    return f"{num}||{base}"


def releve_non_recouvrable(releve, periodes_coupure):
    """Un relevé est "hors recouvrement" si sa période est coupée (règle du
    dashboard Paiements Volume) OU si c'est un relevé réellement vide :
    consommation nulle ET montant nul.

    Un relevé à consommation nulle mais avec un montant (abonnement minimum)
    reste un impayé à recouvrer — ce n'est pas une coupure. Comme les vues
    filtrent déjà `montant > 0`, cette seconde branche ne s'y déclenche jamais ;
    elle ne couvre que d'éventuels appelants sans ce pré-filtre.
    """
    from apps.accounting.views import _is_releve_non_recouvrable
    if _is_releve_non_recouvrable(releve, periodes_coupure):
        return True
    try:
        conso = float(releve.consommation or 0)
        montant = float(releve.montant or 0)
    except (TypeError, ValueError):
        return False
    return conso <= 0 and montant <= 0


def split_mois(annee_int, today=None):
    """Retourne (mois_passes: set[int], mois_en_cours: int | None).

    Meme regle que apps/accounting/views.dashboard_paiements_volume : le mois en
    cours n'existe que pour l'annee courante ; les mois futurs ne sont dans aucun
    des deux groupes.
    """
    today = today or timezone.localdate()
    annee_int = int(annee_int)
    if annee_int < today.year:
        return set(range(1, 13)), None
    if annee_int == today.year:
        return set(range(1, today.month)), today.month
    return set(), None


def build_score_totals_from_releves(releves, annee_int, periodes_coupure, today=None):
    """{point_id: {'expected': Decimal, 'paid': Decimal, 'ouvrage_id': str}}.

    Uniquement les factures des mois cloctures (mois de facturation < mois courant),
    recouvrables. Sert au score "point d'eau paye a 100%" (a risque / tout paye).
    Copie de la logique de views_volumetrique_global.suivi_paiements_global.
    """
    from apps.accounting.dashboard_employee_filter import is_closed_payment_month

    today = today or timezone.localdate()
    annee_int = int(annee_int)
    reference_month = today.replace(day=1)
    totals = {}
    for releve in releves:
        if not releve.datereleve or not releve.point_eau_id:
            continue
        date_facture = releve.datereleve + relativedelta(months=1)
        if date_facture.year != annee_int:
            continue
        if not is_closed_payment_month(date_facture, reference_month):
            continue
        if releve_non_recouvrable(releve, periodes_coupure):
            continue
        point_id = str(releve.point_eau_id)
        entry = totals.setdefault(
            point_id, {'expected': Decimal('0'), 'paid': Decimal('0'), 'ouvrage_id': ''}
        )
        montant = Decimal(str(releve.montant or 0))
        entry['expected'] += montant
        if releve.numeroDiameX and releve.baseDiameX:
            entry['paid'] += montant
        pe = getattr(releve, 'point_eau', None)
        if pe and pe.ouvrage_id:
            entry['ouvrage_id'] = str(pe.ouvrage_id)
    return totals


def build_recouvrement_par_ouvrage_mois(
    releves, ouvrages_scope_ids, annee_int, periodes_coupure, gestionnaire_ids
):
    """Dict {"{ouvrage}_{annee}_{mm}": {...montants prevu/paye/non-pointe...}}.

    Reprend a l'identique les sections DiameX de
    views_volumetrique_global.suivi_paiements_global (releves + compte 707401,
    segments multi-ouvrages).
    """
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.accounting.models import BaseDiameX
    from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
    from apps.organization.models import Base

    annee_int = int(annee_int)
    ouvrages_scope_ids = {str(o) for o in ouvrages_scope_ids if o}
    recouvrement = {}
    pointed_pairs = {}

    if not ouvrages_scope_ids:
        return recouvrement

    def _ensure(cle_mois, ouvrage_id, ouvrage_nom, mois):
        if cle_mois not in recouvrement:
            recouvrement[cle_mois] = {
                'ouvrage_id': ouvrage_id,
                'ouvrage_nom': ouvrage_nom,
                'mois': mois,
                'total_releves': Decimal('0'),
                'total_diamex': Decimal('0'),
                'montant_non_pointe_releve': Decimal('0'),
                'montant_non_pointe_compta': Decimal('0'),
                'nb_non_pointe_releve': 0,
                'nb_non_pointe_compta': 0,
                'montant_non_recouvrable': Decimal('0'),
                'nb_non_recouvrable': 0,
            }
        pointed_pairs.setdefault(cle_mois, set())
        return recouvrement[cle_mois]

    # 1) Montants releves + couples pointes (numeroDiameX / baseDiameX)
    for releve in releves:
        pe = getattr(releve, 'point_eau', None)
        if not releve.datereleve or not pe or not pe.ouvrage:
            continue
        date_facture = releve.datereleve + relativedelta(months=1)
        if date_facture.year != annee_int:
            continue
        ouvrage_id = str(pe.ouvrage.id)
        if ouvrage_id not in ouvrages_scope_ids:
            continue
        cle_mois = f"{ouvrage_id}_{annee_int}_{date_facture.month:02d}"
        data = _ensure(cle_mois, ouvrage_id, pe.ouvrage.nom_ouvrage, date_facture.month)

        montant_releve = Decimal(str(releve.montant or 0))
        non_recouvrable = releve_non_recouvrable(releve, periodes_coupure)
        if non_recouvrable:
            data['montant_non_recouvrable'] += montant_releve
            data['nb_non_recouvrable'] += 1
        else:
            data['total_releves'] += montant_releve

        pair_key = _pair_key(releve.numeroDiameX, releve.baseDiameX)
        if pair_key:
            pointed_pairs[cle_mois].add(pair_key)
        elif not non_recouvrable:
            data['montant_non_pointe_compta'] += montant_releve
            data['nb_non_pointe_compta'] += 1

    # 2) Montants DiameX (compte 707401), segmentes par ouvrage / mois
    diamex_qs = BaseDiameX.objects.filter(compte_code='707401')
    if gestionnaire_ids is not None:
        if gestionnaire_ids:
            allowed_progs = list(
                Base.objects.filter(organisation_id__in=gestionnaire_ids)
                .exclude(prog_diamex__isnull=True)
                .exclude(prog_diamex='')
                .values_list('prog_diamex', flat=True)
                .distinct()
            )
            diamex_qs = diamex_qs.filter(prog__in=allowed_progs) if allowed_progs else diamex_qs.none()
        else:
            diamex_qs = diamex_qs.none()

    for entry in diamex_qs:
        segments = []
        if entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description,
                entry.compte_code,
                entry.montant_in if entry.montant_in else 0,
            )
        if segments:
            items = [
                (segment.get('extraction') or {}, Decimal(str(segment.get('montant') or 0)))
                for segment in segments
            ]
        else:
            items = [(
                extraire_ouvrage_et_mois_generique(entry.description or '', entry.compte_code),
                Decimal(str(entry.montant_in or 0)),
            )]

        diamex_pair_key = _pair_key(entry.id_access, entry.prog)
        for extraction, montant in items:
            ouvrage_obj = extraction.get('ouvrage_obj')
            mois = extraction.get('mois')
            annee_seg = extraction.get('annee')
            if not ouvrage_obj or not mois or annee_seg != annee_int:
                continue
            ouvrage_id = str(ouvrage_obj.id)
            if ouvrage_id not in ouvrages_scope_ids:
                continue
            cle_mois = f"{ouvrage_id}_{annee_int}_{mois:02d}"
            data = _ensure(cle_mois, ouvrage_id, ouvrage_obj.nom_ouvrage, mois)
            data['total_diamex'] += montant
            if not (diamex_pair_key and diamex_pair_key in pointed_pairs.get(cle_mois, set())):
                data['montant_non_pointe_releve'] += montant
                data['nb_non_pointe_releve'] += 1

    return recouvrement


def _k(value):
    return int(Decimal(str(value or 0)) / 1000)


def _totaux_pour_mois(recouvrement_par_ouvrage_mois, month_numbers):
    """Calque sur apps/accounting/views._totaux_recouvrement_pour_mois."""
    month_numbers = set(month_numbers or [])
    prevu = Decimal('0')
    paye = Decimal('0')
    np_releve = Decimal('0')
    np_compta = Decimal('0')
    nb_np_releve = 0
    nb_np_compta = 0
    for data in recouvrement_par_ouvrage_mois.values():
        if data.get('mois') not in month_numbers:
            continue
        prevu += Decimal(str(data.get('total_releves') or 0))
        paye += Decimal(str(data.get('total_diamex') or 0))
        np_releve += Decimal(str(data.get('montant_non_pointe_releve') or 0))
        np_compta += Decimal(str(data.get('montant_non_pointe_compta') or 0))
        nb_np_releve += int(data.get('nb_non_pointe_releve') or 0)
        nb_np_compta += int(data.get('nb_non_pointe_compta') or 0)
    taux = int((paye / prevu) * 100) if prevu > 0 else 0
    ecart = prevu - paye
    return {
        'total_prevu_k': _k(prevu),
        'total_paye_k': _k(paye),
        'ecart_k': _k(ecart),
        'ecart': float(ecart),
        'taux': taux,
        'progression': min(taux, 100),
        'has_data': prevu > 0,
        'montant_non_pointe_releve_k': _k(np_releve),
        'montant_non_pointe_compta_k': _k(np_compta),
        'nb_non_pointe_releve': nb_np_releve,
        'nb_non_pointe_compta': nb_np_compta,
    }


def _counts_pour_mois(facture_counts_par_mois, month_numbers):
    month_numbers = set(month_numbers or [])
    total = payes = impayes = 0
    for mois, counts in (facture_counts_par_mois or {}).items():
        if mois not in month_numbers:
            continue
        total += int(counts.get('total') or 0)
        payes += int(counts.get('payes') or 0)
        impayes += int(counts.get('impayes') or 0)
    taux = int(round(payes / total * 100)) if total > 0 else 0
    return {
        'total_factures': total,
        'factures_payees': payes,
        'factures_impayees': impayes,
        'taux_factures': taux,
    }


def build_volume_kpis(
    *,
    recouvrement_par_ouvrage_mois,
    facture_counts_par_mois,
    score_totals_by_point,
    points_eau_coupes_count,
    annee_int,
    today=None,
):
    """Assemble le contexte `kpis` pour templates/planning/_volume_kpi_blocks.html.

    - montants (prevu / paye / taux / ecart / non-pointe) : recouvrement DiameX
    - comptes de factures (total / payees / impayees) : facture_counts_par_mois,
      un dict {mois_int: {'total': n, 'payes': n, 'impayes': n}} fourni par la vue
      depuis ses propres lignes de tableau
    - a risque / tout paye : score point d'eau (mois cloctures)
    """
    from apps.accounting.dashboard_employee_filter import calculate_water_point_score

    today = today or timezone.localdate()
    annee_int = int(annee_int)
    mois_passes, mois_en_cours = split_mois(annee_int, today)
    tous_les_mois = set(range(1, 13))

    general_montants = _totaux_pour_mois(recouvrement_par_ouvrage_mois, tous_les_mois)
    general_counts = _counts_pour_mois(facture_counts_par_mois, tous_les_mois)

    # Ouvrages a 100% (sur l'annee)
    par_ouvrage = {}
    for data in recouvrement_par_ouvrage_mois.values():
        agg = par_ouvrage.setdefault(
            data['ouvrage_id'], {'prevu': Decimal('0'), 'paye': Decimal('0')}
        )
        agg['prevu'] += Decimal(str(data.get('total_releves') or 0))
        agg['paye'] += Decimal(str(data.get('total_diamex') or 0))
    nb_ouvrages_100 = sum(
        1 for agg in par_ouvrage.values()
        if agg['prevu'] > 0 and agg['paye'] >= agg['prevu']
    )

    score = calculate_water_point_score(
        (score_totals_by_point or {}).keys(), score_totals_by_point or {}
    )

    passes = _totaux_pour_mois(recouvrement_par_ouvrage_mois, mois_passes)
    passes.update(_counts_pour_mois(facture_counts_par_mois, mois_passes))
    passes['nb_mois'] = len(mois_passes)

    en_cours = _totaux_pour_mois(
        recouvrement_par_ouvrage_mois, {mois_en_cours} if mois_en_cours else set()
    )
    en_cours.update(
        _counts_pour_mois(facture_counts_par_mois, {mois_en_cours} if mois_en_cours else set())
    )
    en_cours['libelle_mois'] = NOMS_MOIS_FR[mois_en_cours] if mois_en_cours else ''

    return {
        'annee': annee_int,
        'afficher_mois_en_cours': mois_en_cours is not None,
        'mois_passes_set': sorted(mois_passes),
        'mois_en_cours_num': mois_en_cours,
        'general': {
            **general_montants,
            **general_counts,
            'nb_ouvrages_100': nb_ouvrages_100,
            'pe_a_risque': score['points_ecart'],
            'pe_tout_paye': score['points_acquis'],
            'pe_score_total': score['points_max'],
            'points_eau_coupes': int(points_eau_coupes_count or 0),
        },
        'mois_passes': passes,
        'mois_en_cours': en_cours,
    }
